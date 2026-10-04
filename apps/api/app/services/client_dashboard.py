"""Business logic for client/PMC verified-only dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from ..repositories import client_dashboard as client_dashboard_repo


@dataclass(frozen=True)
class ProjectSummaryResult:
    id: UUID
    name: str
    project_code: str
    verified_field_count: int


def list_project_summaries(session: Session) -> list[ProjectSummaryResult]:
    rows = client_dashboard_repo.list_verified_project_summaries(session)
    return [ProjectSummaryResult(**row) for row in rows]
