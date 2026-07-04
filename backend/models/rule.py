"""Candidate firewall rule models — DB entity, response schema, and status enum."""

import enum
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class RuleStatus(str, enum.Enum):
    """Lifecycle states a candidate rule moves through before reaching the live firewall."""

    PENDING = "PENDING"
    SANDBOX_TESTING = "SANDBOX_TESTING"
    REJECTED = "REJECTED"
    APPROVED_PENDING = "APPROVED_PENDING"
    LIVE = "LIVE"
    REVOKED = "REVOKED"


class CandidateRule(Base):
    """SQLAlchemy ORM model for the candidate_rules table."""

    __tablename__ = "candidate_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", onupdate=datetime.utcnow
    )
    syntax: Mapped[str] = mapped_column(String(20), nullable=False)
    command: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mitre_technique: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    fp_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default=RuleStatus.PENDING.value, nullable=False
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trigger_event: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sandbox_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class RuleResponse(BaseModel):
    """API response body for a candidate rule."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    syntax: str
    command: str
    description: str | None
    mitre_technique: str | None
    confidence: float | None
    fp_rate: float | None
    status: RuleStatus
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    trigger_event: dict[str, Any] | None
    sandbox_result: dict[str, Any] | None
