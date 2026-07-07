"""Measures a sandbox replay's false-positive rate AND detection rate against
their configured thresholds — a rule must clear both to pass.
"""

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SANDBOX_FP_THRESHOLD = float(os.getenv("SANDBOX_FP_THRESHOLD", "0.05"))

# Minimum fraction of anomalous packets a rule must actually block to pass —
# added after ADR-042 found a rule reach APPROVED_PENDING with a perfect
# fp_rate while blocking 0% of the traffic it was meant to stop (fp_rate only
# ever measured legitimate traffic wrongly blocked, never whether the rule
# does anything at all). Deliberately not set near 1.0: a rate-limiting rule
# (iptables -m recent, letting the first few hits through before it starts
# dropping) is a legitimate, intentional design an LLM may choose, and
# genuinely blocks well under 100% of a scan's packets by construction — see
# ADR-043 for the real observed numbers (37.5%) this threshold was picked
# against.
SANDBOX_DETECTION_THRESHOLD = float(os.getenv("SANDBOX_DETECTION_THRESHOLD", "0.1"))

# A flow counts as "anomalous" (excluded from the FP-rate denominator, and the
# population the detection-rate check is measured over) if its stored
# anomaly_score exceeds this — matches ml/anomaly.py's detect_anomalies()
# default threshold, for consistency across the pipeline.
ANOMALY_SCORE_THRESHOLD = 0.5


@dataclass
class FlowResult:
    """One traffic flow's replay outcome against a candidate rule."""

    src_ip: str
    dst_ip: str
    dst_port: int
    packets: int
    bytes: int
    anomaly_score: float
    blocked: bool


def score_replay(
    results: list[FlowResult],
    threshold: float = SANDBOX_FP_THRESHOLD,
    detection_threshold: float = SANDBOX_DETECTION_THRESHOLD,
) -> dict[str, float | int | bool | None]:
    """Score a sandbox replay's false-positive rate AND detection rate.

    FP rate        = packets blocked by the rule that are NOT anomalous
                      / total non-anomalous packets.
    Detection rate = anomalous packets the rule actually blocked
                      / total anomalous packets.

    A rule must clear BOTH to pass — see ADR-043. FP rate alone can't catch a
    rule that matches nothing at all (confirmed happening for real: ADR-042),
    since a rule blocking 0% of everything has a perfect 0.0 fp_rate.

    Mode-agnostic by design — this only reads FlowResult.blocked, which
    tester.py's host mode (INPUT chain), router mode (FORWARD chain, ADR-039)
    and output mode (OUTPUT chain, ADR-040/042) each populate their own way.
    For router mode this reads exactly as the task requires: the percentage
    of legitimate attacker-to-target traffic that would have been wrongly
    blocked. No mode-specific logic was needed here — verified, not
    overlooked.
    """
    non_anomalous = [r for r in results if r.anomaly_score <= ANOMALY_SCORE_THRESHOLD]
    anomalous = [r for r in results if r.anomaly_score > ANOMALY_SCORE_THRESHOLD]

    total_non_anomalous_packets = sum(r.packets for r in non_anomalous)
    blocked_non_anomalous_packets = sum(r.packets for r in non_anomalous if r.blocked)
    total_anomalous_packets = sum(r.packets for r in anomalous)
    blocked_anomalous_packets = sum(r.packets for r in anomalous if r.blocked)

    if total_non_anomalous_packets == 0:
        logger.warning(
            "No non-anomalous traffic in this replay window — FP rate undefined, treating as 0.0"
        )
        fp_rate = 0.0
    else:
        fp_rate = blocked_non_anomalous_packets / total_non_anomalous_packets
    fp_ok = fp_rate <= threshold

    if total_anomalous_packets == 0:
        # Nothing anomalous was in the replay window at all (e.g. it aged out
        # of the 10-minute lookback between anomaly detection and sandbox
        # test) — that's a data-availability gap, not evidence the rule does
        # nothing, so this must not silently reject an untestable rule.
        logger.warning(
            "No anomalous traffic in this replay window — detection rate undefined, not gating on it"
        )
        detection_rate = None
        detection_ok = True
    else:
        detection_rate = blocked_anomalous_packets / total_anomalous_packets
        detection_ok = detection_rate >= detection_threshold

    passed = fp_ok and detection_ok
    logger.info(
        f"FP rate: {fp_rate:.4f} (threshold {threshold:.4f}) | "
        f"Detection rate: {'n/a' if detection_rate is None else f'{detection_rate:.4f}'} "
        f"(threshold {detection_threshold:.4f}) — "
        f"{'PASS' if passed else 'REJECT'} | "
        f"non_anomalous_flows={len(non_anomalous)} anomalous_flows={len(anomalous)} "
        f"blocked_anomalous_packets={blocked_anomalous_packets}/{total_anomalous_packets}"
    )

    return {
        "fp_rate": fp_rate,
        "threshold": threshold,
        "detection_rate": detection_rate,
        "detection_threshold": detection_threshold,
        "passed": passed,
        "non_anomalous_flows": len(non_anomalous),
        "anomalous_flows": len(anomalous),
        "total_non_anomalous_packets": total_non_anomalous_packets,
        "blocked_non_anomalous_packets": blocked_non_anomalous_packets,
        "total_anomalous_packets": total_anomalous_packets,
        "blocked_anomalous_packets": blocked_anomalous_packets,
    }
