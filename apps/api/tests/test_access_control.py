"""Existential tenancy tests for contractor/client/PMC access."""

from sqlalchemy import text

from apps.api.app.core.db import (
    AdminSessionFactory,
    AppSessionFactory,
    org_scoped_session,
)


def test_contractor_sees_only_own_projects(access_data) -> None:
    with org_scoped_session(access_data.contractor_a) as session:
        ids = set(session.execute(text("SELECT id FROM project")).scalars())
    assert ids == {access_data.project_a}


def test_contractor_cannot_see_rival_on_shared_site(access_data) -> None:
    with org_scoped_session(access_data.contractor_b) as session:
        visible = session.execute(
            text("SELECT id FROM project WHERE id = :id"),
            {"id": access_data.project_a},
        ).scalar_one_or_none()
    assert visible is None


def test_client_sees_participant_projects(access_data) -> None:
    with org_scoped_session(access_data.client) as session:
        ids = set(session.execute(text("SELECT id FROM project")).scalars())
    assert ids == {access_data.project_a, access_data.project_b}


def test_client_cannot_write_project_data(access_data) -> None:
    with org_scoped_session(access_data.client) as session:
        result = session.execute(
            text("UPDATE project SET name = 'changed' WHERE id = :id"),
            {"id": access_data.project_a},
        )
    assert result.rowcount == 0


def test_client_participant_can_read_but_not_write_document(access_data) -> None:
    """Client on project_participant must see documents; writes stay owner-only."""
    with org_scoped_session(access_data.client) as session:
        document_id = session.execute(
            text("SELECT id FROM document WHERE id = :id"),
            {"id": access_data.document_a},
        ).scalar_one_or_none()
        update_result = session.execute(
            text("UPDATE document SET filename = 'hijacked.pdf' WHERE id = :id"),
            {"id": access_data.document_a},
        )
    assert document_id == access_data.document_a
    assert update_result.rowcount == 0


def test_client_sees_only_verified_records(access_data) -> None:
    with org_scoped_session(access_data.client) as session:
        rows = session.execute(
            text(
                """
                SELECT id, state FROM extracted_field
                WHERE document_id = :document_id
                """
            ),
            {"document_id": access_data.document_a},
        ).all()
    assert rows == [(access_data.verified_field, "verified")]


def test_pmc_read_access_matches_client_scope(access_data) -> None:
    with org_scoped_session(access_data.pmc) as session:
        project_ids = set(session.execute(text("SELECT id FROM project")).scalars())
        field_ids = set(
            session.execute(text("SELECT id FROM extracted_field")).scalars()
        )
    assert project_ids == {access_data.project_a}
    assert field_ids == {access_data.verified_field}


def test_direct_uuid_lookup_across_orgs_returns_nothing(access_data) -> None:
    with org_scoped_session(access_data.contractor_b) as session:
        document = session.execute(
            text("SELECT id FROM document WHERE id = :id"),
            {"id": access_data.document_a},
        ).scalar_one_or_none()
    assert document is None


def test_unset_org_id_returns_zero_rows(access_data) -> None:
    session = AppSessionFactory()
    try:
        count = session.execute(text("SELECT count(*) FROM project")).scalar_one()
    finally:
        session.rollback()
        session.close()
    assert count == 0


def test_rls_enabled_and_forced_on_every_tenant_table() -> None:
    expected = {
        "org",
        "app_user",
        "project",
        "project_participant",
        "project_module",
        "document",
        "document_classification",
        "extracted_field",
        "event_log",
        "work_order",
        "annexure_requirement",
        "proforma_invoice",
        "annexure_submission",
        "bank_guarantee",
        "bg_event",
    }
    session = AppSessionFactory()
    try:
        rows = session.execute(
            text(
                """
                SELECT relname
                FROM pg_class
                WHERE relnamespace = 'public'::regnamespace
                  AND relname = ANY(:tables)
                  AND relrowsecurity
                  AND relforcerowsecurity
                """
            ),
            {"tables": list(expected)},
        ).scalars()
        actual = set(rows)
    finally:
        session.rollback()
        session.close()
    assert actual == expected


def test_inbound_system_role_has_no_direct_table_grants() -> None:
    session = AdminSessionFactory()
    try:
        grants = session.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.role_table_grants
                WHERE grantee = 'equicontracts_system'
                  AND table_schema = 'public'
                """
            )
        ).all()
    finally:
        session.close()
    assert grants == []
