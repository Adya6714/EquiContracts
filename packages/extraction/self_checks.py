"""Pure BG extraction self-checks. No LLM. Returns short error codes."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.extraction.bg_extractor import BankGuaranteeExtraction, ExtractedField

CLAIM_BEFORE_EXPIRY = "claim_before_expiry"
INVALID_CALENDAR_DATE = "invalid_calendar_date"
VALUE_NOT_POSITIVE = "value_not_positive"
BG_NUMBER_MISSING = "bg_number_missing"
SOURCE_QUOTE_NOT_FOUND = "source_quote_not_found"

_DATE_FIELDS = frozenset({"issue_date", "expiry_date", "claim_expiry_date"})
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def _field_map(
    extraction: BankGuaranteeExtraction,
) -> dict[str, ExtractedField]:
    return {item.field_name: item for item in extraction.fields}


def check_claim_expiry_order(extraction: BankGuaranteeExtraction) -> str | None:
    """claim_expiry_date must be on or after expiry_date when both present."""

    fields = _field_map(extraction)
    expiry = fields.get("expiry_date")
    claim = fields.get("claim_expiry_date")
    if (
        expiry is None
        or claim is None
        or expiry.field_value is None
        or claim.field_value is None
    ):
        return None
    try:
        expiry_d = date.fromisoformat(expiry.field_value)
        claim_d = date.fromisoformat(claim.field_value)
    except ValueError:
        return None
    if claim_d < expiry_d:
        return CLAIM_BEFORE_EXPIRY
    return None


def check_calendar_dates(extraction: BankGuaranteeExtraction) -> str | None:
    """Every non-null ISO date field must be a real calendar date."""

    for item in extraction.fields:
        if item.field_name not in _DATE_FIELDS or item.field_value is None:
            continue
        raw = item.field_value.strip()
        if not _ISO_DATE.fullmatch(raw):
            return INVALID_CALENDAR_DATE
        try:
            date.fromisoformat(raw)
        except ValueError:
            return INVALID_CALENDAR_DATE
    return None


def check_value_positive(extraction: BankGuaranteeExtraction) -> str | None:
    """BG value must be a positive Decimal when present."""

    fields = _field_map(extraction)
    value_field = fields.get("value")
    if value_field is None or value_field.field_value is None:
        return None
    try:
        amount = Decimal(value_field.field_value)
    except (InvalidOperation, ValueError):
        return VALUE_NOT_POSITIVE
    if amount <= 0:
        return VALUE_NOT_POSITIVE
    return None


def check_bg_number_present(extraction: BankGuaranteeExtraction) -> str | None:
    """bg_number must be present and non-empty."""

    fields = _field_map(extraction)
    bg = fields.get("bg_number")
    if bg is None or bg.field_value is None or not str(bg.field_value).strip():
        return BG_NUMBER_MISSING
    return None


def check_source_quotes(
    extraction: BankGuaranteeExtraction, document_text: str
) -> str | None:
    """Every non-null field's source_quote must appear in the document text."""

    collapsed_doc = collapse_whitespace(document_text)
    for item in extraction.fields:
        if item.field_value is None:
            continue
        quote = item.source_quote
        if quote is None or not str(quote).strip():
            return SOURCE_QUOTE_NOT_FOUND
        if collapse_whitespace(str(quote)) not in collapsed_doc:
            return SOURCE_QUOTE_NOT_FOUND
    return None


def run_bg_self_checks(
    extraction: BankGuaranteeExtraction, document_text: str
) -> list[str]:
    """Run all BG self-checks; return error codes (empty list = pass)."""

    codes: list[str] = []
    for result in (
        check_claim_expiry_order(extraction),
        check_calendar_dates(extraction),
        check_value_positive(extraction),
        check_bg_number_present(extraction),
        check_source_quotes(extraction, document_text),
    ):
        if result is not None:
            codes.append(result)
    return codes
