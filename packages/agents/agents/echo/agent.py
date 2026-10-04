"""Echo test agent: read engagement context, emit one proposal. No LLM."""

from __future__ import annotations

from decimal import Decimal

from packages.agents.runtime import AgentRuntime

AGENT_NAME = "echo"
AGENT_VERSION = "0"


def run(runtime: AgentRuntime) -> None:
    engagement_id = runtime.context.engagement_id
    if engagement_id is None:
        raise RuntimeError("echo requires an engagement_id on the event")

    runtime.call_tool("get_engagement_context", engagement_id=engagement_id)
    runtime.emit_proposal(
        "echo.note",
        {"engagement_id": str(engagement_id)},
        confidence=Decimal("1.000"),
    )
