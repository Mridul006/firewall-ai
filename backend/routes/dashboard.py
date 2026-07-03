"""Dashboard summary route."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from models.rule import CandidateRule, RuleStatus
from models.traffic import DashboardStats

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_stats(db: AsyncSession = Depends(get_db)) -> DashboardStats:
    """Summary counters for the dashboard overview.

    Traffic/anomaly counters are 0 until the ingestion pipeline
    (build order phase 3) is deployed.
    """
    try:
        result = await db.execute(
            select(CandidateRule.status, func.count()).group_by(CandidateRule.status)
        )
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Database error") from e

    counts = dict(result.all())

    return DashboardStats(
        total_rules=sum(counts.values()),
        pending_rules=counts.get(RuleStatus.PENDING.value, 0),
        live_rules=counts.get(RuleStatus.LIVE.value, 0),
        rejected_rules=counts.get(RuleStatus.REJECTED.value, 0),
        traffic_events_24h=0,
        anomalies_24h=0,
    )
