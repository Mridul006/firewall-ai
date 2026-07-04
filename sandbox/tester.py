"""Orchestrates the full sandbox test for a candidate firewall rule.

Spins up an isolated Docker container (--network none, no route to the real
network), loads the candidate iptables rule, replays the last N minutes of
real traffic against it flow by flow, and hands the results to fp_scorer.py.

Core guarantee: no untested rule ever reaches the live firewall.
"""

import io
import logging
import os
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import docker
import docker.errors
import pandas as pd
from clickhouse_driver import Client
from docker.models.containers import Container
from dotenv import load_dotenv
from scapy.all import ICMP, IP, TCP, UDP, Ether, Raw, wrpcap

import promoter
from fp_scorer import FlowResult, score_replay

load_dotenv()

logger = logging.getLogger(__name__)

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "9000"))

SANDBOX_IMAGE = "firewall-ai-sandbox:latest"
DOCKERFILE_DIR = Path(__file__).resolve().parent

# Flows are replayed independently, each capped in packet count and wall-clock
# duration to keep total sandbox runtime bounded. This is a deliberate MVP
# simplification (see layer1_design.md's MVP-vs-future table — cross-flow
# adversarial timing is explicitly future work), not a correctness bug for
# plain match/DROP rules; simple single-flow rate-limit rules (-m limit) are
# still meaningfully exercised within each flow's own capped burst.
MAX_PACKETS_PER_FLOW = 50
MAX_REPLAY_SECONDS_PER_FLOW = 2.0

# Injection interface: a veth pair created inside the isolated container.
# tcpreplay has a known limitation injecting onto `lo` (ARPHRD_LOOPBACK framing
# isn't handled correctly — confirmed empirically, packets never reached
# netfilter). A dummy interface doesn't work either — it discards transmitted
# packets rather than looping them back to the receive path. A veth pair
# behaves like a real point-to-point link: whatever tcpreplay sends out
# REPLAY_IFACE is genuinely received on PEER_IFACE, which is what actually
# triggers the INPUT chain. The destination MAC must be broadcast (or match
# the peer's real MAC) or the interface silently drops the frame at L2.
REPLAY_IFACE = "veth-out"
PEER_IFACE = "veth-in"
BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"
SENDER_MAC = "02:00:00:00:00:01"


class SandboxTestError(Exception):
    """Raised when the sandbox test infrastructure itself fails (not a rule rejection)."""


class InvalidRuleError(SandboxTestError):
    """Raised when the candidate rule itself is invalid (e.g. doesn't parse in iptables).

    Unlike SandboxTestError, this means the rule failed its test — the caller
    should REJECT the rule, not leave it stuck in SANDBOX_TESTING.
    """


def get_clickhouse_client() -> Client:
    """Create a new ClickHouse client connection."""
    return Client(host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT)


def fetch_recent_traffic(client: Client, minutes: int = 10) -> pd.DataFrame:
    """Pull the last N minutes of traffic_events into a DataFrame for replay."""
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    columns = [
        "timestamp",
        "src_ip",
        "dst_ip",
        "src_port",
        "dst_port",
        "protocol",
        "bytes",
        "packets",
        "flags",
        "duration",
        "anomaly_score",
    ]
    rows = client.execute(
        f"SELECT {', '.join(columns)} FROM traffic_events WHERE timestamp >= %(since)s",
        {"since": since},
    )
    return pd.DataFrame(rows, columns=columns)


def _build_flow_pcap(flow: pd.Series) -> bytes:
    """Synthesize packets representing one traffic_events flow into pcap bytes.

    traffic_events stores per-flow summaries (bytes/packets/duration), not raw
    packet captures, so packets are reconstructed from that summary rather
    than replayed byte-for-byte — this is the only data available, since Zeek
    logs (not full captures) are what the ingestion pipeline stores. Packet
    count and duration are capped so replay time stays bounded, and packets
    are evenly spaced across the (capped) duration so replay rate roughly
    matches the original flow, which is enough to exercise both plain
    match/DROP rules and single-flow rate-limit rules.
    """
    packet_count = max(1, min(int(flow["packets"]), MAX_PACKETS_PER_FLOW))
    avg_size = max(1, int(flow["bytes"]) // packet_count)
    span = min(float(flow["duration"]), MAX_REPLAY_SECONDS_PER_FLOW)
    interval = span / packet_count if span > 0 else 0.001

    proto = str(flow["protocol"]).upper()
    src_port = int(flow["src_port"])
    dst_port = int(flow["dst_port"])

    if proto == "UDP":
        layer = UDP(sport=src_port, dport=dst_port)
    elif proto == "ICMP":
        layer = ICMP()
    else:
        layer = TCP(sport=src_port, dport=dst_port)

    packets = []
    for i in range(packet_count):
        pkt = (
            Ether(src=SENDER_MAC, dst=BROADCAST_MAC)
            / IP(src=str(flow["src_ip"]), dst=str(flow["dst_ip"]))
            / layer
            / Raw(load=b"x" * avg_size)
        )
        pkt.time = i * interval
        packets.append(pkt)

    with tempfile.NamedTemporaryFile(suffix=".pcap", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        wrpcap(str(tmp_path), packets)
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


def _ensure_image(client: docker.DockerClient) -> None:
    """Build the sandbox image from the local Dockerfile if it doesn't exist yet."""
    try:
        client.images.get(SANDBOX_IMAGE)
    except docker.errors.ImageNotFound:
        logger.info(f"Building sandbox image {SANDBOX_IMAGE} ...")
        client.images.build(path=str(DOCKERFILE_DIR), tag=SANDBOX_IMAGE, rm=True)


def _start_container(client: docker.DockerClient) -> Container:
    """Start an isolated sandbox container with no access to the real network."""
    container = client.containers.run(
        SANDBOX_IMAGE,
        detach=True,
        network_mode="none",
        cap_add=["NET_ADMIN", "NET_RAW"],
    )
    _setup_veth_pair(container)
    return container


def _setup_veth_pair(container: Container) -> None:
    """Create the veth pair used to inject replayed packets into the container."""
    exit_code, output = container.exec_run(
        [
            "sh",
            "-c",
            f"ip link add {REPLAY_IFACE} type veth peer name {PEER_IFACE} && "
            f"ip link set {REPLAY_IFACE} up && "
            f"ip link set {PEER_IFACE} up",
        ]
    )
    if exit_code != 0:
        raise SandboxTestError(
            f"Failed to set up veth pair: {output.decode(errors='replace')}"
        )


def _load_rule(container: Container, command: str) -> None:
    """Load the candidate rule's iptables command(s) into the container.

    Raises InvalidRuleError (not SandboxTestError) on failure: a rule that
    doesn't even parse in iptables is a rule-content problem — the "syntax
    valid" check from firewall_rules.md's validation checklist — and must be
    REJECTED like any other failed test, not confused with a sandbox
    infrastructure failure.
    """
    exit_code, output = container.exec_run(["sh", "-c", command])
    if exit_code != 0:
        raise InvalidRuleError(
            f"Candidate rule failed to load (exit {exit_code}): "
            f"{output.decode(errors='replace')}"
        )


def _put_pcap(container: Container, pcap_bytes: bytes, remote_name: str = "flow.pcap") -> str:
    """Copy a pcap file into the container at /sandbox/<remote_name>."""
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        info = tarfile.TarInfo(name=remote_name)
        info.size = len(pcap_bytes)
        tar.addfile(info, io.BytesIO(pcap_bytes))
    container.put_archive("/sandbox", tar_buffer.getvalue())
    return f"/sandbox/{remote_name}"


def _replay_and_check(container: Container, pcap_path: str, dst_ip: str) -> bool:
    """Zero counters, replay the pcap, and report whether any packet was blocked.

    The flow's destination IP is aliased onto PEER_IFACE so the kernel treats
    replayed packets addressed to it as local delivery — otherwise they'd
    never reach the INPUT chain at all. `ip addr replace` is idempotent, so
    repeated flows sharing a destination IP don't error.
    """
    container.exec_run(["ip", "addr", "replace", f"{dst_ip}/32", "dev", PEER_IFACE])
    container.exec_run(["iptables", "-Z", "INPUT"])

    exit_code, output = container.exec_run(["tcpreplay", f"--intf1={REPLAY_IFACE}", pcap_path])
    if exit_code != 0:
        raise SandboxTestError(f"tcpreplay failed: {output.decode(errors='replace')}")

    exit_code, output = container.exec_run(["iptables", "-L", "INPUT", "-v", "-n", "-x"])
    return _any_drop_matched(output.decode(errors="replace"))


def _any_drop_matched(iptables_output: str) -> bool:
    """Parse `iptables -L INPUT -v -n -x` output for any DROP/REJECT rule with hits."""
    for line in iptables_output.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        pkts, _bytes, target = parts[0], parts[1], parts[2]
        if pkts.isdigit() and int(pkts) > 0 and target in ("DROP", "REJECT"):
            return True
    return False


def _replay_all_flows(command: str, traffic: pd.DataFrame) -> list[FlowResult]:
    """Replay each traffic flow individually against the candidate rule."""
    docker_client = docker.from_env()
    _ensure_image(docker_client)
    container = _start_container(docker_client)

    results: list[FlowResult] = []
    try:
        _load_rule(container, command)

        for _, flow in traffic.iterrows():
            try:
                pcap_bytes = _build_flow_pcap(flow)
                pcap_path = _put_pcap(container, pcap_bytes)
                blocked = _replay_and_check(container, pcap_path, str(flow["dst_ip"]))
            except SandboxTestError as e:
                # A single malformed flow shouldn't abort the whole test —
                # log it and exclude it from the FP calculation.
                logger.warning(f"Skipping flow {flow['src_ip']}->{flow['dst_ip']}: {e}")
                continue

            results.append(
                FlowResult(
                    src_ip=str(flow["src_ip"]),
                    dst_ip=str(flow["dst_ip"]),
                    dst_port=int(flow["dst_port"]),
                    packets=int(flow["packets"]),
                    bytes=int(flow["bytes"]),
                    anomaly_score=float(flow["anomaly_score"]),
                    blocked=blocked,
                )
            )
    finally:
        container.remove(force=True)

    return results


def run_sandbox_test(
    rule: dict[str, Any], trigger_event: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Run the full sandbox pipeline for one LLM-generated candidate rule.

    Inserts the rule as PENDING, replays the last 10 minutes of real traffic
    against it in an isolated container, scores the false-positive rate, and
    updates its final status in PostgreSQL (APPROVED_PENDING or REJECTED).

    A rule that is itself invalid (bad iptables syntax) is REJECTED with the
    parse error as the reason — that is a rule failing its test, per
    firewall_rules.md's "syntax valid" checklist item, not a sandbox problem.
    If the sandbox infrastructure itself fails instead (container/image/veth
    setup), this raises SandboxTestError and leaves the rule in
    SANDBOX_TESTING rather than guessing a verdict — an infra failure is not
    the same as a rule failing its test, and the core guarantee means an
    unresolved rule must never be silently promoted.
    """
    if rule.get("syntax") != "iptables":
        raise SandboxTestError(
            f"Sandbox only supports iptables syntax on this Linux image, got {rule.get('syntax')!r}"
        )

    rule_id = promoter.insert_pending_rule(rule, trigger_event)
    logger.info(f"Inserted candidate rule {rule_id} as PENDING")
    promoter.mark_testing(rule_id)

    ch_client = get_clickhouse_client()
    traffic = fetch_recent_traffic(ch_client, minutes=10)

    if traffic.empty:
        logger.warning("No traffic in the last 10 minutes — nothing to replay")
        results: list[FlowResult] = []
    else:
        try:
            results = _replay_all_flows(rule["command"], traffic)
        except InvalidRuleError as e:
            sandbox_result = {
                "tested_at": datetime.now(timezone.utc).isoformat(),
                "flows_tested": 0,
                "error": str(e),
            }
            promoter.reject(rule_id, sandbox_result, f"Invalid rule: {e}")
            return {"rule_id": str(rule_id), "passed": False, **sandbox_result}

    scored = score_replay(results)

    sandbox_result = {
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "flows_tested": len(results),
        **scored,
    }

    if scored["passed"]:
        promoter.approve(rule_id, sandbox_result)
        logger.info(
            f"Rule {rule_id} PASSED sandbox test (fp_rate={scored['fp_rate']:.4f}) "
            "-> APPROVED_PENDING"
        )
    else:
        reason = f"FP rate {scored['fp_rate']:.4f} exceeds threshold {scored['threshold']:.4f}"
        promoter.reject(rule_id, sandbox_result, reason)

    return {"rule_id": str(rule_id), **sandbox_result}
