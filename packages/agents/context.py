"""Immutable run context. Org and engagement come from the claimed event."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RunContext:
    """Read-only identity for one agent run.

    ``services`` is an opaque handle supplied by the worker. Agents and tools
    must not treat it as a session or try to change org/engagement.
    """

    org_id: UUID
    engagement_id: UUID | None
    run_id: UUID
    services: Any
