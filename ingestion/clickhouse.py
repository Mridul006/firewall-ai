"""Writes parsed traffic events to ClickHouse."""

import logging
import os
from typing import Any

from clickhouse_driver import Client
from clickhouse_driver.errors import Error as ClickHouseError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "9000"))

CREATE_TABLE_QUERY = """
CREATE TABLE IF NOT EXISTS traffic_events (
    timestamp    DateTime,
    src_ip       String,
    dst_ip       String,
    src_port     UInt16,
    dst_port     UInt16,
    protocol     String,
    bytes        UInt64,
    packets      UInt32,
    flags        String,
    duration     Float32,
    anomaly_score Float32
) ENGINE = MergeTree()
ORDER BY (timestamp, src_ip)
TTL timestamp + INTERVAL 30 DAY
"""

INSERT_QUERY = """
INSERT INTO traffic_events
(timestamp, src_ip, dst_ip, src_port, dst_port, protocol, bytes, packets, flags, duration, anomaly_score)
VALUES
"""


def get_client() -> Client:
    """Create a new ClickHouse client connection."""
    return Client(host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT)


def ensure_table(client: Client) -> None:
    """Create the traffic_events table if it does not already exist."""
    try:
        client.execute(CREATE_TABLE_QUERY)
    except ClickHouseError as e:
        logger.error(f"Failed to create traffic_events table: {e}")
        raise


def insert_traffic_events(client: Client, events: list[dict[str, Any]]) -> None:
    """Bulk-insert parsed traffic events into ClickHouse."""
    if not events:
        return

    try:
        client.execute(INSERT_QUERY, events)
    except ClickHouseError as e:
        logger.error(f"Failed to insert {len(events)} traffic events: {e}")
        raise
