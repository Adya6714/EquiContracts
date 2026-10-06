"""Intake Agent stub: routing target for document.received (logic lands in 6b.2)."""

from __future__ import annotations

from packages.agents.runtime import AgentRuntime

AGENT_NAME = "intake"
AGENT_VERSION = "0"


def run(runtime: AgentRuntime) -> None:
    """No-op until Part 6b.2. Keeps document.received routable and verify green."""

    _ = runtime
