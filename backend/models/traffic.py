"""Traffic and anomaly event models, plus dashboard summary stats."""

from datetime import datetime

from pydantic import BaseModel


class TrafficEvent(BaseModel):
    """A single traffic flow record read from ClickHouse."""

    timestamp: datetime
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: str
    bytes: int
    packets: int
    flags: str
    duration: float
    anomaly_score: float


class AnomalyEvent(TrafficEvent):
    """A traffic event whose anomaly_score crossed the alert threshold."""

    anomaly_type: str | None = None


class DashboardStats(BaseModel):
    """Summary counters shown on the dashboard overview."""

    total_rules: int
    pending_rules: int
    live_rules: int
    rejected_rules: int
    traffic_events_24h: int
    anomalies_24h: int
