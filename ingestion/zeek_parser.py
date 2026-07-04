"""Parses Zeek conn.log records into traffic_events rows.

Assumes Zeek is configured to emit conn.log as JSON (LogAscii::use_json = T)
and that each record is shipped as a single Kafka message value.
"""

import json
from datetime import datetime, timezone
from typing import Any


class ZeekParseError(Exception):
    """Raised when a raw Kafka message cannot be parsed as a Zeek conn.log record."""


def parse_zeek_conn_log(raw: bytes | str) -> dict[str, Any]:
    """Parse one Zeek conn.log JSON record into a traffic_events row dict."""
    try:
        record: dict[str, Any] = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        raise ZeekParseError(f"Invalid JSON in Zeek record: {e}") from e

    try:
        ts = float(record["ts"])
        src_ip = str(record["id.orig_h"])
        dst_ip = str(record["id.resp_h"])
        src_port = int(record["id.orig_p"])
        dst_port = int(record["id.resp_p"])
    except (KeyError, TypeError, ValueError) as e:
        raise ZeekParseError(f"Missing or invalid required field: {e}") from e

    orig_bytes = int(record.get("orig_bytes") or 0)
    resp_bytes = int(record.get("resp_bytes") or 0)
    orig_pkts = int(record.get("orig_pkts") or 0)
    resp_pkts = int(record.get("resp_pkts") or 0)

    return {
        "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc),
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "src_port": src_port,
        "dst_port": dst_port,
        "protocol": str(record.get("proto", "")).upper(),
        "bytes": orig_bytes + resp_bytes,
        "packets": orig_pkts + resp_pkts,
        "flags": str(record.get("history", "")),
        "duration": float(record.get("duration") or 0.0),
        # Populated later by the Isolation Forest anomaly detector (build order
        # phase 4) — ingestion has no anomaly signal to offer yet.
        "anomaly_score": 0.0,
    }
