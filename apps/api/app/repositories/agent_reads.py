"""Read-only SQL for agent tools (IDs and metadata only)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def fetch_engagement_context(
    session: Session, *, engagement_id: UUID
) -> dict[str, Any] | None:
    row = (
        session.execute(
            text(
                """
                SELECT id, owner_org_id, site_id, project_code
                FROM engagement
                WHERE id = :engagement_id
                """
            ),
            {"engagement_id": engagement_id},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def fetch_document_metadata(
    session: Session, *, document_id: UUID
) -> dict[str, Any] | None:
    """Never select filename, sender_email, or storage body fields for agents."""

    row = (
        session.execute(
            text(
                """
                SELECT id, engagement_id, sha256, source
                FROM document
                WHERE id = :document_id
                """
            ),
            {"document_id": document_id},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def fetch_document_storage_ref(
    session: Session, *, document_id: UUID
) -> dict[str, Any] | None:
    """Ids + storage_uri for server-side byte fetch. Not for agent step logs."""

    row = (
        session.execute(
            text(
                """
                SELECT id, engagement_id, storage_uri, filename
                FROM document
                WHERE id = :document_id
                """
            ),
            {"document_id": document_id},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None
