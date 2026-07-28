"""Orchestrates the full sandbox test for a candidate firewall rule.

Three testing modes, auto-selected by which iptables chain the candidate
rule targets (see _detect_chain) — never a manual toggle:

- Host mode (INPUT chain): a single isolated container (--network none, no
  route to the real network), candidate rule loaded, traffic replayed via an
  internal veth pair. Original implementation — unchanged by router or
  output mode.
- Router mode (FORWARD chain): three containers (attacker, firewall, target)
  with genuine Docker-network routing between them, candidate rule loaded on
  the firewall's FORWARD chain. Added because host mode's single-container
  approach never actually exercises FORWARD-chain rules at all — see
  ADR-038 and ADR-039.
- Output mode (OUTPUT chain): reuses host mode's exact container/veth setup,
  but generates traffic as genuine locally-originated connections (bash's
  /dev/tcp or /dev/udp) instead of tcpreplay-injected frames — OUTPUT only
  ever fires for packets the container's own kernel constructs, never for
  injected/received ones. Added because a rule targeting OUTPUT was
  previously silently misrouted to host mode's INPUT-chain check, which
  would never see it match anything at all. See ADR-040.

Core guarantee: no untested rule ever reaches the live firewall.
"""

import io
import logging
import os
import re
import tarfile
import tempfile
import uuid
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

import conflict_checker
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

# A DROPped SYN gets no RST, so an unbounded /dev/tcp connect() blocks on the
# kernel's own SYN-retry timeout (many minutes, several retries with
# exponential backoff) instead of failing fast the way a REJECT or a refused
# loopback connection does. Each egress attempt must be individually bounded
# or a single DROP-matching flow can hang the whole test. See ADR-040.
EGRESS_CONNECT_TIMEOUT_SECONDS = 2

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


def _build_flow_pcap(flow: pd.Series, dst_mac: str = BROADCAST_MAC) -> bytes:
    """Synthesize packets representing one traffic_events flow into pcap bytes.

    traffic_events stores per-flow summaries (bytes/packets/duration), not raw
    packet captures, so packets are reconstructed from that summary rather
    than replayed byte-for-byte — this is the only data available, since Zeek
    logs (not full captures) are what the ingestion pipeline stores. Packet
    count and duration are capped so replay time stays bounded, and packets
    are evenly spaced across the (capped) duration so replay rate roughly
    matches the original flow, which is enough to exercise both plain
    match/DROP rules and single-flow rate-limit rules.

    dst_mac defaults to broadcast (host mode's veth pair requires this — see
    ADR-020). Router mode passes the firewall's real MAC explicitly instead —
    a broadcast destination is silently dropped somewhere in Docker's bridge
    delivery path there (confirmed empirically; see ADR-039).
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
            Ether(src=SENDER_MAC, dst=dst_mac)
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


# ============================================================================
# ROUTER MODE (FORWARD chain) — attacker -> firewall -> target
#
# Host mode above is untouched by everything below. Router mode exists
# because aliasing a flow's destination IP onto one container's own
# interface (host mode's approach) makes the kernel treat replayed traffic as
# locally delivered, which always goes through INPUT — FORWARD is never
# evaluated no matter which chain's counters get checked. A rule that
# targets FORWARD needs packets to genuinely cross from one host's network
# namespace, through a second host's routing decision, toward a third host,
# for FORWARD to mean anything. See ADR-038 (the gap) and ADR-039 (this fix).
# ============================================================================

FORWARD_CHAIN_PATTERN = re.compile(r"-[AIDR]\s+FORWARD\b")
OUTPUT_CHAIN_PATTERN = re.compile(r"-[AIDR]\s+OUTPUT\b")

ROUTER_CAPS = ["NET_ADMIN", "NET_RAW"]


def _detect_chain(command: str) -> str:
    """Detect which iptables chain a candidate rule targets.

    Returns "FORWARD", "OUTPUT", or "INPUT" — the last being the
    default/existing assumption, preserving host-mode testing for every rule
    shape seen before router/output mode existed. FORWARD is checked first:
    a command matching both (unusual, but possible for a multi-statement
    rule) is treated as FORWARD, since that's the chain more likely to be
    silently under-tested if mis-detected.
    """
    if FORWARD_CHAIN_PATTERN.search(command):
        return "FORWARD"
    if OUTPUT_CHAIN_PATTERN.search(command):
        return "OUTPUT"
    return "INPUT"


def _create_router_networks(client: docker.DockerClient) -> tuple[Any, Any]:
    """Create the two Docker networks for router mode's attacker/firewall/target topology.

    Deliberately NOT internal=True: empirically, Docker Desktop's networking
    backend silently blocks inter-container FORWARD-chain traffic through a
    multi-homed container on internal networks (confirmed by testing — a
    LOG-all rule on FORWARD stayed at 0 packets with internal=True, and
    started counting immediately once removed), even though internal
    networks are documented as only blocking *external* routing. Isolation
    from the real network is enforced instead by stripping each container's
    default route after it starts (_strip_default_route) — the containers
    then have no path anywhere except their two directly-connected /16s and
    the one static route added per flow under test.
    """
    suffix = uuid.uuid4().hex[:8]
    attacker_net = client.networks.create(f"fwai-router-attacker-{suffix}", driver="bridge")
    target_net = client.networks.create(f"fwai-router-target-{suffix}", driver="bridge")
    return attacker_net, target_net


def _strip_default_route(container: Container) -> None:
    """Remove a container's default route so it has no path to the real network.

    Docker assigns a default route via the bridge gateway to every container
    on a (non-internal) network. Without removing it, router-mode containers
    could reach the real internet through the host's NAT — this is what
    keeps router mode's safety guarantee equivalent to host mode's
    --network none.
    """
    container.exec_run(["ip", "route", "del", "default"])


def _start_router_topology(client: docker.DockerClient) -> dict[str, Any]:
    """Stand up the attacker/firewall/target containers and wire their networks.

    firewall is multi-homed (attacker_net + target_net) and is where the
    candidate rule actually gets loaded, on its FORWARD chain.

    Builds the topology dict incrementally and tears down whatever was
    already created if any step fails partway through — three containers and
    two networks is a lot more to leak than host mode's single container, so
    this is deliberately more defensive than host mode's _start_container.
    """
    topology: dict[str, Any] = {}
    try:
        topology["attacker_net"], topology["target_net"] = _create_router_networks(client)
        attacker_net, target_net = topology["attacker_net"], topology["target_net"]

        topology["attacker"] = client.containers.run(
            SANDBOX_IMAGE, detach=True, network=attacker_net.name, cap_add=ROUTER_CAPS
        )
        topology["firewall"] = client.containers.run(
            SANDBOX_IMAGE, detach=True, network=attacker_net.name, cap_add=ROUTER_CAPS
        )
        topology["target"] = client.containers.run(
            SANDBOX_IMAGE, detach=True, network=target_net.name, cap_add=ROUTER_CAPS
        )
        firewall = topology["firewall"]
        target_net.connect(firewall)

        for key in ("attacker", "firewall", "target"):
            _strip_default_route(topology[key])

        # Docker Desktop's VM already has ip_forward=1 at the host level,
        # which this project's container runtime inherits even though
        # writing to /proc/sys/net/ipv4/ip_forward from inside the container
        # is read-only (confirmed empirically) — so a failed write is only
        # fatal if the value genuinely isn't 1.
        firewall.exec_run(["sh", "-c", "echo 1 > /proc/sys/net/ipv4/ip_forward"])
        _, check_output = firewall.exec_run(["cat", "/proc/sys/net/ipv4/ip_forward"])
        if check_output.decode().strip() != "1":
            raise SandboxTestError(
                "ip_forward is not enabled on the router-mode firewall container"
            )
    except Exception:
        _teardown_router_topology(topology)
        raise

    return topology


def _teardown_router_topology(topology: dict[str, Any]) -> None:
    """Remove all router-mode containers and networks, best-effort.

    Tolerant of a partially-built topology (e.g. setup failed partway
    through) — only tears down whatever actually got created.
    """
    for key in ("attacker", "firewall", "target"):
        container = topology.get(key)
        if container is None:
            continue
        try:
            container.remove(force=True)
        except docker.errors.APIError as e:
            logger.warning(f"Failed to remove router-mode container {key}: {e}")

    for key in ("attacker_net", "target_net"):
        network = topology.get(key)
        if network is None:
            continue
        try:
            network.remove()
        except docker.errors.APIError as e:
            logger.warning(f"Failed to remove router-mode network {key}: {e}")


def _firewall_facing_mac(container: Container, network_name: str) -> str:
    """Look up a container's MAC address on a specific Docker network.

    Router-mode packets must be addressed (L2) to the firewall's real MAC.
    Unlike host mode's internal veth pair, a broadcast destination MAC is
    silently dropped somewhere in Docker's bridge delivery path here —
    confirmed empirically: identical packets with a real MAC traversed
    FORWARD correctly; with a broadcast MAC, they never arrived at all.
    """
    container.reload()
    return container.attrs["NetworkSettings"]["Networks"][network_name]["MacAddress"]


def _container_ip(container: Container, network_name: str) -> str:
    """Look up a container's IP address on a specific Docker network."""
    container.reload()
    return container.attrs["NetworkSettings"]["Networks"][network_name]["IPAddress"]


def _replay_and_check_router(
    firewall: Container, attacker: Container, pcap_path: str, dst_ip: str, target_ip: str
) -> bool:
    """Route dst_ip toward the target via the firewall, replay from the attacker,
    and report whether the firewall's FORWARD chain blocked it.

    `ip route replace` is idempotent, same as host mode's `ip addr replace`,
    so repeated flows sharing a destination IP don't error.
    """
    firewall.exec_run(["ip", "route", "replace", f"{dst_ip}/32", "via", target_ip])
    firewall.exec_run(["iptables", "-Z", "FORWARD"])

    exit_code, output = attacker.exec_run(["tcpreplay", "--intf1=eth0", pcap_path])
    if exit_code != 0:
        raise SandboxTestError(f"tcpreplay failed (router mode): {output.decode(errors='replace')}")

    exit_code, output = firewall.exec_run(["iptables", "-L", "FORWARD", "-v", "-n", "-x"])
    return _any_drop_matched(output.decode(errors="replace"))


def _replay_all_flows_router_mode(command: str, traffic: pd.DataFrame) -> list[FlowResult]:
    """Replay each traffic flow through a genuine attacker -> firewall -> target topology."""
    docker_client = docker.from_env()
    _ensure_image(docker_client)
    topology = _start_router_topology(docker_client)
    attacker, firewall, target = topology["attacker"], topology["firewall"], topology["target"]

    results: list[FlowResult] = []
    try:
        _load_rule(firewall, command)  # reused unchanged -- just a different container

        firewall_mac = _firewall_facing_mac(firewall, topology["attacker_net"].name)
        target_ip = _container_ip(target, topology["target_net"].name)

        for _, flow in traffic.iterrows():
            try:
                pcap_bytes = _build_flow_pcap(flow, dst_mac=firewall_mac)
                pcap_path = _put_pcap(attacker, pcap_bytes)  # reused unchanged
                blocked = _replay_and_check_router(
                    firewall, attacker, pcap_path, str(flow["dst_ip"]), target_ip
                )
            except SandboxTestError as e:
                logger.warning(
                    f"Skipping flow {flow['src_ip']}->{flow['dst_ip']} (router mode): {e}"
                )
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
        _teardown_router_topology(topology)

    return results


# ============================================================================
# OUTPUT MODE (traffic leaving the firewall itself)
#
# Reuses host mode's exact container/veth setup unchanged (_start_container,
# _load_rule, _any_drop_matched) — OUTPUT chain fires for any packet the
# container's own kernel constructs, *including* one addressed to an IP
# aliased onto its own interface (confirmed empirically: a real connection
# attempt to a locally-aliased address traverses OUTPUT before the kernel
# short-circuits it to local delivery). What has to differ from host mode is
# how traffic is generated: tcpreplay's injected frames are inbound, never
# locally-originated, so they can only ever hit INPUT or FORWARD — never
# OUTPUT. Genuine egress traffic instead comes from real socket connections
# made from inside the container. See ADR-040.
#
# The generated packet's *source* address also has to be pinned to the
# flow's real src_ip, not just its destination — otherwise any rule with a
# `-s <this-host-ip>` clause (a completely natural thing for an LLM to write)
# silently never matches. See _replay_and_check_output's docstring and
# ADR-042 for why this needs both an address alias and an explicit `local`
# table route override, not just one or the other.
# ============================================================================

def _build_egress_script(dst_ip: str, dst_port: int, protocol: str, count: int) -> str:
    """Build a shell snippet that attempts `count` real outbound connections.

    Uses bash's /dev/tcp and /dev/udp, which genuinely traverse the kernel's
    own egress path (confirmed empirically against OUTPUT chain counters) —
    unlike tcpreplay, which cannot generate locally-originated traffic at
    all. Raises SandboxTestError for protocols with no real egress-generation
    mechanism available here (ICMP: no ping-equivalent tool is installable,
    since --network none blocks all network access including apt — see
    ADR-040). The caller treats that the same as any other skippable flow.

    Each attempt is wrapped in `timeout` — a DROPped SYN produces no RST, so
    an unbounded connect() blocks on the kernel's own SYN-retry timeout
    (empirically observed: still retrying past 9 attempts / several minutes
    with no cap). Without this, a single DROP-matching flow hangs the entire
    test. See ADR-040.
    """
    if protocol == "TCP":
        attempt = (
            f"(timeout {EGRESS_CONNECT_TIMEOUT_SECONDS} "
            f"bash -c 'exec 3<>/dev/tcp/{dst_ip}/{dst_port}') 2>/dev/null"
        )
    elif protocol == "UDP":
        attempt = (
            f"(timeout {EGRESS_CONNECT_TIMEOUT_SECONDS} "
            f"bash -c 'exec 3<>/dev/udp/{dst_ip}/{dst_port} && echo x >&3') 2>/dev/null"
        )
    else:
        raise SandboxTestError(
            f"No real egress-generation mechanism for protocol {protocol!r} in "
            "output mode (see ADR-040)"
        )
    return f"for i in $(seq 1 {count}); do {attempt}; done"


def _replay_and_check_output(
    container: Container, src_ip: str, dst_ip: str, dst_port: int, protocol: str, count: int
) -> bool:
    """Alias src_ip and dst_ip, generate real outbound connection attempts, and
    report whether the container's own OUTPUT chain blocked them.

    Aliasing dst_ip alone (the original ADR-040 design) is not enough to make
    the generated packet's *source* address match the flow's real src_ip —
    confirmed empirically (see ADR-042): once dst_ip is aliased as a /32, the
    kernel treats it as a local-delivery destination and its auto-generated
    `local` table route always picks the *destination* address as the source
    too, regardless of what other addresses are configured on the container.
    A plain `ip route replace <dst>/32 ... src <src_ip>` in the main table has
    no effect either — the `local` table takes priority and is never
    consulted. Two things are required together: (1) `src_ip` must be a
    locally-assigned address (the kernel rejects an unassigned address as an
    invalid `prefsrc`), and (2) the `local` table's own route for `dst_ip`
    must be explicitly replaced with one specifying that `src_ip`. Without
    both, any rule with a `-s <this-host-ip>` clause — which is exactly what
    an LLM naturally writes for "this host is exfiltrating data" — silently
    never matches, no matter how correct the rule actually is.

    `ip addr replace` / `ip route replace` are idempotent, same as host
    mode's own per-flow setup. Individual connection attempts are expected to
    fail/refuse/time out — nothing is listening on the other end — that is
    not a sandbox error, unlike tcpreplay's exit code, which does indicate a
    real injection failure in the other two modes.
    """
    container.exec_run(["ip", "addr", "replace", f"{dst_ip}/32", "dev", PEER_IFACE])
    container.exec_run(["ip", "addr", "replace", f"{src_ip}/32", "dev", REPLAY_IFACE])
    container.exec_run(
        ["ip", "route", "replace", "local", dst_ip, "dev", PEER_IFACE, "src", src_ip, "table", "local"]
    )
    container.exec_run(["iptables", "-Z", "OUTPUT"])

    script = _build_egress_script(dst_ip, dst_port, protocol, count)
    container.exec_run(["bash", "-c", script])

    exit_code, output = container.exec_run(["iptables", "-L", "OUTPUT", "-v", "-n", "-x"])
    return _any_drop_matched(output.decode(errors="replace"))


def _replay_all_flows_output_mode(command: str, traffic: pd.DataFrame) -> list[FlowResult]:
    """Replay each traffic flow as genuine outbound connections from a single container."""
    docker_client = docker.from_env()
    _ensure_image(docker_client)
    container = _start_container(docker_client)  # reused unchanged -- host mode's own setup

    results: list[FlowResult] = []
    try:
        _load_rule(container, command)  # reused unchanged -- just checked against OUTPUT after

        for _, flow in traffic.iterrows():
            try:
                count = max(1, min(int(flow["packets"]), MAX_PACKETS_PER_FLOW))
                blocked = _replay_and_check_output(
                    container,
                    str(flow["src_ip"]),
                    str(flow["dst_ip"]),
                    int(flow["dst_port"]),
                    str(flow["protocol"]).upper(),
                    count,
                )
            except SandboxTestError as e:
                # Same convention as host/router mode: one bad flow (or, here,
                # an unsupported protocol) shouldn't abort the whole test.
                logger.warning(f"Skipping flow {flow['src_ip']}->{flow['dst_ip']} (output mode): {e}")
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


def _pipeline_duration_seconds(trigger_event: dict[str, Any] | None) -> float | None:
    """Seconds from anomaly detection to now, if trigger_event carries a detected_at.

    detected_at (set by ml/rule_gen.py's AnomalyContext) marks when the
    anomaly was picked up for rule generation — earlier than this sandbox
    test even starts — so this captures LLM latency plus sandbox-test time,
    the full "time to generate and validate" a rule end to end.
    """
    if not trigger_event or "detected_at" not in trigger_event:
        return None
    try:
        detected_at = datetime.fromisoformat(trigger_event["detected_at"])
    except (TypeError, ValueError) as e:
        logger.warning(f"Could not parse trigger_event.detected_at for timing: {e}")
        return None
    return (datetime.now(timezone.utc) - detected_at).total_seconds()


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

    Automatically dispatches to host mode (INPUT chain), router mode
    (FORWARD chain), or output mode (OUTPUT chain) based on which chain the
    rule's command targets — see _detect_chain, ADR-039, ADR-040. Never a
    manual toggle.
    """
    if rule.get("syntax") != "iptables":
        raise SandboxTestError(
            f"Sandbox only supports iptables syntax on this Linux image, got {rule.get('syntax')!r}"
        )

    chain = _detect_chain(rule["command"])
    mode = {"FORWARD": "router", "OUTPUT": "output"}.get(chain, "host")
    logger.info(f"Detected target chain={chain} -> testing in {mode} mode")

    rule_id = promoter.insert_pending_rule(rule, trigger_event)
    logger.info(f"Inserted candidate rule {rule_id} as PENDING")
    promoter.mark_testing(rule_id)

    ch_client = get_clickhouse_client()
    traffic = fetch_recent_traffic(ch_client, minutes=10)

    if traffic.empty:
        logger.warning("No traffic in the last 10 minutes — nothing to replay")
        results: list[FlowResult] = []
    else:
        replay_fns = {
            "router": _replay_all_flows_router_mode,
            "output": _replay_all_flows_output_mode,
        }
        replay_fn = replay_fns.get(mode, _replay_all_flows)
        try:
            results = replay_fn(rule["command"], traffic)
        except InvalidRuleError as e:
            sandbox_result = {
                "tested_at": datetime.now(timezone.utc).isoformat(),
                "flows_tested": 0,
                "error": str(e),
                "mode": mode,
                "pipeline_duration_seconds": _pipeline_duration_seconds(trigger_event),
            }
            promoter.reject(rule_id, sandbox_result, f"Invalid rule: {e}")
            logger.info(
                f"Rule {rule_id} REJECTED (invalid syntax, {mode} mode) in "
                f"{sandbox_result['pipeline_duration_seconds']} s end to end"
            )
            return {"rule_id": str(rule_id), "passed": False, **sandbox_result}

    scored = score_replay(results)

    # Policy conflict check against currently-LIVE rules -- purely
    # informational (see ADR-044). Never affects passed/rejected: the human
    # reviewer sees any conflict in the dashboard and decides, the system
    # never auto-rejects on this basis alone, per the explicit design
    # requirement.
    try:
        policy_conflicts = conflict_checker.check_conflicts(
            rule["command"], promoter.get_live_rules()
        )
    except Exception as e:
        # A conflict-check failure (e.g. a transient DB error) must not
        # block the rule reaching its otherwise-earned verdict -- this is an
        # advisory check, not part of the core guarantee.
        logger.warning(f"Policy conflict check failed, continuing without it: {e}")
        policy_conflicts = []

    sandbox_result = {
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "flows_tested": len(results),
        "mode": mode,
        "pipeline_duration_seconds": _pipeline_duration_seconds(trigger_event),
        "policy_conflicts": policy_conflicts,
        **scored,
    }

    if scored["passed"]:
        promoter.approve(rule_id, sandbox_result)
        detection_str = (
            "n/a" if scored["detection_rate"] is None else f"{scored['detection_rate']:.4f}"
        )
        conflict_str = f", {len(policy_conflicts)} policy conflict(s)" if policy_conflicts else ""
        logger.info(
            f"Rule {rule_id} PASSED sandbox test ({mode} mode, fp_rate={scored['fp_rate']:.4f}, "
            f"detection_rate={detection_str}{conflict_str}) "
            f"-> APPROVED_PENDING in {sandbox_result['pipeline_duration_seconds']} s end to end"
        )
    else:
        # Report every check that actually failed -- a rule can fail on FP
        # rate, detection rate, or both, and the two are independent
        # findings (see ADR-043). Reusing a single hardcoded "FP rate
        # exceeded" message regardless of cause would misreport why a rule
        # with 0.0 fp_rate but 0% detection was rejected.
        reasons = []
        if scored["fp_rate"] > scored["threshold"]:
            reasons.append(f"FP rate {scored['fp_rate']:.4f} exceeds threshold {scored['threshold']:.4f}")
        if scored["detection_rate"] is not None and scored["detection_rate"] < scored["detection_threshold"]:
            reasons.append(
                f"detection rate {scored['detection_rate']:.4f} below threshold "
                f"{scored['detection_threshold']:.4f}"
            )
        reason = "; ".join(reasons) if reasons else "sandbox test failed"
        promoter.reject(rule_id, sandbox_result, reason)
        logger.info(
            f"Rule {rule_id} REJECTED ({mode} mode) in "
            f"{sandbox_result['pipeline_duration_seconds']} s end to end"
        )

    return {"rule_id": str(rule_id), **sandbox_result}
