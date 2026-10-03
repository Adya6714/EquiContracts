#!/usr/bin/env python3
"""Fetch private eval bytes by hash and verify before writing locally."""

import hashlib
import json
import os
from pathlib import Path

import boto3  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "eval" / "eval_set_v0"


def main() -> int:
    bucket = os.environ.get("EVAL_BUCKET")
    if not bucket:
        raise SystemExit("EVAL_BUCKET is required")
    prefix = os.environ.get("EVAL_PREFIX", "eval-set-v0").strip("/")
    destination = EVAL_ROOT / "documents"
    destination.mkdir(parents=True, exist_ok=True)
    cases = json.loads((EVAL_ROOT / "cases.json").read_text())
    client = boto3.client("s3")

    for case in cases:
        case_id = case["id"]
        expected_hash = case["sha256"]
        target = destination / f"{case_id}.msg"
        client.download_file(bucket, f"{prefix}/{expected_hash}.msg", str(target))
        actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            target.unlink(missing_ok=True)
            raise SystemExit(f"{case_id}: downloaded bytes failed hash verification")
        print(f"{case_id}: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
