"""Business logic for contractor project setup and modules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.project_code import (
    display_inbound_address,
    generate_project_code,
    inbound_alias_for,
)
from ..repositories import projects as projects_repo


class ProjectConflictError(Exception):
    """Project create failed on integrity or invalid value in the write path."""


class ProjectNotFoundError(Exception):
    """Module write affected zero rows under the caller's org scope."""


@dataclass(frozen=True)
class ProjectResult:
    id: UUID
    name: str
    project_code: str
    inbound_email: str


@dataclass(frozen=True)
class ParticipantSpec:
    org_id: UUID
    role: str


@dataclass(frozen=True)
class WorkOrderSpec:
    wo_number: str
    trade: str | None
    value: Decimal | None
    certification_sla_days: int | None


def create_project(
    session: Session,
    *,
    owner_org_id: UUID,
    name: str,
    city_code: str,
    participants: list[ParticipantSpec],
    work_orders: list[WorkOrderSpec],
    modules: list[str],
) -> ProjectResult:
    # City-code validation errors propagate (same as when this ran before the DB try).
    project_code = generate_project_code(city_code)
    inbound_alias = inbound_alias_for(project_code, name)
    inbound_email = display_inbound_address(inbound_alias)

    try:
        row = projects_repo.insert_project(
            session,
            owner_org_id=owner_org_id,
            name=name,
            project_code=project_code,
            inbound_alias=inbound_alias,
        )
        project_id = row["id"]
        for participant in participants:
            projects_repo.insert_participant(
                session,
                project_id=project_id,
                org_id=participant.org_id,
                role=participant.role,
            )
        for work_order in work_orders:
            projects_repo.insert_work_order(
                session,
                project_id=project_id,
                wo_number=work_order.wo_number,
                trade=work_order.trade,
                value=work_order.value,
                certification_sla_days=work_order.certification_sla_days,
            )
        for module_name in set(modules):
            projects_repo.insert_module(
                session,
                project_id=project_id,
                module_name=module_name,
            )
    except (IntegrityError, ValueError) as exc:
        raise ProjectConflictError from exc

    return ProjectResult(
        id=row["id"],
        name=row["name"],
        project_code=row["project_code"],
        inbound_email=inbound_email,
    )


def list_projects(session: Session) -> list[ProjectResult]:
    rows = projects_repo.list_owned_projects(session)
    return [
        ProjectResult(
            id=row["id"],
            name=row["name"],
            project_code=row["project_code"],
            inbound_email=display_inbound_address(row["inbound_alias"]),
        )
        for row in rows
    ]


def toggle_module(
    session: Session,
    *,
    project_id: UUID,
    module_name: str,
    enabled: bool,
) -> None:
    rowcount = projects_repo.upsert_module(
        session,
        project_id=project_id,
        module_name=module_name,
        enabled=enabled,
    )
    if rowcount == 0:
        raise ProjectNotFoundError
