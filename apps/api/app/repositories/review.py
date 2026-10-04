"""SQL for contractor review queue and field verification."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_queue_rows(session: Session) -> list[dict[str, Any]]:
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
    return [dict(row) for row in rows]


def lock_field_for_verify(session: Session, *, field_id: UUID) -> dict[str, Any] | None:
    row = (
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
    return dict(row) if row is not None else None


def insert_verified_correction(
    session: Session,
    *,
    document_id: UUID,
    field_name: str,
    field_value: str | None,
    is_financial: bool,
    confidence: Any,
    model_version: str | None,
    verified_by: UUID,
) -> UUID:
    new_id = session.execute(
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
            "document_id": document_id,
            "field_name": field_name,
            "field_value": field_value,
            "is_financial": is_financial,
            "confidence": confidence,
            "model_version": model_version,
            "verified_by": verified_by,
        },
    ).scalar_one()
    return UUID(str(new_id))


def mark_superseded(session: Session, *, old_id: UUID, new_id: UUID) -> None:
    session.execute(
        text(
            """
            UPDATE extracted_field
            SET superseded_by = :new_id
            WHERE id = :old_id
            """
        ),
        {"new_id": new_id, "old_id": old_id},
    )


def mark_verified_in_place(
    session: Session, *, field_id: UUID, verified_by: UUID
) -> None:
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
        {"verified_by": verified_by, "field_id": field_id},
    )
