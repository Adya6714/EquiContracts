"""Would-have-cost price table."""

from __future__ import annotations

from decimal import Decimal

from packages.extraction.llm_pricing import estimate_would_have_cost


def test_estimate_would_have_cost_uses_price_table_even_for_free_tier() -> None:
    cost = estimate_would_have_cost(
        "gemini-2.5-flash",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )
    # 0.15 + 0.60 = 0.75 USD per 1M in + 1M out
    assert cost == Decimal("0.750000")


def test_estimate_would_have_cost_unknown_model_uses_default() -> None:
    cost = estimate_would_have_cost(
        "some-unknown-model",
        prompt_tokens=0,
        completion_tokens=0,
    )
    assert cost == Decimal("0.000000")
