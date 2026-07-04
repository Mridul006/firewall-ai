"""Extracts Isolation Forest features from ClickHouse traffic_events."""

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from clickhouse_driver import Client

from config import settings

logger = logging.getLogger(__name__)

FLAG_CHARS_SYN = {"S", "s"}
FLAG_CHARS_RST = {"R", "r"}

FEATURE_COLUMNS = [
    "bytes_per_second",
    "packets_per_second",
    "avg_packet_size",
    "duration",
    "dst_port",
    "src_port",
    "flags_syn_ratio",
    "flags_rst_ratio",
    "unique_dst_ports_per_src",
    "dns_query_entropy",
]


def get_client() -> Client:
    """Create a new ClickHouse client connection."""
    return Client(host=settings.CLICKHOUSE_HOST, port=settings.CLICKHOUSE_PORT)


def _flag_ratio(flags: str, chars: set[str]) -> float:
    """Fraction of a Zeek history string's characters belonging to the given set."""
    if not flags:
        return 0.0
    return sum(1 for c in flags if c in chars) / len(flags)


def fetch_recent_traffic(client: Client, minutes: int = 10) -> pd.DataFrame:
    """Pull the last N minutes of traffic_events into a DataFrame."""
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
    ]
    rows = client.execute(
        f"SELECT {', '.join(columns)} FROM traffic_events WHERE timestamp >= %(since)s",
        {"since": since},
    )
    return pd.DataFrame(rows, columns=columns)


def extract_features(traffic: pd.DataFrame) -> pd.DataFrame:
    """Compute the Isolation Forest feature matrix from raw traffic rows."""
    if traffic.empty:
        return pd.DataFrame(columns=FEATURE_COLUMNS)

    features = pd.DataFrame(index=traffic.index)

    safe_duration = traffic["duration"].replace(0, pd.NA).fillna(1e-6)
    safe_packets = traffic["packets"].replace(0, pd.NA).fillna(1)

    features["bytes_per_second"] = traffic["bytes"] / safe_duration
    features["packets_per_second"] = traffic["packets"] / safe_duration
    features["avg_packet_size"] = traffic["bytes"] / safe_packets
    features["duration"] = traffic["duration"]
    features["dst_port"] = traffic["dst_port"]
    features["src_port"] = traffic["src_port"]
    features["flags_syn_ratio"] = traffic["flags"].apply(
        lambda f: _flag_ratio(f, FLAG_CHARS_SYN)
    )
    features["flags_rst_ratio"] = traffic["flags"].apply(
        lambda f: _flag_ratio(f, FLAG_CHARS_RST)
    )

    # Port-scan indicator: how many distinct destination ports each source IP
    # touched in this window, broadcast back to every row from that source.
    features["unique_dst_ports_per_src"] = traffic.groupby("src_ip")["dst_port"].transform(
        "nunique"
    )

    # traffic_events stores conn-level summaries, not DNS query names — that
    # requires ingesting Zeek's dns.log, which isn't wired up yet. Placeholder
    # until DNS query ingestion exists; DNS-tunneling detection won't work
    # until then.
    features["dns_query_entropy"] = 0.0
    logger.warning(
        "dns_query_entropy is a placeholder (0.0) — DNS query log ingestion is not built yet"
    )

    return features[FEATURE_COLUMNS]
