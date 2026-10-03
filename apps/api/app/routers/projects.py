"""Contractor-owned project setup and module management."""

from decimal import Decimal
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from ..core.auth import Principal, get_principal, require_contractor, require_roles
from ..core.db import org_scoped_session
from ..core.project_code import (
    display_inbound_address,
    generate_project_code,
    inbound_alias_for,
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
    project_code = generate_project_code(payload.city_code)
    inbound_alias = inbound_alias_for(project_code, payload.name)
    inbound_email = display_inbound_address(inbound_alias)

    try:
        with org_scoped_session(principal.org_id) as session:
            row = (
                session.execute(
                    text(
                        """
                        INSERT INTO project (
                          owner_org_id, name, project_code, inbound_alias
                        )
                        VALUES (
                          :owner_org_id, :name, :project_code, :inbound_alias
                        )
                        RETURNING id, name, project_code, inbound_alias
                        """
                    ),
                    {
                        "owner_org_id": principal.org_id,
                        "name": payload.name,
                        "project_code": project_code,
                        "inbound_alias": inbound_alias,
                    },
                )
                .mappings()
                .one()
            )
            project_id = row["id"]
            for participant in payload.participants:
                session.execute(
                    text(
                        """
                        INSERT INTO project_participant (project_id, org_id, role)
                        VALUES (:project_id, :org_id, :role)
                        """
                    ),
                    {
                        "project_id": project_id,
                        "org_id": participant.org_id,
                        "role": participant.role,
                    },
                )
            for work_order in payload.work_orders:
                session.execute(
                    text(
                        """
                        INSERT INTO work_order (
                          project_id, wo_number, trade, value,
                          certification_sla_days
                        )
                        VALUES (
                          :project_id, :wo_number, :trade, :value,
                          :certification_sla_days
                        )
                        """
                    ),
                    {
                        "project_id": project_id,
                        **work_order.model_dump(),
                    },
                )
            for module_name in set(payload.modules):
                session.execute(
                    text(
                        """
                        INSERT INTO project_module (project_id, module_name)
                        VALUES (:project_id, :module_name)
                        """
                    ),
                    {"project_id": project_id, "module_name": module_name},
                )
    except (IntegrityError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "project could not be created", "code": "conflict"},
        ) from exc

    return ProjectOutput(
        id=row["id"],
        name=row["name"],
        project_code=row["project_code"],
        inbound_email=inbound_email,
    )


@router.get("", response_model=list[ProjectOutput])
def list_projects(
    principal: Annotated[Principal, Depends(get_principal)],
) -> list[ProjectOutput]:
    require_contractor(principal)
    with org_scoped_session(principal.org_id) as session:
        rows = (
            session.execute(
                text(
                    """
                    SELECT id, name, project_code, inbound_alias
                    FROM project
                    ORDER BY created_at DESC
                    """
                )
            )
            .mappings()
            .all()
        )
    return [
        ProjectOutput(
            id=row["id"],
            name=row["name"],
            project_code=row["project_code"],
            inbound_email=display_inbound_address(row["inbound_alias"]),
        )
        for row in rows
    ]


@router.patch("/{project_id}/modules", status_code=status.HTTP_204_NO_CONTENT)
def toggle_module(
    project_id: UUID,
    payload: ModuleUpdate,
    principal: Annotated[Principal, Depends(get_principal)],
) -> None:
    require_contractor(principal)
    require_roles(principal, "contractor_admin")
    with org_scoped_session(principal.org_id) as session:
        result = cast(
            CursorResult[Any],
            session.execute(
                text(
                    """
                    INSERT INTO project_module (project_id, module_name, enabled)
                    VALUES (:project_id, :module_name, :enabled)
                    ON CONFLICT (project_id, module_name)
                    DO UPDATE SET enabled = EXCLUDED.enabled
                    """
                ),
                {
                    "project_id": project_id,
                    "module_name": payload.module_name,
                    "enabled": payload.enabled,
                },
            ),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
