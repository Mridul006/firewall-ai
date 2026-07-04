"""Dashboard summary route."""

import logging
from datetime import datetime, timedelta, timezone

from clickhouse_driver.errors import Error as ClickHouseError
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from core.clickhouse import get_clickhouse_client
from core.config import settings
from core.db import get_db
from models.rule import CandidateRule, RuleStatus
from models.traffic import DashboardStats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _fetch_traffic_counts_24h() -> tuple[int, int]:
    """Query ClickHouse for the last 24h's total and anomalous event counts.

    Synchronous — callers must run this via run_in_threadpool.
    """
    client = get_clickhouse_client()
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    total = client.execute(
        "SELECT count() FROM traffic_events WHERE timestamp >= %(since)s",
        {"since": since},
    )[0][0]
    anomalies = client.execute(
        "SELECT count() FROM traffic_events WHERE timestamp >= %(since)s AND anomaly_score > %(threshold)s",
        {"since": since, "threshold": settings.ANOMALY_ALERT_THRESHOLD},
    )[0][0]
    return total, anomalies


@router.get("/stats", response_model=DashboardStats)
async def get_stats(db: AsyncSession = Depends(get_db)) -> DashboardStats:
    """Summary counters for the dashboard overview."""
    try:
        result = await db.execute(
            select(CandidateRule.status, func.count()).group_by(CandidateRule.status)
        )
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Database error") from e

    counts = dict(result.all())

    try:
        traffic_events_24h, anomalies_24h = await run_in_threadpool(_fetch_traffic_counts_24h)
    except ClickHouseError as e:
        # Rule counts are still useful on their own — don't fail the whole
        # dashboard just because ClickHouse is unreachable.
        logger.error(f"ClickHouse traffic counts failed: {e}")
        traffic_events_24h, anomalies_24h = 0, 0

    return DashboardStats(
        total_rules=sum(counts.values()),
        pending_rules=counts.get(RuleStatus.PENDING.value, 0),
        live_rules=counts.get(RuleStatus.LIVE.value, 0),
        rejected_rules=counts.get(RuleStatus.REJECTED.value, 0),
        traffic_events_24h=traffic_events_24h,
        anomalies_24h=anomalies_24h,
    )
