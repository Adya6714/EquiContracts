"""Read-only document metadata (ids/scalars only; never filename or text)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from packages.agents.context import RunContext
from packages.agents.tools._base import ToolRefusal


def run(ctx: RunContext, *, document_id: str | UUID) -> dict[str, Any]:
    if ctx.engagement_id is None:
        raise ToolRefusal("no_engagement")
    target = UUID(str(document_id))
    services = ctx.services
    fetch = getattr(services, "fetch_document_metadata", None)
    if fetch is None:
        raise ToolRefusal("missing_fetch_document")
    row = fetch(document_id=target)
    if row is None:
        raise ToolRefusal("document_not_found")
    doc_engagement = UUID(str(row["engagement_id"]))
    if doc_engagement != ctx.engagement_id:
        raise ToolRefusal("wrong_engagement")
    return {
        "id": str(row["id"]),
        "engagement_id": str(doc_engagement),
        "sha256": row["sha256"],
        "source": row["source"],
    }
