"""Read document page text for the pinned engagement document only."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from packages.agents.context import RunContext
from packages.agents.tools._base import ToolRefusal


def run(ctx: RunContext, *, document_id: str | UUID) -> dict[str, Any]:
    if ctx.engagement_id is None:
        raise ToolRefusal("no_engagement")

    pinned = getattr(ctx.services, "pinned_document_id", None)
    if pinned is None:
        raise ToolRefusal("no_pinned_document")

    target = UUID(str(document_id))
    if target != UUID(str(pinned)):
        raise ToolRefusal("not_pinned_document")

    fetch = getattr(ctx.services, "fetch_document_pages", None)
    if fetch is None:
        raise ToolRefusal("missing_fetch_document_pages")

    row = fetch(document_id=target)
    if row is None:
        raise ToolRefusal("document_not_found")

    doc_engagement = UUID(str(row["engagement_id"]))
    if doc_engagement != ctx.engagement_id:
        raise ToolRefusal("wrong_engagement")

    pages = row.get("pages") or []
    return {
        "document_id": str(target),
        "page_count": int(row.get("page_count") or len(pages)),
        "pages": pages,
    }
