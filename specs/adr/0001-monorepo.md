# ADR 0001 — Monorepo

- **Status:** Accepted
- **Decision:** D-001

Keep database, extraction, API and web code in one repository under `packages/` and
`apps/`. Early features cross all layers and must remain reviewable as one change.
