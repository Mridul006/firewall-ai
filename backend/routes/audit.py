"""Audit log routes — query the record of who changed a rule's status, when, and how."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from models.audit_log import AuditAction, AuditLog, AuditLogResponse
from models.user import User
from routes.auth import get_current_user

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/", response_model=list[AuditLogResponse])
async def list_audit_log(
    rule_id: uuid.UUID | None = None,
    action: AuditAction | None = None,
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    """List audit log entries, newest first, optionally filtered by rule or action.

    Requires auth even though most other GET routes in this API don't — an
    accountability log that anyone can read without logging in undercuts its
    own purpose.
    """
    query = select(AuditLog, User.email).outerjoin(User, AuditLog.actor_id == User.id)
    if rule_id is not None:
        query = query.where(AuditLog.rule_id == rule_id)
    if action is not None:
        query = query.where(AuditLog.action == action.value)
    query = query.order_by(AuditLog.timestamp.desc()).limit(limit)

    try:
        result = await db.execute(query)
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Database error") from e

    return [
        AuditLogResponse(
            id=log.id,
            timestamp=log.timestamp,
            actor_id=log.actor_id,
            actor_email=actor_email,
            action=log.action,
            rule_id=log.rule_id,
            event_metadata=log.event_metadata,
        )
        for log, actor_email in result.all()
    ]
