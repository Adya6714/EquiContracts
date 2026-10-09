"""Intake Agent: classify document type + evidence weight (Level 2 proposals)."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from packages.agents.follow_ups import handoff_threshold
from packages.agents.runtime import AgentRuntime
from packages.extraction.llm_pricing import estimate_would_have_cost

AGENT_NAME = "intake"
AGENT_VERSION = "0"

DOCUMENT_TYPES = frozenset(
    {
        "bank_guarantee",
        "work_order",
        "proforma_invoice",
        "certified_ra_bill",
        "measurement_sheet_annexure",
        "work_completion_certificate",
        "warranty_document",
        "payment_reconciliation",
        "delay_site_instruction_mom",
        "email",
        "resolution_statement",
        "other",
    }
)
EVIDENCE_WEIGHTS = frozenset({"routine", "core_evidence", "potential_dispute"})
DISPUTE_SIGNAL_CODES = frozenset(
    {
        "blame",
        "defect",
        "debit_note",
        "reminder_escalation",
        "legal_tone",
        "refusal_to_pay",
        "deadline_pressure",
        "third_party_pressure",
    }
)
DISPUTE_BIAS_THRESHOLD = Decimal("0.40")
MAX_INTAKE_CHARS = 12_000
DOCUMENT_START = "<<<DOCUMENT_CONTENT_START>>>"
DOCUMENT_END = "<<<DOCUMENT_CONTENT_END>>>"

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "intake.v1.md"
_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def run(runtime: AgentRuntime) -> None:
    services = runtime.context.services
    payload = getattr(services, "event_payload", None) or {}
    if not isinstance(payload, dict):
        payload = {}

    raw_doc_id = payload.get("document_id")
    if raw_doc_id is None:
        runtime.emit_proposal(
            "propose_classification",
            {
                "document_id": None,
                "doc_type": "other",
                "evidence_weight": "routine",
                "confidence": "0",
                "dispute_signals": [],
                "reason_code": "missing_document_id",
            },
            confidence=Decimal("0"),
        )
        runtime.finish_needs_human("missing_document_id")

    document_id = UUID(str(raw_doc_id))
    runtime.call_tool("read_document_metadata", document_id=document_id)
    pages_result = runtime.call_tool("read_document_pages", document_id=document_id)
    pages = pages_result.get("pages") or []
    document_text = "\n\n".join(
        str(page.get("text") or "") for page in pages if isinstance(page, dict)
    ).strip()
    document_text = document_text[:MAX_INTAKE_CHARS]

    system = _PROMPT_PATH.read_text(encoding="utf-8")
    user = (
        f"{DOCUMENT_START}\n{document_text}\n{DOCUMENT_END}\n\n"
        "Classify the document. JSON only."
    )
    model_version, raw_text, prompt_tokens, completion_tokens = _call_llm(
        runtime, system=system, user=user
    )
    runtime.model_version = model_version
    runtime.record_llm_usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )

    parsed = _parse_model_json(raw_text)
    content, confidence, needs_human, human_code = _normalise_classification(
        document_id=document_id,
        parsed=parsed,
    )
    runtime.emit_proposal(
        "propose_classification",
        content,
        confidence=confidence,
    )
    if needs_human:
        runtime.finish_needs_human(human_code)


def _call_llm(
    runtime: AgentRuntime, *, system: str, user: str
) -> tuple[str, str, int, int]:
    services = runtime.context.services
    call = getattr(services, "call_intake_llm", None)
    if call is None:
        raise RuntimeError("missing_call_intake_llm")
    result = call(system=system, user=user)
    if not isinstance(result, dict):
        raise RuntimeError("invalid_llm_result")
    model_version = str(result.get("model_version") or "unknown")
    raw_text = str(result.get("raw_text") or "")
    prompt_tokens = int(result.get("prompt_tokens") or 0)
    completion_tokens = int(result.get("completion_tokens") or 0)
    if result.get("cost") is not None:
        runtime.add_cost(Decimal(str(result["cost"])))
    else:
        runtime.add_cost(
            estimate_would_have_cost(
                model_version,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        )
    return model_version, raw_text, prompt_tokens, completion_tokens


def _parse_model_json(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        return {}
    match = _JSON_FENCE.search(text)
    if match:
        text = match.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}


def _normalise_classification(
    *,
    document_id: UUID,
    parsed: dict[str, Any],
) -> tuple[dict[str, Any], Decimal, bool, str]:
    raw_type = str(parsed.get("doc_type") or "").strip()
    doc_type = raw_type if raw_type in DOCUMENT_TYPES else "other"

    confidence = _as_decimal(parsed.get("confidence"), default=Decimal("0"))
    if confidence < 0:
        confidence = Decimal("0")
    if confidence > 1:
        confidence = Decimal("1")

    dispute_score = _as_decimal(parsed.get("dispute_score"), default=Decimal("0"))
    signals = _clean_signals(parsed.get("dispute_signals"))

    weight = str(parsed.get("evidence_weight") or "").strip()
    if weight not in EVIDENCE_WEIGHTS:
        weight = "routine"
    # Content-driven dispute bias — never copy weight from doc_type.
    if dispute_score >= DISPUTE_BIAS_THRESHOLD:
        weight = "potential_dispute"

    reason = str(parsed.get("reason_code") or "unspecified").strip() or "unspecified"
    reason = re.sub(r"[^a-zA-Z0-9_./-]", "_", reason)[:64]

    content: dict[str, Any] = {
        "document_id": str(document_id),
        "doc_type": doc_type,
        "evidence_weight": weight,
        "confidence": str(confidence),
        "dispute_signals": signals,
        "reason_code": reason,
    }

    threshold = handoff_threshold()
    if doc_type == "other":
        return content, confidence, True, "unknown_doc_type"
    if confidence < threshold:
        return content, confidence, True, "low_confidence"
    return content, confidence, False, ""


def _as_decimal(value: Any, *, default: Decimal) -> Decimal:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _clean_signals(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        code = str(item or "").strip()
        if code in DISPUTE_SIGNAL_CODES and code not in out:
            out.append(code)
    return out
