"""`python -m apps.api.app.workers` / `make worker` loop."""

from __future__ import annotations

import time

from .agent_events import run_once

SLEEP_SECONDS = 1.0


def main() -> None:
    while True:
        worked = run_once()
        if not worked:
            time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()
