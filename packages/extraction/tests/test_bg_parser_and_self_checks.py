"""BG extractor parser, financial rule, and pure self-checks (no network)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from packages.extraction.bg_extractor import (
    BankGuaranteeExtraction,
    ExtractedField,
    is_financial_field,
    parse_extraction_payload,
)
from packages.extraction.self_checks import (
    BG_NUMBER_MISSING,
    CLAIM_BEFORE_EXPIRY,
    INVALID_CALENDAR_DATE,
    QUOTE_DOES_NOT_SUPPORT_VALUE,
    SOURCE_QUOTE_NOT_FOUND,
    VALUE_NOT_POSITIVE,
    check_bg_number_present,
    check_calendar_dates,
    check_claim_expiry_order,
    check_quote_supports_value,
    check_source_quotes,
    check_value_positive,
    run_bg_self_checks,
)

ROOT = Path(__file__).resolve().parents[3]
GECPL_GOLD = ROOT / "eval" / "eval_set_v0" / "expected" / "gecpl-bg-invocation.json"

DOC_TEXT = (
    "Performance Bank Guarantee No. 0544BGR0097618 "
    "for Rs.1,70,80,000/- valid till 23.04.2023 "
    "claim period up to 23.04.2024 issued by State Bank."
)


def _payload() -> dict:
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
        "unresolved": [
            {"field": "issue_date", "reason": "not stated in excerpt"},
        ],
        "field_confidence": {
            "bg_number": 0.95,
            "value": 0.9,
            "expiry_date": 0.9,
            "claim_expiry_date": 0.9,
            "issuing_bank": 0.8,
        },
    }


def test_parser_reads_page_source_quote_unresolved_reason() -> None:
    extraction = parse_extraction_payload(_payload(), model_version="fixture")
    by_name = {f.field_name: f for f in extraction.fields}

    assert by_name["bg_number"].field_value == "0544BGR0097618"
    assert by_name["bg_number"].page is None
    assert by_name["bg_number"].source_quote == "0544BGR0097618"
    assert by_name["bg_number"].unresolved_reason is None
    assert by_name["bg_number"].confidence == Decimal("0.950")

    assert by_name["issue_date"].field_value is None
    assert by_name["issue_date"].unresolved_reason == "not stated in excerpt"
    assert by_name["value"].is_financial is True
    assert by_name["bg_number"].is_financial is False
    assert by_name["issuing_bank"].is_financial is False


def test_financial_rule_matches_gecpl_gold_flags() -> None:
    gold = json.loads(GECPL_GOLD.read_text(encoding="utf-8"))
    for name, definition in gold["fields"].items():
        assert is_financial_field(name) is bool(definition["financial"]), name


def _extraction_with(**updates: str | None) -> BankGuaranteeExtraction:
    payload = _payload()
    for name, value in updates.items():
        payload["extracted"][name] = {
            "value": value,
            "page": None,
            "source_quote": value,
        }
    return parse_extraction_payload(payload)


def test_claim_expiry_order_passes_and_fails() -> None:
    good = _extraction_with(expiry_date="2023-04-23", claim_expiry_date="2024-04-23")
    assert check_claim_expiry_order(good) is None

    bad = _extraction_with(expiry_date="2024-04-23", claim_expiry_date="2023-04-23")
    assert check_claim_expiry_order(bad) == CLAIM_BEFORE_EXPIRY


def test_calendar_dates_pass_and_fail() -> None:
    good = _extraction_with(expiry_date="2023-04-23")
    assert check_calendar_dates(good) is None

    bad = BankGuaranteeExtraction(
        fields=(
            ExtractedField(
                field_name="expiry_date",
                field_value="2023-02-30",
                confidence=Decimal("0.9"),
                is_financial=True,
                source_quote="2023-02-30",
            ),
        ),
        unresolved=(),
        model_version="t",
        raw_extracted={},
    )
    assert check_calendar_dates(bad) == INVALID_CALENDAR_DATE


def test_value_positive_pass_and_fail() -> None:
    good = _extraction_with(value="17080000.00")
    assert check_value_positive(good) is None

    bad = _extraction_with(value="0.00")
    assert check_value_positive(bad) == VALUE_NOT_POSITIVE


def test_bg_number_present_pass_and_fail() -> None:
    good = _extraction_with(bg_number="0544BGR0097618")
    assert check_bg_number_present(good) is None

    payload = _payload()
    payload["extracted"]["bg_number"] = {
        "value": None,
        "page": None,
        "source_quote": None,
    }
    payload["unresolved"] = [{"field": "bg_number", "reason": "missing"}]
    bad = parse_extraction_payload(payload)
    assert check_bg_number_present(bad) == BG_NUMBER_MISSING


def test_source_quote_fails_invented_passes_whitespace_variant() -> None:
    only_bg = BankGuaranteeExtraction(
        fields=(
            ExtractedField(
                field_name="bg_number",
                field_value="0544BGR0097618",
                confidence=Decimal("0.9"),
                is_financial=False,
                source_quote="0544BGR0097618",
            ),
        ),
        unresolved=(),
        model_version="t",
        raw_extracted={},
    )
    doc_spaced = "Performance   Bank   Guarantee No.\n0544BGR0097618 for amount"
    assert check_source_quotes(only_bg, doc_spaced) is None

    invented = BankGuaranteeExtraction(
        fields=(
            ExtractedField(
                field_name="bg_number",
                field_value="0544BGR0097618",
                confidence=Decimal("0.9"),
                is_financial=False,
                source_quote="THIS-QUOTE-IS-INVENTED",
            ),
        ),
        unresolved=(),
        model_version="t",
        raw_extracted={},
    )
    assert check_source_quotes(invented, DOC_TEXT) == SOURCE_QUOTE_NOT_FOUND


def test_run_bg_self_checks_all_pass_on_good_fixture() -> None:
    extraction = parse_extraction_payload(_payload())
    assert run_bg_self_checks(extraction, DOC_TEXT) == []


def test_quote_supports_gecpl_style_money_and_date() -> None:
    extraction = parse_extraction_payload(_payload())
    assert check_quote_supports_value(extraction) is None


def test_quote_with_different_amount_fails() -> None:
    payload = _payload()
    payload["extracted"]["value"]["source_quote"] = "Rs.1,50,00,000/-"
    # Quote must still appear in document for the other check; use a doc that
    # contains both amounts so only the support check fails.
    doc = DOC_TEXT + " also mentions Rs.1,50,00,000/- elsewhere"
    extraction = parse_extraction_payload(payload)
    assert check_source_quotes(extraction, doc) is None
    assert check_quote_supports_value(extraction) == QUOTE_DOES_NOT_SUPPORT_VALUE


def test_quote_with_different_date_fails() -> None:
    payload = _payload()
    payload["extracted"]["expiry_date"]["source_quote"] = "01.01.2020"
    doc = DOC_TEXT + " old date 01.01.2020"
    extraction = parse_extraction_payload(payload)
    assert check_source_quotes(extraction, doc) is None
    assert check_quote_supports_value(extraction) == QUOTE_DOES_NOT_SUPPORT_VALUE
