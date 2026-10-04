"""Thin read services for agent tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from packages.extraction.document_text import (
    load_document_text_from_bytes,
    pages_from_text,
)

from ..core.storage import DocumentStorage
from ..repositories import agent_reads as agent_reads_repo


def get_engagement_context(
    session: Session, *, engagement_id: UUID
) -> dict[str, Any] | None:
    return agent_reads_repo.fetch_engagement_context(
        session, engagement_id=engagement_id
    )


def get_document_metadata(
    session: Session, *, document_id: UUID
) -> dict[str, Any] | None:
    return agent_reads_repo.fetch_document_metadata(session, document_id=document_id)


def get_document_pages(
    session: Session,
    *,
    document_id: UUID,
    storage: DocumentStorage | None = None,
) -> dict[str, Any] | None:
    """Load page text for a document. Location comes from the DB row only."""

    row = agent_reads_repo.fetch_document_storage_ref(session, document_id=document_id)
    if row is None:
        return None
    store = storage or DocumentStorage()
    data = store.get_document_bytes(str(row["storage_uri"]))
    suffix = Path(str(row["filename"] or "document.txt")).suffix or ".txt"
    document_text = load_document_text_from_bytes(data, suffix=suffix)
    pages = pages_from_text(document_text)
    return {
        "document_id": str(row["id"]),
        "engagement_id": str(row["engagement_id"]),
        "page_count": len(pages),
        "pages": pages,
    }
