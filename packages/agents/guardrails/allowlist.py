"""Explicit tool allowlist per agent. Unlisted tools are blocked."""

from __future__ import annotations

_ALLOWLIST: dict[str, frozenset[str]] = {
    "echo": frozenset({"get_engagement_context", "read_document_metadata"}),
    "intake": frozenset({"read_document_pages", "read_document_metadata"}),
    "extraction": frozenset({"read_document_pages", "read_document_metadata"}),
}


def allowed_tools(agent_name: str) -> frozenset[str]:
    return _ALLOWLIST.get(agent_name, frozenset())


def is_tool_allowed(agent_name: str, tool_name: str) -> bool:
    return tool_name in allowed_tools(agent_name)


def all_allowlisted_tools() -> frozenset[str]:
    names: set[str] = set()
    for tools in _ALLOWLIST.values():
        names.update(tools)
    return frozenset(names)
