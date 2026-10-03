"""Contractor review queue and human verification."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from ..core.auth import Principal, get_principal, require_contractor
from ..core.db import org_scoped_session
from ..core.event_log import append_event

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
        rows = (
            session.execute(
                text(
                    """
                    SELECT
                      d.id AS document_id,
                      d.filename,
                      ef.id AS field_id,
                      ef.field_name,
                      ef.field_value,
                      ef.state,
                      ef.is_financial
                    FROM document d
                    LEFT JOIN extracted_field ef
                      ON ef.document_id = d.id
                     AND ef.superseded_by IS NULL
                     AND ef.state <> 'verified'
                    WHERE ef.id IS NOT NULL
                       OR NOT EXISTS (
                         SELECT 1 FROM extracted_field existing
                         WHERE existing.document_id = d.id
                       )
                    ORDER BY d.received_at DESC, ef.created_at
                    """
                )
            )
            .mappings()
            .all()
        )
    return [ReviewItem(**row) for row in rows]


@router.post("/fields/{field_id}/verify")
def verify_field(
    field_id: UUID,
    payload: VerifyFieldInput,
    principal: Annotated[Principal, Depends(get_principal)],
) -> dict[str, str]:
    require_contractor(principal)
    with org_scoped_session(principal.org_id) as session:
        field = (
            session.execute(
                text(
                    """
                    SELECT
                      ef.id, ef.document_id, ef.field_name, ef.field_value,
                      ef.is_financial, ef.confidence, ef.model_version,
                      d.project_id
                    FROM extracted_field ef
                    JOIN document d ON d.id = ef.document_id
                    WHERE ef.id = :field_id
                      AND ef.superseded_by IS NULL
                    FOR UPDATE
                    """
                ),
                {"field_id": field_id},
            )
            .mappings()
            .one_or_none()
        )
        if field is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": "field not found", "code": "not_found"},
            )

        value_changed = (
            "corrected_value" in payload.model_fields_set
            and payload.corrected_value != field["field_value"]
        )
        verified_field_id = field_id
        if value_changed:
            verified_field_id = session.execute(
                text(
                    """
                    INSERT INTO extracted_field (
                      document_id, field_name, field_value, state, is_financial,
                      confidence, model_version, verified_by, verified_at
                    )
                    VALUES (
                      :document_id, :field_name, :field_value, 'verified',
                      :is_financial, :confidence, :model_version,
                      :verified_by, now()
                    )
                    RETURNING id
                    """
                ),
                {
                    "document_id": field["document_id"],
                    "field_name": field["field_name"],
                    "field_value": payload.corrected_value,
                    "is_financial": field["is_financial"],
                    "confidence": field["confidence"],
                    "model_version": field["model_version"],
                    "verified_by": principal.user_id,
                },
            ).scalar_one()
            session.execute(
                text(
                    """
                    UPDATE extracted_field
                    SET superseded_by = :new_id
                    WHERE id = :old_id
                    """
                ),
                {"new_id": verified_field_id, "old_id": field_id},
            )
        else:
            session.execute(
                text(
                    """
                    UPDATE extracted_field
                    SET state = 'verified',
                        verified_by = :verified_by,
                        verified_at = now()
                    WHERE id = :field_id
                    """
                ),
                {"verified_by": principal.user_id, "field_id": field_id},
            )

        append_event(
            session,
            project_id=field["project_id"],
            event_type="field_verified",
            actor_user_id=principal.user_id,
            entity_type="extracted_field",
            entity_id=verified_field_id,
            metadata={"corrected": str(value_changed).lower()},
        )

    return {"status": "verified", "field_id": str(verified_field_id)}
