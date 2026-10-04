"""Read-only client/PMC projection of verified data."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..core.auth import Principal, get_principal
from ..core.db import org_scoped_session
from ..services import client_dashboard as client_dashboard_service

router = APIRouter(prefix="/client", tags=["client"])


class ProjectSummary(BaseModel):
    id: UUID
    name: str
    project_code: str
    verified_field_count: int


@router.get("/dashboard", response_model=list[ProjectSummary])
def overview(
    principal: Annotated[Principal, Depends(get_principal)],
) -> list[ProjectSummary]:
    if principal.org_type not in ("client", "pmc"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "client or PMC access required", "code": "forbidden"},
        )

    with org_scoped_session(principal.org_id) as session:
        rows = client_dashboard_service.list_project_summaries(session)
    return [
        ProjectSummary(
            id=row.id,
            name=row.name,
            project_code=row.project_code,
            verified_field_count=row.verified_field_count,
        )
        for row in rows
    ]
