#!/usr/bin/env python3
"""Fast static enforcement for repository non-negotiables."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE_SUFFIXES = {".py", ".sql", ".ts", ".tsx", ".js", ".jsx"}


def files_under(*roots: str, suffixes: set[str] | None = None) -> Iterable[Path]:
    for root in roots:
        path = ROOT / root
        if not path.exists():
            continue
        for candidate in path.rglob("*"):
            if any(
                part in {".git", ".next", ".venv", "node_modules", "__pycache__"}
                for part in candidate.parts
            ):
                continue
            if candidate.is_file() and (
                suffixes is None or candidate.suffix in suffixes
            ):
                yield candidate


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def non_comment_lines(path: Path) -> Iterable[tuple[int, str]]:
    in_block = False
    for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("/*"):
            in_block = True
        if not in_block and not stripped.startswith(("#", "--", "*", "//")):
            yield number, line
        if stripped.endswith("*/"):
            in_block = False


def no_skipped_tests() -> list[str]:
    pattern = re.compile(
        r"pytest\.skip|pytest\.mark\.(?:skip|xfail)|@mark\.(?:skip|xfail)"
    )
    return [
        f"{relative(path)}:{number}: skipped/xfail test"
        for path in files_under("apps/api/tests", suffixes={".py"})
        for number, line in non_comment_lines(path)
        if pattern.search(line)
    ]


def eval_set_untouched() -> list[str]:
    commands = [
        ["git", "diff", "--name-status", "--", "eval/eval_set_v0"],
        ["git", "diff", "--cached", "--name-status", "--", "eval/eval_set_v0"],
    ]
    has_main = subprocess.run(
        ["git", "rev-parse", "--verify", "origin/main"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if has_main.returncode == 0:
        commands.append(
            [
                "git",
                "diff",
                "--name-status",
                "origin/main...HEAD",
                "--",
                "eval/eval_set_v0",
            ]
        )
    changed: set[str] = set()
    for command in commands:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            status_code, _, path = line.partition("\t")
            if (
                status_code
                and not status_code.startswith("A")
                and not path.endswith("/.gitkeep")
            ):
                changed.add(path)
    return [f"{path}: frozen eval case modified or deleted" for path in sorted(changed)]


def no_float_money() -> list[str]:
    money = r"(?:amount|value|price|rate|tax|gst|tds|wct|retention|rupees|interest)"
    patterns = (
        re.compile(rf"\bfloat\s*\([^)]*{money}", re.IGNORECASE),
        re.compile(rf"\b{money}\w*\s*:\s*float\b", re.IGNORECASE),
    )
    return [
        f"{relative(path)}:{number}: float used for money-shaped value"
        for path in files_under("apps", "packages", suffixes={".py"})
        for number, line in non_comment_lines(path)
        if any(pattern.search(line) for pattern in patterns)
    ]


def no_rls_bypass() -> list[str]:
    # Named DROP POLICY is required when recreating policies (0009+).
    # CASCADE and RLS disable / BYPASSRLS remain forbidden.
    pattern = re.compile(
        r"\b(?:BYPASSRLS|DISABLE\s+ROW\s+LEVEL\s+SECURITY|"
        r"DROP\s+(?:POLICY|FUNCTION|TABLE|VIEW|INDEX|TRIGGER|TYPE)"
        r"\s+.*\bCASCADE\b)\b",
        re.IGNORECASE,
    )
    return [
        f"{relative(path)}:{number}: RLS bypass operation"
        for path in files_under("packages/db", suffixes={".sql"})
        for number, line in non_comment_lines(path)
        if pattern.search(line)
    ]


def no_pii_logging() -> list[str]:
    logger = re.compile(r"\b(?:logger|logging)\.(?:debug|info|warning|error|exception)")
    pii = re.compile(
        r"\b(?:field_value|subject|filename|sender|email|document_content)\b",
        re.IGNORECASE,
    )
    return [
        f"{relative(path)}:{number}: possible PII in application log"
        for path in files_under("apps", "packages", suffixes={".py"})
        for number, line in non_comment_lines(path)
        if logger.search(line) and pii.search(line)
    ]


def no_secrets() -> list[str]:
    patterns = (
        re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"(?i)(?:api_key|secret_key)\s*=\s*['\"][^'\"]{16,}['\"]"),
    )
    excluded = {
        ".env.example",
        ".gitleaks.toml",
        "scripts/check_agent_rules.py",
    }
    return [
        f"{relative(path)}:{number}: possible committed secret"
        for path in files_under("apps", "packages", "scripts", ".github", suffixes=None)
        if relative(path) not in excluded
        for number, line in non_comment_lines(path)
        if any(pattern.search(line) for pattern in patterns)
    ]


def rules_engine_deterministic() -> list[str]:
    pattern = re.compile(r"\b(?:anthropic|openai|litellm|boto3\.bedrock)\b")
    return [
        f"{relative(path)}:{number}: model client in deterministic rules layer"
        for path in files_under("apps/api/app/rules", suffixes={".py"})
        for number, line in non_comment_lines(path)
        if pattern.search(line)
    ]


def client_routes_verified_only() -> list[str]:
    """Client SQL (router or repository) that touches extracted_field must filter verified."""

    failures: list[str] = []
    for path in files_under(
        "apps/api/app/routers",
        "apps/api/app/repositories",
        "apps/api/app/services",
        suffixes={".py"},
    ):
        if "client" not in path.name:
            continue
        content = path.read_text()
        if "extracted_field" in content and not re.search(
            r"state\s*=\s*['\"]verified['\"]", content
        ):
            failures.append(f"{relative(path)}: missing explicit verified-only filter")
    return failures


def tenant_routes_are_scoped() -> list[str]:
    failures: list[str] = []
    for path in files_under("apps/api/app/routers", suffixes={".py"}):
        content = path.read_text()
        if "session.execute" not in content:
            continue
        if not any(
            marker in content for marker in ("org_scoped_session", "privileged_session")
        ):
            failures.append(f"{relative(path)}: database access has no scoped session")
    return failures


def routers_have_no_sql(routers_dir: Path | None = None) -> list[str]:
    """Routers must not import sqlalchemy.text or call .execute()."""

    root = routers_dir if routers_dir is not None else ROOT / "apps/api/app/routers"
    if not root.exists():
        return []
    text_import = re.compile(
        r"(?:from\s+sqlalchemy[\w.]*\s+import\s+[^\n]*\btext\b)"
        r"|(?:import\s+sqlalchemy\.text\b)"
    )
    execute_call = re.compile(r"\.execute\s*\(")
    failures: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in {"__pycache__", ".venv"} for part in path.parts):
            continue
        try:
            rel = str(path.relative_to(ROOT))
        except ValueError:
            rel = str(path)
        for number, line in non_comment_lines(path):
            if text_import.search(line):
                failures.append(f"{rel}:{number}: router imports sqlalchemy text")
            if execute_call.search(line):
                failures.append(f"{rel}:{number}: router calls .execute()")
    return failures


def agents_have_no_db_access(agents_dir: Path | None = None) -> list[str]:
    """packages/agents may not touch SQLAlchemy, repos, sessions, or set_config."""

    root = agents_dir if agents_dir is not None else ROOT / "packages/agents"
    if not root.exists():
        return []
    forbidden = re.compile(
        r"(?:"
        r"\bsqlalchemy\b"
        r"|\brepositories\b"
        r"|(?:App|Agent|Admin)SessionFactory\b"
        r"|\b(?:org_scoped_session|agent_org_scoped_session|"
        r"privileged_session|provisioning_session)\b"
        r"|\bset_config\s*\("
        r"|\.execute\s*\("
        r")"
    )
    failures: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in {"__pycache__", ".venv"} for part in path.parts):
            continue
        try:
            rel = str(path.relative_to(ROOT))
        except ValueError:
            rel = str(path)
        for number, line in non_comment_lines(path):
            if forbidden.search(line):
                failures.append(f"{rel}:{number}: agents package database access")
    return failures


def agent_folders_have_card_and_agent(agents_dir: Path | None = None) -> list[str]:
    """Every folder under packages/agents/agents/ must have card.md and agent.py."""

    root = agents_dir if agents_dir is not None else ROOT / "packages/agents/agents"
    if not root.exists():
        return []
    failures: list[str] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name.startswith((".", "_")):
            continue
        if any(part == "__pycache__" for part in path.parts):
            continue
        try:
            rel = str(path.relative_to(ROOT))
        except ValueError:
            rel = str(path)
        if not (path / "card.md").is_file():
            failures.append(f"{rel}: missing card.md")
        if not (path / "agent.py").is_file():
            failures.append(f"{rel}: missing agent.py")
    return failures


def allowlisted_tools_are_registered(
    *,
    allowlist_path: Path | None = None,
    registry_path: Path | None = None,
) -> list[str]:
    """Every tool name on any allowlist must exist in the tool registry."""

    allowlist_file = (
        allowlist_path
        if allowlist_path is not None
        else ROOT / "packages/agents/guardrails/allowlist.py"
    )
    registry_file = (
        registry_path
        if registry_path is not None
        else ROOT / "packages/agents/tools/__init__.py"
    )
    if not allowlist_file.exists() or not registry_file.exists():
        return ["packages/agents: allowlist or tool registry missing"]

    allowlist_names = set(
        re.findall(r'["\']([a-z][a-z0-9_]*)["\']', allowlist_file.read_text())
    )
    # Drop the agent name key "echo" etc. by intersecting with registry keys only
    # after reading registry; allowlist file also contains agent names.
    registry_names = set(
        re.findall(
            r'["\']([a-z][a-z0-9_]*)["\']\s*:',
            registry_file.read_text(),
        )
    )
    # Tools in allowlist frozensets are quoted strings; agent keys too.
    # Compare: every string that appears inside frozenset({...}) style tool lists.
    tool_literals = set(
        re.findall(
            r"frozenset\(\{([^}]*)\}\)",
            allowlist_file.read_text(),
            flags=re.DOTALL,
        )
    )
    required: set[str] = set()
    for block in tool_literals:
        required.update(re.findall(r'["\']([a-z][a-z0-9_]*)["\']', block))
    if not required:
        # Fallback: all quoted names in allowlist that look like tools (contain _)
        required = {name for name in allowlist_names if "_" in name}

    missing = sorted(required - registry_names)
    return [f"allowlisted tool not in registry: {name}" for name in missing]


def follow_up_event_only_from_workers(
    *,
    scan_roots: tuple[str, ...] | None = None,
) -> list[str]:
    """create_follow_up_event may only be called from apps/api/app/workers/."""

    roots = scan_roots if scan_roots is not None else ("apps", "packages")
    pattern = re.compile(r"\bcreate_follow_up_event\b")
    failures: list[str] = []
    for path in files_under(*roots, suffixes={".py"}):
        try:
            rel = relative(path)
        except ValueError:
            rel = str(path)
        if rel.startswith("apps/api/app/workers/"):
            continue
        if "/tests/" in rel.replace("\\", "/") or rel.startswith("apps/api/tests/"):
            continue
        for number, line in non_comment_lines(path):
            if pattern.search(line):
                failures.append(
                    f"{rel}:{number}: create_follow_up_event outside workers/"
                )
    return failures


def decisions_log_updated() -> list[str]:
    commands = [
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
    ]
    has_main = subprocess.run(
        ["git", "rev-parse", "--verify", "origin/main"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if has_main.returncode == 0:
        commands.append(["git", "diff", "--name-only", "origin/main...HEAD"])
    changed: set[str] = set()
    for command in commands:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        changed.update(result.stdout.splitlines())
    dependency_or_boundary_change = any(
        path.startswith("packages/db/migrations/")
        or path.endswith(("requirements.txt", "requirements-dev.txt", "package.json"))
        for path in changed
    )
    if dependency_or_boundary_change and "DECISIONS.md" not in changed:
        return ["dependency or migration changed without DECISIONS.md"]
    return []


CHECKS: tuple[tuple[str, Callable[[], list[str]]], ...] = (
    ("no_skipped_tests", no_skipped_tests),
    ("eval_set_untouched", eval_set_untouched),
    ("no_float_money", no_float_money),
    ("no_rls_bypass", no_rls_bypass),
    ("no_pii_logging", no_pii_logging),
    ("no_secrets", no_secrets),
    ("rules_engine_deterministic", rules_engine_deterministic),
    ("client_routes_verified_only", client_routes_verified_only),
    ("tenant_routes_are_scoped", tenant_routes_are_scoped),
    ("routers_have_no_sql", routers_have_no_sql),
    ("agents_have_no_db_access", agents_have_no_db_access),
    ("agent_folders_have_card_and_agent", agent_folders_have_card_and_agent),
    ("allowlisted_tools_are_registered", allowlisted_tools_are_registered),
    ("follow_up_event_only_from_workers", follow_up_event_only_from_workers),
    ("decisions_log_updated", decisions_log_updated),
)


def main() -> int:
    failures = [(name, messages) for name, check in CHECKS if (messages := check())]
    if not failures:
        print(f"agent rules: {len(CHECKS)} checks passed")
        return 0
    for name, messages in failures:
        print(f"{name}:")
        for message in messages:
            print(f"  - {message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
