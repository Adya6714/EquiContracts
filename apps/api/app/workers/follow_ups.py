"""Plain-code follow-up events after agent runs.

Only apps/api/app/workers/ may call create_follow_up_event (CI-enforced).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def create_follow_up_event(
    session: Session,
    *,
    parent_event_id: UUID,
    proposal_id: UUID,
) -> UUID:
    """Create document.classified from a verified Intake proposal (SECURITY DEFINER)."""

    child_id = session.execute(
        text(
            """
            SELECT create_follow_up_event(
              CAST(:parent_event_id AS uuid),
              CAST(:proposal_id AS uuid)
            )
            """
        ),
        {
            "parent_event_id": parent_event_id,
            "proposal_id": proposal_id,
        },
    ).scalar_one()
    return UUID(str(child_id))
