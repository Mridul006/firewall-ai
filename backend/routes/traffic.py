"""Traffic and anomaly routes.

Backed by ClickHouse once the ingestion pipeline (build order phase 3) is deployed.
Until then these endpoints are wired but return 503, since there is no data source yet.
"""

from fastapi import APIRouter, HTTPException, status

from models.traffic import AnomalyEvent, TrafficEvent

router = APIRouter(prefix="/api/v1/traffic", tags=["traffic"])

_NOT_READY = "Traffic ingestion pipeline is not yet deployed"


@router.get("/", response_model=list[TrafficEvent])
async def list_traffic() -> list[TrafficEvent]:
    """List recent traffic events with anomaly scores."""
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_READY)


@router.get("/anomalies", response_model=list[AnomalyEvent])
async def list_anomalies() -> list[AnomalyEvent]:
    """List only traffic events above the anomaly threshold."""
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_READY)
