"""SQL access for contractor engagements.

HTTP/JSON still say "project"; this repository talks to `engagement` /
`engagement_module` and maps columns to the existing JSON names.
Session is always caller-supplied.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session


def insert_project(
    session: Session,
    *,
    owner_org_id: UUID,
    name: str,
    project_code: str,
    inbound_alias: str,
) -> dict[str, Any]:
    row = (
        session.execute(
            text(
                """
                INSERT INTO engagement (
                  owner_org_id, name, project_code, inbound_alias
                )
                VALUES (
                  :owner_org_id, :name, :project_code, :inbound_alias
                )
                RETURNING id, name, project_code, inbound_alias
                """
            ),
            {
                "owner_org_id": owner_org_id,
                "name": name,
                "project_code": project_code,
                "inbound_alias": inbound_alias,
            },
        )
        .mappings()
        .one()
    )
    return dict(row)


def insert_work_order(
    session: Session,
    *,
    project_id: UUID,
    wo_number: str,
    trade: str | None,
    value: Decimal | None,
    certification_sla_days: int | None,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO work_order (
              engagement_id, wo_number, trade, value,
              certification_sla_days
            )
            VALUES (
              :engagement_id, :wo_number, :trade, :value,
              :certification_sla_days
            )
            """
        ),
        {
            "engagement_id": project_id,
            "wo_number": wo_number,
            "trade": trade,
            "value": value,
            "certification_sla_days": certification_sla_days,
        },
    )


def insert_module(
    session: Session,
    *,
    project_id: UUID,
    module_name: str,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO engagement_module (engagement_id, module_name)
            VALUES (:engagement_id, :module_name)
            """
        ),
        {"engagement_id": project_id, "module_name": module_name},
    )


def list_owned_projects(session: Session) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            text(
                """
                SELECT id, name, project_code, inbound_alias
                FROM engagement
                ORDER BY created_at DESC
                """
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def upsert_module(
    session: Session,
    *,
    project_id: UUID,
    module_name: str,
    enabled: bool,
) -> int:
    result = cast(
        CursorResult[Any],
        session.execute(
            text(
                """
                INSERT INTO engagement_module (
                  engagement_id, module_name, enabled
                )
                VALUES (:engagement_id, :module_name, :enabled)
                ON CONFLICT (engagement_id, module_name)
                DO UPDATE SET enabled = EXCLUDED.enabled
                """
            ),
            {
                "engagement_id": project_id,
                "module_name": module_name,
                "enabled": enabled,
            },
        ),
    )
    return int(result.rowcount or 0)
