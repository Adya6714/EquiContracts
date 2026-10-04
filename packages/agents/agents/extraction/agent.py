"""Extraction Agent (BG only): read pages, call LLM, self-check, propose fields."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from packages.agents.runtime import AgentRuntime
from packages.extraction.bg_extractor import (
    BankGuaranteeExtraction,
    build_user_message,
    is_financial_field,
    load_system_prompt,
    parse_extraction_payload,
    parse_model_json,
)
from packages.extraction.llm_pricing import estimate_would_have_cost
from packages.extraction.self_checks import run_bg_self_checks

AGENT_NAME = "extraction"
AGENT_VERSION = "0"

_BG_TYPES = frozenset({"bank_guarantee", "bg_document"})
_MAX_SELF_CHECK_ATTEMPTS = 3  # initial + 2 retries


def run(runtime: AgentRuntime) -> None:
    services = runtime.context.services
    payload = getattr(services, "event_payload", None) or {}
    if not isinstance(payload, dict):
        payload = {}

    doc_type = str(payload.get("doc_type") or payload.get("category") or "")
    if doc_type not in _BG_TYPES:
        return

    raw_doc_id = payload.get("document_id")
    if raw_doc_id is None:
        runtime.emit_proposal(
            "extraction.unreadable",
            {"reason": "missing_document_id"},
            confidence=None,
        )
        runtime.finish_needs_human("missing_document_id")

    document_id = UUID(str(raw_doc_id))
    pages_result = runtime.call_tool("read_document_pages", document_id=document_id)
    pages = pages_result.get("pages") or []
    document_text = "\n\n".join(
        str(page.get("text") or "") for page in pages if isinstance(page, dict)
    ).strip()
    if not document_text:
        runtime.emit_proposal(
            "extraction.unreadable",
            {
                "document_id": str(document_id),
                "reason": "empty_text",
            },
            confidence=None,
        )
        runtime.finish_needs_human("empty_text")

    system = load_system_prompt()
    feedback: list[str] = []
    last_codes: list[str] = []

    for _attempt in range(_MAX_SELF_CHECK_ATTEMPTS):
        user = build_user_message(document_text)
        if feedback:
            user = (
                user
                + "\n\nPrevious extraction failed self-check: "
                + ", ".join(feedback)
                + ". Fix these fields. Do not invent values."
            )
        model_version, raw_text, prompt_tokens, completion_tokens = _call_llm(
            runtime, system=system, user=user
        )
        runtime.model_version = model_version
        runtime.record_llm_usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        try:
            parsed = parse_model_json(raw_text)
            extraction = parse_extraction_payload(parsed, model_version=model_version)
        except (ValueError, TypeError, KeyError):
            last_codes = ["parse_error"]
            feedback = last_codes
            continue

        codes = run_bg_self_checks(extraction, document_text)
        if not codes:
            _emit_field_proposals(runtime, document_id, extraction)
            return
        last_codes = codes
        feedback = codes
        runtime.discard_proposals()

    runtime.discard_proposals()
    runtime.emit_proposal(
        "extraction.unreadable",
        {
            "document_id": str(document_id),
            "reason": "self_check_exhausted",
            "failed_checks": last_codes,
        },
        confidence=None,
    )
    runtime.finish_needs_human("self_check_exhausted")


def _call_llm(
    runtime: AgentRuntime, *, system: str, user: str
) -> tuple[str, str, int, int]:
    services = runtime.context.services
    call = getattr(services, "call_bg_extraction_llm", None)
    if call is None:
        raise RuntimeError("missing_call_bg_extraction_llm")
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


def _emit_field_proposals(
    runtime: AgentRuntime,
    document_id: UUID,
    extraction: BankGuaranteeExtraction,
) -> None:
    for field in extraction.fields:
        proposal_type = (
            "propose_financial_field"
            if field.is_financial or is_financial_field(field.field_name)
            else "propose_field"
        )
        content: dict[str, Any] = {
            "document_id": str(document_id),
            "field_name": field.field_name,
            "value": field.field_value,
            "page": field.page,
            "source_quote": field.source_quote,
            "is_financial": field.is_financial,
        }
        if field.unresolved_reason is not None:
            content["unresolved_reason"] = field.unresolved_reason
        runtime.emit_proposal(
            proposal_type,
            content,
            confidence=field.confidence,
        )
