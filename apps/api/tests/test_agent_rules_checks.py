"""New agent-rules checks must catch violations."""

from __future__ import annotations

from pathlib import Path

from scripts.check_agent_rules import (
    agent_folders_have_card_and_agent,
    agents_have_no_db_access,
    allowlisted_tools_are_registered,
    follow_up_event_only_from_workers,
)


def test_agents_have_no_db_access_catches_sqlalchemy(tmp_path: Path) -> None:
    root = tmp_path / "agents"
    root.mkdir()
    (root / "bad.py").write_text(
        "import sqlalchemy\n\ndef x():\n    return sqlalchemy\n",
        encoding="utf-8",
    )
    failures = agents_have_no_db_access(root)
    assert any("database access" in item for item in failures)


def test_agents_have_no_db_access_catches_execute(tmp_path: Path) -> None:
    root = tmp_path / "agents"
    root.mkdir()
    (root / "bad.py").write_text(
        "def x(session):\n    session.execute('SELECT 1')\n",
        encoding="utf-8",
    )
    failures = agents_have_no_db_access(root)
    assert any("database access" in item for item in failures)


def test_agents_have_no_db_access_passes_clean(tmp_path: Path) -> None:
    root = tmp_path / "agents"
    root.mkdir()
    (root / "ok.py").write_text("def x():\n    return 1\n", encoding="utf-8")
    assert agents_have_no_db_access(root) == []


def test_agent_folders_have_card_and_agent_catches_missing(tmp_path: Path) -> None:
    root = tmp_path / "agents"
    root.mkdir()
    (root / "ghost").mkdir()
    failures = agent_folders_have_card_and_agent(root)
    assert any("missing card.md" in item for item in failures)
    assert any("missing agent.py" in item for item in failures)


def test_agent_folders_have_card_and_agent_passes(tmp_path: Path) -> None:
    root = tmp_path / "agents"
    agent = root / "echo"
    agent.mkdir(parents=True)
    (agent / "card.md").write_text("Agent name: Echo\n", encoding="utf-8")
    (agent / "agent.py").write_text("def run():\n    pass\n", encoding="utf-8")
    assert agent_folders_have_card_and_agent(root) == []


def test_allowlisted_tools_are_registered_catches_missing(tmp_path: Path) -> None:
    allowlist = tmp_path / "allowlist.py"
    registry = tmp_path / "registry.py"
    allowlist.write_text(
        '_ALLOWLIST = {"echo": frozenset({"missing_tool"})}\n',
        encoding="utf-8",
    )
    registry.write_text(
        'TOOL_REGISTRY = {"get_engagement_context": None}\n',
        encoding="utf-8",
    )
    failures = allowlisted_tools_are_registered(
        allowlist_path=allowlist, registry_path=registry
    )
    assert any("missing_tool" in item for item in failures)


def test_follow_up_event_only_from_workers_catches_outside_call(tmp_path: Path) -> None:
    root = tmp_path / "apps" / "api" / "app" / "services"
    root.mkdir(parents=True)
    (root / "bad.py").write_text(
        "def x(session):\n    session.execute('SELECT create_follow_up_event()')\n",
        encoding="utf-8",
    )
    workers = tmp_path / "apps" / "api" / "app" / "workers"
    workers.mkdir(parents=True)
    (workers / "ok.py").write_text(
        "def x():\n    return 'create_follow_up_event'\n",
        encoding="utf-8",
    )
    # Point checker at a fake tree by monkeypatching ROOT-relative scan via
    # scan_roots under tmp — recreate relative layout under cwd-independent path.
    from scripts import check_agent_rules as rules

    original_root = rules.ROOT
    rules.ROOT = tmp_path
    try:
        failures = follow_up_event_only_from_workers(scan_roots=("apps",))
    finally:
        rules.ROOT = original_root
    assert any("outside workers/" in item for item in failures)
    assert not any("workers/ok.py" in item for item in failures)


def test_allowlisted_tools_are_registered_passes_when_present(tmp_path: Path) -> None:
    allowlist = tmp_path / "allowlist.py"
    registry = tmp_path / "registry.py"
    allowlist.write_text(
        '_ALLOWLIST = {"echo": frozenset({"get_engagement_context"})}\n',
        encoding="utf-8",
    )
    registry.write_text(
        'TOOL_REGISTRY = {"get_engagement_context": None}\n',
        encoding="utf-8",
    )
    assert (
        allowlisted_tools_are_registered(
            allowlist_path=allowlist, registry_path=registry
        )
        == []
    )
