# ADR 0002 — Postgres RLS tenancy

- **Status:** Accepted
- **Decision:** D-002

Force RLS on every tenant table. Scope application transactions through
`set_config('app.current_org_id', ..., true)` so missing scope fails closed and pooled
connections cannot retain a prior tenant.
