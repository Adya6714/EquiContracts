"""Shared tool exceptions."""

from __future__ import annotations


class ToolRefusal(Exception):
    """Tool refused the call. ``code`` is a short safe token for logs/errors."""

    def __init__(self, code: str = "refused") -> None:
        self.code = code
        super().__init__(code)
