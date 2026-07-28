"""Audit log model — records every rule status change: who, when, what changed."""

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class AuditAction(str, enum.Enum):
    """Rule lifecycle events that get audit-logged."""

    RULE_APPROVED = "RULE_APPROVED"
    RULE_REJECTED = "RULE_REJECTED"
    RULE_REVOKED = "RULE_REVOKED"


class AuditLog(Base):
    """SQLAlchemy ORM model for the audit_log table."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # A Python-side default, not server_default="now()" — that pattern (used
    # elsewhere in this codebase for users.created_at / candidate_rules.
    # created_at) turns out to be a real, active bug: SQLAlchemy quotes a
    # bare string into DEFAULT 'now()', which Postgres casts to a FROZEN
    # literal timestamp at table-creation time, not a live per-row now()
    # call. Confirmed directly: a user registered long after this table
    # existed still showed the table's original creation date as
    # created_at. A Python-side default sidesteps the DDL-quoting pitfall
    # entirely and matches this project's own UTC convention (ADR-034).
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidate_rules.id"), nullable=True
    )
    # Mapped to the DB column literally named "metadata" (per the documented
    # schema in layer1_design.md) under a different Python attribute name —
    # `metadata` is reserved on every SQLAlchemy declarative model, since
    # Base.metadata is the schema's own MetaData object.
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class AuditLogResponse(BaseModel):
    """API response body for one audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    timestamp: datetime
    actor_id: uuid.UUID | None
    actor_email: str | None = None
    action: str
    rule_id: uuid.UUID | None
    event_metadata: dict[str, Any] | None


async def record(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: AuditAction,
    rule_id: uuid.UUID | None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Stage a new audit log entry on the given session.

    Does not commit — callers add this to the same transaction as the rule
    status change it documents, so the two can never disagree (an audit
    entry for a status change that failed to save, or vice versa).
    """
    entry = AuditLog(
        actor_id=actor_id,
        action=action.value,
        rule_id=rule_id,
        event_metadata=metadata,
    )
    db.add(entry)
    return entry
