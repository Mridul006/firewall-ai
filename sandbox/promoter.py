"""Promotes sandbox-tested rules in PostgreSQL: PENDING -> SANDBOX_TESTING -> APPROVED_PENDING or REJECTED."""

import json
import logging
import os
import uuid
from typing import Any

import psycopg
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

POSTGRES_URL = os.getenv("POSTGRES_URL", "")


def _get_connection() -> psycopg.Connection:
    """Open a new synchronous PostgreSQL connection."""
    if not POSTGRES_URL:
        raise RuntimeError("POSTGRES_URL is not set — check .env")
    return psycopg.connect(POSTGRES_URL)


def insert_pending_rule(
    rule: dict[str, Any], trigger_event: dict[str, Any] | None = None
) -> uuid.UUID:
    """Insert an LLM-generated candidate rule as a new PENDING row.

    The id is generated here rather than left to a DB default: backend's
    SQLAlchemy model (backend/models/rule.py) only sets a Python-side
    `default=uuid.uuid4`, not a `server_default`, so the live table's `id`
    column has no DB-level default to fall back on.

    `confidence` is explicitly coerced to float: LLM providers sometimes
    return it as a quoted string (observed with mistral during ML core
    testing), which would otherwise be bound against a `double precision`
    column as text.
    """
    rule_id = uuid.uuid4()
    confidence = rule.get("confidence")
    with _get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO candidate_rules
                (id, syntax, command, description, mitre_technique, confidence,
                 status, trigger_event)
            VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', %s)
            """,
            (
                rule_id,
                rule["syntax"],
                rule["command"],
                rule.get("description"),
                rule.get("mitre_technique"),
                float(confidence) if confidence is not None else None,
                json.dumps(trigger_event) if trigger_event else None,
            ),
        )
        conn.commit()
    return rule_id


def mark_testing(rule_id: uuid.UUID) -> None:
    """Move a rule from PENDING to SANDBOX_TESTING while its replay is running."""
    _set_status(rule_id, "SANDBOX_TESTING")


def get_live_rules() -> list[dict[str, Any]]:
    """Fetch id and command for every currently-LIVE rule, for policy conflict checking."""
    try:
        with _get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, command FROM candidate_rules WHERE status = 'LIVE'")
            rows = cur.fetchall()
    except psycopg.Error as e:
        logger.error(f"Failed to fetch LIVE rules for conflict checking: {e}")
        raise
    return [{"id": row[0], "command": row[1]} for row in rows]


def approve(rule_id: uuid.UUID, sandbox_result: dict[str, Any]) -> None:
    """Mark a rule APPROVED_PENDING after it passes its sandbox test.

    APPROVED_PENDING still awaits human approval in HITL mode — the sandbox
    passing is necessary but never sufficient for a rule to go live.
    """
    _update_status(rule_id, "APPROVED_PENDING", sandbox_result)


def reject(rule_id: uuid.UUID, sandbox_result: dict[str, Any], reason: str) -> None:
    """Mark a rule REJECTED after it fails its sandbox test, logging why."""
    logger.warning(f"Rejecting rule {rule_id}: {reason}")
    _update_status(rule_id, "REJECTED", sandbox_result)


def _set_status(rule_id: uuid.UUID, status: str) -> None:
    """Update only a rule's status column."""
    try:
        with _get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE candidate_rules SET status = %s, updated_at = NOW() WHERE id = %s",
                (status, rule_id),
            )
            conn.commit()
    except psycopg.Error as e:
        logger.error(f"Failed to set rule {rule_id} status to {status}: {e}")
        raise


def _update_status(
    rule_id: uuid.UUID, status: str, sandbox_result: dict[str, Any]
) -> None:
    """Write the final sandbox status, fp_rate, and full result JSON for a rule."""
    try:
        with _get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE candidate_rules
                SET status = %s, fp_rate = %s, sandbox_result = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (status, sandbox_result.get("fp_rate"), json.dumps(sandbox_result), rule_id),
            )
            conn.commit()
    except psycopg.Error as e:
        logger.error(f"Failed to update rule {rule_id} to {status}: {e}")
        raise
