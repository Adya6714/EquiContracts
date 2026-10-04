"""Step 5 Part B: runtime, guardrails, echo agent, worker run_once."""

from __future__ import annotations

import inspect
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from apps.api.app.core.db import (
    AdminSessionFactory,
    agent_org_scoped_session,
    org_scoped_session,
)
from apps.api.app.repositories import agent_events as agent_events_repo
from apps.api.app.services import agent_events as agent_events_service
from apps.api.app.workers.agent_events import NO_AGENT_MESSAGE, run_once
from apps.api.app.workers.service_handle import WorkerServiceHandle
from packages.agents.context import RunContext
from packages.agents.guardrails import autonomy
from packages.agents.guardrails.number_check import numbers_and_dates_ok
from packages.agents.runtime import (
    AgentRuntime,
    SelfCheckError,
    ServicesHandleError,
    run_agent,
    sanitize_for_log,
)
from packages.agents.tools import TOOL_REGISTRY
from packages.agents.tools._base import ToolRefusal


def _drain() -> None:
    from apps.api.app.workers.agent_events import claim_next_event

    for _ in range(50):
        if claim_next_event() is None:
            break


def test_echo_end_to_end_event_run_steps_proposal_processed(access_data) -> None:
    _drain()
    with org_scoped_session(access_data.contractor_a) as session:
        event = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"echo-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
        event_id = event["id"]

    assert run_once() is True

    with agent_org_scoped_session(access_data.contractor_a) as session:
        status = agent_events_repo.get_event_status(session, event_id=event_id)
        runs = (
            session.execute(
                text(
                    """
                SELECT id, status, attempt FROM agent_run
                WHERE event_id = :event_id
                """
                ),
                {"event_id": event_id},
            )
            .mappings()
            .all()
        )
        assert len(runs) == 1
        run_id = runs[0]["id"]
        assert runs[0]["status"] == "succeeded"
        assert runs[0]["attempt"] == 1
        steps = agent_events_repo.list_steps_for_run(session, run_id=run_id)
        proposals = agent_events_repo.list_proposals_for_run(session, run_id=run_id)

    assert status == "processed"
    assert len(steps) >= 2
    assert {step["tool_called"] for step in steps} >= {
        "get_engagement_context",
        "emit_proposal",
    }
    assert len(proposals) == 1
    assert proposals[0]["proposal_type"] == "echo.note"
    assert proposals[0]["autonomy_level"] == 2
    assert proposals[0]["state"] == "pending"


def test_unlisted_tool_blocked_logged_no_proposal(access_data) -> None:
    _drain()
    with org_scoped_session(access_data.contractor_a) as session:
        event = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"block-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
        # Claim manually so we can run a custom agent on a real run row.
    from apps.api.app.workers.agent_events import claim_next_event

    claim = claim_next_event()
    assert claim is not None
    assert claim.event_id == event["id"]

    def bad_agent(runtime: AgentRuntime) -> None:
        runtime.call_tool("send_client_email", to="x@example.com")
        runtime.emit_proposal("echo.note", {"engagement_id": str(claim.engagement_id)})

    with agent_org_scoped_session(claim.org_id) as session:
        run = agent_events_service.start_run(
            session,
            event_id=claim.event_id,
            org_id=claim.org_id,
            agent_name="echo",
            agent_version="0",
            engagement_id=claim.engagement_id,
            attempt=1,
        )
        ctx = RunContext(
            org_id=claim.org_id,
            engagement_id=claim.engagement_id,
            run_id=run.run_id,
            services=WorkerServiceHandle(session),
        )
        outcome = run_agent(ctx, agent_name="echo", agent_fn=bad_agent)
        steps = agent_events_repo.list_steps_for_run(session, run_id=run.run_id)
        proposals = agent_events_repo.list_proposals_for_run(session, run_id=run.run_id)

    assert outcome.status == "failed"
    assert any(
        step["tool_called"] == "send_client_email" and step["outcome"] == "blocked"
        for step in steps
    )
    assert proposals == []


def _app_event_and_agent_run(access_data, *, key_prefix: str):
    with org_scoped_session(access_data.contractor_a) as session:
        event = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"{key_prefix}-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
        event_id = event["id"]
    with agent_org_scoped_session(access_data.contractor_a) as session:
        run = agent_events_service.start_run(
            session,
            event_id=event_id,
            org_id=access_data.contractor_a,
            agent_name="echo",
            agent_version="0",
            engagement_id=access_data.project_a,
            attempt=1,
        )
        return event_id, run.run_id


def test_max_steps_stops_the_run(access_data) -> None:
    _event_id, run_id = _app_event_and_agent_run(access_data, key_prefix="steps")
    with agent_org_scoped_session(access_data.contractor_a) as session:
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=run_id,
            services=WorkerServiceHandle(session),
        )

        def looper(runtime: AgentRuntime) -> None:
            for _ in range(20):
                runtime.call_tool(
                    "get_engagement_context",
                    engagement_id=access_data.project_a,
                )

        outcome = run_agent(ctx, agent_name="echo", agent_fn=looper, max_steps=3)
    assert outcome.status == "failed"
    assert outcome.error == "RunLimitError:max_steps"
    assert outcome.steps_used == 3


def test_max_retries_stops_the_run(access_data) -> None:
    _event_id, run_id = _app_event_and_agent_run(access_data, key_prefix="retry")
    with agent_org_scoped_session(access_data.contractor_a) as session:
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=run_id,
            services=WorkerServiceHandle(session),
        )

        def flaky(runtime: AgentRuntime) -> None:
            raise SelfCheckError("nope")

        outcome = run_agent(ctx, agent_name="echo", agent_fn=flaky, max_retries=2)
    assert outcome.status == "failed"
    assert outcome.error == "RunLimitError:max_retries"
    assert outcome.retries_used == 2


def test_cost_cap_stops_the_run(access_data) -> None:
    _event_id, run_id = _app_event_and_agent_run(access_data, key_prefix="cost")
    with agent_org_scoped_session(access_data.contractor_a) as session:
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=run_id,
            services=WorkerServiceHandle(session),
        )

        def once(runtime: AgentRuntime) -> None:
            runtime.call_tool(
                "get_engagement_context",
                engagement_id=access_data.project_a,
            )

        outcome = run_agent(
            ctx,
            agent_name="echo",
            agent_fn=once,
            cost_cap=Decimal("0.50"),
            cost_per_step=Decimal("1.00"),
        )
    assert outcome.status == "failed"
    assert outcome.error == "RunLimitError:cost_cap"


def test_agent_cannot_set_autonomy_unknown_defaults_level4_never_applied(
    access_data,
) -> None:
    assert (
        "autonomy_level" not in inspect.signature(AgentRuntime.emit_proposal).parameters
    )
    assert autonomy.autonomy_level_for("brand_new_action") == 2
    assert autonomy.autonomy_level_for("mark_financial_field_verified") == 4
    assert not hasattr(AgentRuntime.emit_proposal, "applied")
    assert "applied" not in inspect.signature(AgentRuntime.emit_proposal).parameters

    _event_id, run_id = _app_event_and_agent_run(access_data, key_prefix="auto")
    with agent_org_scoped_session(access_data.contractor_a) as session:
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=run_id,
            services=WorkerServiceHandle(session),
        )

        def level4_agent(runtime: AgentRuntime) -> None:
            emission = runtime.emit_proposal(
                "mark_financial_field_verified",
                {"engagement_id": str(access_data.project_a)},
            )
            assert emission.autonomy_level == 4
            assert not hasattr(emission, "applied")

        outcome = run_agent(ctx, agent_name="echo", agent_fn=level4_agent)
        proposals = agent_events_repo.list_proposals_for_run(session, run_id=run_id)
    assert outcome.status == "succeeded"
    assert proposals[0]["autonomy_level"] == 4
    assert proposals[0]["state"] == "pending"


def test_tool_refuses_other_engagement_same_org_and_other_org(access_data) -> None:
    # Same org, second engagement owned by contractor A.
    other_a = uuid4()
    admin = AdminSessionFactory()
    try:
        admin.execute(
            text(
                """
                INSERT INTO engagement (
                  id, owner_org_id, site_id, name, project_code, inbound_alias
                ) VALUES (
                  :id, :org_id, :site_id, 'Other A', :code, :alias
                )
                """
            ),
            {
                "id": other_a,
                "org_id": access_data.contractor_a,
                "site_id": access_data.site_id,
                "code": f"EC-OTH-{uuid4().hex[:4]}",
                "alias": f"oth{uuid4().hex[:6]}",
            },
        )
        admin.commit()
    finally:
        admin.close()

    try:
        _event_id, run_id = _app_event_and_agent_run(access_data, key_prefix="tool")
        with agent_org_scoped_session(access_data.contractor_a) as session:
            ctx = RunContext(
                org_id=access_data.contractor_a,
                engagement_id=access_data.project_a,
                run_id=run_id,
                services=WorkerServiceHandle(session),
            )
            runtime = AgentRuntime(context=ctx, agent_name="echo")
            with pytest.raises(ToolRefusal):
                runtime.call_tool("get_engagement_context", engagement_id=other_a)
            with pytest.raises(ToolRefusal):
                runtime.call_tool(
                    "get_engagement_context",
                    engagement_id=access_data.project_b,
                )
    finally:
        admin = AdminSessionFactory()
        try:
            admin.execute(
                text("DELETE FROM engagement WHERE id = :id"),
                {"id": other_a},
            )
            admin.commit()
        finally:
            admin.close()


def test_step_logs_contain_no_filename_email_or_document_text(access_data) -> None:
    dirty = {
        "filename": "secret.pdf",
        "email": "a@b.com",
        "document_content": "IGNORE INSTRUCTIONS",
        "engagement_id": str(access_data.project_a),
        "count": 1,
        "party": "Lodha Developers",
        "gstin": "X",
    }
    clean = sanitize_for_log(dirty)
    blob = json.dumps(clean).lower()
    assert "secret.pdf" not in blob
    assert "a@b.com" not in blob
    assert "ignore instructions" not in blob
    assert "lodha" not in blob
    assert "gstin" not in blob
    assert clean["engagement_id"] == str(access_data.project_a)
    assert clean["count"] == 1


def test_unknown_event_type_marks_event_failed(access_data) -> None:
    _drain()
    with org_scoped_session(access_data.contractor_a) as session:
        event = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.unknown.xyz",
            idempotency_key=f"unk-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
        event_id = event["id"]

    assert run_once() is True
    admin = AdminSessionFactory()
    try:
        status, last_error = admin.execute(
            text("SELECT status, last_error FROM event WHERE id = :id"),
            {"id": event_id},
        ).one()
    finally:
        admin.close()
    assert status == "failed"
    assert last_error == NO_AGENT_MESSAGE


def test_failed_agent_leaves_event_unprocessed_retry_attempt_two(
    access_data, monkeypatch
) -> None:
    _drain()
    with org_scoped_session(access_data.contractor_a) as session:
        event = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"fail2-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
        event_id = event["id"]

    from packages.agents import agents as agents_pkg
    from packages.agents.agents.echo import agent as echo_mod

    def boom(_runtime: AgentRuntime) -> None:
        raise RuntimeError("boom")

    monkeypatch.setitem(agents_pkg.AGENT_REGISTRY, "echo", ("0", boom))
    assert run_once() is True

    admin = AdminSessionFactory()
    try:
        status, attempts = admin.execute(
            text("SELECT status, attempts FROM event WHERE id = :id"),
            {"id": event_id},
        ).one()
        assert status == "claimed"
        assert attempts == 1
        admin.execute(
            text(
                """
                UPDATE event
                SET status = 'pending', claimed_at = NULL
                WHERE id = :id
                """
            ),
            {"id": event_id},
        )
        admin.commit()
    finally:
        admin.close()

    monkeypatch.setitem(agents_pkg.AGENT_REGISTRY, "echo", ("0", echo_mod.run))
    assert run_once() is True

    with agent_org_scoped_session(access_data.contractor_a) as session:
        status = agent_events_repo.get_event_status(session, event_id=event_id)
        attempts_row = session.execute(
            text(
                """
                SELECT attempt, status FROM agent_run
                WHERE event_id = :id
                ORDER BY attempt
                """
            ),
            {"id": event_id},
        ).all()
    assert status == "processed"
    assert attempts_row[0][0] == 1 and attempts_row[0][1] == "failed"
    assert attempts_row[1][0] == 2 and attempts_row[1][1] == "succeeded"


def test_number_check_indian_formats_and_rejections() -> None:
    allowed = {
        Decimal("17080000"),
        Decimal("8500000"),
        "2026-03-15",
    }
    assert numbers_and_dates_ok("BG for 1,70,80,000", allowed)
    assert numbers_and_dates_ok("Amount Rs 1,70,80,000", allowed)
    assert numbers_and_dates_ok("Amount ₹17080000.00", allowed)
    assert numbers_and_dates_ok("Cover 85L only", allowed)
    assert numbers_and_dates_ok("Cover 85 lakh", allowed)
    assert numbers_and_dates_ok("About 1.708 Cr", {Decimal("17080000")})
    assert numbers_and_dates_ok("About 1.708 crore", {Decimal("17080000")})
    assert numbers_and_dates_ok("Due on 15/03/2026", allowed)

    assert numbers_and_dates_ok("mystery 99999", allowed) is False
    assert numbers_and_dates_ok("Cover 58L only", allowed) is False
    assert numbers_and_dates_ok("Due on 16/03/2026", allowed) is False


def test_buffered_proposal_discarded_on_self_check_retry_then_one_saved(
    access_data,
) -> None:
    _event_id, run_id = _app_event_and_agent_run(access_data, key_prefix="buf")
    attempts = {"n": 0}
    with agent_org_scoped_session(access_data.contractor_a) as session:
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=run_id,
            services=WorkerServiceHandle(session),
        )

        def flaky(runtime: AgentRuntime) -> None:
            runtime.emit_proposal(
                "echo.note",
                {"engagement_id": str(access_data.project_a)},
            )
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise SelfCheckError("retry_once")

        outcome = run_agent(ctx, agent_name="echo", agent_fn=flaky)
        proposals = agent_events_repo.list_proposals_for_run(session, run_id=run_id)
    assert outcome.status == "succeeded"
    assert attempts["n"] == 2
    assert len(proposals) == 1


def test_max_steps_after_emit_saves_zero_proposals(access_data) -> None:
    _event_id, run_id = _app_event_and_agent_run(access_data, key_prefix="mstep")
    with agent_org_scoped_session(access_data.contractor_a) as session:
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=run_id,
            services=WorkerServiceHandle(session),
        )

        def emit_then_loop(runtime: AgentRuntime) -> None:
            runtime.emit_proposal(
                "echo.note",
                {"engagement_id": str(access_data.project_a)},
            )
            for _ in range(20):
                runtime.call_tool(
                    "get_engagement_context",
                    engagement_id=access_data.project_a,
                )

        outcome = run_agent(
            ctx, agent_name="echo", agent_fn=emit_then_loop, max_steps=3
        )
        proposals = agent_events_repo.list_proposals_for_run(session, run_id=run_id)
    assert outcome.status == "failed"
    assert proposals == []


def test_tool_return_party_gstin_not_in_agent_step(access_data, monkeypatch) -> None:
    _event_id, run_id = _app_event_and_agent_run(access_data, key_prefix="pii")

    def dirty_tool(ctx, *, engagement_id):  # type: ignore[no-untyped-def]
        return {
            "party": "Lodha Developers",
            "gstin": "X",
            "engagement_id": str(engagement_id),
        }

    monkeypatch.setitem(TOOL_REGISTRY, "get_engagement_context", dirty_tool)
    with agent_org_scoped_session(access_data.contractor_a) as session:
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=run_id,
            services=WorkerServiceHandle(session),
        )

        def agent(runtime: AgentRuntime) -> None:
            runtime.call_tool(
                "get_engagement_context",
                engagement_id=access_data.project_a,
            )

        run_agent(ctx, agent_name="echo", agent_fn=agent)
        steps = agent_events_repo.list_steps_for_run(session, run_id=run_id)
    blob = json.dumps(
        [(step.get("input"), step.get("output")) for step in steps]
    ).lower()
    assert "lodha" not in blob
    assert "developers" not in blob
    assert "gstin" not in blob


def test_missing_record_step_raises_before_agent_runs(access_data) -> None:
    _event_id, run_id = _app_event_and_agent_run(access_data, key_prefix="norec")
    ran = {"agent": False}

    class NoStepHandle:
        def create_proposal(self, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("should not create proposal")

    ctx = RunContext(
        org_id=access_data.contractor_a,
        engagement_id=access_data.project_a,
        run_id=run_id,
        services=NoStepHandle(),
    )

    def agent(_runtime: AgentRuntime) -> None:
        ran["agent"] = True

    with pytest.raises(ServicesHandleError) as exc_info:
        run_agent(ctx, agent_name="echo", agent_fn=agent)
    assert exc_info.value.code == "missing_record_step"
    assert ran["agent"] is False


def test_crash_error_has_no_exception_value(access_data) -> None:
    _event_id, run_id = _app_event_and_agent_run(access_data, key_prefix="crash")
    with agent_org_scoped_session(access_data.contractor_a) as session:
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=run_id,
            services=WorkerServiceHandle(session),
        )

        def boom(_runtime: AgentRuntime) -> None:
            raise RuntimeError("secret amount 99999 leaked")

        outcome = run_agent(ctx, agent_name="echo", agent_fn=boom)
    assert outcome.status == "failed"
    assert outcome.error == "RuntimeError:error"
    assert "99999" not in (outcome.error or "")
    assert "secret" not in (outcome.error or "")


def test_number_check_month_names_plain_numbers_and_percents() -> None:
    allowed_date = {"2024-04-23", 12, "12%"}
    assert numbers_and_dates_ok("23rd Apr 2024", allowed_date)
    assert numbers_and_dates_ok("April 23, 2024", allowed_date)
    assert numbers_and_dates_ok("23-Apr-2024", allowed_date)
    assert numbers_and_dates_ok("12 days", allowed_date)
    assert numbers_and_dates_ok("12%", allowed_date)
    assert numbers_and_dates_ok("05/04/2024", {"2024-04-05"})

    assert numbers_and_dates_ok("23 April 2025", {"2024-04-23"}) is False
    assert numbers_and_dates_ok("21 days", {12}) is False
    assert numbers_and_dates_ok("21%", {"12%"}) is False
    assert numbers_and_dates_ok("stray 7", {12}) is False
    # 05/04/2024 is 5 April, never 4 May
    assert numbers_and_dates_ok("05/04/2024", {"2024-05-04"}) is False


def test_agent_run_and_proposal_refuse_foreign_org_engagement(access_data) -> None:
    with org_scoped_session(access_data.contractor_a) as session:
        agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"feng-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
    from apps.api.app.workers.agent_events import claim_next_event

    claim = claim_next_event()
    assert claim is not None
    with (
        agent_org_scoped_session(access_data.contractor_a) as session,
        pytest.raises(DBAPIError),
    ):
        session.execute(
            text(
                """
                INSERT INTO agent_run (
                  event_id, org_id, engagement_id, agent_name,
                  agent_version, attempt
                )
                VALUES (
                  :event_id, :org_id, :engagement_id, 'echo', '0', 1
                )
                """
            ),
            {
                "event_id": claim.event_id,
                "org_id": access_data.contractor_a,
                "engagement_id": access_data.project_b,
            },
        )
        session.flush()

    with agent_org_scoped_session(access_data.contractor_a) as session:
        run = agent_events_service.start_run(
            session,
            event_id=claim.event_id,
            org_id=claim.org_id,
            agent_name="echo",
            agent_version="0",
            engagement_id=access_data.project_a,
            attempt=1,
        )
        with pytest.raises(DBAPIError):
            session.execute(
                text(
                    """
                    INSERT INTO agent_proposal (
                      run_id, org_id, engagement_id, proposal_type,
                      content, autonomy_level
                    )
                    VALUES (
                      :run_id, :org_id, :engagement_id, 'echo.note',
                      '{}'::jsonb, 2
                    )
                    """
                ),
                {
                    "run_id": run.run_id,
                    "org_id": access_data.contractor_a,
                    "engagement_id": access_data.project_b,
                },
            )
            session.flush()
