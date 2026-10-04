"""Would-have-cost estimates from token counts (even on free / zero-bill tiers)."""

from __future__ import annotations

from decimal import Decimal

# USD per 1M tokens: (input, output). Used for accounting, not billing.
_PRICE_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    "gemini-2.5-flash": (Decimal("0.15"), Decimal("0.60")),
    "gemini-2.0-flash": (Decimal("0.10"), Decimal("0.40")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "claude-3-5-haiku": (Decimal("0.80"), Decimal("4.00")),
}

_DEFAULT_PRICE = (Decimal("0.15"), Decimal("0.60"))


def estimate_would_have_cost(
    model_version: str,
    *,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal:
    """Return estimated USD cost from a static price table."""

    key = (model_version or "").strip().lower()
    inp_rate, out_rate = _DEFAULT_PRICE
    for name, rates in _PRICE_PER_MTOK.items():
        if key == name or key.startswith(name):
            inp_rate, out_rate = rates
            break
    cost = Decimal(prompt_tokens) * inp_rate / Decimal("1000000") + Decimal(
        completion_tokens
    ) * out_rate / Decimal("1000000")
    return cost.quantize(Decimal("0.000001"))
