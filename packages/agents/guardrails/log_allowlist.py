"""Keys permitted in agent_step log payloads (plus any ``*_id``)."""

from __future__ import annotations

LOG_KEY_ALLOWLIST = frozenset(
    {
        "tool",
        "tool_called",
        "status",
        "outcome",
        "reason",
        "count",
        "page_count",
        "proposal_type",
        "autonomy_level",
        "applied",
        "step_no",
        "prompt_tokens",
        "completion_tokens",
    }
)
