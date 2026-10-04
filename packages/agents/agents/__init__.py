"""Per-agent packages (card.md + agent.py each)."""

from __future__ import annotations

from collections.abc import Callable

from packages.agents.agents.echo import agent as echo_agent
from packages.agents.agents.extraction import agent as extraction_agent
from packages.agents.runtime import AgentRuntime

AgentFn = Callable[[AgentRuntime], None]

AGENT_REGISTRY: dict[str, tuple[str, AgentFn]] = {
    # name -> (version, callable)
    echo_agent.AGENT_NAME: (echo_agent.AGENT_VERSION, echo_agent.run),
    extraction_agent.AGENT_NAME: (
        extraction_agent.AGENT_VERSION,
        extraction_agent.run,
    ),
}


def get_agent(name: str) -> tuple[str, AgentFn] | None:
    entry = AGENT_REGISTRY.get(name)
    if entry is None:
        return None
    return entry
