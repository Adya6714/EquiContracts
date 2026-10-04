"""Read-only engagement summary for the run's engagement only."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from packages.agents.context import RunContext
from packages.agents.tools._base import ToolRefusal


def run(ctx: RunContext, *, engagement_id: str | UUID) -> dict[str, Any]:
    target = UUID(str(engagement_id))
    if ctx.engagement_id is None or target != ctx.engagement_id:
        raise ToolRefusal("wrong_engagement")
    services = ctx.services
    fetch = getattr(services, "fetch_engagement_context", None)
    if fetch is None:
        raise ToolRefusal("missing_fetch_engagement")
    row = fetch(engagement_id=target)
    if row is None:
        raise ToolRefusal("engagement_not_found")
    return {
        "id": str(row["id"]),
        "owner_org_id": str(row["owner_org_id"]),
        "site_id": str(row["site_id"]) if row.get("site_id") is not None else None,
        "project_code": row.get("project_code"),
    }
