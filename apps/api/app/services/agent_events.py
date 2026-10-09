"""Business logic for agent foundation events and runs (no agent runtime)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..repositories import agent_events as agent_events_repo


class EventConflictError(Exception):
    """Idempotent create collided in an unexpected way."""


@dataclass(frozen=True)
class ClaimedEvent:
    event_id: UUID
    org_id: UUID
    engagement_id: UUID | None
    event_type: str


@dataclass(frozen=True)
class AgentRunResult:
    run_id: UUID
    event_id: UUID
    agent_name: str
    attempt: int
    status: str


def create_event(
    session: Session,
    *,
    org_id: UUID,
    event_type: str,
    idempotency_key: str,
    engagement_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        return agent_events_repo.insert_event(
            session,
            org_id=org_id,
            event_type=event_type,
            idempotency_key=idempotency_key,
            engagement_id=engagement_id,
            payload=payload,
        )
    except IntegrityError as exc:
        raise EventConflictError from exc


def start_run(
    session: Session,
    *,
    event_id: UUID,
    org_id: UUID,
    agent_name: str,
    agent_version: str,
    engagement_id: UUID | None = None,
    model_version: str | None = None,
    attempt: int | None = None,
) -> AgentRunResult:
    resolved_attempt = (
        attempt
        if attempt is not None
        else agent_events_repo.next_attempt_for_agent(
            session, event_id=event_id, agent_name=agent_name
        )
    )
    row = agent_events_repo.insert_agent_run(
        session,
        event_id=event_id,
        org_id=org_id,
        engagement_id=engagement_id,
        agent_name=agent_name,
        agent_version=agent_version,
        attempt=resolved_attempt,
        model_version=model_version,
    )
    return AgentRunResult(
        run_id=UUID(str(row["id"])),
        event_id=event_id,
        agent_name=agent_name,
        attempt=resolved_attempt,
        status=str(row["status"]),
    )


def succeed_run(
    session: Session,
    *,
    run_id: UUID,
    event_id: UUID,
    agent_name: str,
    steps_used: int,
    retries_used: int = 0,
    cost: Decimal = Decimal("0"),
    model_version: str | None = None,
) -> None:
    """Finish a run as succeeded. Event processed is decided by the worker (fan-out)."""

    agent_events_repo.finish_agent_run(
        session,
        run_id=run_id,
        status="succeeded",
        steps_used=steps_used,
        retries_used=retries_used,
        cost=cost,
        model_version=model_version,
    )
    _ = event_id
    _ = agent_name


def mark_run_needs_human(
    session: Session,
    *,
    run_id: UUID,
    steps_used: int,
    retries_used: int = 0,
    cost: Decimal = Decimal("0"),
    model_version: str | None = None,
    last_error: str | None = None,
) -> None:
    """Finish a run as needs_human (proposals already flushed)."""

    agent_events_repo.finish_agent_run(
        session,
        run_id=run_id,
        status="needs_human",
        steps_used=steps_used,
        retries_used=retries_used,
        cost=cost,
        model_version=model_version,
    )
    _ = last_error


def get_event_payload(session: Session, *, event_id: UUID) -> dict[str, Any]:
    return agent_events_repo.fetch_event_payload(session, event_id=event_id)


def mark_event_processed(session: Session, *, event_id: UUID) -> None:
    agent_events_repo.mark_event_processed(session, event_id=event_id)


def mark_event_failed(session: Session, *, event_id: UUID, last_error: str) -> None:
    agent_events_repo.mark_event_failed(
        session, event_id=event_id, last_error=last_error
    )


def event_attempts(session: Session, *, event_id: UUID) -> int:
    return agent_events_repo.get_event_attempts(session, event_id=event_id)


def fail_run(
    session: Session,
    *,
    run_id: UUID,
    event_id: UUID,
    steps_used: int,
    last_error: str,
    retries_used: int = 0,
) -> None:
    """Finish a run as failed. Never marks the event processed."""

    agent_events_repo.finish_agent_run(
        session,
        run_id=run_id,
        status="failed",
        steps_used=steps_used,
        retries_used=retries_used,
        cost=Decimal("0"),
    )
    # Leave event claimed/pending for reclaim or explicit failed later; not processed.
    _ = event_id
    _ = last_error


def record_step(
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
    return agent_events_repo.insert_agent_step(
        session,
        run_id=run_id,
        org_id=org_id,
        step_no=step_no,
        outcome=outcome,
        tool_called=tool_called,
        input_payload=input_payload,
        output_payload=output_payload,
    )


def create_proposal(
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
    """Insert a proposal. Autonomy level is chosen by the caller (runtime in Part B)."""

    return agent_events_repo.insert_agent_proposal(
        session,
        run_id=run_id,
        org_id=org_id,
        engagement_id=engagement_id,
        proposal_type=proposal_type,
        content=content,
        autonomy_level=autonomy_level,
        confidence=confidence,
    )


def list_proposals_for_run(session: Session, *, run_id: UUID) -> list[dict[str, Any]]:
    return agent_events_repo.list_proposals_for_run(session, run_id=run_id)


def record_review_decision(
    session: Session,
    *,
    proposal_id: UUID,
    org_id: UUID,
    decided_by: UUID,
    decision: str,
    correction: dict[str, Any] | None = None,
    reason: str | None = None,
) -> UUID:
    return agent_events_repo.insert_review_decision(
        session,
        proposal_id=proposal_id,
        org_id=org_id,
        decided_by=decided_by,
        decision=decision,
        correction=correction,
        reason=reason,
    )


def claim_timeout_interval(minutes: int = 10) -> timedelta:
    return timedelta(minutes=minutes)
