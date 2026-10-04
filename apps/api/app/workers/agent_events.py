"""Claim agent events cross-org, then open an org-pinned agent session.

packages/agents (Part B) never opens DB connections. This worker owns claim +
session setup only.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from ..core.db import AgentSessionFactory, agent_org_scoped_session
from ..repositories import agent_events as agent_events_repo
from ..services.agent_events import ClaimedEvent


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
