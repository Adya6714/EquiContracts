"""SQL for inbound email resolve / quarantine / document insert.

Caller supplies the session: privileged (system) for resolve/quarantine,
org-scoped app role for document insert.

JSON/service still use project_id; columns are engagement_id.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def resolve_project_by_alias(session: Session, *, alias: str) -> dict[str, Any] | None:
    row = (
        session.execute(
            text(
                """
                SELECT id, owner_org_id
                FROM resolve_inbound_engagement(:alias)
                """
            ),
            {"alias": alias},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def quarantine_unknown_recipient(
    session: Session, *, recipient: str, payload_hash: str
) -> None:
    session.execute(
        text(
            """
            SELECT quarantine_inbound(
              :recipient, :payload_hash, 'unknown_recipient'
            )
            """
        ),
        {
            "recipient": recipient,
            "payload_hash": payload_hash,
        },
    )


def upsert_inbound_document(
    session: Session,
    *,
    project_id: UUID,
    filename: str,
    storage_uri: str,
    sha256: str,
    sender_email: str | None,
    reminder_sequence_number: int | None,
) -> UUID:
    document_id = session.execute(
        text(
            """
            INSERT INTO document (
              engagement_id, filename, storage_uri, sha256, source,
              sender_email, reminder_sequence_number
            )
            VALUES (
              :engagement_id, :filename, :storage_uri, :sha256,
              'email_forward', :sender_email, :reminder_sequence_number
            )
            ON CONFLICT (engagement_id, sha256)
            DO UPDATE SET received_at = EXCLUDED.received_at
            RETURNING id
            """
        ),
        {
            "engagement_id": project_id,
            "filename": filename,
            "storage_uri": storage_uri,
            "sha256": sha256,
            "sender_email": sender_email,
            "reminder_sequence_number": reminder_sequence_number,
        },
    ).scalar_one()
    return UUID(str(document_id))
