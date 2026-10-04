"""SQL for agent foundation events, runs, steps, proposals, decisions."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def insert_event(
    session: Session,
    *,
    org_id: UUID,
    event_type: str,
    idempotency_key: str,
    engagement_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = (
        session.execute(
            text(
                """
                INSERT INTO event (
                  org_id, engagement_id, event_type, idempotency_key, payload
                )
                VALUES (
                  :org_id, :engagement_id, :event_type, :idempotency_key,
                  CAST(:payload AS jsonb)
                )
                ON CONFLICT (org_id, idempotency_key) DO NOTHING
                RETURNING id, org_id, engagement_id, event_type, status,
                          idempotency_key, attempts
                """
            ),
            {
                "org_id": org_id,
                "engagement_id": engagement_id,
                "event_type": event_type,
                "idempotency_key": idempotency_key,
                "payload": json.dumps(payload or {}),
            },
        )
        .mappings()
        .one_or_none()
    )
    if row is not None:
        return dict(row)
    existing = (
        session.execute(
            text(
                """
                SELECT id, org_id, engagement_id, event_type, status,
                       idempotency_key, attempts
                FROM event
                WHERE org_id = :org_id AND idempotency_key = :idempotency_key
                """
            ),
            {"org_id": org_id, "idempotency_key": idempotency_key},
        )
        .mappings()
        .one()
    )
    return dict(existing)


def claim_next_event_row(
    session: Session,
    *,
    claim_timeout: timedelta = timedelta(minutes=10),
    max_attempts: int = 3,
) -> dict[str, Any] | None:
    row = (
        session.execute(
            text(
                """
                SELECT event_id, org_id, engagement_id, event_type
                FROM claim_next_event(
                  CAST(:timeout AS interval),
                  CAST(:max_attempts AS integer)
                )
                """
            ),
            {"timeout": claim_timeout, "max_attempts": max_attempts},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def insert_agent_run(
    session: Session,
    *,
    event_id: UUID,
    org_id: UUID,
    agent_name: str,
    agent_version: str,
    attempt: int,
    engagement_id: UUID | None = None,
    model_version: str | None = None,
) -> dict[str, Any]:
    row = (
        session.execute(
            text(
                """
                INSERT INTO agent_run (
                  event_id, org_id, engagement_id, agent_name, agent_version,
                  model_version, attempt, status
                )
                VALUES (
                  :event_id, :org_id, :engagement_id, :agent_name,
                  :agent_version, :model_version, :attempt, 'running'
                )
                RETURNING id, event_id, org_id, agent_name, attempt, status
                """
            ),
            {
                "event_id": event_id,
                "org_id": org_id,
                "engagement_id": engagement_id,
                "agent_name": agent_name,
                "agent_version": agent_version,
                "model_version": model_version,
                "attempt": attempt,
            },
        )
        .mappings()
        .one()
    )
    return dict(row)


def next_attempt_for_agent(session: Session, *, event_id: UUID, agent_name: str) -> int:
    current = session.execute(
        text(
            """
            SELECT COALESCE(MAX(attempt), 0)
            FROM agent_run
            WHERE event_id = :event_id AND agent_name = :agent_name
            """
        ),
        {"event_id": event_id, "agent_name": agent_name},
    ).scalar_one()
    return int(current) + 1


def finish_agent_run(
    session: Session,
    *,
    run_id: UUID,
    status: str,
    steps_used: int,
    retries_used: int = 0,
    cost: Decimal = Decimal("0"),
) -> None:
    session.execute(
        text(
            """
            UPDATE agent_run
            SET status = :status,
                steps_used = :steps_used,
                retries_used = :retries_used,
                cost = :cost,
                finished_at = now()
            WHERE id = :run_id
            """
        ),
        {
            "run_id": run_id,
            "status": status,
            "steps_used": steps_used,
            "retries_used": retries_used,
            "cost": cost,
        },
    )


def mark_event_processed(session: Session, *, event_id: UUID) -> None:
    session.execute(
        text(
            """
            UPDATE event
            SET status = 'processed',
                processed_at = now()
            WHERE id = :event_id
            """
        ),
        {"event_id": event_id},
    )


def mark_event_failed(session: Session, *, event_id: UUID, last_error: str) -> None:
    session.execute(
        text(
            """
            UPDATE event
            SET status = 'failed',
                last_error = :last_error
            WHERE id = :event_id
            """
        ),
        {"event_id": event_id, "last_error": last_error},
    )


def event_has_succeeded_run_for_agent(
    session: Session, *, event_id: UUID, agent_name: str
) -> bool:
    found = session.execute(
        text(
            """
            SELECT 1
            FROM agent_run
            WHERE event_id = :event_id
              AND agent_name = :agent_name
              AND status = 'succeeded'
            LIMIT 1
            """
        ),
        {"event_id": event_id, "agent_name": agent_name},
    ).scalar_one_or_none()
    return found is not None


def insert_agent_step(
    session: Session,
    *,
    run_id: UUID,
    org_id: UUID,
    step_no: int,
    outcome: str,
    tool_called: str | None = None,
    input_payload: dict[str, Any] | None = None,
    output_payload: dict[str, Any] | None = None,
) -> UUID:
    step_id = session.execute(
        text(
            """
            INSERT INTO agent_step (
              run_id, org_id, step_no, tool_called, input, output, outcome
            )
            VALUES (
              :run_id, :org_id, :step_no, :tool_called,
              CAST(:input AS jsonb), CAST(:output AS jsonb), :outcome
            )
            RETURNING id
            """
        ),
        {
            "run_id": run_id,
            "org_id": org_id,
            "step_no": step_no,
            "tool_called": tool_called,
            "input": json.dumps(input_payload or {}),
            "output": json.dumps(output_payload or {}),
            "outcome": outcome,
        },
    ).scalar_one()
    return UUID(str(step_id))


def insert_agent_proposal(
    session: Session,
    *,
    run_id: UUID,
    org_id: UUID,
    proposal_type: str,
    content: dict[str, Any],
    autonomy_level: int,
    engagement_id: UUID | None = None,
    confidence: Decimal | None = None,
) -> UUID:
    proposal_id = session.execute(
        text(
            """
            INSERT INTO agent_proposal (
              run_id, org_id, engagement_id, proposal_type, content,
              confidence, autonomy_level, state
            )
            VALUES (
              :run_id, :org_id, :engagement_id, :proposal_type,
              CAST(:content AS jsonb), :confidence, :autonomy_level, 'pending'
            )
            RETURNING id
            """
        ),
        {
            "run_id": run_id,
            "org_id": org_id,
            "engagement_id": engagement_id,
            "proposal_type": proposal_type,
            "content": json.dumps(content),
            "confidence": confidence,
            "autonomy_level": autonomy_level,
        },
    ).scalar_one()
    return UUID(str(proposal_id))


def insert_review_decision(
    session: Session,
    *,
    proposal_id: UUID,
    org_id: UUID,
    decided_by: UUID,
    decision: str,
    correction: dict[str, Any] | None = None,
    reason: str | None = None,
) -> UUID:
    decision_id = session.execute(
        text(
            """
            INSERT INTO review_decision (
              proposal_id, org_id, decided_by, decision, correction, reason
            )
            VALUES (
              :proposal_id, :org_id, :decided_by, :decision,
              CAST(:correction AS jsonb), :reason
            )
            RETURNING id
            """
        ),
        {
            "proposal_id": proposal_id,
            "org_id": org_id,
            "decided_by": decided_by,
            "decision": decision,
            "correction": json.dumps(correction or {}),
            "reason": reason,
        },
    ).scalar_one()
    return UUID(str(decision_id))


def get_proposal_state(session: Session, *, proposal_id: UUID) -> str | None:
    return session.execute(
        text("SELECT state FROM agent_proposal WHERE id = :id"),
        {"id": proposal_id},
    ).scalar_one_or_none()


def get_event_status(session: Session, *, event_id: UUID) -> str | None:
    return session.execute(
        text("SELECT status FROM event WHERE id = :id"),
        {"id": event_id},
    ).scalar_one_or_none()
