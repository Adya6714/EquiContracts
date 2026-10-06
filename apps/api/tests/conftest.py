"""Database fixtures exercise RLS as the application role."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from apps.api.app.core.db import (
    AdminSessionFactory,
    AppSessionFactory,
)


@dataclass(frozen=True)
class AccessFixture:
    contractor_a: UUID
    contractor_b: UUID
    client: UUID
    pmc: UUID
    user_a: UUID
    site_id: UUID
    project_a: UUID  # engagement A (JSON/API still say project)
    project_b: UUID  # engagement B
    document_a: UUID
    verified_field: UUID
    review_field: UUID


def admin_insert_event(
    *,
    org_id: UUID,
    event_type: str,
    idempotency_key: str,
    engagement_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
    caused_by_event_id: UUID | None = None,
    chain_depth: int = 0,
) -> UUID:
    """Insert an event as admin (bypasses app-role root-event INSERT policy)."""
    admin = AdminSessionFactory()
    try:
        event_id = admin.execute(
            text(
                """
                INSERT INTO event (
                  org_id, engagement_id, event_type, idempotency_key, payload,
                  caused_by_event_id, chain_depth
                ) VALUES (
                  :org, :eng, :etype, :key, CAST(:payload AS jsonb),
                  :caused_by, :depth
                )
                RETURNING id
                """
            ),
            {
                "org": org_id,
                "eng": engagement_id,
                "etype": event_type,
                "key": idempotency_key,
                "payload": json.dumps(payload or {}),
                "caused_by": caused_by_event_id,
                "depth": chain_depth,
            },
        ).scalar_one()
        admin.commit()
        return UUID(str(event_id))
    finally:
        admin.close()


@pytest.fixture()
def access_data() -> Iterator[AccessFixture]:
    ids = [uuid4() for _ in range(11)]
    data = AccessFixture(*ids)
    suffix = uuid4().hex[:10]

    admin = AdminSessionFactory()
    try:
        admin.execute(
            text(
                """
                INSERT INTO org (id, name, org_type) VALUES
                  (:contractor_a, 'Contractor A', 'contractor'),
                  (:contractor_b, 'Contractor B', 'contractor'),
                  (:client, 'Client', 'client'),
                  (:pmc, 'PMC', 'pmc')
                """
            ),
            data.__dict__,
        )
        admin.execute(
            text(
                """
                INSERT INTO app_user (id, org_id, email, role)
                VALUES (:user_a, :contractor_a, :email, 'contractor_admin')
                """
            ),
            {
                **data.__dict__,
                "email": f"contractor-{suffix}@example.invalid",
            },
        )
        admin.execute(
            text(
                """
                INSERT INTO site (id, owner_org_id, name, city)
                VALUES (:site_id, :client, 'Fixture Site', 'Mumbai')
                """
            ),
            data.__dict__,
        )
        admin.execute(
            text(
                """
                INSERT INTO site_member (site_id, org_id, role)
                VALUES
                  (:site_id, :client, 'client'),
                  (:site_id, :pmc, 'pmc')
                """
            ),
            data.__dict__,
        )
        admin.execute(
            text(
                """
                INSERT INTO engagement (
                  id, owner_org_id, site_id, name, project_code, inbound_alias
                ) VALUES
                  (
                    :project_a, :contractor_a, :site_id, 'A Project',
                    :code_a, :alias_a
                  ),
                  (
                    :project_b, :contractor_b, :site_id, 'B Project',
                    :code_b, :alias_b
                  )
                """
            ),
            {
                **data.__dict__,
                "code_a": f"EC-TST-{suffix[:3]}A",
                "code_b": f"EC-TST-{suffix[:3]}B",
                "alias_a": f"ectst{suffix[:3]}a",
                "alias_b": f"ectst{suffix[:3]}b",
            },
        )
        admin.execute(
            text(
                """
                INSERT INTO document (
                  id, engagement_id, filename, storage_uri, sha256, source
                )
                VALUES (
                  :document_a, :project_a, 'fixture.pdf',
                  's3://equicontracts-documents/fixture',
                  :sha256, 'manual_upload'
                )
                """
            ),
            {**data.__dict__, "sha256": "a" * 64},
        )
        admin.execute(
            text(
                """
                INSERT INTO extracted_field (
                  id, document_id, field_name, field_value, state,
                  is_financial, verified_at
                ) VALUES
                  (
                    :verified_field, :document_a, 'completion_date',
                    '2026-08-12', 'verified', false, now()
                  ),
                  (
                    :review_field, :document_a, 'bg_value',
                    '17080000.00', 'needs_review', true, NULL
                  )
                """
            ),
            data.__dict__,
        )
        admin.commit()
        yield data
    finally:
        admin.rollback()
        # Agent foundation rows may reference engagement; clear before delete.
        admin.execute(
            text(
                """
                DELETE FROM review_decision
                WHERE org_id IN (:a, :b)
                """
            ),
            {"a": data.contractor_a, "b": data.contractor_b},
        )
        admin.execute(
            text(
                """
                DELETE FROM agent_proposal
                WHERE org_id IN (:a, :b)
                """
            ),
            {"a": data.contractor_a, "b": data.contractor_b},
        )
        admin.execute(
            text(
                """
                DELETE FROM agent_step
                WHERE org_id IN (:a, :b)
                """
            ),
            {"a": data.contractor_a, "b": data.contractor_b},
        )
        admin.execute(
            text(
                """
                DELETE FROM agent_run
                WHERE org_id IN (:a, :b)
                """
            ),
            {"a": data.contractor_a, "b": data.contractor_b},
        )
        admin.execute(
            text("DELETE FROM event WHERE org_id IN (:a, :b)"),
            {"a": data.contractor_a, "b": data.contractor_b},
        )
        admin.execute(
            text("DELETE FROM engagement WHERE id IN (:a, :b)"),
            {"a": data.project_a, "b": data.project_b},
        )
        admin.execute(
            text("DELETE FROM site WHERE id = :site_id"),
            {"site_id": data.site_id},
        )
        admin.execute(
            text("DELETE FROM app_user WHERE id = :user_a"),
            {"user_a": data.user_a},
        )
        admin.execute(
            text("DELETE FROM org WHERE id IN (:a, :b, :client, :pmc)"),
            {
                "a": data.contractor_a,
                "b": data.contractor_b,
                "client": data.client,
                "pmc": data.pmc,
            },
        )
        admin.commit()
        admin.close()


@pytest.fixture()
def unscoped_app_session() -> Iterator[object]:
    session = AppSessionFactory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
