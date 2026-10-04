"""The agent-rules check must reject SQL inside routers."""

from pathlib import Path

from scripts.check_agent_rules import routers_have_no_sql


def test_routers_have_no_sql_check_catches_text_import(tmp_path: Path) -> None:
    routers = tmp_path / "routers"
    routers.mkdir()
    (routers / "bad.py").write_text(
        "from sqlalchemy import text\n\ndef boom():\n    return text('SELECT 1')\n",
        encoding="utf-8",
    )
    failures = routers_have_no_sql(routers)
    assert any("imports sqlalchemy text" in item for item in failures)


def test_routers_have_no_sql_check_catches_execute(tmp_path: Path) -> None:
    routers = tmp_path / "routers"
    routers.mkdir()
    (routers / "bad.py").write_text(
        "def boom(session):\n    session.execute('SELECT 1')\n",
        encoding="utf-8",
    )
    failures = routers_have_no_sql(routers)
    assert any("calls .execute()" in item for item in failures)


def test_routers_have_no_sql_check_passes_clean_router(tmp_path: Path) -> None:
    routers = tmp_path / "routers"
    routers.mkdir()
    (routers / "ok.py").write_text(
        "def boom():\n    return 'no sql here'\n",
        encoding="utf-8",
    )
    assert routers_have_no_sql(routers) == []
