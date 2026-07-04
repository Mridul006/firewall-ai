"""Kafka consumer that reads Zeek traffic records from raw-traffic and writes them to ClickHouse."""

import logging
import os

from clickhouse_driver.errors import Error as ClickHouseError
from dotenv import load_dotenv
from kafka import KafkaConsumer

from clickhouse import ensure_table, get_client, insert_traffic_events
from zeek_parser import ZeekParseError, parse_zeek_conn_log

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
RAW_TRAFFIC_TOPIC = "raw-traffic"
CONSUMER_GROUP = "ingestion-service"
POLL_TIMEOUT_MS = 1000
MAX_BATCH_SIZE = 500


def run() -> None:
    """Continuously poll Kafka, parse Zeek records, and flush them to ClickHouse."""
    ch_client = get_client()
    ensure_table(ch_client)

    consumer = KafkaConsumer(
        RAW_TRAFFIC_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=CONSUMER_GROUP,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )

    logger.info(f"Consuming '{RAW_TRAFFIC_TOPIC}' from {KAFKA_BOOTSTRAP}")

    try:
        while True:
            batches = consumer.poll(timeout_ms=POLL_TIMEOUT_MS, max_records=MAX_BATCH_SIZE)
            if not batches:
                continue

            events = []
            for records in batches.values():
                for record in records:
                    try:
                        events.append(parse_zeek_conn_log(record.value))
                    except ZeekParseError as e:
                        logger.error(
                            f"Skipping unparseable record at offset {record.offset}: {e}"
                        )

            try:
                insert_traffic_events(ch_client, events)
            except ClickHouseError:
                # Already logged inside insert_traffic_events — do not commit
                # offsets so this batch is redelivered on the next poll.
                continue

            consumer.commit()
    except KeyboardInterrupt:
        logger.info("Shutting down consumer")
    finally:
        consumer.close()


if __name__ == "__main__":
    run()
