"""Candidate firewall rule routes — list, retrieve, approve, reject, revoke."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from models.audit_log import AuditAction
from models.audit_log import record as record_audit_log
from models.rule import CandidateRule, RuleResponse, RuleStatus
from models.user import User
from routes.auth import get_current_user

router = APIRouter(prefix="/api/v1/rules", tags=["rules"])


@router.get("/", response_model=list[RuleResponse])
async def list_rules(
    status_filter: RuleStatus | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[CandidateRule]:
    """List candidate rules, optionally filtered by status."""
    query = select(CandidateRule)
    if status_filter is not None:
        query = query.where(CandidateRule.status == status_filter.value)

    try:
        result = await db.execute(query.order_by(CandidateRule.created_at.desc()))
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Database error") from e

    return list(result.scalars().all())


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> CandidateRule:
    """Get a single candidate rule by id."""
    return await _get_rule_or_404(rule_id, db)


@router.post("/{rule_id}/approve", response_model=RuleResponse)
async def approve_rule(
    rule_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CandidateRule:
    """Human approves a pending rule (HITL) — moves it to LIVE."""
    rule = await _get_rule_or_404(rule_id, db)
    if rule.status != RuleStatus.APPROVED_PENDING.value:
        raise HTTPException(
            status_code=400,
            detail=f"Rule must be {RuleStatus.APPROVED_PENDING.value} to approve",
        )

    previous_status = rule.status
    rule.status = RuleStatus.LIVE.value
    rule.approved_by = current_user.id
    rule.approved_at = datetime.now(timezone.utc)
    await record_audit_log(
        db,
        actor_id=current_user.id,
        action=AuditAction.RULE_APPROVED,
        rule_id=rule.id,
        metadata={
            "from_status": previous_status,
            "to_status": rule.status,
            "command": rule.command,
        },
    )
    await _commit(db)
    return rule


@router.post("/{rule_id}/reject", response_model=RuleResponse)
async def reject_rule(
    rule_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CandidateRule:
    """Human rejects a pending rule."""
    rule = await _get_rule_or_404(rule_id, db)
    previous_status = rule.status
    rule.status = RuleStatus.REJECTED.value
    await record_audit_log(
        db,
        actor_id=current_user.id,
        action=AuditAction.RULE_REJECTED,
        rule_id=rule.id,
        metadata={
            "from_status": previous_status,
            "to_status": rule.status,
            "command": rule.command,
        },
    )
    await _commit(db)
    return rule


@router.post("/{rule_id}/revoke", response_model=RuleResponse)
async def revoke_rule(
    rule_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CandidateRule:
    """Revoke a rule that is currently live."""
    rule = await _get_rule_or_404(rule_id, db)
    if rule.status != RuleStatus.LIVE.value:
        raise HTTPException(status_code=400, detail="Only a LIVE rule can be revoked")

    previous_status = rule.status
    rule.status = RuleStatus.REVOKED.value
    await record_audit_log(
        db,
        actor_id=current_user.id,
        action=AuditAction.RULE_REVOKED,
        rule_id=rule.id,
        metadata={
            "from_status": previous_status,
            "to_status": rule.status,
            "command": rule.command,
        },
    )
    await _commit(db)
    return rule


async def _get_rule_or_404(rule_id: uuid.UUID, db: AsyncSession) -> CandidateRule:
    """Fetch a candidate rule by id or raise 404."""
    try:
        result = await db.execute(
            select(CandidateRule).where(CandidateRule.id == rule_id)
        )
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Database error") from e

    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


async def _commit(db: AsyncSession) -> None:
    """Commit the current transaction, rolling back on failure."""
    try:
        await db.commit()
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error") from e
