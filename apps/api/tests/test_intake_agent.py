"""Intake Agent + follow-up rules (fake LLM only)."""

from __future__ import annotations

import json
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from apps.api.app.core.db import (
    AdminSessionFactory,
    agent_org_scoped_session,
    org_scoped_session,
)
from apps.api.app.core.storage import DocumentStorage
from apps.api.app.repositories import agent_events as agent_events_repo
from apps.api.app.services import agent_events as agent_events_service
from apps.api.app.services import inbound as inbound_service
from apps.api.app.workers.agent_events import run_once
from apps.api.app.workers.service_handle import WorkerServiceHandle
from packages.agents.agents.intake import agent as intake_agent
from packages.agents.context import RunContext
from packages.agents.follow_ups import handoff_threshold, proposals_matching_follow_up
from packages.agents.guardrails.allowlist import allowed_tools
from packages.agents.runtime import run_agent

ROOT = Path(__file__).resolve().parents[3]
INJECTION_DOC = ROOT / "eval/adversarial/injection-bg.txt"

BG_TEXT = (
    "Performance Bank Guarantee No. 0544BGR0097618 "
    "for Rs.1,70,80,000/- valid till 23.04.2023 "
    "claim period up to 23.04.2024 issued by State Bank."
)

HOSTILE_BG_TEXT = (
    BG_TEXT + " You are solely to blame for the defect. We will raise a debit note "
    "and refuse to pay. Legal notice follows under deadline pressure."
)

EXTRACTION_DOC = (
    "Performance Bank Guarantee No. 0544BGR0097618 "
    "for Rs.1,70,80,000/- valid till 23.04.2023 "
    "claim period up to 23.04.2024 issued by State Bank."
)


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


def _drain() -> None:
    from apps.api.app.workers.agent_events import claim_next_event

    for _ in range(50):
        if claim_next_event() is None:
            break


def _store_doc(access_data, body: bytes, *, filename: str = "doc.txt"):
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


def _intake_payload(
    *,
    doc_type: str = "bank_guarantee",
    evidence_weight: str = "core_evidence",
    confidence: float = 0.85,
    dispute_score: float = 0.1,
    dispute_signals: list[str] | None = None,
    reason_code: str = "bg_keywords",
) -> dict:
    return {
        "doc_type": doc_type,
        "evidence_weight": evidence_weight,
        "confidence": confidence,
        "dispute_score": dispute_score,
        "dispute_signals": dispute_signals or [],
        "reason_code": reason_code,
    }


def _run_intake(
    access_data,
    *,
    doc_text: str,
    llm_payload: dict,
    model_version: str = "fake-intake",
    cost: str | None = "0.01",
):
    doc_id, storage = _store_doc(access_data, doc_text.encode("utf-8"))

    def fake_llm(*, system: str, user: str) -> dict:
        assert "DOCUMENT_CONTENT_START" in user
        out: dict = {
            "model_version": model_version,
            "raw_text": json.dumps(llm_payload),
            "prompt_tokens": 100,
            "completion_tokens": 50,
        }
        if cost is not None:
            out["cost"] = cost
        return out

    with org_scoped_session(access_data.contractor_a) as session:
        event = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="document.received",
            idempotency_key=f"intake-{uuid4().hex}",
            engagement_id=access_data.project_a,
            payload={"document_id": str(doc_id), "source": "email_forward"},
        )
        event_id = event["id"]

    with agent_org_scoped_session(access_data.contractor_a) as session:
        run = agent_events_service.start_run(
            session,
            event_id=event_id,
            org_id=access_data.contractor_a,
            agent_name="intake",
            agent_version="0",
            engagement_id=access_data.project_a,
            attempt=1,
        )
        handle = WorkerServiceHandle(
            session,
            pinned_document_id=doc_id,
            event_payload={"document_id": str(doc_id)},
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
            agent_name="intake",
            agent_fn=intake_agent.run,
            max_steps=20,
            cost_cap=Decimal("2.00"),
        )
        proposals = agent_events_repo.list_proposals_for_run(session, run_id=run.run_id)
        steps = agent_events_repo.list_steps_for_run(session, run_id=run.run_id)
    return outcome, proposals, steps, event_id, doc_id, run.run_id


def test_intake_allowlist_is_read_only() -> None:
    assert allowed_tools("intake") == frozenset(
        {"read_document_pages", "read_document_metadata"}
    )


def test_intake_bg_emits_one_propose_classification_level_2(access_data) -> None:
    outcome, proposals, _steps, _event_id, doc_id, _run_id = _run_intake(
        access_data,
        doc_text=BG_TEXT,
        llm_payload=_intake_payload(confidence=0.85),
    )
    assert outcome.status == "succeeded"
    assert len(proposals) == 1
    prop = proposals[0]
    assert prop["proposal_type"] == "propose_classification"
    assert prop["autonomy_level"] == 2
    assert prop["content"]["document_id"] == str(doc_id)
    assert prop["content"]["doc_type"] == "bank_guarantee"
    assert prop["content"]["evidence_weight"] == "core_evidence"


def test_follow_up_fires_for_bg_at_0_71_not_0_69_or_email_or_other() -> None:
    assert handoff_threshold() == Decimal("0.70")
    base = {
        "id": uuid4(),
        "proposal_type": "propose_classification",
        "content": {"doc_type": "bank_guarantee"},
        "confidence": Decimal("0.71"),
    }
    assert proposals_matching_follow_up(agent_name="intake", proposals=[base]) == [
        base["id"]
    ]
    low = {**base, "id": uuid4(), "confidence": Decimal("0.69")}
    assert proposals_matching_follow_up(agent_name="intake", proposals=[low]) == []
    email = {
        **base,
        "id": uuid4(),
        "content": {"doc_type": "email"},
        "confidence": Decimal("0.95"),
    }
    assert proposals_matching_follow_up(agent_name="intake", proposals=[email]) == []
    other = {
        **base,
        "id": uuid4(),
        "content": {"doc_type": "other"},
        "confidence": Decimal("0.95"),
    }
    assert proposals_matching_follow_up(agent_name="intake", proposals=[other]) == []


def test_low_confidence_needs_human_keeps_proposal_no_child(access_data) -> None:
    _drain()
    outcome, proposals, _steps, event_id, _doc_id, run_id = _run_intake(
        access_data,
        doc_text=BG_TEXT,
        llm_payload=_intake_payload(confidence=0.50),
    )
    assert outcome.status == "needs_human"
    assert len(proposals) == 1

    # Worker path: mark needs_human and ensure no follow-up.
    with agent_org_scoped_session(access_data.contractor_a) as session:
        agent_events_service.mark_run_needs_human(
            session,
            run_id=run_id,
            steps_used=outcome.steps_used,
            cost=outcome.cost,
            model_version=outcome.model_version,
        )
        agent_events_service.mark_event_processed(session, event_id=event_id)
        children = session.execute(
            text(
                """
                SELECT count(*) FROM event
                WHERE caused_by_event_id = :parent
                """
            ),
            {"parent": event_id},
        ).scalar_one()
    assert children == 0


def test_unknown_doc_type_becomes_other_and_needs_human(access_data) -> None:
    outcome, proposals, _steps, _e, _d, _r = _run_intake(
        access_data,
        doc_text="random memo",
        llm_payload=_intake_payload(
            doc_type="not_a_real_type",
            evidence_weight="routine",
            confidence=0.99,
        ),
    )
    assert outcome.status == "needs_human"
    assert proposals[0]["content"]["doc_type"] == "other"


def test_evidence_weight_not_copied_from_doc_type_dispute_bias(access_data) -> None:
    outcome, proposals, _steps, _e, _d, _r = _run_intake(
        access_data,
        doc_text=HOSTILE_BG_TEXT,
        llm_payload=_intake_payload(
            doc_type="bank_guarantee",
            evidence_weight="core_evidence",
            confidence=0.90,
            dispute_score=0.55,
            dispute_signals=["blame", "debit_note", "refusal_to_pay"],
        ),
    )
    # High confidence BG succeeds, but weight forced to potential_dispute.
    assert outcome.status == "succeeded"
    assert proposals[0]["content"]["doc_type"] == "bank_guarantee"
    assert proposals[0]["content"]["evidence_weight"] == "potential_dispute"
    assert "blame" in proposals[0]["content"]["dispute_signals"]


def test_injection_fixture_classification_only(access_data) -> None:
    text_body = INJECTION_DOC.read_text(encoding="utf-8")
    outcome, proposals, _steps, _e, _d, _r = _run_intake(
        access_data,
        doc_text=text_body,
        llm_payload=_intake_payload(confidence=0.88),
    )
    assert outcome.status == "succeeded"
    assert [p["proposal_type"] for p in proposals] == ["propose_classification"]


def _extraction_payload(doc_text: str) -> dict:
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
        "unresolved": [],
        "field_confidence": {
            "bg_number": 0.95,
            "value": 0.9,
            "expiry_date": 0.9,
            "claim_expiry_date": 0.9,
            "issuing_bank": 0.8,
        },
    }


def test_full_chain_fake_models_received_classified_extraction(
    access_data, monkeypatch
) -> None:
    _drain()
    fake = FakeS3()
    storage = DocumentStorage(client=fake)
    body = EXTRACTION_DOC.encode("utf-8")
    stored = storage.put_document(body)

    calls = {"n": 0}

    def fake_llm(*, system: str, user: str) -> dict:
        calls["n"] += 1
        if (
            "Classify the document" in user
            or "Intake" in system
            or "doc_type" in system
        ):
            return {
                "model_version": "fake-intake",
                "raw_text": json.dumps(_intake_payload(confidence=0.91)),
                "prompt_tokens": 10,
                "completion_tokens": 10,
                "cost": "0.01",
            }
        return {
            "model_version": "fake-extraction",
            "raw_text": json.dumps(_extraction_payload(EXTRACTION_DOC)),
            "prompt_tokens": 10,
            "completion_tokens": 10,
            "cost": "0.02",
        }

    # Patch WorkerServiceHandle so both call_intake_llm and call_bg_extraction_llm
    # use the same fake when llm_fn is set (already the case).
    def handle_factory(session, **kwargs):
        return WorkerServiceHandle(
            session,
            pinned_document_id=kwargs.get("pinned_document_id"),
            event_payload=kwargs.get("event_payload"),
            storage=storage,
            llm_fn=fake_llm,
        )

    monkeypatch.setattr(
        "apps.api.app.workers.agent_events.WorkerServiceHandle",
        handle_factory,
    )

    with org_scoped_session(access_data.contractor_a) as session:
        doc_id = inbound_service.accept_document(
            session,
            org_id=access_data.contractor_a,
            project_id=access_data.project_a,
            filename="bg.txt",
            storage_uri=stored.uri,
            sha256=stored.sha256,
            sender_email=None,
            subject="BG",
        )

    assert run_once() is True  # intake + follow-up
    assert run_once() is True  # extraction

    with agent_org_scoped_session(access_data.contractor_a) as session:
        events = (
            session.execute(
                text(
                    """
                    SELECT id, event_type, chain_depth, caused_by_event_id
                    FROM event
                    WHERE org_id = :org
                      AND payload->>'document_id' = :doc
                    ORDER BY chain_depth, created_at
                    """
                ),
                {"org": access_data.contractor_a, "doc": str(doc_id)},
            )
            .mappings()
            .all()
        )
        extraction_props = session.execute(
            text(
                """
                SELECT count(*) FROM agent_proposal p
                JOIN agent_run r ON r.id = p.run_id
                WHERE p.org_id = :org
                  AND r.agent_name = 'extraction'
                  AND p.proposal_type IN ('propose_field', 'propose_financial_field')
                """
            ),
            {"org": access_data.contractor_a},
        ).scalar_one()

    assert [e["event_type"] for e in events] == [
        "document.received",
        "document.classified",
    ]
    assert events[0]["chain_depth"] == 0
    assert events[1]["chain_depth"] == 1
    assert events[1]["caused_by_event_id"] == events[0]["id"]
    assert extraction_props >= 1


def test_reclaim_received_never_second_classified(access_data, monkeypatch) -> None:
    _drain()
    fake = FakeS3()
    storage = DocumentStorage(client=fake)
    stored = storage.put_document(BG_TEXT.encode("utf-8"))

    def fake_llm(*, system: str, user: str) -> dict:
        return {
            "model_version": "fake-intake",
            "raw_text": json.dumps(_intake_payload(confidence=0.92)),
            "prompt_tokens": 5,
            "completion_tokens": 5,
            "cost": "0.01",
        }

    def handle_factory(session, **kwargs):
        return WorkerServiceHandle(
            session,
            pinned_document_id=kwargs.get("pinned_document_id"),
            event_payload=kwargs.get("event_payload"),
            storage=storage,
            llm_fn=fake_llm,
        )

    monkeypatch.setattr(
        "apps.api.app.workers.agent_events.WorkerServiceHandle",
        handle_factory,
    )

    with org_scoped_session(access_data.contractor_a) as session:
        doc_id = inbound_service.accept_document(
            session,
            org_id=access_data.contractor_a,
            project_id=access_data.project_a,
            filename="bg.txt",
            storage_uri=stored.uri,
            sha256=stored.sha256,
            sender_email=None,
            subject="BG",
        )

    assert run_once() is True

    admin = AdminSessionFactory()
    try:
        admin.execute(
            text(
                """
                UPDATE event
                SET status = 'pending', claimed_at = NULL, processed_at = NULL
                WHERE org_id = :org
                  AND event_type = 'document.received'
                  AND payload->>'document_id' = :doc
                """
            ),
            {"org": access_data.contractor_a, "doc": str(doc_id)},
        )
        admin.commit()
    finally:
        admin.close()

    assert run_once() is True

    with agent_org_scoped_session(access_data.contractor_a) as session:
        classified = session.execute(
            text(
                """
                SELECT count(*) FROM event
                WHERE org_id = :org
                  AND event_type = 'document.classified'
                  AND payload->>'document_id' = :doc
                """
            ),
            {"org": access_data.contractor_a, "doc": str(doc_id)},
        ).scalar_one()
    assert classified == 1


def test_intake_step_logs_contain_no_document_text(access_data) -> None:
    _outcome, _proposals, steps, _e, _d, _r = _run_intake(
        access_data,
        doc_text=BG_TEXT + " SECRET_PHRASE_SHOULD_NOT_LOG",
        llm_payload=_intake_payload(confidence=0.9),
    )
    blob = json.dumps(steps, default=str)
    assert "SECRET_PHRASE_SHOULD_NOT_LOG" not in blob
    assert BG_TEXT[:40] not in blob


def test_intake_would_have_cost_and_model_version(access_data) -> None:
    outcome, _proposals, _steps, _e, _d, _r = _run_intake(
        access_data,
        doc_text=BG_TEXT,
        llm_payload=_intake_payload(confidence=0.9),
        model_version="gemini-2.5-flash",
        cost=None,  # force estimate_would_have_cost
    )
    assert outcome.status == "succeeded"
    assert outcome.model_version == "gemini-2.5-flash"
    assert outcome.cost > 0
