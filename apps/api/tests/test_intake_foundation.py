"""Step 6b Part 1: document types, inbound document.received, follow-up DEFINER."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from apps.api.app.core.db import (
    AdminSessionFactory,
    AgentSessionFactory,
    AppSessionFactory,
    agent_org_scoped_session,
    org_scoped_session,
)
from apps.api.app.services import agent_events as agent_events_service
from apps.api.app.services import inbound as inbound_service
from apps.api.app.workers.follow_ups import create_follow_up_event
from packages.agents.router import agents_for


def _sha() -> str:
    return uuid4().hex + uuid4().hex[:32]


def test_inbound_creates_document_and_received_together(access_data) -> None:
    sha = _sha()
    with org_scoped_session(access_data.contractor_a) as session:
        doc_id = inbound_service.accept_document(
            session,
            org_id=access_data.contractor_a,
            project_id=access_data.project_a,
            filename="bg.pdf",
            storage_uri="s3://equicontracts-documents/bg-test",
            sha256=sha,
            sender_email=None,
            subject="BG attached",
        )
        docs = session.execute(
            text("SELECT count(*) FROM document WHERE id = :id"),
            {"id": doc_id},
        ).scalar_one()
        events = (
            session.execute(
                text(
                    """
                SELECT id, event_type, idempotency_key, chain_depth,
                       caused_by_event_id, payload
                FROM event
                WHERE org_id = :org
                  AND idempotency_key = :key
                """
                ),
                {
                    "org": access_data.contractor_a,
                    "key": f"document.received:{doc_id}",
                },
            )
            .mappings()
            .one()
        )

    assert docs == 1
    assert events["event_type"] == "document.received"
    assert events["chain_depth"] == 0
    assert events["caused_by_event_id"] is None
    assert events["payload"]["document_id"] == str(doc_id)
    assert events["payload"]["source"] == "email_forward"


def test_inbound_same_attachment_twice_one_event(access_data) -> None:
    sha = _sha()
    kwargs = dict(
        org_id=access_data.contractor_a,
        project_id=access_data.project_a,
        filename="bg.pdf",
        storage_uri="s3://equicontracts-documents/bg-dup",
        sha256=sha,
        sender_email=None,
        subject="BG",
    )
    with org_scoped_session(access_data.contractor_a) as session:
        first = inbound_service.accept_document(session, **kwargs)
    with org_scoped_session(access_data.contractor_a) as session:
        second = inbound_service.accept_document(session, **kwargs)
    assert first == second
    with org_scoped_session(access_data.contractor_a) as session:
        count = session.execute(
            text(
                """
                SELECT count(*) FROM event
                WHERE org_id = :org
                  AND event_type = 'document.received'
                  AND payload->>'document_id' = :doc
                """
            ),
            {"org": access_data.contractor_a, "doc": str(first)},
        ).scalar_one()
    assert count == 1


def test_inbound_event_insert_failure_rolls_back_document(access_data) -> None:
    sha = _sha()
    with (
        patch(
            "apps.api.app.services.inbound.agent_events_service.create_event",
            side_effect=RuntimeError("forced_event_failure"),
        ),
        pytest.raises(RuntimeError, match="forced_event_failure"),
        org_scoped_session(access_data.contractor_a) as session,
    ):
        inbound_service.accept_document(
            session,
            org_id=access_data.contractor_a,
            project_id=access_data.project_a,
            filename="roll.pdf",
            storage_uri="s3://equicontracts-documents/roll",
            sha256=sha,
            sender_email=None,
            subject="x",
        )
    with org_scoped_session(access_data.contractor_a) as session:
        found = session.execute(
            text("SELECT count(*) FROM document WHERE sha256 = :sha"),
            {"sha": sha},
        ).scalar_one()
    assert found == 0


def _expect_follow_up_denied(*, org_id, parent_event_id, proposal_id) -> None:
    with (
        agent_org_scoped_session(org_id) as session,
        pytest.raises((DBAPIError, ProgrammingError)),
    ):
        create_follow_up_event(
            session, parent_event_id=parent_event_id, proposal_id=proposal_id
        )


def test_document_received_routes_to_intake() -> None:
    assert agents_for("document.received") == ["intake"]


def _seed_classification_proposal(
    *,
    org_id,
    engagement_id,
    document_id,
    doc_type: str = "bank_guarantee",
    parent_event_type: str = "document.received",
    parent_payload_document_id=None,
    chain_depth: int = 0,
    proposal_type: str = "propose_classification",
    agent_name: str = "intake",
    proposal_document_id=None,
    extra_content: dict | None = None,
):
    from apps.api.tests.conftest import admin_insert_event

    parent_doc = (
        parent_payload_document_id
        if parent_payload_document_id is not None
        else document_id
    )
    proposal_doc = (
        proposal_document_id if proposal_document_id is not None else document_id
    )
    parent_payload = {"document_id": str(parent_doc)}
    # App role may only insert root document.received / test.echo.
    if parent_event_type in ("document.received", "test.echo") and chain_depth == 0:
        with org_scoped_session(org_id) as session:
            parent = agent_events_service.create_event(
                session,
                org_id=org_id,
                event_type=parent_event_type,
                idempotency_key=f"parent-{uuid4().hex}",
                engagement_id=engagement_id,
                payload=parent_payload,
            )
            parent_id = parent["id"]
    else:
        parent_id = admin_insert_event(
            org_id=org_id,
            event_type=parent_event_type,
            idempotency_key=f"parent-{uuid4().hex}",
            engagement_id=engagement_id,
            payload=parent_payload,
            chain_depth=chain_depth,
        )

    with agent_org_scoped_session(org_id) as session:
        run = agent_events_service.start_run(
            session,
            event_id=parent_id,
            org_id=org_id,
            agent_name=agent_name,
            agent_version="0",
            engagement_id=engagement_id,
            attempt=1,
        )
        content = {
            "document_id": str(proposal_doc),
            "doc_type": doc_type,
            "evidence_weight": "core_evidence",
        }
        if extra_content:
            content.update(extra_content)
        proposal_id = agent_events_service.create_proposal(
            session,
            run_id=run.run_id,
            org_id=org_id,
            engagement_id=engagement_id,
            proposal_type=proposal_type,
            content=content,
            autonomy_level=2,
            confidence=Decimal("0.900"),
        )
    return parent_id, proposal_id


def test_create_follow_up_event_works_for_valid_bg_proposal(access_data) -> None:
    parent_id, proposal_id = _seed_classification_proposal(
        org_id=access_data.contractor_a,
        engagement_id=access_data.project_a,
        document_id=access_data.document_a,
    )
    with agent_org_scoped_session(access_data.contractor_a) as session:
        child_id = create_follow_up_event(
            session,
            parent_event_id=parent_id,
            proposal_id=proposal_id,
        )
        child = (
            session.execute(
                text(
                    """
                SELECT event_type, caused_by_event_id, chain_depth,
                       payload, idempotency_key
                FROM event WHERE id = :id
                """
                ),
                {"id": child_id},
            )
            .mappings()
            .one()
        )

    assert child["event_type"] == "document.classified"
    assert child["caused_by_event_id"] == parent_id
    assert child["chain_depth"] == 1
    assert child["payload"] == {
        "document_id": str(access_data.document_a),
        "doc_type": "bank_guarantee",
    }
    assert child["idempotency_key"] == (
        f"document.classified:{access_data.document_a}:bank_guarantee"
    )


def test_create_follow_up_event_refuses_non_allowlisted_transition(
    access_data,
) -> None:
    parent_id, proposal_id = _seed_classification_proposal(
        org_id=access_data.contractor_a,
        engagement_id=access_data.project_a,
        document_id=access_data.document_a,
        parent_event_type="document.classified",
    )
    _expect_follow_up_denied(
        org_id=access_data.contractor_a,
        parent_event_id=parent_id,
        proposal_id=proposal_id,
    )


def test_create_follow_up_event_refuses_non_bg_doc_type(access_data) -> None:
    parent_id, proposal_id = _seed_classification_proposal(
        org_id=access_data.contractor_a,
        engagement_id=access_data.project_a,
        document_id=access_data.document_a,
        doc_type="email",
    )
    _expect_follow_up_denied(
        org_id=access_data.contractor_a,
        parent_event_id=parent_id,
        proposal_id=proposal_id,
    )


def test_create_follow_up_event_refuses_proposal_from_another_run(
    access_data,
) -> None:
    parent_a, _ = _seed_classification_proposal(
        org_id=access_data.contractor_a,
        engagement_id=access_data.project_a,
        document_id=access_data.document_a,
    )
    _parent_b, proposal_b = _seed_classification_proposal(
        org_id=access_data.contractor_a,
        engagement_id=access_data.project_a,
        document_id=access_data.document_a,
    )
    _expect_follow_up_denied(
        org_id=access_data.contractor_a,
        parent_event_id=parent_a,
        proposal_id=proposal_b,
    )


def test_create_follow_up_event_refuses_other_org_proposal(access_data) -> None:
    parent_a, _ = _seed_classification_proposal(
        org_id=access_data.contractor_a,
        engagement_id=access_data.project_a,
        document_id=access_data.document_a,
    )
    # Org B document + proposal
    admin = AdminSessionFactory()
    try:
        doc_b = uuid4()
        admin.execute(
            text(
                """
                INSERT INTO document (
                  id, engagement_id, filename, storage_uri, sha256, source
                ) VALUES (
                  :id, :eng, 'b.pdf', 's3://x/b', :sha, 'manual_upload'
                )
                """
            ),
            {
                "id": doc_b,
                "eng": access_data.project_b,
                "sha": _sha(),
            },
        )
        admin.commit()
    finally:
        admin.close()
    _parent_b, proposal_b = _seed_classification_proposal(
        org_id=access_data.contractor_b,
        engagement_id=access_data.project_b,
        document_id=doc_b,
    )
    _expect_follow_up_denied(
        org_id=access_data.contractor_a,
        parent_event_id=parent_a,
        proposal_id=proposal_b,
    )


def test_create_follow_up_event_refuses_depth_above_three(access_data) -> None:
    parent_id, proposal_id = _seed_classification_proposal(
        org_id=access_data.contractor_a,
        engagement_id=access_data.project_a,
        document_id=access_data.document_a,
        chain_depth=3,
    )
    _expect_follow_up_denied(
        org_id=access_data.contractor_a,
        parent_event_id=parent_id,
        proposal_id=proposal_id,
    )


def test_create_follow_up_event_refuses_missing_proposal(access_data) -> None:
    with org_scoped_session(access_data.contractor_a) as session:
        parent = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="document.received",
            idempotency_key=f"missing-prop-{uuid4().hex}",
            engagement_id=access_data.project_a,
            payload={"document_id": str(access_data.document_a)},
        )
        parent_id = parent["id"]
    _expect_follow_up_denied(
        org_id=access_data.contractor_a,
        parent_event_id=parent_id,
        proposal_id=uuid4(),
    )


def test_create_follow_up_event_payload_from_proposal_not_caller(
    access_data,
) -> None:
    """Function ignores anything except parent + proposal ids (no caller payload)."""

    parent_id, proposal_id = _seed_classification_proposal(
        org_id=access_data.contractor_a,
        engagement_id=access_data.project_a,
        document_id=access_data.document_a,
        extra_content={"doc_type": "bank_guarantee", "bogus": "ignore-me"},
    )
    with agent_org_scoped_session(access_data.contractor_a) as session:
        child_id = create_follow_up_event(
            session,
            parent_event_id=parent_id,
            proposal_id=proposal_id,
        )
        payload = session.execute(
            text("SELECT payload FROM event WHERE id = :id"),
            {"id": child_id},
        ).scalar_one()
    assert set(payload.keys()) == {"document_id", "doc_type"}
    assert payload["doc_type"] == "bank_guarantee"
    assert payload["document_id"] == str(access_data.document_a)


def test_create_follow_up_event_refuses_non_intake_agent(access_data) -> None:
    parent_id, proposal_id = _seed_classification_proposal(
        org_id=access_data.contractor_a,
        engagement_id=access_data.project_a,
        document_id=access_data.document_a,
        agent_name="extraction",
    )
    _expect_follow_up_denied(
        org_id=access_data.contractor_a,
        parent_event_id=parent_id,
        proposal_id=proposal_id,
    )


def test_create_follow_up_event_refuses_different_document_same_engagement(
    access_data,
) -> None:
    other_doc = uuid4()
    admin = AdminSessionFactory()
    try:
        admin.execute(
            text(
                """
                INSERT INTO document (
                  id, engagement_id, filename, storage_uri, sha256, source
                ) VALUES (
                  :id, :eng, 'other.pdf', 's3://x/other', :sha, 'manual_upload'
                )
                """
            ),
            {
                "id": other_doc,
                "eng": access_data.project_a,
                "sha": _sha(),
            },
        )
        admin.commit()
    finally:
        admin.close()
    parent_id, proposal_id = _seed_classification_proposal(
        org_id=access_data.contractor_a,
        engagement_id=access_data.project_a,
        document_id=access_data.document_a,
        proposal_document_id=other_doc,
    )
    _expect_follow_up_denied(
        org_id=access_data.contractor_a,
        parent_event_id=parent_id,
        proposal_id=proposal_id,
    )


def test_create_follow_up_event_refuses_document_other_engagement(
    access_data,
) -> None:
    """Parent engagement A; payload+proposal name a document owned by B."""
    other_doc = uuid4()
    admin = AdminSessionFactory()
    try:
        admin.execute(
            text(
                """
                INSERT INTO document (
                  id, engagement_id, filename, storage_uri, sha256, source
                ) VALUES (
                  :id, :eng, 'b-eng.pdf', 's3://x/be', :sha, 'manual_upload'
                )
                """
            ),
            {
                "id": other_doc,
                "eng": access_data.project_b,
                "sha": _sha(),
            },
        )
        admin.commit()
    finally:
        admin.close()
    parent_id, proposal_id = _seed_classification_proposal(
        org_id=access_data.contractor_a,
        engagement_id=access_data.project_a,
        document_id=other_doc,
        parent_payload_document_id=other_doc,
        proposal_document_id=other_doc,
    )
    _expect_follow_up_denied(
        org_id=access_data.contractor_a,
        parent_event_id=parent_id,
        proposal_id=proposal_id,
    )


def test_app_role_cannot_insert_document_classified(access_data) -> None:
    with (
        org_scoped_session(access_data.contractor_a) as session,
        pytest.raises((DBAPIError, ProgrammingError)),
    ):
        session.execute(
            text(
                """
                INSERT INTO event (
                  org_id, engagement_id, event_type, idempotency_key, payload
                ) VALUES (
                  :org, :eng, 'document.classified', :key, '{}'::jsonb
                )
                """
            ),
            {
                "org": access_data.contractor_a,
                "eng": access_data.project_a,
                "key": f"classified-{uuid4().hex}",
            },
        )
        session.flush()


def test_app_role_cannot_insert_event_with_caused_by_or_depth(
    access_data,
) -> None:
    with org_scoped_session(access_data.contractor_a) as session:
        root = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="document.received",
            idempotency_key=f"root-{uuid4().hex}",
            engagement_id=access_data.project_a,
            payload={"document_id": str(access_data.document_a)},
        )
        root_id = root["id"]
    with (
        org_scoped_session(access_data.contractor_a) as session,
        pytest.raises((DBAPIError, ProgrammingError)),
    ):
        session.execute(
            text(
                """
                INSERT INTO event (
                  org_id, engagement_id, event_type, idempotency_key,
                  payload, caused_by_event_id, chain_depth
                ) VALUES (
                  :org, :eng, 'document.received', :key, '{}'::jsonb,
                  :caused, 0
                )
                """
            ),
            {
                "org": access_data.contractor_a,
                "eng": access_data.project_a,
                "key": f"caused-{uuid4().hex}",
                "caused": root_id,
            },
        )
        session.flush()
    with (
        org_scoped_session(access_data.contractor_a) as session,
        pytest.raises((DBAPIError, ProgrammingError)),
    ):
        session.execute(
            text(
                """
                INSERT INTO event (
                  org_id, engagement_id, event_type, idempotency_key,
                  payload, chain_depth
                ) VALUES (
                  :org, :eng, 'document.received', :key, '{}'::jsonb, 1
                )
                """
            ),
            {
                "org": access_data.contractor_a,
                "eng": access_data.project_a,
                "key": f"depth-{uuid4().hex}",
            },
        )
        session.flush()


def test_app_role_can_insert_document_received_and_test_echo(access_data) -> None:
    with org_scoped_session(access_data.contractor_a) as session:
        received = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="document.received",
            idempotency_key=f"recv-ok-{uuid4().hex}",
            engagement_id=access_data.project_a,
            payload={"document_id": str(access_data.document_a)},
        )
        echo = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"echo-ok-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
    assert received["event_type"] == "document.received"
    assert echo["event_type"] == "test.echo"


def test_app_role_cannot_update_document_identity_or_storage(access_data) -> None:
    for column, value in (
        ("storage_uri", "s3://hijacked/x"),
        ("sha256", "b" * 64),
        ("engagement_id", str(access_data.project_b)),
    ):
        with (
            org_scoped_session(access_data.contractor_a) as session,
            pytest.raises((DBAPIError, ProgrammingError)),
        ):
            session.execute(
                text(f"UPDATE document SET {column} = :v WHERE id = :id"),
                {"v": value, "id": access_data.document_a},
            )
            session.flush()


def test_inbound_reaccept_still_updates_received_at(access_data) -> None:
    sha = _sha()
    kwargs = dict(
        org_id=access_data.contractor_a,
        project_id=access_data.project_a,
        filename="bg.pdf",
        storage_uri="s3://equicontracts-documents/reaccept",
        sha256=sha,
        sender_email=None,
        subject="BG",
    )
    with org_scoped_session(access_data.contractor_a) as session:
        doc_id = inbound_service.accept_document(session, **kwargs)
        first_received = session.execute(
            text("SELECT received_at FROM document WHERE id = :id"),
            {"id": doc_id},
        ).scalar_one()
    with org_scoped_session(access_data.contractor_a) as session:
        second = inbound_service.accept_document(session, **kwargs)
        second_received = session.execute(
            text("SELECT received_at FROM document WHERE id = :id"),
            {"id": doc_id},
        ).scalar_one()
    assert second == doc_id
    assert second_received >= first_received


def test_agent_role_cannot_insert_event_directly(access_data) -> None:
    session = AgentSessionFactory()
    try:
        session.execute(
            text("SELECT set_config('app.current_org_id', :org, true)"),
            {"org": str(access_data.contractor_a)},
        )
        with pytest.raises((DBAPIError, ProgrammingError)):
            session.execute(
                text(
                    """
                    INSERT INTO event (
                      org_id, engagement_id, event_type, idempotency_key, payload
                    ) VALUES (
                      :org, :eng, 'document.classified', :key, '{}'::jsonb
                    )
                    """
                ),
                {
                    "org": access_data.contractor_a,
                    "eng": access_data.project_a,
                    "key": f"direct-{uuid4().hex}",
                },
            )
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_app_role_cannot_execute_create_follow_up_event(access_data) -> None:
    parent_id, proposal_id = _seed_classification_proposal(
        org_id=access_data.contractor_a,
        engagement_id=access_data.project_a,
        document_id=access_data.document_a,
    )
    session = AppSessionFactory()
    try:
        session.execute(
            text("SELECT set_config('app.current_org_id', :org, true)"),
            {"org": str(access_data.contractor_a)},
        )
        with pytest.raises((DBAPIError, ProgrammingError)):
            session.execute(
                text(
                    """
                    SELECT create_follow_up_event(
                      CAST(:parent AS uuid), CAST(:proposal AS uuid)
                    )
                    """
                ),
                {"parent": parent_id, "proposal": proposal_id},
            )
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_document_type_readable_not_writable() -> None:
    app = AppSessionFactory()
    agent = AgentSessionFactory()
    try:
        app_count = app.execute(text("SELECT count(*) FROM document_type")).scalar_one()
        agent_count = agent.execute(
            text("SELECT count(*) FROM document_type")
        ).scalar_one()
        assert app_count >= 12
        assert agent_count == app_count
        with pytest.raises((DBAPIError, ProgrammingError)):
            app.execute(
                text("INSERT INTO document_type (code, label) VALUES ('x', 'X')")
            )
            app.commit()
    finally:
        app.rollback()
        app.close()
    try:
        with pytest.raises((DBAPIError, ProgrammingError)):
            agent.execute(
                text("INSERT INTO document_type (code, label) VALUES ('y', 'Y')")
            )
            agent.commit()
    finally:
        agent.rollback()
        agent.close()


def test_doc_type_and_evidence_weight_no_update_for_app_or_agent(
    access_data,
) -> None:
    for factory in (AppSessionFactory, AgentSessionFactory):
        session = factory()
        try:
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(access_data.contractor_a)},
            )
            with pytest.raises((DBAPIError, ProgrammingError)):
                session.execute(
                    text(
                        """
                        UPDATE document
                        SET doc_type = 'bank_guarantee'
                        WHERE id = :id
                        """
                    ),
                    {"id": access_data.document_a},
                )
                session.commit()
        finally:
            session.rollback()
            session.close()
        session = factory()
        try:
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(access_data.contractor_a)},
            )
            with pytest.raises((DBAPIError, ProgrammingError)):
                session.execute(
                    text(
                        """
                        UPDATE document
                        SET evidence_weight = 'core_evidence'
                        WHERE id = :id
                        """
                    ),
                    {"id": access_data.document_a},
                )
                session.commit()
        finally:
            session.rollback()
            session.close()
