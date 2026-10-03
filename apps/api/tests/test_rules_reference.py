from datetime import UTC, datetime

from apps.api.app.rules.engine import (
    load_definitions,
    pending_financial_review_matches,
)


def test_reference_rule_definition_has_safe_default() -> None:
    rules = {rule.id: rule for rule in load_definitions()}
    assert rules["pending_financial_review"].autonomy_tier == "draft"


def test_pending_financial_review_rule_is_deterministic() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    assert pending_financial_review_matches(
        is_financial=True,
        state="needs_review",
        now=now,
    )
    assert not pending_financial_review_matches(
        is_financial=False,
        state="needs_review",
        now=now,
    )
