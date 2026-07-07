#!/usr/bin/env python
"""Seed ClickHouse with fresh, realistic traffic_events for demos.

Run this any time before a demo so the dashboard's default 60-minute view
shows data immediately, without needing a live Zeek/Kafka ingestion pipeline
running. Safe to re-run repeatedly -- each run just inserts new rows with
current timestamps; old rows age out of the dashboard's default view on
their own and out of ClickHouse via the table's 30-day TTL.

Usage:
    python scripts/seed_demo_data.py
    python scripts/seed_demo_data.py --normal-count 150 --minutes-back 50

See knowledge/architecture/decisions.md (ADR-041) for why this script exists.
"""

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))

from clickhouse import ensure_table, get_client, insert_traffic_events  # noqa: E402

# Internal hosts generating normal traffic, and the external services they
# talk to -- a believable small-office/small-network mix (web, DNS, SSH).
INTERNAL_HOSTS = ["10.0.0.5", "10.0.0.7", "10.0.0.9"]
NORMAL_SERVICES = [
    ("93.184.216.34", 443, "TCP"),   # HTTPS
    ("93.184.216.34", 80, "TCP"),    # HTTP
    ("8.8.8.8", 53, "UDP"),          # DNS
    ("1.1.1.1", 53, "UDP"),          # DNS
    ("140.82.112.3", 443, "TCP"),    # HTTPS (e.g. github-like)
]

# Anomaly scenario 1: external scanner probing a range of ports on one host.
SCANNER_IP = "198.51.100.66"
SCAN_TARGET = "10.0.0.9"
SCAN_PORTS = [21, 22, 23, 25, 135, 139, 445, 3389]

# Anomaly scenario 2: an internal host beaconing/exfiltrating to a
# suspicious external destination -- high bytes, tight beacon interval.
EXFIL_SRC = "10.0.0.9"
EXFIL_DST = "203.0.113.99"
EXFIL_PORT = 4444


def _normal_traffic(now: datetime, count: int, minutes_back: int) -> list[dict]:
    rows = []
    for _ in range(count):
        dst_ip, dst_port, protocol = random.choice(NORMAL_SERVICES)
        rows.append({
            "timestamp": now - timedelta(seconds=random.randint(0, minutes_back * 60)),
            "src_ip": random.choice(INTERNAL_HOSTS),
            "dst_ip": dst_ip,
            "src_port": random.randint(1024, 65535),
            "dst_port": dst_port,
            "protocol": protocol,
            "bytes": random.randint(400, 25000),
            "packets": random.randint(3, 20),
            "flags": "ShADadfF" if protocol == "TCP" else "",
            "duration": round(random.uniform(0.1, 2.5), 3),
            "anomaly_score": round(random.uniform(0.0, 0.25), 3),
        })
    return rows


def _port_scan_anomaly(now: datetime) -> list[dict]:
    rows = []
    for port in SCAN_PORTS:
        rows.append({
            "timestamp": now - timedelta(seconds=random.randint(0, 180)),
            "src_ip": SCANNER_IP,
            "dst_ip": SCAN_TARGET,
            "src_port": random.randint(40000, 60000),
            "dst_port": port,
            "protocol": "TCP",
            "bytes": 60,
            "packets": 1,
            "flags": "S",
            "duration": 0.01,
            "anomaly_score": round(random.uniform(0.85, 0.95), 3),
        })
    return rows


def _exfiltration_anomaly(now: datetime) -> list[dict]:
    rows = []
    for _ in range(6):
        rows.append({
            "timestamp": now - timedelta(seconds=random.randint(0, 120)),
            "src_ip": EXFIL_SRC,
            "dst_ip": EXFIL_DST,
            "src_port": random.randint(40000, 60000),
            "dst_port": EXFIL_PORT,
            "protocol": "TCP",
            "bytes": random.randint(15000, 40000),
            "packets": random.randint(10, 25),
            "flags": "ShADadfF",
            "duration": round(random.uniform(0.5, 1.5), 3),
            "anomaly_score": round(random.uniform(0.9, 0.98), 3),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normal-count", type=int, default=120,
                         help="Number of normal traffic rows to insert (default: 120)")
    parser.add_argument("--minutes-back", type=int, default=50,
                         help="Spread normal traffic over the last N minutes (default: 50)")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)

    rows = []
    rows += _normal_traffic(now, args.normal_count, args.minutes_back)
    rows += _port_scan_anomaly(now)
    rows += _exfiltration_anomaly(now)

    client = get_client()
    ensure_table(client)
    insert_traffic_events(client, rows)

    anomalous = sum(1 for r in rows if r["anomaly_score"] > 0.5)
    print(f"Seeded {len(rows)} traffic_events rows (as of {now.isoformat()}):")
    print(f"  {len(rows) - anomalous} normal flows across {len(INTERNAL_HOSTS)} internal hosts")
    print(f"  {len(SCAN_PORTS)} anomalous flows: port scan from {SCANNER_IP} -> {SCAN_TARGET}")
    print(f"  6 anomalous flows: suspected exfiltration {EXFIL_SRC} -> {EXFIL_DST}:{EXFIL_PORT}")
    print("All timestamps are within the last hour -- the dashboard's default")
    print("60-minute view will show this data immediately, no extra query params needed.")


if __name__ == "__main__":
    main()
