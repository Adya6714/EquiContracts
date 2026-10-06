"""Existential tenancy tests for contractor/client/PMC access."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from apps.api.app.core.db import (
    AdminSessionFactory,
    AppSessionFactory,
    SystemSessionFactory,
    org_scoped_session,
)


def test_contractor_sees_only_own_projects(access_data) -> None:
    with org_scoped_session(access_data.contractor_a) as session:
        ids = set(session.execute(text("SELECT id FROM engagement")).scalars())
    assert ids == {access_data.project_a}


def test_contractor_cannot_see_rival_on_shared_site(access_data) -> None:
    with org_scoped_session(access_data.contractor_b) as session:
        visible = session.execute(
            text("SELECT id FROM engagement WHERE id = :id"),
            {"id": access_data.project_a},
        ).scalar_one_or_none()
        docs = session.execute(
            text("SELECT id FROM document WHERE id = :id"),
            {"id": access_data.document_a},
        ).scalar_one_or_none()
    assert visible is None
    assert docs is None


def test_client_sees_participant_projects(access_data) -> None:
    with org_scoped_session(access_data.client) as session:
        ids = set(session.execute(text("SELECT id FROM engagement")).scalars())
    assert ids == {access_data.project_a, access_data.project_b}


def test_client_cannot_write_project_data(access_data) -> None:
    # No app UPDATE grants on engagement; client write is privilege-denied.
    with (
        org_scoped_session(access_data.client) as session,
        pytest.raises((ProgrammingError, DBAPIError)),
    ):
        session.execute(
            text("UPDATE engagement SET name = 'changed' WHERE id = :id"),
            {"id": access_data.project_a},
        )
        session.flush()


def test_client_participant_can_read_but_not_write_document(access_data) -> None:
    """Client site_member must see documents; writes stay owner-only / revoked."""
    with org_scoped_session(access_data.client) as session:
        document_id = session.execute(
            text("SELECT id FROM document WHERE id = :id"),
            {"id": access_data.document_a},
        ).scalar_one_or_none()
    assert document_id == access_data.document_a
    # filename has no UPDATE grant (0011); privilege denied for any app caller.
    with (
        org_scoped_session(access_data.client) as session,
        pytest.raises((ProgrammingError, DBAPIError)),
    ):
        session.execute(
            text("UPDATE document SET filename = 'hijacked.pdf' WHERE id = :id"),
            {"id": access_data.document_a},
        )
        session.flush()
    # received_at is granted but RLS still blocks non-owners.
    with org_scoped_session(access_data.client) as session:
        update_result = session.execute(
            text("UPDATE document SET received_at = now() WHERE id = :id"),
            {"id": access_data.document_a},
        )
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
        project_ids = set(session.execute(text("SELECT id FROM engagement")).scalars())
        field_ids = set(
            session.execute(text("SELECT id FROM extracted_field")).scalars()
        )
    assert project_ids == {access_data.project_a, access_data.project_b}
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
        count = session.execute(text("SELECT count(*) FROM engagement")).scalar_one()
    finally:
        session.rollback()
        session.close()
    assert count == 0


def test_rls_enabled_and_forced_on_every_tenant_table() -> None:
    expected = {
        "org",
        "app_user",
        "site",
        "site_member",
        "engagement",
        "engagement_module",
        "document",
        "document_classification",
        "extracted_field",
        "event_log",
        "inbound_quarantine",
        "work_order",
        "annexure_requirement",
        "proforma_invoice",
        "annexure_submission",
        "bank_guarantee",
        "bg_event",
        "event",
        "agent_run",
        "agent_step",
        "agent_proposal",
        "review_decision",
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


def test_no_policy_uses_for_all_command() -> None:
    """Policy inventory: fail if any policy still has cmd = ALL."""
    session = AdminSessionFactory()
    try:
        rows = session.execute(
            text(
                """
                SELECT schemaname, tablename, policyname, cmd
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND cmd = 'ALL'
                ORDER BY tablename, policyname
                """
            )
        ).all()
    finally:
        session.close()
    assert rows == []


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


def test_two_contractors_on_one_site_cannot_see_each_other(access_data) -> None:
    with org_scoped_session(access_data.contractor_a) as session:
        rival_engagement = session.execute(
            text("SELECT id FROM engagement WHERE id = :id"),
            {"id": access_data.project_b},
        ).scalar_one_or_none()
        rival_docs = set(session.execute(text("SELECT id FROM document")).scalars())
    assert rival_engagement is None
    assert rival_docs == {access_data.document_a}


def test_client_sees_both_engagements_on_site(access_data) -> None:
    with org_scoped_session(access_data.client) as session:
        ids = set(session.execute(text("SELECT id FROM engagement")).scalars())
    assert ids == {access_data.project_a, access_data.project_b}


def test_client_cannot_mutate_engagement_document_or_site_member(access_data) -> None:
    with org_scoped_session(access_data.client) as session:
        eng = session.execute(
            text("DELETE FROM engagement WHERE id = :id"),
            {"id": access_data.project_a},
        )
        doc = session.execute(
            text("DELETE FROM document WHERE id = :id"),
            {"id": access_data.document_a},
        )
        # site_member has SELECT only for app — write is refused by privilege.
        with pytest.raises((ProgrammingError, DBAPIError)):
            session.execute(
                text(
                    """
                    UPDATE site_member
                    SET data_scope = data_scope
                    WHERE site_id = :site_id
                    """
                ),
                {"site_id": access_data.site_id},
            )
            session.flush()
    assert eng.rowcount == 0
    assert doc.rowcount == 0


def test_unlinked_engagement_invisible_to_client_until_linked(access_data) -> None:
    admin = AdminSessionFactory()
    engagement_id = uuid4()
    try:
        admin.execute(
            text(
                """
                INSERT INTO engagement (
                  id, owner_org_id, site_id, name, project_code, inbound_alias
                ) VALUES (
                  :id, :owner, NULL, 'Unlinked', :code, :alias
                )
                """
            ),
            {
                "id": engagement_id,
                "owner": access_data.contractor_a,
                "code": f"EC-UNL-{uuid4().hex[:6]}",
                "alias": f"unl{uuid4().hex[:8]}",
            },
        )
        admin.commit()

        with org_scoped_session(access_data.client) as session:
            before = session.execute(
                text("SELECT id FROM engagement WHERE id = :id"),
                {"id": engagement_id},
            ).scalar_one_or_none()
        assert before is None

        admin.execute(
            text("SELECT link_engagement_to_site(:engagement_id, :site_id)"),
            {
                "engagement_id": engagement_id,
                "site_id": access_data.site_id,
            },
        )
        admin.commit()

        with org_scoped_session(access_data.client) as session:
            after = session.execute(
                text("SELECT id FROM engagement WHERE id = :id"),
                {"id": engagement_id},
            ).scalar_one_or_none()
        assert after == engagement_id
    finally:
        admin.rollback()
        admin.execute(
            text("DELETE FROM engagement WHERE id = :id"),
            {"id": engagement_id},
        )
        admin.commit()
        admin.close()


def test_link_engagement_refuses_relink_and_app_role_cannot_call(access_data) -> None:
    admin = AdminSessionFactory()
    engagement_id = uuid4()
    try:
        admin.execute(
            text(
                """
                INSERT INTO engagement (
                  id, owner_org_id, site_id, name, project_code, inbound_alias
                ) VALUES (
                  :id, :owner, NULL, 'Link once', :code, :alias
                )
                """
            ),
            {
                "id": engagement_id,
                "owner": access_data.contractor_a,
                "code": f"EC-LNK-{uuid4().hex[:6]}",
                "alias": f"lnk{uuid4().hex[:8]}",
            },
        )
        admin.commit()

        admin.execute(
            text("SELECT link_engagement_to_site(:engagement_id, :site_id)"),
            {
                "engagement_id": engagement_id,
                "site_id": access_data.site_id,
            },
        )
        admin.commit()

        with pytest.raises(DBAPIError):
            admin.execute(
                text("SELECT link_engagement_to_site(:engagement_id, :site_id)"),
                {
                    "engagement_id": engagement_id,
                    "site_id": access_data.site_id,
                },
            )
            admin.flush()
        admin.rollback()

        app = AppSessionFactory()
        try:
            with pytest.raises((ProgrammingError, DBAPIError)):
                app.execute(
                    text("SELECT link_engagement_to_site(:engagement_id, :site_id)"),
                    {
                        "engagement_id": engagement_id,
                        "site_id": access_data.site_id,
                    },
                )
                app.flush()
        finally:
            app.rollback()
            app.close()
    finally:
        admin.rollback()
        admin.execute(
            text("DELETE FROM engagement WHERE id = :id"),
            {"id": engagement_id},
        )
        admin.commit()
        admin.close()


def test_contractor_org_cannot_be_site_member(access_data) -> None:
    session = AdminSessionFactory()
    try:
        with pytest.raises(DBAPIError):
            session.execute(
                text(
                    """
                    INSERT INTO site_member (site_id, org_id, role)
                    VALUES (:site_id, :contractor, 'client')
                    """
                ),
                {
                    "site_id": access_data.site_id,
                    "contractor": access_data.contractor_a,
                },
            )
            session.flush()
    finally:
        session.rollback()
        session.close()


def test_site_owner_must_be_client_org(access_data) -> None:
    session = AdminSessionFactory()
    try:
        with pytest.raises(DBAPIError):
            session.execute(
                text(
                    """
                    INSERT INTO site (owner_org_id, name)
                    VALUES (:owner, 'Bad Site')
                    """
                ),
                {"owner": access_data.contractor_a},
            )
            session.flush()
    finally:
        session.rollback()
        session.close()


def test_inbound_quarantine_app_role_select_permission_denied() -> None:
    """No app grants on quarantine: SELECT is permission denied."""
    admin = AdminSessionFactory()
    payload = "b" * 64
    try:
        admin.execute(
            text(
                """
                INSERT INTO inbound_quarantine (recipient, payload_hash, reason)
                VALUES ('nobody@example.invalid', :payload, 'test_lock')
                """
            ),
            {"payload": payload},
        )
        admin.commit()

        app = AppSessionFactory()
        try:
            with pytest.raises((ProgrammingError, DBAPIError)):
                app.execute(
                    text("SELECT count(*) FROM inbound_quarantine")
                ).scalar_one()
        finally:
            app.rollback()
            app.close()
    finally:
        admin.execute(
            text("DELETE FROM inbound_quarantine WHERE payload_hash = :payload"),
            {"payload": payload},
        )
        admin.commit()
        admin.close()


def test_contractor_insert_engagement_with_site_id_refused(access_data) -> None:
    with (
        org_scoped_session(access_data.contractor_a) as session,
        pytest.raises((ProgrammingError, DBAPIError)),
    ):
        session.execute(
            text(
                """
                INSERT INTO engagement (
                  owner_org_id, site_id, name, project_code, inbound_alias
                ) VALUES (
                  :owner, :site_id, 'Hijack', :code, :alias
                )
                """
            ),
            {
                "owner": access_data.contractor_a,
                "site_id": access_data.site_id,
                "code": f"EC-HIJ-{uuid4().hex[:6]}",
                "alias": f"hij{uuid4().hex[:8]}",
            },
        )
        session.flush()


def test_contractor_update_site_id_refused(access_data) -> None:
    admin = AdminSessionFactory()
    engagement_id = uuid4()
    try:
        admin.execute(
            text(
                """
                INSERT INTO engagement (
                  id, owner_org_id, site_id, name, project_code, inbound_alias
                ) VALUES (
                  :id, :owner, NULL, 'No site yet', :code, :alias
                )
                """
            ),
            {
                "id": engagement_id,
                "owner": access_data.contractor_a,
                "code": f"EC-NOS-{uuid4().hex[:6]}",
                "alias": f"nos{uuid4().hex[:8]}",
            },
        )
        admin.commit()

        with (
            org_scoped_session(access_data.contractor_a) as session,
            pytest.raises((ProgrammingError, DBAPIError)),
        ):
            session.execute(
                text(
                    """
                    UPDATE engagement
                    SET site_id = :site_id
                    WHERE id = :id
                    """
                ),
                {"site_id": access_data.site_id, "id": engagement_id},
            )
            session.flush()
    finally:
        admin.rollback()
        admin.execute(
            text("DELETE FROM engagement WHERE id = :id"),
            {"id": engagement_id},
        )
        admin.commit()
        admin.close()


def test_org_type_cannot_change(access_data) -> None:
    session = AdminSessionFactory()
    try:
        with pytest.raises(DBAPIError):
            session.execute(
                text("UPDATE org SET org_type = 'pmc' WHERE id = :id"),
                {"id": access_data.client},
            )
            session.flush()
    finally:
        session.rollback()
        session.close()


# App code never UPDATEs engagement; keep this list in sync with grants in 0009.
ALLOWED_ENGAGEMENT_UPDATE_COLUMNS: tuple[str, ...] = ()


def test_contractor_cannot_change_owner_org_id(access_data) -> None:
    with (
        org_scoped_session(access_data.contractor_a) as session,
        pytest.raises((ProgrammingError, DBAPIError)),
    ):
        session.execute(
            text(
                """
                UPDATE engagement
                SET owner_org_id = :other
                WHERE id = :id
                """
            ),
            {"other": access_data.contractor_b, "id": access_data.project_a},
        )
        session.flush()


def test_contractor_cannot_change_engagement_id_or_created_at(access_data) -> None:
    with (
        org_scoped_session(access_data.contractor_a) as session,
        pytest.raises((ProgrammingError, DBAPIError)),
    ):
        session.execute(
            text(
                """
                UPDATE engagement
                SET id = :new_id
                WHERE id = :id
                """
            ),
            {"new_id": uuid4(), "id": access_data.project_a},
        )
        session.flush()

    with (
        org_scoped_session(access_data.contractor_a) as session,
        pytest.raises((ProgrammingError, DBAPIError)),
    ):
        session.execute(
            text(
                """
                UPDATE engagement
                SET created_at = now()
                WHERE id = :id
                """
            ),
            {"id": access_data.project_a},
        )
        session.flush()


def test_owner_can_update_each_allowed_engagement_column(access_data) -> None:
    """Each column granted for UPDATE must succeed for the owning contractor."""
    # Empty today: apps/api never UPDATEs engagement. When a column is added to
    # ALLOWED_ENGAGEMENT_UPDATE_COLUMNS and to 0009 GRANT UPDATE, exercise it here.
    assert ALLOWED_ENGAGEMENT_UPDATE_COLUMNS == ()
    for column in ALLOWED_ENGAGEMENT_UPDATE_COLUMNS:
        with org_scoped_session(access_data.contractor_a) as session:
            if column == "name":
                result = session.execute(
                    text(
                        """
                        UPDATE engagement
                        SET name = :value
                        WHERE id = :id
                        """
                    ),
                    {
                        "value": f"renamed-{uuid4().hex[:6]}",
                        "id": access_data.project_a,
                    },
                )
            else:
                raise AssertionError(f"no test path for allowed column {column}")
            assert result.rowcount == 1


def test_system_quarantine_inbound_still_inserts() -> None:
    """Unknown-recipient path: system SECURITY DEFINER insert still works."""
    system = SystemSessionFactory()
    payload = "c" * 64
    recipient = f"unknown-{uuid4().hex[:8]}@example.invalid"
    try:
        system.execute(
            text(
                """
                SELECT quarantine_inbound(
                  :recipient, :payload, 'unknown_recipient'
                )
                """
            ),
            {"recipient": recipient, "payload": payload},
        )
        system.commit()

        admin = AdminSessionFactory()
        try:
            found = admin.execute(
                text(
                    """
                    SELECT count(*) FROM inbound_quarantine
                    WHERE payload_hash = :payload
                    """
                ),
                {"payload": payload},
            ).scalar_one()
        finally:
            admin.execute(
                text("DELETE FROM inbound_quarantine WHERE payload_hash = :payload"),
                {"payload": payload},
            )
            admin.commit()
            admin.close()
        assert found == 1
    finally:
        system.rollback()
        system.close()
