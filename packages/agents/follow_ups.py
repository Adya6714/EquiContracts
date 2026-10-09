"""Plain-data follow-up rules after agent runs.

Workers interpret these rules and call the DEFINER follow-up function.
Agents never invoke that database function.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


def handoff_threshold() -> Decimal:
    """Confidence floor for Intake → Extraction handoff (env override)."""

    raw = (os.environ.get("HANDOFF_THRESHOLD") or "0.70").strip()
    try:
        return Decimal(raw)
    except Exception:
        return Decimal("0.70")


@dataclass(frozen=True)
class FollowUpRule:
    agent_name: str
    proposal_type: str
    doc_types: frozenset[str]
    # Confidence compared at apply time via handoff_threshold().


FOLLOW_UP_RULES: tuple[FollowUpRule, ...] = (
    FollowUpRule(
        agent_name="intake",
        proposal_type="propose_classification",
        doc_types=frozenset({"bank_guarantee"}),
    ),
)


def proposals_matching_follow_up(
    *,
    agent_name: str,
    proposals: list[dict[str, Any]],
    threshold: Decimal | None = None,
) -> list[Any]:
    """Return proposal ids that should create a follow-up event."""

    floor = threshold if threshold is not None else handoff_threshold()
    matched: list[Any] = []
    for proposal in proposals:
        if not _matches(agent_name=agent_name, proposal=proposal, floor=floor):
            continue
        proposal_id = proposal.get("id")
        if proposal_id is not None:
            matched.append(proposal_id)
    return matched


def _matches(
    *,
    agent_name: str,
    proposal: dict[str, Any],
    floor: Decimal,
) -> bool:
    for rule in FOLLOW_UP_RULES:
        if rule.agent_name != agent_name:
            continue
        if proposal.get("proposal_type") != rule.proposal_type:
            continue
        content = proposal.get("content") or {}
        if not isinstance(content, dict):
            continue
        doc_type = str(content.get("doc_type") or "")
        if doc_type not in rule.doc_types:
            continue
        confidence = _confidence(proposal, content)
        if confidence < floor:
            continue
        return True
    return False


def _confidence(proposal: dict[str, Any], content: dict[str, Any]) -> Decimal:
    raw = proposal.get("confidence")
    if raw is None:
        raw = content.get("confidence")
    if raw is None or raw == "":
        return Decimal("0")
    try:
        return Decimal(str(raw))
    except Exception:
        return Decimal("0")
