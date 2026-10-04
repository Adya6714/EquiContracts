"""Contractor-owned project setup and module management."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..core.auth import Principal, get_principal, require_contractor, require_roles
from ..core.db import org_scoped_session
from ..services import projects as projects_service
from ..services.projects import (
    ParticipantSpec,
    ProjectConflictError,
    ProjectNotFoundError,
    WorkOrderSpec,
)

router = APIRouter(prefix="/projects", tags=["projects"])

ModuleName = Literal[
    "bg_verify",
    "milestone_validator",
    "payment_mismatch",
    "evidence_locker",
    "resolution_statement",
]


class ParticipantInput(BaseModel):
    org_id: UUID
    role: Literal["client", "pmc"]


class WorkOrderInput(BaseModel):
    wo_number: str = Field(min_length=1, max_length=120)
    trade: str | None = Field(default=None, max_length=120)
    value: Decimal | None = Field(default=None, ge=0)
    certification_sla_days: int | None = Field(default=None, gt=0)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    city_code: str = Field(min_length=3, max_length=3)
    participants: list[ParticipantInput] = Field(default_factory=list)
    work_orders: list[WorkOrderInput] = Field(default_factory=list)
    modules: list[ModuleName] = Field(default_factory=list)


class ProjectOutput(BaseModel):
    id: UUID
    name: str
    project_code: str
    inbound_email: str


class ModuleUpdate(BaseModel):
    module_name: ModuleName
    enabled: bool


@router.post("", response_model=ProjectOutput, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    principal: Annotated[Principal, Depends(get_principal)],
) -> ProjectOutput:
    require_contractor(principal)
    require_roles(principal, "contractor_admin")
    try:
        with org_scoped_session(principal.org_id) as session:
            result = projects_service.create_project(
                session,
                owner_org_id=principal.org_id,
                name=payload.name,
                city_code=payload.city_code,
                participants=[
                    ParticipantSpec(org_id=item.org_id, role=item.role)
                    for item in payload.participants
                ],
                work_orders=[
                    WorkOrderSpec(
                        wo_number=item.wo_number,
                        trade=item.trade,
                        value=item.value,
                        certification_sla_days=item.certification_sla_days,
                    )
                    for item in payload.work_orders
                ],
                modules=list(payload.modules),
            )
    except ProjectConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "project could not be created", "code": "conflict"},
        ) from exc

    return ProjectOutput(
        id=result.id,
        name=result.name,
        project_code=result.project_code,
        inbound_email=result.inbound_email,
    )


@router.get("", response_model=list[ProjectOutput])
def list_projects(
    principal: Annotated[Principal, Depends(get_principal)],
) -> list[ProjectOutput]:
    require_contractor(principal)
    with org_scoped_session(principal.org_id) as session:
        results = projects_service.list_projects(session)
    return [
        ProjectOutput(
            id=item.id,
            name=item.name,
            project_code=item.project_code,
            inbound_email=item.inbound_email,
        )
        for item in results
    ]


@router.patch("/{project_id}/modules", status_code=status.HTTP_204_NO_CONTENT)
def toggle_module(
    project_id: UUID,
    payload: ModuleUpdate,
    principal: Annotated[Principal, Depends(get_principal)],
) -> None:
    require_contractor(principal)
    require_roles(principal, "contractor_admin")
    try:
        with org_scoped_session(principal.org_id) as session:
            projects_service.toggle_module(
                session,
                project_id=project_id,
                module_name=payload.module_name,
                enabled=payload.enabled,
            )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
