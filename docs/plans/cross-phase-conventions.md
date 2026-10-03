# Cross-phase conventions

Shared rules for Phases 1–5. Less granular plans still obey these.

---

## Per-phase test suites

Prefer `apps/api/tests/phase0/`, `phase1/`, etc., with `make test-phase0` (and siblings)
targets. Before starting any phase's work, run the *previous* phase's suite — that is the
"is the foundation still solid" check, and it is only meaningful if the suites are separable.

## Real-document gate

Every phase ends with a real-document gate. Not a unit test — one actual document from
`eval_set_v0` through the live pipeline, end to end. Unit tests prove the pieces work;
only this proves they're wired together.

## Agents from Phase 1 onward

Three concurrent max, worktree-isolated, one task each (see `AGENTS.md`). If a Postgres MCP
server is wired: worktrees isolate files, not the database. Separate DB per worktree, or all
migrations through `schema-agent` alone.

## Phase numbering (authoritative)

| Phase | Module |
|------:|--------|
| 0 | Foundation |
| 1 | BG Verify |
| 2 | Milestone Validator |
| 3 | Evidence Locker |
| 4 | Payment Mismatch |
| 5 | Resolution Statement |

Older drafts that swapped phases 4 and 5 are superseded by this table.
