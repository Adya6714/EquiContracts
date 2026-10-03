"""Deterministic rule-definition loading and evaluation primitives."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml

DEFINITIONS = Path(__file__).with_name("definitions")


@dataclass(frozen=True)
class RuleDefinition:
    id: str
    when: str
    severity: Literal["low", "medium", "high", "critical"]
    evidence_query: str
    action_owner: Literal["contractor", "client_pm", "pmc"]
    autonomy_tier: Literal["draft", "suggest", "auto_with_undo"]


def load_definitions(path: Path = DEFINITIONS) -> tuple[RuleDefinition, ...]:
    definitions: list[RuleDefinition] = []
    for definition_path in sorted(path.glob("*.yaml")):
        raw = yaml.safe_load(definition_path.read_text())
        definitions.append(RuleDefinition(**raw))
    return tuple(definitions)


def pending_financial_review_matches(
    *,
    is_financial: bool,
    state: str,
    now: datetime,
) -> bool:
    """Reference pure rule; `now` is injected even though this rule ignores it."""

    del now
    return is_financial and state == "needs_review"
