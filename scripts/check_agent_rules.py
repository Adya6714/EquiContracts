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
    pattern = re.compile(
        r"\b(?:BYPASSRLS|DISABLE\s+ROW\s+LEVEL\s+SECURITY|DROP\s+POLICY)\b",
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
