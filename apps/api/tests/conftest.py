"""Database fixtures exercise RLS as the application role."""

from collections.abc import Iterator
from dataclasses import dataclass
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
    project_a: UUID
    project_b: UUID
    document_a: UUID
    verified_field: UUID
    review_field: UUID


@pytest.fixture()
def access_data() -> Iterator[AccessFixture]:
    ids = [uuid4() for _ in range(10)]
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
                INSERT INTO project (
                  id, owner_org_id, name, project_code, inbound_alias
                ) VALUES
                  (
                    :project_a, :contractor_a, 'A Project',
                    :code_a, :alias_a
                  ),
                  (
                    :project_b, :contractor_b, 'B Project',
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
                INSERT INTO project_participant (project_id, org_id, role)
                VALUES
                  (:project_a, :client, 'client'),
                  (:project_a, :pmc, 'pmc'),
                  (:project_b, :client, 'client')
                """
            ),
            data.__dict__,
        )
        admin.execute(
            text(
                """
                INSERT INTO document (
                  id, project_id, filename, storage_uri, sha256, source
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
        admin.execute(
            text("DELETE FROM project WHERE id IN (:a, :b)"),
            {"a": data.project_a, "b": data.project_b},
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
