"""Bank guarantee extraction — one document type only."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from .document_text import load_document_text
from .llm_config import get_llm_settings

ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "bank_guarantee.v2.md"
SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "bank_guarantee.json"

_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
BG_FINANCIAL_FIELDS = frozenset(_SCHEMA.get("financialFields") or [])

DOCUMENT_START = "<<<DOCUMENT_CONTENT_START>>>"
DOCUMENT_END = "<<<DOCUMENT_CONTENT_END>>>"


@dataclass(frozen=True)
class ExtractedField:
    field_name: str
    field_value: str | None
    confidence: Decimal
    is_financial: bool
    page: int | None = None
    source_quote: str | None = None
    unresolved_reason: str | None = None


@dataclass(frozen=True)
class BankGuaranteeExtraction:
    fields: tuple[ExtractedField, ...]
    unresolved: tuple[dict[str, str], ...]
    model_version: str
    raw_extracted: dict[str, Any]

    def as_eval_fields(self) -> dict[str, Any]:
        """Shape expected by eval_harness.score_fields."""

        return {
            "fields": {
                item.field_name: {"value": item.field_value}
                for item in self.fields
                if item.field_value is not None
            },
            "unresolved": list(self.unresolved),
            "model_version": self.model_version,
        }


def is_financial_field(field_name: str) -> bool:
    return field_name in BG_FINANCIAL_FIELDS


def build_user_message(document_text: str) -> str:
    return (
        "Extract bank-guarantee fields from the following document.\n"
        "Prefer the Performance Bank Guarantee (PBG) when multiple guarantees "
        "are quoted.\n\n"
        f"{DOCUMENT_START}\n"
        f"{document_text}\n"
        f"{DOCUMENT_END}"
    )


def extract_bank_guarantee_from_path(path: Path) -> BankGuaranteeExtraction:
    return extract_bank_guarantee_from_text(load_document_text(path))


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def call_extraction_model(*, system: str, user: str) -> tuple[str, str]:
    """Call the configured LLM. Returns (model_version, raw_text)."""

    result = call_extraction_model_detailed(system=system, user=user)
    return result["model_version"], result["raw_text"]


def call_extraction_model_detailed(*, system: str, user: str) -> dict[str, Any]:
    """Call LLM; include token counts when the provider reports them."""

    return _call_model_detailed(system=system, user=user)


def extract_bank_guarantee_from_text(document_text: str) -> BankGuaranteeExtraction:
    prompt = load_system_prompt()
    user_message = build_user_message(document_text)
    detailed = call_extraction_model_detailed(system=prompt, user=user_message)
    payload = _parse_model_json(detailed["raw_text"])
    return parse_extraction_payload(
        payload, model_version=str(detailed["model_version"])
    )


def parse_model_json(raw_text: str) -> dict[str, Any]:
    """Public wrapper for tests and the Extraction Agent."""

    return _parse_model_json(raw_text)


def persist_bank_guarantee_fields(
    session: Session,
    *,
    document_id: UUID,
    extraction: BankGuaranteeExtraction,
) -> list[UUID]:
    """Insert extracted_field rows for a BG. Does not write bank_guarantee."""

    inserted: list[UUID] = []
    for field in extraction.fields:
        if field.field_value is None:
            continue
        result = session.execute(
            text(
                """
                INSERT INTO extracted_field (
                  document_id, field_name, field_value, state,
                  is_financial, confidence, model_version
                ) VALUES (
                  :document_id, :field_name, :field_value, 'ai_extracted',
                  :is_financial, :confidence, :model_version
                )
                RETURNING id
                """
            ),
            {
                "document_id": document_id,
                "field_name": field.field_name,
                "field_value": field.field_value,
                "is_financial": field.is_financial,
                "confidence": str(field.confidence),
                "model_version": extraction.model_version,
            },
        )
        inserted.append(result.scalar_one())
    return inserted


def process_bank_guarantee_document(
    session: Session,
    *,
    document_id: UUID,
    category: str,
    document_path: Path,
) -> BankGuaranteeExtraction | None:
    """Run BG extraction when classification is a bank guarantee; else no-op."""

    if category not in {"bg_document", "bank_guarantee"}:
        return None
    extraction = extract_bank_guarantee_from_path(document_path)
    persist_bank_guarantee_fields(
        session, document_id=document_id, extraction=extraction
    )
    return extraction


def parse_extraction_payload(
    payload: dict[str, Any], *, model_version: str = "test"
) -> BankGuaranteeExtraction:
    """Parse model/fixture JSON into BankGuaranteeExtraction (no LLM)."""

    return _to_extraction(payload, model_version=model_version)


def _call_model_detailed(*, system: str, user: str) -> dict[str, Any]:
    settings = get_llm_settings()
    if settings.provider == "anthropic":
        return _call_anthropic(
            system=system,
            user=user,
            model=settings.model,
            api_key=settings.api_key,
        )
    if settings.provider in {"gemini", "openai", "ollama"}:
        return _call_openai_compatible(
            system=system,
            user=user,
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model,
        )
    raise RuntimeError(f"unsupported LLM_PROVIDER={settings.provider!r}")


def _call_anthropic(
    *, system: str, user: str, model: str, api_key: str
) -> dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text_parts: list[str] = []
    for block in message.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(str(getattr(block, "text", "")))
    usage = getattr(message, "usage", None)
    prompt_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    return {
        "model_version": model,
        "raw_text": "\n".join(text_parts),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }


def _call_openai_compatible(
    *,
    system: str,
    user: str,
    base_url: str | None,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    # Ollama's OpenAI-compat endpoint is more reliable via plain HTTP than the
    # OpenAI SDK against a flaky local daemon.
    if base_url and "11434" in base_url:
        return _call_ollama_http(
            system=system, user=user, base_url=base_url, model=model
        )

    from openai import OpenAI

    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        kwargs["response_format"] = {"type": "json_object"}
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(**kwargs)
    except Exception:
        kwargs.pop("response_format", None)
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content or ""
    usage = getattr(response, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    return {
        "model_version": model,
        "raw_text": content,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }


def _call_ollama_http(
    *, system: str, user: str, base_url: str, model: str
) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    url = f"{root}/api/chat"
    body = json.dumps(
        {
            "model": model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": 2048},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=1800) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ollama HTTP {exc.code} at {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"ollama request failed at {url}; is `ollama serve` running?"
        ) from exc
    message = payload.get("message") or {}
    content = message.get("content") or ""
    if not content.strip():
        raise RuntimeError(f"ollama returned empty content: {payload!r}")
    return {
        "model_version": model,
        "raw_text": content,
        "prompt_tokens": int(payload.get("prompt_eval_count") or 0),
        "completion_tokens": int(payload.get("eval_count") or 0),
    }


def _parse_model_json(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("model output must be a JSON object")
    return payload


def _unwrap_field_entry(raw: Any) -> tuple[Any, int | None, str | None]:
    """Support v2 nested objects and v1 flat values."""

    if isinstance(raw, dict) and "value" in raw:
        page_raw = raw.get("page")
        page = None if page_raw is None or page_raw == "" else int(page_raw)
        quote = raw.get("source_quote")
        quote_s = None if quote is None else str(quote)
        return raw.get("value"), page, quote_s
    return raw, None, None


def _to_extraction(
    payload: dict[str, Any], *, model_version: str
) -> BankGuaranteeExtraction:
    property_names = list(_SCHEMA["properties"].keys())
    extracted = payload.get("extracted")
    if extracted is None and any(name in payload for name in property_names):
        extracted = {name: payload.get(name) for name in property_names}
    if not isinstance(extracted, dict):
        raise ValueError("model output missing 'extracted' object")

    confidence_map = payload.get("field_confidence") or payload.get("confidence") or {}
    if not isinstance(confidence_map, dict):
        confidence_map = {}

    unresolved_raw = payload.get("unresolved") or []
    unresolved: list[dict[str, str]] = []
    unresolved_by_field: dict[str, str] = {}
    if isinstance(unresolved_raw, list):
        for item in unresolved_raw:
            if isinstance(item, dict) and "field" in item and "reason" in item:
                entry = {"field": str(item["field"]), "reason": str(item["reason"])}
                unresolved.append(entry)
                unresolved_by_field[entry["field"]] = entry["reason"]

    fields: list[ExtractedField] = []
    raw_extracted: dict[str, Any] = {}
    for name in property_names:
        raw_entry = extracted.get(name)
        value_raw, page, source_quote = _unwrap_field_entry(raw_entry)
        raw_extracted[name] = value_raw

        if value_raw is None:
            if name in unresolved_by_field:
                fields.append(
                    ExtractedField(
                        field_name=name,
                        field_value=None,
                        confidence=Decimal("0.000"),
                        is_financial=is_financial_field(name),
                        page=page,
                        source_quote=source_quote,
                        unresolved_reason=unresolved_by_field[name],
                    )
                )
            continue

        value: str | None
        if name == "value":
            value = _normalize_money(value_raw)
        elif name.endswith("_date") and not name.endswith("_raw"):
            value = _normalize_iso_date(value_raw)
        else:
            value = str(value_raw).strip() if value_raw is not None else None

        conf_raw = confidence_map.get(name, "0.850")
        confidence = Decimal(str(conf_raw)).quantize(Decimal("0.001"))
        if confidence < 0 or confidence > 1:
            confidence = Decimal("0.850")
        fields.append(
            ExtractedField(
                field_name=name,
                field_value=value,
                confidence=confidence,
                is_financial=is_financial_field(name),
                page=page,
                source_quote=source_quote,
                unresolved_reason=None,
            )
        )

    return BankGuaranteeExtraction(
        fields=tuple(fields),
        unresolved=tuple(unresolved),
        model_version=model_version,
        raw_extracted=raw_extracted,
    )


def _normalize_money(value: Any) -> str:
    if isinstance(value, (int, float, Decimal)):
        raise ValueError("money must be a decimal string, not a JSON number")
    text = str(value).strip()
    text = text.replace("Rs.", "").replace("Rs", "").replace("/-", "")
    text = text.replace(",", "").replace(" ", "")
    if re.fullmatch(r"\d+", text):
        text = f"{text}.00"
    if not re.fullmatch(r"\d+\.\d{2}", text):
        raise ValueError(f"invalid money string: {value!r}")
    return text


def _normalize_iso_date(value: Any) -> str:
    text = str(value).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError(f"date must be ISO YYYY-MM-DD, got {value!r}")
    return text
