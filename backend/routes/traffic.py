"""Traffic and anomaly routes, backed by ClickHouse's traffic_events table."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from clickhouse_driver.errors import Error as ClickHouseError
from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from core.clickhouse import get_clickhouse_client, to_aware_utc
from core.config import settings
from models.traffic import AnomalyEvent, TrafficEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/traffic", tags=["traffic"])

_COLUMNS = [
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


def _fetch_traffic(minutes: int, anomaly_threshold: float | None = None) -> list[dict[str, Any]]:
    """Query traffic_events for the last N minutes, optionally above an anomaly threshold.

    Synchronous — callers must run this via run_in_threadpool.
    """
    client = get_clickhouse_client()
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    query = f"SELECT {', '.join(_COLUMNS)} FROM traffic_events WHERE timestamp >= %(since)s"
    params: dict[str, Any] = {"since": since}
    if anomaly_threshold is not None:
        query += " AND anomaly_score > %(threshold)s"
        params["threshold"] = anomaly_threshold
    query += " ORDER BY timestamp DESC"

    rows = client.execute(query, params)
    events = [dict(zip(_COLUMNS, row, strict=True)) for row in rows]
    for event in events:
        event["timestamp"] = to_aware_utc(event["timestamp"])
    return events


@router.get("/", response_model=list[TrafficEvent])
async def list_traffic(
    minutes: int = Query(60, ge=1, le=1440, description="How far back to look, in minutes"),
) -> list[TrafficEvent]:
    """List recent traffic events with anomaly scores."""
    try:
        rows = await run_in_threadpool(_fetch_traffic, minutes)
    except ClickHouseError as e:
        logger.error(f"Traffic query failed: {e}")
        raise HTTPException(status_code=500, detail="Traffic query failed") from e

    return [TrafficEvent(**row) for row in rows]


@router.get("/anomalies", response_model=list[AnomalyEvent])
async def list_anomalies(
    minutes: int = Query(60, ge=1, le=1440, description="How far back to look, in minutes"),
) -> list[AnomalyEvent]:
    """List only traffic events above the anomaly alert threshold."""
    try:
        rows = await run_in_threadpool(
            _fetch_traffic, minutes, settings.ANOMALY_ALERT_THRESHOLD
        )
    except ClickHouseError as e:
        logger.error(f"Anomaly query failed: {e}")
        raise HTTPException(status_code=500, detail="Traffic query failed") from e

    return [AnomalyEvent(**row) for row in rows]
