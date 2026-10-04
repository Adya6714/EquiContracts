"""Claim agent events cross-org, then run routed agents in an org-pinned session.

packages/agents never opens DB connections. This worker owns claim, session,
and run_once orchestration.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from packages.agents.agents import get_agent
from packages.agents.context import RunContext
from packages.agents.router import agents_for
from packages.agents.runtime import run_agent

from ..core.db import AgentSessionFactory, agent_org_scoped_session
from ..repositories import agent_events as agent_events_repo
from ..services import agent_events as agent_events_service
from ..services.agent_events import ClaimedEvent
from .service_handle import WorkerServiceHandle

NO_AGENT_MESSAGE = "no agent for event type"


def claim_next_event(
    *,
    claim_timeout: timedelta = timedelta(minutes=10),
    max_attempts: int = 3,
) -> ClaimedEvent | None:
    """Call claim_next_event() as the agent role (no org pin), return claim or None."""

    session = AgentSessionFactory()
    try:
        row = agent_events_repo.claim_next_event_row(
            session,
            claim_timeout=claim_timeout,
            max_attempts=max_attempts,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    if row is None:
        return None
    engagement = row["engagement_id"]
    return ClaimedEvent(
        event_id=UUID(str(row["event_id"])),
        org_id=UUID(str(row["org_id"])),
        engagement_id=UUID(str(engagement)) if engagement is not None else None,
        event_type=str(row["event_type"]),
    )


@contextmanager
def claimed_event_session(
    claim: ClaimedEvent,
) -> Iterator[tuple[ClaimedEvent, Session]]:
    """Yield (claim, agent org-scoped session) for the claimed event's org."""

    with agent_org_scoped_session(claim.org_id) as session:
        yield claim, session


def run_once(
    *,
    claim_timeout: timedelta = timedelta(minutes=10),
    max_attempts: int = 3,
) -> bool:
    """Claim one event and run every routed agent. Return True if work was done."""

    claim = claim_next_event(claim_timeout=claim_timeout, max_attempts=max_attempts)
    if claim is None:
        return False

    routed = agents_for(claim.event_type)
    with agent_org_scoped_session(claim.org_id) as session:
        if routed is None:
            agent_events_service.mark_event_failed(
                session,
                event_id=claim.event_id,
                last_error=NO_AGENT_MESSAGE,
            )
            return True

        attempt = agent_events_service.event_attempts(session, event_id=claim.event_id)
        handle = WorkerServiceHandle(session)
        all_succeeded = True

        for agent_name in routed:
            registered = get_agent(agent_name)
            if registered is None:
                agent_events_service.mark_event_failed(
                    session,
                    event_id=claim.event_id,
                    last_error=NO_AGENT_MESSAGE,
                )
                return True
            agent_version, agent_fn = registered
            run = agent_events_service.start_run(
                session,
                event_id=claim.event_id,
                org_id=claim.org_id,
                agent_name=agent_name,
                agent_version=agent_version,
                engagement_id=claim.engagement_id,
                attempt=attempt,
            )
            ctx = RunContext(
                org_id=claim.org_id,
                engagement_id=claim.engagement_id,
                run_id=run.run_id,
                services=handle,
            )
            outcome = run_agent(ctx, agent_name=agent_name, agent_fn=agent_fn)
            if outcome.status == "succeeded":
                agent_events_service.succeed_run(
                    session,
                    run_id=run.run_id,
                    event_id=claim.event_id,
                    agent_name=agent_name,
                    steps_used=outcome.steps_used,
                    retries_used=outcome.retries_used,
                    cost=outcome.cost,
                )
            else:
                all_succeeded = False
                agent_events_service.fail_run(
                    session,
                    run_id=run.run_id,
                    event_id=claim.event_id,
                    steps_used=outcome.steps_used,
                    last_error=outcome.error or "agent failed",
                    retries_used=outcome.retries_used,
                )

        if all_succeeded:
            agent_events_service.mark_event_processed(session, event_id=claim.event_id)
        # On failure: leave status claimed for reclaim / attempt cap.
    return True
