"""Contractor review queue and human verification."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..core.auth import Principal, get_principal, require_contractor
from ..core.db import org_scoped_session
from ..services import review as review_service
from ..services.review import FieldNotFoundError

router = APIRouter(prefix="/review", tags=["review"])


class ReviewItem(BaseModel):
    document_id: UUID
    filename: str
    field_id: UUID | None
    field_name: str | None
    field_value: str | None
    state: str | None
    is_financial: bool | None


class VerifyFieldInput(BaseModel):
    corrected_value: str | None = None


@router.get("/queue", response_model=list[ReviewItem])
def queue(
    principal: Annotated[Principal, Depends(get_principal)],
) -> list[ReviewItem]:
    require_contractor(principal)
    with org_scoped_session(principal.org_id) as session:
        items = review_service.list_queue(session)
    return [ReviewItem(**item.__dict__) for item in items]


@router.post("/fields/{field_id}/verify")
def verify_field(
    field_id: UUID,
    payload: VerifyFieldInput,
    principal: Annotated[Principal, Depends(get_principal)],
) -> dict[str, str]:
    require_contractor(principal)
    try:
        with org_scoped_session(principal.org_id) as session:
            verified_field_id = review_service.verify_field(
                session,
                field_id=field_id,
                user_id=principal.user_id,
                corrected_value=payload.corrected_value,
                corrected_value_provided="corrected_value" in payload.model_fields_set,
            )
    except FieldNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "field not found", "code": "not_found"},
        ) from exc

    return {"status": "verified", "field_id": str(verified_field_id)}
