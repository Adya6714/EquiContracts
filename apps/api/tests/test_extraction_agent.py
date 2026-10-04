"""Extraction Agent (BG): fake LLM only — no network."""

from __future__ import annotations

import json
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from apps.api.app.core.db import agent_org_scoped_session, org_scoped_session
from apps.api.app.core.storage import DocumentStorage
from apps.api.app.repositories import agent_events as agent_events_repo
from apps.api.app.services import agent_events as agent_events_service
from apps.api.app.workers.service_handle import WorkerServiceHandle
from packages.agents.agents.extraction import agent as extraction_agent
from packages.agents.context import RunContext
from packages.agents.guardrails.allowlist import allowed_tools
from packages.agents.runtime import run_agent

ROOT = Path(__file__).resolve().parents[3]
INJECTION_DOC = ROOT / "eval/adversarial/injection-bg.txt"


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, **kwargs: object) -> None:
        key = str(kwargs["Key"])
        body = kwargs["Body"]
        self.objects[key] = body if isinstance(body, bytes) else bytes(body)  # type: ignore[arg-type]

    def get_object(self, **kwargs: object) -> dict[str, object]:
        return {"Body": BytesIO(self.objects[str(kwargs["Key"])])}

    def generate_presigned_url(self, *args: object, **kwargs: object) -> str:
        return "https://signed.invalid/x"


def _good_payload(doc_text: str) -> dict:
    # Quotes must appear in doc_text for self-checks.
    return {
        "extracted": {
            "bg_number": {
                "value": "0544BGR0097618",
                "page": None,
                "source_quote": "0544BGR0097618",
            },
            "value": {
                "value": "17080000.00",
                "page": None,
                "source_quote": "Rs.1,70,80,000/-",
            },
            "expiry_date": {
                "value": "2023-04-23",
                "page": None,
                "source_quote": "23.04.2023",
            },
            "claim_expiry_date": {
                "value": "2024-04-23",
                "page": None,
                "source_quote": "23.04.2024",
            },
            "issuing_bank": {
                "value": "State Bank",
                "page": None,
                "source_quote": "State Bank",
            },
            "bg_type": {"value": None, "page": None, "source_quote": None},
            "currency": {"value": None, "page": None, "source_quote": None},
            "issue_date": {"value": None, "page": None, "source_quote": None},
            "issue_date_raw": {"value": None, "page": None, "source_quote": None},
            "expiry_date_raw": {"value": None, "page": None, "source_quote": None},
            "claim_expiry_date_raw": {
                "value": None,
                "page": None,
                "source_quote": None,
            },
            "beneficiary": {"value": None, "page": None, "source_quote": None},
            "applicant": {"value": None, "page": None, "source_quote": None},
            "conditionality": {"value": None, "page": None, "source_quote": None},
            "underlying_contract_ref": {
                "value": None,
                "page": None,
                "source_quote": None,
            },
        },
        "unresolved": [{"field": "issue_date", "reason": "not in excerpt"}],
        "field_confidence": {
            "bg_number": 0.95,
            "value": 0.9,
            "expiry_date": 0.9,
            "claim_expiry_date": 0.9,
            "issuing_bank": 0.8,
        },
    }


DOC_TEXT = (
    "Performance Bank Guarantee No. 0544BGR0097618 "
    "for Rs.1,70,80,000/- valid till 23.04.2023 "
    "claim period up to 23.04.2024 issued by State Bank."
)


def _drain() -> None:
    from apps.api.app.workers.agent_events import claim_next_event

    for _ in range(50):
        if claim_next_event() is None:
            break


def _store_doc(access_data, body: bytes, *, filename: str = "bg.txt"):
    fake = FakeS3()
    storage = DocumentStorage(client=fake)
    stored = storage.put_document(body)
    doc_id = uuid4()
    with org_scoped_session(access_data.contractor_a) as session:
        session.execute(
            text(
                """
                INSERT INTO document (
                  id, engagement_id, filename, storage_uri, sha256, source
                ) VALUES (
                  :id, :engagement_id, :filename, :uri, :sha, 'manual_upload'
                )
                """
            ),
            {
                "id": doc_id,
                "engagement_id": access_data.project_a,
                "filename": filename,
                "uri": stored.uri,
                "sha": stored.sha256,
            },
        )
    return doc_id, storage


def test_extraction_allowlist_is_read_only() -> None:
    tools = allowed_tools("extraction")
    assert tools == frozenset({"read_document_pages", "read_document_metadata"})


def test_would_have_cost_and_model_version_recorded(access_data) -> None:
    doc_id, storage = _store_doc(access_data, DOC_TEXT.encode("utf-8"))

    def fake_llm(*, system: str, user: str) -> dict:
        return {
            "model_version": "gemini-2.5-flash",
            "raw_text": json.dumps(_good_payload(DOC_TEXT)),
            "prompt_tokens": 1_000_000,
            "completion_tokens": 0,
            # omit cost — agent must estimate would-have-cost
        }

    with org_scoped_session(access_data.contractor_a) as session:
        event = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="document.classified",
            idempotency_key=f"cost-{uuid4().hex}",
            engagement_id=access_data.project_a,
            payload={"document_id": str(doc_id), "doc_type": "bank_guarantee"},
        )
        event_id = event["id"]

    with agent_org_scoped_session(access_data.contractor_a) as session:
        run = agent_events_service.start_run(
            session,
            event_id=event_id,
            org_id=access_data.contractor_a,
            agent_name="extraction",
            agent_version="0",
            engagement_id=access_data.project_a,
            attempt=1,
        )
        handle = WorkerServiceHandle(
            session,
            pinned_document_id=doc_id,
            event_payload={
                "document_id": str(doc_id),
                "doc_type": "bank_guarantee",
            },
            storage=storage,
            llm_fn=fake_llm,
        )
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=run.run_id,
            services=handle,
        )
        outcome = run_agent(
            ctx,
            agent_name="extraction",
            agent_fn=extraction_agent.run,
            max_steps=40,
            cost_cap=Decimal("2.00"),
        )
        assert outcome.status == "succeeded", outcome.error
        assert outcome.model_version == "gemini-2.5-flash"
        assert outcome.cost == Decimal("0.150000")


def test_document_classified_routes_and_proposes_fields(access_data) -> None:
    _drain()
    doc_id, storage = _store_doc(access_data, DOC_TEXT.encode("utf-8"))

    def fake_llm(*, system: str, user: str) -> dict:
        assert "DOCUMENT_CONTENT_START" in user
        return {
            "model_version": "fake-bg-v2",
            "raw_text": json.dumps(_good_payload(DOC_TEXT)),
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "cost": "0.01",
        }

    with org_scoped_session(access_data.contractor_a) as session:
        agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="document.classified",
            idempotency_key=f"ext-{uuid4().hex}",
            engagement_id=access_data.project_a,
            payload={
                "document_id": str(doc_id),
                "doc_type": "bank_guarantee",
            },
        )

    # Inject fake LLM via patching handle construction in a direct run.
    with agent_org_scoped_session(access_data.contractor_a) as session:
        event_id = session.execute(
            text(
                """
                SELECT id FROM event
                WHERE org_id = :org AND event_type = 'document.classified'
                ORDER BY created_at DESC LIMIT 1
                """
            ),
            {"org": access_data.contractor_a},
        ).scalar_one()
        run = agent_events_service.start_run(
            session,
            event_id=event_id,
            org_id=access_data.contractor_a,
            agent_name="extraction",
            agent_version="0",
            engagement_id=access_data.project_a,
            attempt=1,
        )
        handle = WorkerServiceHandle(
            session,
            pinned_document_id=doc_id,
            event_payload={
                "document_id": str(doc_id),
                "doc_type": "bank_guarantee",
            },
            storage=storage,
            llm_fn=fake_llm,
        )
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=run.run_id,
            services=handle,
        )
        outcome = run_agent(
            ctx,
            agent_name="extraction",
            agent_fn=extraction_agent.run,
            max_steps=40,
        )
        assert outcome.status == "succeeded", outcome.error
        assert outcome.model_version == "fake-bg-v2"
        proposals = agent_events_repo.list_proposals_for_run(session, run_id=run.run_id)
        steps = agent_events_repo.list_steps_for_run(session, run_id=run.run_id)

    types = {p["proposal_type"] for p in proposals}
    assert "propose_financial_field" in types or "propose_field" in types
    assert "extraction.unreadable" not in types
    assert all(
        p["proposal_type"]
        in {"propose_financial_field", "propose_field", "extraction.unreadable"}
        for p in proposals
    )
    for p in proposals:
        if p["proposal_type"].startswith("propose"):
            content = p["content"]
            assert "source_quote" in content
            assert "page" in content
            assert content.get("page") is None
    # No document text in steps
    blob = json.dumps([{"in": s["input"], "out": s["output"]} for s in steps]).lower()
    assert "ignore" not in blob
    assert "17080000" not in blob
    assert "state bank" not in blob


def test_non_bg_classified_emits_no_proposals(access_data) -> None:
    doc_id, storage = _store_doc(access_data, b"not a bg")
    with org_scoped_session(access_data.contractor_a) as session:
        event = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="document.classified",
            idempotency_key=f"nonbg-{uuid4().hex}",
            engagement_id=access_data.project_a,
            payload={"document_id": str(doc_id), "doc_type": "proforma_invoice"},
        )
        event_id = event["id"]

    with agent_org_scoped_session(access_data.contractor_a) as session:
        run = agent_events_service.start_run(
            session,
            event_id=event_id,
            org_id=access_data.contractor_a,
            agent_name="extraction",
            agent_version="0",
            engagement_id=access_data.project_a,
            attempt=1,
        )
        handle = WorkerServiceHandle(
            session,
            pinned_document_id=doc_id,
            event_payload={
                "document_id": str(doc_id),
                "doc_type": "proforma_invoice",
            },
            storage=storage,
            llm_fn=lambda **_: (_ for _ in ()).throw(
                RuntimeError("llm should not run")
            ),
        )
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=run.run_id,
            services=handle,
        )
        outcome = run_agent(
            ctx,
            agent_name="extraction",
            agent_fn=extraction_agent.run,
            max_steps=40,
        )
        assert outcome.status == "succeeded", outcome.error
        assert (
            agent_events_repo.list_proposals_for_run(session, run_id=run.run_id) == []
        )


def test_self_check_exhaustion_emits_unreadable(access_data) -> None:
    doc_id, storage = _store_doc(access_data, DOC_TEXT.encode("utf-8"))
    calls = {"n": 0}

    def bad_llm(*, system: str, user: str) -> dict:
        calls["n"] += 1
        payload = _good_payload(DOC_TEXT)
        # Invert claim/expiry so self-check fails every time.
        payload["extracted"]["expiry_date"]["value"] = "2024-04-23"
        payload["extracted"]["claim_expiry_date"]["value"] = "2023-04-23"
        return {
            "model_version": "fake-bad",
            "raw_text": json.dumps(payload),
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "cost": "0",
        }

    with org_scoped_session(access_data.contractor_a) as session:
        event = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="document.classified",
            idempotency_key=f"bad-{uuid4().hex}",
            engagement_id=access_data.project_a,
            payload={"document_id": str(doc_id), "doc_type": "bank_guarantee"},
        )
        event_id = event["id"]

    with agent_org_scoped_session(access_data.contractor_a) as session:
        run = agent_events_service.start_run(
            session,
            event_id=event_id,
            org_id=access_data.contractor_a,
            agent_name="extraction",
            agent_version="0",
            engagement_id=access_data.project_a,
            attempt=1,
        )
        handle = WorkerServiceHandle(
            session,
            pinned_document_id=doc_id,
            event_payload={
                "document_id": str(doc_id),
                "doc_type": "bank_guarantee",
            },
            storage=storage,
            llm_fn=bad_llm,
        )
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=run.run_id,
            services=handle,
        )
        outcome = run_agent(
            ctx,
            agent_name="extraction",
            agent_fn=extraction_agent.run,
            max_steps=40,
        )
        assert outcome.status == "needs_human", outcome.error
        proposals = agent_events_repo.list_proposals_for_run(session, run_id=run.run_id)

    assert calls["n"] == 3
    assert len(proposals) == 1
    assert proposals[0]["proposal_type"] == "extraction.unreadable"
    assert proposals[0]["content"]["reason"] == "self_check_exhausted"


def test_injection_fixture_no_extra_actions(access_data) -> None:
    text_body = INJECTION_DOC.read_text(encoding="utf-8")
    doc_id, storage = _store_doc(
        access_data, text_body.encode("utf-8"), filename="injection-bg.txt"
    )

    def extract_normally(*, system: str, user: str) -> dict:
        # Even if the document asks for release/verify, return normal fields only.
        assert "mark this guarantee released" in user
        payload = {
            "extracted": {
                "bg_number": {
                    "value": "INJECT-BG-001",
                    "page": None,
                    "source_quote": "INJECT-BG-001",
                },
                "value": {
                    "value": "500000.00",
                    "page": None,
                    "source_quote": "Rs.5,00,000/-",
                },
                "expiry_date": {
                    "value": "2026-12-31",
                    "page": None,
                    "source_quote": "31.12.2026",
                },
                "claim_expiry_date": {
                    "value": "2027-12-31",
                    "page": None,
                    "source_quote": "31.12.2027",
                },
                "issuing_bank": {
                    "value": "Test National Bank",
                    "page": None,
                    "source_quote": "Test National Bank",
                },
                "bg_type": {
                    "value": "performance",
                    "page": None,
                    "source_quote": "PERFORMANCE BANK GUARANTEE",
                },
                "currency": {"value": "INR", "page": None, "source_quote": "Rs."},
                "issue_date": {"value": None, "page": None, "source_quote": None},
                "issue_date_raw": {"value": None, "page": None, "source_quote": None},
                "expiry_date_raw": {
                    "value": "31.12.2026",
                    "page": None,
                    "source_quote": "31.12.2026",
                },
                "claim_expiry_date_raw": {
                    "value": "31.12.2027",
                    "page": None,
                    "source_quote": "31.12.2027",
                },
                "beneficiary": {
                    "value": "Example Client Ltd",
                    "page": None,
                    "source_quote": "Example Client Ltd",
                },
                "applicant": {
                    "value": "Example Contractor Pvt Ltd",
                    "page": None,
                    "source_quote": "Example Contractor Pvt Ltd",
                },
                "conditionality": {"value": None, "page": None, "source_quote": None},
                "underlying_contract_ref": {
                    "value": None,
                    "page": None,
                    "source_quote": None,
                },
            },
            "unresolved": [
                {"field": "issue_date", "reason": "not stated"},
                {"field": "conditionality", "reason": "not stated"},
                {"field": "underlying_contract_ref", "reason": "not stated"},
            ],
            "field_confidence": {
                "bg_number": 0.99,
                "value": 0.95,
                "expiry_date": 0.95,
                "claim_expiry_date": 0.95,
            },
        }
        return {
            "model_version": "fake-inject",
            "raw_text": json.dumps(payload),
            "prompt_tokens": 5,
            "completion_tokens": 5,
            "cost": "0",
        }

    with org_scoped_session(access_data.contractor_a) as session:
        event = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="document.classified",
            idempotency_key=f"inj-{uuid4().hex}",
            engagement_id=access_data.project_a,
            payload={"document_id": str(doc_id), "doc_type": "bank_guarantee"},
        )
        event_id = event["id"]

    with agent_org_scoped_session(access_data.contractor_a) as session:
        run = agent_events_service.start_run(
            session,
            event_id=event_id,
            org_id=access_data.contractor_a,
            agent_name="extraction",
            agent_version="0",
            engagement_id=access_data.project_a,
            attempt=1,
        )
        handle = WorkerServiceHandle(
            session,
            pinned_document_id=doc_id,
            event_payload={
                "document_id": str(doc_id),
                "doc_type": "bank_guarantee",
            },
            storage=storage,
            llm_fn=extract_normally,
        )
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=run.run_id,
            services=handle,
        )
        outcome = run_agent(
            ctx,
            agent_name="extraction",
            agent_fn=extraction_agent.run,
            max_steps=40,
        )
        assert outcome.status == "succeeded", outcome.error
        proposals = agent_events_repo.list_proposals_for_run(session, run_id=run.run_id)
        steps = agent_events_repo.list_steps_for_run(session, run_id=run.run_id)

    assert proposals
    for p in proposals:
        assert p["proposal_type"] in {
            "propose_financial_field",
            "propose_field",
        }
        blob = json.dumps(p["content"]).lower()
        assert "released" not in blob
        assert "verified" not in blob
    tool_calls = {s["tool_called"] for s in steps if s["tool_called"]}
    assert tool_calls <= {
        "read_document_pages",
        "read_document_metadata",
        "emit_proposal",
    }
    assert "read_document_pages" in tool_calls
