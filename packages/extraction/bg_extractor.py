"""Bank guarantee extraction — one document type only."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from .document_text import load_document_text

ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "bank_guarantee.v1.md"
SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "bank_guarantee.json"

# Every bank-guarantee field is financial: wrong values cost real money.
BG_FINANCIAL_FIELDS = frozenset(
    json.loads(SCHEMA_PATH.read_text())["properties"].keys()
)

DOCUMENT_START = "<<<DOCUMENT_CONTENT_START>>>"
DOCUMENT_END = "<<<DOCUMENT_CONTENT_END>>>"


@dataclass(frozen=True)
class ExtractedField:
    field_name: str
    field_value: str | None
    confidence: Decimal
    is_financial: bool = True


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


def extract_bank_guarantee_from_text(document_text: str) -> BankGuaranteeExtraction:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    user_message = build_user_message(document_text)
    model_version, raw_text = _call_model(system=prompt, user=user_message)
    payload = _parse_model_json(raw_text)
    return _to_extraction(payload, model_version=model_version)


def persist_bank_guarantee_fields(
    session: Session,
    *,
    document_id: UUID,
    extraction: BankGuaranteeExtraction,
) -> list[UUID]:
    """Insert extracted_field rows for a BG. Does not write bank_guarantee."""

    inserted: list[UUID] = []
    for field in extraction.fields:
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


def _call_model(*, system: str, user: str) -> tuple[str, str]:
    provider = os.environ.get("EXTRACTION_PROVIDER", "").strip().lower()
    if not provider:
        if os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
        else:
            provider = "ollama"

    if provider == "anthropic":
        return _call_anthropic(system=system, user=user)
    if provider == "openai":
        return _call_openai_compatible(
            system=system,
            user=user,
            base_url=os.environ.get("OPENAI_BASE_URL"),
            api_key=os.environ["OPENAI_API_KEY"],
            model=os.environ.get("EXTRACTION_MODEL", "gpt-4o"),
        )
    if provider == "ollama":
        return _call_openai_compatible(
            system=system,
            user=user,
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
            api_key=os.environ.get("OLLAMA_API_KEY", "ollama"),
            model=os.environ.get("EXTRACTION_MODEL", "llama3:latest"),
        )
    raise RuntimeError(f"unsupported EXTRACTION_PROVIDER={provider!r}")


def _call_anthropic(*, system: str, user: str) -> tuple[str, str]:
    import anthropic

    model = os.environ.get("EXTRACTION_MODEL", "claude-sonnet-4-20250514")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text_parts = [
        block.text
        for block in message.content
        if getattr(block, "type", None) == "text"
    ]
    return model, "\n".join(text_parts)


def _call_openai_compatible(
    *,
    system: str,
    user: str,
    base_url: str | None,
    api_key: str,
    model: str,
) -> tuple[str, str]:
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
    return model, content


def _call_ollama_http(
    *, system: str, user: str, base_url: str, model: str
) -> tuple[str, str]:
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
    return model, content


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


def _to_extraction(
    payload: dict[str, Any], *, model_version: str
) -> BankGuaranteeExtraction:
    schema = json.loads(SCHEMA_PATH.read_text())
    property_names = list(schema["properties"].keys())
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
    if isinstance(unresolved_raw, list):
        for item in unresolved_raw:
            if isinstance(item, dict) and "field" in item and "reason" in item:
                unresolved.append(
                    {"field": str(item["field"]), "reason": str(item["reason"])}
                )

    fields: list[ExtractedField] = []
    for name in property_names:
        value = extracted.get(name)
        if value is None:
            continue
        if name == "value":
            value = _normalize_money(value)
        elif name.endswith("_date") and not name.endswith("_raw"):
            value = _normalize_iso_date(value)
        else:
            value = str(value).strip() if value is not None else None
        conf_raw = confidence_map.get(name, "0.850")
        confidence = Decimal(str(conf_raw)).quantize(Decimal("0.001"))
        if confidence < 0 or confidence > 1:
            confidence = Decimal("0.850")
        fields.append(
            ExtractedField(
                field_name=name,
                field_value=value,
                confidence=confidence,
                is_financial=True,
            )
        )

    return BankGuaranteeExtraction(
        fields=tuple(fields),
        unresolved=tuple(unresolved),
        model_version=model_version,
        raw_extracted={k: extracted.get(k) for k in property_names},
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
