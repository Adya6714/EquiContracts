"""Step 5 Part A: agent foundation schema, claim, and role grants."""

from __future__ import annotations

import threading
from datetime import timedelta
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
from apps.api.app.workers.agent_events import claim_next_event


def _drain_pending_events() -> None:
    """Claim leftover pending events so claim-order tests are isolated."""
    for _ in range(50):
        if claim_next_event() is None:
            break


def test_claim_next_event_returns_oldest_pending(access_data) -> None:
    _drain_pending_events()
    with org_scoped_session(access_data.contractor_a) as session:
        older = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"oldest-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
    with org_scoped_session(access_data.contractor_a) as session:
        agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"newer-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )

    claimed = claim_next_event()
    assert claimed is not None
    assert claimed.event_id == older["id"]
    assert claimed.org_id == access_data.contractor_a


def test_concurrent_claims_never_share_same_event(access_data) -> None:
    _drain_pending_events()
    with org_scoped_session(access_data.contractor_a) as session:
        agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"once-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )

    results: list[object] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait()
        results.append(claim_next_event())

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    won = [item for item in results if item is not None]
    assert len(won) == 1
    # Stronger: even if leftovers exist, both winners must not share an id.
    ids = {item.event_id for item in won}  # type: ignore[union-attr]
    assert len(ids) == len(won)


def test_stuck_claimed_event_reclaimed_after_timeout(access_data) -> None:
    with org_scoped_session(access_data.contractor_a) as session:
        row = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"stuck-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
        event_id = row["id"]

    admin = AdminSessionFactory()
    try:
        admin.execute(
            text(
                """
                UPDATE event
                SET status = 'claimed',
                    claimed_at = now() - interval '20 minutes',
                    attempts = 1
                WHERE id = :id
                """
            ),
            {"id": event_id},
        )
        admin.commit()
    finally:
        admin.close()

    claimed = claim_next_event(claim_timeout=timedelta(minutes=10))
    assert claimed is not None
    assert claimed.event_id == event_id


def test_app_role_cannot_execute_claim_next_event() -> None:
    session = AppSessionFactory()
    try:
        with pytest.raises((ProgrammingError, DBAPIError)):
            session.execute(text("SELECT * FROM claim_next_event()")).all()
            session.flush()
    finally:
        session.rollback()
        session.close()


def test_agent_role_cannot_insert_review_decision(access_data) -> None:
    with org_scoped_session(access_data.contractor_a) as session:
        event = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"rd-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
    claim = claim_next_event()
    assert claim is not None
    with agent_org_scoped_session(claim.org_id) as session:
        run = agent_events_service.start_run(
            session,
            event_id=claim.event_id,
            org_id=claim.org_id,
            agent_name="echo",
            agent_version="0",
            engagement_id=claim.engagement_id,
        )
        proposal_id = agent_events_service.create_proposal(
            session,
            run_id=run.run_id,
            org_id=claim.org_id,
            engagement_id=claim.engagement_id,
            proposal_type="echo.note",
            content={"engagement_id": str(access_data.project_a)},
            autonomy_level=2,
        )
        with pytest.raises((ProgrammingError, DBAPIError)):
            session.execute(
                text(
                    """
                    INSERT INTO review_decision (
                      proposal_id, org_id, decided_by, decision
                    )
                    VALUES (:proposal_id, :org_id, :user_id, 'approved')
                    """
                ),
                {
                    "proposal_id": proposal_id,
                    "org_id": access_data.contractor_a,
                    "user_id": access_data.user_a,
                },
            )
            session.flush()
    _ = event


def test_agent_role_cannot_update_agent_proposal(access_data) -> None:
    with org_scoped_session(access_data.contractor_a) as session:
        agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"prop-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
    claim = claim_next_event()
    assert claim is not None
    with agent_org_scoped_session(claim.org_id) as session:
        run = agent_events_service.start_run(
            session,
            event_id=claim.event_id,
            org_id=claim.org_id,
            agent_name="echo",
            agent_version="0",
            engagement_id=claim.engagement_id,
        )
        proposal_id = agent_events_service.create_proposal(
            session,
            run_id=run.run_id,
            org_id=claim.org_id,
            proposal_type="echo.note",
            content={},
            autonomy_level=2,
        )
        with pytest.raises((ProgrammingError, DBAPIError)):
            session.execute(
                text(
                    """
                    UPDATE agent_proposal
                    SET state = 'approved'
                    WHERE id = :id
                    """
                ),
                {"id": proposal_id},
            )
            session.flush()


def test_agent_role_cannot_update_extracted_field(access_data) -> None:
    with (
        agent_org_scoped_session(access_data.contractor_a) as session,
        pytest.raises((ProgrammingError, DBAPIError)),
    ):
        session.execute(
            text(
                """
                UPDATE extracted_field
                SET state = 'verified'
                WHERE id = :id
                """
            ),
            {"id": access_data.verified_field},
        )
        session.flush()


def test_review_decision_refuses_foreign_org_decider(access_data) -> None:
    admin = AdminSessionFactory()
    foreign_user = uuid4()
    try:
        admin.execute(
            text(
                """
                INSERT INTO app_user (id, org_id, email, role)
                VALUES (
                  :id, :org_id, :email, 'contractor_admin'
                )
                """
            ),
            {
                "id": foreign_user,
                "org_id": access_data.contractor_b,
                "email": f"b-{uuid4().hex[:8]}@example.invalid",
            },
        )
        admin.commit()
    finally:
        admin.close()

    with org_scoped_session(access_data.contractor_a) as session:
        agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"foreign-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
    claim = claim_next_event()
    assert claim is not None
    with agent_org_scoped_session(claim.org_id) as session:
        run = agent_events_service.start_run(
            session,
            event_id=claim.event_id,
            org_id=claim.org_id,
            agent_name="echo",
            agent_version="0",
            engagement_id=claim.engagement_id,
        )
        proposal_id = agent_events_service.create_proposal(
            session,
            run_id=run.run_id,
            org_id=claim.org_id,
            proposal_type="echo.note",
            content={},
            autonomy_level=2,
        )

    with (
        org_scoped_session(access_data.contractor_a) as session,
        pytest.raises(DBAPIError),
    ):
        agent_events_service.record_review_decision(
            session,
            proposal_id=proposal_id,
            org_id=access_data.contractor_a,
            decided_by=foreign_user,
            decision="approved",
        )
        session.flush()

    admin = AdminSessionFactory()
    try:
        admin.execute(
            text("DELETE FROM app_user WHERE id = :id"),
            {"id": foreign_user},
        )
        admin.commit()
    finally:
        admin.close()


def test_review_decision_updates_proposal_state(access_data) -> None:
    with org_scoped_session(access_data.contractor_a) as session:
        agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"state-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
    claim = claim_next_event()
    assert claim is not None
    with agent_org_scoped_session(claim.org_id) as session:
        run = agent_events_service.start_run(
            session,
            event_id=claim.event_id,
            org_id=claim.org_id,
            agent_name="echo",
            agent_version="0",
            engagement_id=claim.engagement_id,
        )
        proposal_id = agent_events_service.create_proposal(
            session,
            run_id=run.run_id,
            org_id=claim.org_id,
            proposal_type="echo.note",
            content={},
            autonomy_level=2,
        )

    with org_scoped_session(access_data.contractor_a) as session:
        agent_events_service.record_review_decision(
            session,
            proposal_id=proposal_id,
            org_id=access_data.contractor_a,
            decided_by=access_data.user_a,
            decision="approved",
        )
        state = session.execute(
            text("SELECT state FROM agent_proposal WHERE id = :id"),
            {"id": proposal_id},
        ).scalar_one()
    assert state == "approved"


def test_same_idempotency_key_creates_one_event(access_data) -> None:
    key = f"idem-{uuid4().hex}"
    with org_scoped_session(access_data.contractor_a) as session:
        first = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=key,
            engagement_id=access_data.project_a,
        )
        second = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=key,
            engagement_id=access_data.project_a,
        )
        count = session.execute(
            text(
                """
                SELECT count(*) FROM event
                WHERE org_id = :org_id AND idempotency_key = :key
                """
            ),
            {"org_id": access_data.contractor_a, "key": key},
        ).scalar_one()
    assert first["id"] == second["id"]
    assert count == 1


def test_failed_run_does_not_process_event_retry_is_attempt_two(access_data) -> None:
    with org_scoped_session(access_data.contractor_a) as session:
        agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"fail-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
    claim = claim_next_event()
    assert claim is not None
    with agent_org_scoped_session(claim.org_id) as session:
        run1 = agent_events_service.start_run(
            session,
            event_id=claim.event_id,
            org_id=claim.org_id,
            agent_name="echo",
            agent_version="0",
            engagement_id=claim.engagement_id,
        )
        assert run1.attempt == 1
        agent_events_service.fail_run(
            session,
            run_id=run1.run_id,
            event_id=claim.event_id,
            steps_used=1,
            last_error="boom",
        )
        status = session.execute(
            text("SELECT status FROM event WHERE id = :id"),
            {"id": claim.event_id},
        ).scalar_one()
        assert status != "processed"

        run2 = agent_events_service.start_run(
            session,
            event_id=claim.event_id,
            org_id=claim.org_id,
            agent_name="echo",
            agent_version="0",
            engagement_id=claim.engagement_id,
        )
        assert run2.attempt == 2
        agent_events_service.succeed_run(
            session,
            run_id=run2.run_id,
            event_id=claim.event_id,
            agent_name="echo",
            steps_used=1,
        )
        agent_events_service.mark_event_processed(session, event_id=claim.event_id)
        status = session.execute(
            text("SELECT status FROM event WHERE id = :id"),
            {"id": claim.event_id},
        ).scalar_one()
    assert status == "processed"


def test_agent_session_org_a_cannot_read_org_b_engagement_or_document(
    access_data,
) -> None:
    with agent_org_scoped_session(access_data.contractor_a) as session:
        rival = session.execute(
            text("SELECT id FROM engagement WHERE id = :id"),
            {"id": access_data.project_b},
        ).scalar_one_or_none()
        # Org A owns document_a; ensure B's world stays empty for A.
        docs = set(session.execute(text("SELECT id FROM document")).scalars())
    assert rival is None
    assert docs == {access_data.document_a}


def test_agent_session_factory_uses_agent_role() -> None:
    session = AgentSessionFactory()
    try:
        role = session.execute(text("SELECT current_user")).scalar_one()
    finally:
        session.close()
    assert role == "equicontracts_agent"


def test_event_insert_refuses_foreign_org_engagement(access_data) -> None:
    with (
        org_scoped_session(access_data.contractor_a) as session,
        pytest.raises(DBAPIError),
    ):
        session.execute(
            text(
                """
                INSERT INTO event (
                  org_id, engagement_id, event_type, idempotency_key
                )
                VALUES (:org_id, :engagement_id, 'test.echo', :key)
                """
            ),
            {
                "org_id": access_data.contractor_a,
                "engagement_id": access_data.project_b,
                "key": f"xeng-{uuid4().hex}",
            },
        )
        session.flush()


def test_agent_run_insert_refuses_foreign_org_event(access_data) -> None:
    with org_scoped_session(access_data.contractor_b) as session:
        foreign = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_b,
            event_type="test.echo",
            idempotency_key=f"brun-{uuid4().hex}",
            engagement_id=access_data.project_b,
        )
    with (
        agent_org_scoped_session(access_data.contractor_a) as session,
        pytest.raises(DBAPIError),
    ):
        session.execute(
            text(
                """
                INSERT INTO agent_run (
                  event_id, org_id, agent_name, agent_version, attempt
                )
                VALUES (:event_id, :org_id, 'echo', '0', 1)
                """
            ),
            {
                "event_id": foreign["id"],
                "org_id": access_data.contractor_a,
            },
        )
        session.flush()


def test_agent_step_insert_refuses_foreign_org_run(access_data) -> None:
    _drain_pending_events()
    with org_scoped_session(access_data.contractor_b) as session:
        agent_events_service.create_event(
            session,
            org_id=access_data.contractor_b,
            event_type="test.echo",
            idempotency_key=f"bstep-{uuid4().hex}",
            engagement_id=access_data.project_b,
        )
    claim = claim_next_event()
    assert claim is not None
    assert claim.org_id == access_data.contractor_b
    with agent_org_scoped_session(claim.org_id) as session:
        foreign_run = agent_events_service.start_run(
            session,
            event_id=claim.event_id,
            org_id=claim.org_id,
            agent_name="echo",
            agent_version="0",
            engagement_id=claim.engagement_id,
        )
    with (
        agent_org_scoped_session(access_data.contractor_a) as session,
        pytest.raises(DBAPIError),
    ):
        session.execute(
            text(
                """
                INSERT INTO agent_step (
                  run_id, org_id, step_no, outcome
                )
                VALUES (:run_id, :org_id, 1, 'ok')
                """
            ),
            {
                "run_id": foreign_run.run_id,
                "org_id": access_data.contractor_a,
            },
        )
        session.flush()


def test_agent_proposal_insert_refuses_foreign_org_run(access_data) -> None:
    _drain_pending_events()
    with org_scoped_session(access_data.contractor_b) as session:
        agent_events_service.create_event(
            session,
            org_id=access_data.contractor_b,
            event_type="test.echo",
            idempotency_key=f"bprop-{uuid4().hex}",
            engagement_id=access_data.project_b,
        )
    claim = claim_next_event()
    assert claim is not None
    assert claim.org_id == access_data.contractor_b
    with agent_org_scoped_session(claim.org_id) as session:
        foreign_run = agent_events_service.start_run(
            session,
            event_id=claim.event_id,
            org_id=claim.org_id,
            agent_name="echo",
            agent_version="0",
            engagement_id=claim.engagement_id,
        )
    with (
        agent_org_scoped_session(access_data.contractor_a) as session,
        pytest.raises(DBAPIError),
    ):
        session.execute(
            text(
                """
                INSERT INTO agent_proposal (
                  run_id, org_id, proposal_type, content, autonomy_level
                )
                VALUES (
                  :run_id, :org_id, 'echo.note', '{}'::jsonb, 2
                )
                """
            ),
            {
                "run_id": foreign_run.run_id,
                "org_id": access_data.contractor_a,
            },
        )
        session.flush()


def test_review_decision_insert_refuses_foreign_org_proposal(access_data) -> None:
    _drain_pending_events()
    with org_scoped_session(access_data.contractor_b) as session:
        agent_events_service.create_event(
            session,
            org_id=access_data.contractor_b,
            event_type="test.echo",
            idempotency_key=f"bdec-{uuid4().hex}",
            engagement_id=access_data.project_b,
        )
    claim = claim_next_event()
    assert claim is not None
    assert claim.org_id == access_data.contractor_b
    with agent_org_scoped_session(claim.org_id) as session:
        run = agent_events_service.start_run(
            session,
            event_id=claim.event_id,
            org_id=claim.org_id,
            agent_name="echo",
            agent_version="0",
            engagement_id=claim.engagement_id,
        )
        foreign_proposal = agent_events_service.create_proposal(
            session,
            run_id=run.run_id,
            org_id=claim.org_id,
            proposal_type="echo.note",
            content={},
            autonomy_level=2,
        )
    with (
        org_scoped_session(access_data.contractor_a) as session,
        pytest.raises(DBAPIError),
    ):
        session.execute(
            text(
                """
                INSERT INTO review_decision (
                  proposal_id, org_id, decided_by, decision
                )
                VALUES (:proposal_id, :org_id, :user_id, 'approved')
                """
            ),
            {
                "proposal_id": foreign_proposal,
                "org_id": access_data.contractor_a,
                "user_id": access_data.user_a,
            },
        )
        session.flush()


def test_event_at_max_attempts_marked_failed_not_claimed(access_data) -> None:
    _drain_pending_events()
    with org_scoped_session(access_data.contractor_a) as session:
        row = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"max-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
        event_id = row["id"]

    admin = AdminSessionFactory()
    try:
        admin.execute(
            text(
                """
                UPDATE event
                SET status = 'pending',
                    attempts = 3,
                    claimed_at = NULL
                WHERE id = :id
                """
            ),
            {"id": event_id},
        )
        admin.commit()
    finally:
        admin.close()

    claimed = claim_next_event(max_attempts=3)
    assert claimed is None or claimed.event_id != event_id

    admin = AdminSessionFactory()
    try:
        status, last_error = admin.execute(
            text(
                """
                SELECT status, last_error FROM event WHERE id = :id
                """
            ),
            {"id": event_id},
        ).one()
    finally:
        admin.close()
    assert status == "failed"
    assert last_error == "max attempts reached"


def test_app_role_cannot_update_event(access_data) -> None:
    with org_scoped_session(access_data.contractor_a) as session:
        row = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"noup-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
        event_id = row["id"]
        with pytest.raises((ProgrammingError, DBAPIError)):
            session.execute(
                text(
                    """
                    UPDATE event
                    SET status = 'failed'
                    WHERE id = :id
                    """
                ),
                {"id": event_id},
            )
            session.flush()


def test_agent_role_cannot_select_app_user(access_data) -> None:
    with (
        agent_org_scoped_session(access_data.contractor_a) as session,
        pytest.raises((ProgrammingError, DBAPIError)),
    ):
        session.execute(text("SELECT id FROM app_user LIMIT 1")).all()
        session.flush()


def _priv_cols(
    grantee: str, table: str, privilege: str, columns: tuple[str, ...]
) -> set[tuple[str, str, str, str]]:
    return {(grantee, table, col, privilege) for col in columns}


def test_agent_foundation_privilege_snapshot() -> None:
    """Exact table/column/EXECUTE privileges for app + agent on foundation tables."""
    tables = (
        "event",
        "agent_run",
        "agent_step",
        "agent_proposal",
        "review_decision",
    )
    event_cols = (
        "id",
        "org_id",
        "engagement_id",
        "event_type",
        "payload",
        "idempotency_key",
        "status",
        "attempts",
        "last_error",
        "created_at",
        "claimed_at",
        "processed_at",
    )
    run_cols = (
        "id",
        "event_id",
        "org_id",
        "engagement_id",
        "agent_name",
        "agent_version",
        "model_version",
        "attempt",
        "status",
        "steps_used",
        "retries_used",
        "cost",
        "started_at",
        "finished_at",
    )
    step_cols = (
        "id",
        "run_id",
        "org_id",
        "step_no",
        "tool_called",
        "input",
        "output",
        "outcome",
        "created_at",
    )
    proposal_cols = (
        "id",
        "run_id",
        "org_id",
        "engagement_id",
        "proposal_type",
        "content",
        "confidence",
        "autonomy_level",
        "state",
        "created_at",
    )
    decision_cols = (
        "id",
        "proposal_id",
        "org_id",
        "decided_by",
        "decision",
        "correction",
        "reason",
        "created_at",
    )
    run_update_cols = (
        "status",
        "steps_used",
        "retries_used",
        "cost",
        "finished_at",
        "model_version",
    )
    event_update_cols = (
        "status",
        "processed_at",
        "last_error",
        "claimed_at",
        "attempts",
    )

    session = AdminSessionFactory()
    try:
        table_rows = session.execute(
            text(
                """
                SELECT grantee, table_name, privilege_type
                FROM information_schema.table_privileges
                WHERE table_schema = 'public'
                  AND grantee IN ('equicontracts_app', 'equicontracts_agent')
                  AND table_name = ANY(:tables)
                ORDER BY 1, 2, 3
                """
            ),
            {"tables": list(tables)},
        ).all()
        column_rows = session.execute(
            text(
                """
                SELECT grantee, table_name, column_name, privilege_type
                FROM information_schema.column_privileges
                WHERE table_schema = 'public'
                  AND grantee IN ('equicontracts_app', 'equicontracts_agent')
                  AND table_name = ANY(:tables)
                ORDER BY 1, 2, 3, 4
                """
            ),
            {"tables": list(tables)},
        ).all()
        exec_rows = session.execute(
            text(
                """
                SELECT grantee, routine_name, privilege_type
                FROM information_schema.routine_privileges
                WHERE specific_schema = 'public'
                  AND routine_name = 'claim_next_event'
                  AND grantee IN (
                    'equicontracts_app',
                    'equicontracts_agent',
                    'PUBLIC'
                  )
                ORDER BY 1, 2, 3
                """
            )
        ).all()
    finally:
        session.close()

    # Column-level UPDATE does not appear in table_privileges.
    expected_table = {
        ("equicontracts_agent", "agent_proposal", "INSERT"),
        ("equicontracts_agent", "agent_proposal", "SELECT"),
        ("equicontracts_agent", "agent_run", "INSERT"),
        ("equicontracts_agent", "agent_run", "SELECT"),
        ("equicontracts_agent", "agent_step", "INSERT"),
        ("equicontracts_agent", "agent_step", "SELECT"),
        ("equicontracts_agent", "event", "SELECT"),
        ("equicontracts_app", "agent_proposal", "SELECT"),
        ("equicontracts_app", "agent_run", "SELECT"),
        ("equicontracts_app", "agent_step", "SELECT"),
        ("equicontracts_app", "event", "INSERT"),
        ("equicontracts_app", "event", "SELECT"),
        ("equicontracts_app", "review_decision", "INSERT"),
        ("equicontracts_app", "review_decision", "SELECT"),
    }
    expected_columns = set()
    expected_columns |= _priv_cols("equicontracts_app", "event", "SELECT", event_cols)
    expected_columns |= _priv_cols("equicontracts_app", "event", "INSERT", event_cols)
    expected_columns |= _priv_cols("equicontracts_app", "agent_run", "SELECT", run_cols)
    expected_columns |= _priv_cols(
        "equicontracts_app", "agent_step", "SELECT", step_cols
    )
    expected_columns |= _priv_cols(
        "equicontracts_app", "agent_proposal", "SELECT", proposal_cols
    )
    expected_columns |= _priv_cols(
        "equicontracts_app", "review_decision", "SELECT", decision_cols
    )
    expected_columns |= _priv_cols(
        "equicontracts_app", "review_decision", "INSERT", decision_cols
    )
    expected_columns |= _priv_cols("equicontracts_agent", "event", "SELECT", event_cols)
    expected_columns |= _priv_cols(
        "equicontracts_agent", "event", "UPDATE", event_update_cols
    )
    expected_columns |= _priv_cols(
        "equicontracts_agent", "agent_run", "SELECT", run_cols
    )
    expected_columns |= _priv_cols(
        "equicontracts_agent", "agent_run", "INSERT", run_cols
    )
    expected_columns |= _priv_cols(
        "equicontracts_agent", "agent_run", "UPDATE", run_update_cols
    )
    expected_columns |= _priv_cols(
        "equicontracts_agent", "agent_step", "SELECT", step_cols
    )
    expected_columns |= _priv_cols(
        "equicontracts_agent", "agent_step", "INSERT", step_cols
    )
    expected_columns |= _priv_cols(
        "equicontracts_agent", "agent_proposal", "SELECT", proposal_cols
    )
    expected_columns |= _priv_cols(
        "equicontracts_agent", "agent_proposal", "INSERT", proposal_cols
    )
    expected_exec = {
        ("equicontracts_agent", "claim_next_event", "EXECUTE"),
    }

    actual_table = {(r[0], r[1], r[2]) for r in table_rows}
    actual_columns = {(r[0], r[1], r[2], r[3]) for r in column_rows}
    actual_exec = {(r[0], r[1], r[2]) for r in exec_rows}

    assert actual_table == expected_table
    assert actual_columns == expected_columns
    assert actual_exec == expected_exec
