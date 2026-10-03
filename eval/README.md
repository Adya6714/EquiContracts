# Evaluation sets

EquiContracts measures extraction and (later) intake quality against a frozen set of
real construction documents.

## `eval_set_v0`

- Catalogue: [`eval_set_v0/cases.json`](eval_set_v0/cases.json)
- Human answer keys: [`eval_set_v0/expected/`](eval_set_v0/expected/)
  (example: `gecpl-bg-invocation.json`, not `gecpl.json`)
- **Frozen rule:** never edit anything under `eval/eval_set_v0/` once committed.
  CI fails the PR if that tree changes. Fix the code or add a new set — do not
  "fix" accuracy by editing gold labels.
- **Documents are not in git.** Raw `.msg` / workbooks live in a private bucket
  (see `EVAL_BUCKET` / `scripts/eval_fetch.py`) or a local reference folder.
  `eval_set_v0/documents/` may hold staged copies for local runs; do not commit them.

## Scoring

The harness in `packages/extraction/eval_harness.py` scores against **reviewed**
expected JSON only. Draft or unreviewed answer keys must never be used as gold.

## Future sets

When a new document-type reader is built, draft answer keys for that type first
(AI draft → co-founder correct), then build the reader. See MASTER_PLAN backlog.
