"""Frozen evaluation harness for extraction accuracy."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = ROOT / "eval" / "eval_set_v0"
REFERENCE_DOCS = ROOT / "Equicontracts Reference Documents"

# Private reference filenames keyed by eval case id (bytes stay gitignored).
REFERENCE_BY_CASE = {
    "gecpl-bg-invocation": (
        "sample - BG related resolution statement -GECPL BG invocation "
        "5-7-22- ( Final draft).msg"
    ),
}


@dataclass(frozen=True)
class Accuracy:
    correct: int
    total: int

    @property
    def ratio(self) -> float:
        return self.correct / self.total if self.total else 1.0


def run_extraction(document_path: Path, extractor: str) -> dict[str, Any]:
    """Run the selected extractor against one document."""

    if extractor == "vision" and _is_gecpl_bg_path(document_path):
        from packages.extraction.bg_extractor import extract_bank_guarantee_from_path

        return extract_bank_guarantee_from_path(document_path).as_eval_fields()

    raise NotImplementedError(
        f"{extractor} extraction is not wired for {document_path.name}"
    )


def _is_gecpl_bg_path(document_path: Path) -> bool:
    name = document_path.name.lower()
    return "gecpl" in name or document_path.stem == "gecpl-bg-invocation"


def score_fields(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    financial: bool,
) -> Accuracy:
    expected_fields = expected.get("fields", {})
    actual_fields = actual.get("fields", {})
    selected = [
        (name, definition)
        for name, definition in expected_fields.items()
        if bool(definition.get("financial")) is financial
    ]
    correct = sum(
        1
        for name, definition in selected
        if name in actual_fields
        and actual_fields[name].get("value") == definition.get("value")
    )
    return Accuracy(correct=correct, total=len(selected))


def load_cases() -> list[dict[str, Any]]:
    return json.loads((EVAL_ROOT / "cases.json").read_text())


def resolve_case_document(case: dict[str, Any]) -> Path:
    case_id = case["id"]
    staged = EVAL_ROOT / "documents" / f"{case_id}.msg"
    if staged.exists() and staged.stat().st_size > 0:
        return staged
    ref_name = REFERENCE_BY_CASE.get(case_id)
    if ref_name:
        candidate = REFERENCE_DOCS / ref_name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"no local document for {case_id}; run scripts/eval_fetch.py or place "
        f"{case_id}.msg under eval/eval_set_v0/documents/"
    )


def validate_fixtures() -> int:
    cases = load_cases()
    errors: list[str] = []
    seen_ids: set[str] = set()
    for case in cases:
        case_id = case["id"]
        if case_id in seen_ids:
            errors.append(f"duplicate case id: {case_id}")
        seen_ids.add(case_id)
        if len(case["sha256"]) != 64:
            errors.append(f"{case_id}: invalid sha256")
        expected_path = EVAL_ROOT / "expected" / f"{case_id}.json"
        if case["status"] == "transcribed" and not expected_path.exists():
            errors.append(f"{case_id}: transcribed case has no expected output")
    if errors:
        for error in errors:
            print(error)
        return 1
    transcribed = sum(case["status"] == "transcribed" for case in cases)
    print(f"eval fixtures valid: {len(cases)} cases, {transcribed} transcribed")
    return 0


def run_case(case_id: str) -> int:
    cases = {case["id"]: case for case in load_cases()}
    if case_id not in cases:
        print(f"unknown case id: {case_id}")
        return 1
    case = cases[case_id]
    expected_path = EVAL_ROOT / "expected" / f"{case_id}.json"
    if not expected_path.exists():
        print(f"{case_id}: missing expected output")
        return 1
    document_path = resolve_case_document(case)
    expected = json.loads(expected_path.read_text())
    actual = run_extraction(document_path, case["extractor"])

    print(f"case: {case_id}")
    print(f"document: {document_path}")
    print(f"model_version: {actual.get('model_version')}")
    print()
    print(f"{'field':<22} {'expected':<18} {'actual':<18} {'match'}")
    print("-" * 70)
    for name, definition in expected.get("fields", {}).items():
        exp = definition.get("value")
        got = (actual.get("fields") or {}).get(name, {}).get("value")
        match = "YES" if got == exp else "NO"
        print(f"{name:<22} {str(exp):<18} {str(got):<18} {match}")
    print()
    fin = score_fields(expected, actual, financial=True)
    non = score_fields(expected, actual, financial=False)
    print(f"financial accuracy:     {fin.correct}/{fin.total} ({fin.ratio:.3f})")
    print(f"non-financial accuracy: {non.correct}/{non.total} ({non.ratio:.3f})")
    if actual.get("unresolved"):
        print("unresolved:")
        for item in actual["unresolved"]:
            print(f"  - {item.get('field')}: {item.get('reason')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-under", type=float, default=0.0)
    parser.add_argument("--validate-fixtures", action="store_true")
    parser.add_argument(
        "--case",
        help="Run extraction for a single eval case id (e.g. gecpl-bg-invocation)",
    )
    args = parser.parse_args()
    if args.validate_fixtures:
        return validate_fixtures()
    if args.case:
        return run_case(args.case)
    print("extractors are intentionally unwired in Phase 0")
    print("use --case gecpl-bg-invocation to run the BG extractor")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
