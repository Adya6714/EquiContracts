"""SQL for client/PMC verified-only dashboard projection."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_verified_project_summaries(session: Session) -> list[dict[str, Any]]:
    """Count only verified, current extracted_field rows (never unverified)."""

    rows = (
        session.execute(
            text(
                """
                SELECT
                  e.id,
                  e.name,
                  e.project_code,
                  count(ef.id)::integer AS verified_field_count
                FROM engagement e
                LEFT JOIN document d ON d.engagement_id = e.id
                LEFT JOIN extracted_field ef
                  ON ef.document_id = d.id
                 AND ef.state = 'verified'
                 AND ef.superseded_by IS NULL
                GROUP BY e.id, e.name, e.project_code
                ORDER BY e.name
                """
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]
