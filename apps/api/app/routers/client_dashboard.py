"""Read-only client/PMC projection of verified data."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from ..core.auth import Principal, get_principal
from ..core.db import org_scoped_session

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
        rows = (
            session.execute(
                text(
                    """
                    SELECT
                      p.id,
                      p.name,
                      p.project_code,
                      count(ef.id)::integer AS verified_field_count
                    FROM project p
                    LEFT JOIN document d ON d.project_id = p.id
                    LEFT JOIN extracted_field ef
                      ON ef.document_id = d.id
                     AND ef.state = 'verified'
                     AND ef.superseded_by IS NULL
                    GROUP BY p.id, p.name, p.project_code
                    ORDER BY p.name
                    """
                )
            )
            .mappings()
            .all()
        )
    return [ProjectSummary(**row) for row in rows]
