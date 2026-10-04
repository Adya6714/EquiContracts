"""Tool belt. Each tool calls a service through the run's opaque handle."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from packages.agents.tools import (
    get_engagement_context,
    read_document_metadata,
    read_document_pages,
)

ToolFn = Callable[..., Any]

TOOL_REGISTRY: dict[str, ToolFn] = {
    "get_engagement_context": get_engagement_context.run,
    "read_document_metadata": read_document_metadata.run,
    "read_document_pages": read_document_pages.run,
}


def get_tool(name: str) -> ToolFn | None:
    return TOOL_REGISTRY.get(name)


def registered_tool_names() -> frozenset[str]:
    return frozenset(TOOL_REGISTRY)
