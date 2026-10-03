from decimal import Decimal

from apps.api.app.core.verification import contradiction_state, next_state


def test_financial_field_always_needs_review() -> None:
    assert next_state(is_financial=True, confidence=Decimal("1.000")) == "needs_review"


def test_low_confidence_non_financial_needs_review() -> None:
    assert next_state(is_financial=False, confidence=Decimal("0.899")) == "needs_review"


def test_missing_confidence_needs_review() -> None:
    assert next_state(is_financial=False, confidence=None) == "needs_review"


def test_high_confidence_non_financial_can_verify() -> None:
    assert next_state(is_financial=False, confidence=Decimal("0.900")) == "verified"


def test_verified_contradiction_returns_to_review() -> None:
    assert contradiction_state("verified") == "needs_review"
