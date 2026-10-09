"""Action key → autonomy level (AGENTIC_DESIGN Part 7). Unknown → 2."""

from __future__ import annotations

# Keys match Part 7.2 actions (snake_case). New actions default to 2.
_LEVELS: dict[str, int] = {
    "sort_document": 3,
    "set_evidence_weight": 3,
    "propose_classification": 2,
    "link_exact": 3,
    "link_fuzzy": 1,
    "propose_financial_field": 1,
    "propose_field": 1,
    "extraction.unreadable": 1,
    "mark_financial_field_verified": 4,
    "raise_gap": 3,
    "close_gap": 3,
    "remind_contractor_team": 3,
    "escalate_contractor_team": 3,
    "message_client_or_pmc": 2,
    "formal_letter": 2,
    "accept_risk": 4,
    "morning_digest": 3,
    "weekly_client_report": 2,
    "answer_question": 3,
    "export_resolution_statement": 2,
    # Echo test proposal
    "echo.note": 2,
}

DEFAULT_AUTONOMY_LEVEL = 2
NEVER_AUTO_LEVEL = 4


def autonomy_level_for(action_key: str) -> int:
    return _LEVELS.get(action_key, DEFAULT_AUTONOMY_LEVEL)


def may_auto_apply(level: int) -> bool:
    """Level 3 can act with undo. Level 4 is never applied by the runtime."""

    return level == 3
