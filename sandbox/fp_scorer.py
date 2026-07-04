"""Measures the false-positive rate of a sandbox replay against the configured threshold."""

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SANDBOX_FP_THRESHOLD = float(os.getenv("SANDBOX_FP_THRESHOLD", "0.05"))

# A flow counts as "anomalous" (excluded from the FP-rate denominator) if its
# stored anomaly_score exceeds this — matches ml/anomaly.py's
# detect_anomalies() default threshold, for consistency across the pipeline.
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
    results: list[FlowResult], threshold: float = SANDBOX_FP_THRESHOLD
) -> dict[str, float | int | bool]:
    """Score a sandbox replay's false-positive rate.

    FP rate = packets blocked by the rule that are NOT anomalous
              / total non-anomalous packets.
    """
    non_anomalous = [r for r in results if r.anomaly_score <= ANOMALY_SCORE_THRESHOLD]
    anomalous = [r for r in results if r.anomaly_score > ANOMALY_SCORE_THRESHOLD]

    total_non_anomalous_packets = sum(r.packets for r in non_anomalous)
    blocked_non_anomalous_packets = sum(r.packets for r in non_anomalous if r.blocked)
    blocked_anomalous_packets = sum(r.packets for r in anomalous if r.blocked)

    if total_non_anomalous_packets == 0:
        logger.warning(
            "No non-anomalous traffic in this replay window — FP rate undefined, treating as 0.0"
        )
        fp_rate = 0.0
    else:
        fp_rate = blocked_non_anomalous_packets / total_non_anomalous_packets

    passed = fp_rate <= threshold
    logger.info(
        f"FP rate: {fp_rate:.4f} (threshold {threshold:.4f}) — "
        f"{'PASS' if passed else 'REJECT'} | "
        f"non_anomalous_flows={len(non_anomalous)} anomalous_flows={len(anomalous)} "
        f"blocked_anomalous_packets={blocked_anomalous_packets}"
    )

    return {
        "fp_rate": fp_rate,
        "threshold": threshold,
        "passed": passed,
        "non_anomalous_flows": len(non_anomalous),
        "anomalous_flows": len(anomalous),
        "total_non_anomalous_packets": total_non_anomalous_packets,
        "blocked_non_anomalous_packets": blocked_non_anomalous_packets,
        "blocked_anomalous_packets": blocked_anomalous_packets,
    }
