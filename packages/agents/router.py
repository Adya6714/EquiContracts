"""Plain-code event_type → agent name list. Never guess unknown types."""

from __future__ import annotations

# Fan-out ready: one event type may wake several agents.
_ROUTES: dict[str, list[str]] = {
    "test.echo": ["echo"],
    "document.received": ["intake"],
    "document.classified": ["extraction"],
}


def agents_for(event_type: str) -> list[str] | None:
    """Return routed agent names, or None if the event type is unknown."""

    route = _ROUTES.get(event_type)
    if route is None:
        return None
    return list(route)


def known_event_types() -> frozenset[str]:
    return frozenset(_ROUTES)
