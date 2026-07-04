"""ClickHouse client for traffic_events queries.

clickhouse-driver has no async client. Routes and background tasks that use
it must run queries via starlette.concurrency.run_in_threadpool so the
synchronous I/O never blocks the event loop.
"""

from datetime import datetime, timezone

from clickhouse_driver import Client

from core.config import settings


def get_clickhouse_client() -> Client:
    """Create a new ClickHouse client connection."""
    return Client(host=settings.CLICKHOUSE_HOST, port=settings.CLICKHOUSE_PORT)


def to_aware_utc(value: datetime) -> datetime:
    """Normalize a ClickHouse-returned datetime to aware UTC.

    ClickHouse's DateTime columns carry no timezone metadata, so
    clickhouse-driver returns naive datetimes (this project always writes
    them as UTC — see ADR-034). Pydantic serializes a naive datetime to JSON
    with no "Z"/offset suffix, which browsers then misparse as local time
    (per the JS/ECMA-262 date-time string rules) instead of converting from
    UTC — this is what must be called on every ClickHouse timestamp before it
    reaches a response model or a WebSocket message.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
