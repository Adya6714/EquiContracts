"""Business logic for contractor review queue and verification."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from ..core.event_log import append_event
from ..repositories import review as review_repo


class FieldNotFoundError(Exception):
    """Field missing or not visible under the caller's org scope."""


@dataclass(frozen=True)
class ReviewQueueItem:
    document_id: UUID
    filename: str
    field_id: UUID | None
    field_name: str | None
    field_value: str | None
    state: str | None
    is_financial: bool | None


def list_queue(session: Session) -> list[ReviewQueueItem]:
    return [ReviewQueueItem(**row) for row in review_repo.list_queue_rows(session)]


def verify_field(
    session: Session,
    *,
    field_id: UUID,
    user_id: UUID,
    corrected_value: str | None,
    corrected_value_provided: bool,
) -> UUID:
    field = review_repo.lock_field_for_verify(session, field_id=field_id)
    if field is None:
        raise FieldNotFoundError

    value_changed = corrected_value_provided and corrected_value != field["field_value"]
    verified_field_id = field_id
    if value_changed:
        verified_field_id = review_repo.insert_verified_correction(
            session,
            document_id=field["document_id"],
            field_name=field["field_name"],
            field_value=corrected_value,
            is_financial=field["is_financial"],
            confidence=field["confidence"],
            model_version=field["model_version"],
            verified_by=user_id,
        )
        review_repo.mark_superseded(session, old_id=field_id, new_id=verified_field_id)
    else:
        review_repo.mark_verified_in_place(
            session, field_id=field_id, verified_by=user_id
        )

    append_event(
        session,
        project_id=field["project_id"],
        event_type="field_verified",
        actor_user_id=user_id,
        entity_type="extracted_field",
        entity_id=verified_field_id,
        metadata={"corrected": str(value_changed).lower()},
    )
    return verified_field_id
