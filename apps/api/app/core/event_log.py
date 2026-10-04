"""Append-only, hash-chained audit events."""

import hashlib
import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def append_event(
    session: Session,
    *,
    project_id: UUID,
    event_type: str,
    actor_user_id: UUID | None,
    entity_type: str,
    entity_id: UUID,
    metadata: dict[str, str] | None = None,
) -> None:
    safe_metadata = metadata or {}
    previous_hash = session.execute(
        text(
            """
            SELECT event_hash
            FROM event_log
            WHERE engagement_id = :engagement_id
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ),
        {"engagement_id": project_id},
    ).scalar_one_or_none()
    # Hash payload keeps project_id key for chain stability / API naming.
    canonical = json.dumps(
        {
            "project_id": str(project_id),
            "event_type": event_type,
            "actor_user_id": str(actor_user_id) if actor_user_id else None,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "metadata": safe_metadata,
            "previous_hash": previous_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    event_hash = hashlib.sha256(canonical.encode()).hexdigest()
    session.execute(
        text(
            """
            INSERT INTO event_log (
              engagement_id, event_type, actor_user_id, entity_type, entity_id,
              metadata, previous_hash, event_hash
            )
            VALUES (
              :engagement_id, :event_type, :actor_user_id, :entity_type,
              :entity_id, CAST(:metadata AS jsonb), :previous_hash, :event_hash
            )
            """
        ),
        {
            "engagement_id": project_id,
            "event_type": event_type,
            "actor_user_id": actor_user_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "metadata": json.dumps(safe_metadata),
            "previous_hash": previous_hash,
            "event_hash": event_hash,
        },
    )
