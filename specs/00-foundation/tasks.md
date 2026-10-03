# Foundation Tasks

Ordered implementation checklist for Phase 0. Maps to steps in `docs/plans/phase-0-foundation.md`.

---

## Completed

- [x] Step 0.1 — Scaffold directories and .gitignore
- [x] Step 0.3 — Rule files (AGENTS.md, CLAUDE.md, .cursor/rules/\*.mdc)
- [x] Step 0.4 — Living documents (DECISIONS.md, FLOW.md, docs/)
- [x] Step 0.5 — Foundation spec (18 EARS requirements)

## In progress

- [ ] Step 0.2 — docker-compose + Makefile implemented; live gate needs Docker
- [ ] Step 0.6 — Orgs/access migration implemented; live gate needs Docker
- [ ] Step 0.7 — Forced participant-aware RLS implemented; 10 tests need Docker
- [ ] Step 0.8 — Documents and three-state verification implemented; DB gate needs Docker
- [ ] Step 0.9 — Work orders, annexures, BG dual dates implemented; DB gate needs Docker
- [ ] Step 0.10 — API core and `/health` implemented; live storage path needs Docker/MinIO
- [ ] Step 0.11 — Access, verification, storage and inbound suites implemented; DB tests pending
- [ ] Step 0.12 — Rule checks and CI workflows implemented; deliberate-violation exercise pending
- [ ] Step 0.13 — Walking skeleton and eval harness implemented; 2/11 cases transcribed

## Pending

- [ ] Hand-transcribe expected outputs for the remaining 9 real-document eval cases
- [ ] Configure a real inbound provider test subdomain and HMAC secret
- [ ] Run `make up`, `make reset`, all DB/RLS tests, and the full browser flow
- [ ] Exercise every CI guardrail with a deliberate temporary violation
- [ ] Take and restore a database/object-storage backup
