"""Phase 0 header auth stub with production invariants preserved."""

from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Header, HTTPException, status

OrgType = Literal["contractor", "client", "pmc", "internal"]
Role = Literal[
    "contractor_admin",
    "contractor_user",
    "client_mgmt",
    "client_pm",
    "pmc_user",
    "ec_admin",
]


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    org_id: UUID
    org_type: OrgType
    role: Role


def get_principal(
    x_user_id: Annotated[UUID, Header()],
    x_org_id: Annotated[UUID, Header()],
    x_org_type: Annotated[OrgType, Header()],
    x_role: Annotated[Role, Header()],
) -> Principal:
    """Resolve identity from trusted dev headers.

    TODO(phase-1): replace with signed-token validation. Route bodies never
    contain org_id, so replacing this stub cannot weaken the tenancy boundary.
    """

    return Principal(
        user_id=x_user_id,
        org_id=x_org_id,
        org_type=x_org_type,
        role=x_role,
    )


def require_roles(principal: Principal, *allowed: Role) -> None:
    if principal.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "role is not permitted", "code": "forbidden"},
        )


def require_contractor(principal: Principal) -> None:
    if principal.org_type != "contractor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "contractor access required", "code": "forbidden"},
        )
