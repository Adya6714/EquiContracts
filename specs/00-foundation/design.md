# Foundation Design

Design decisions for Phase 0. Each maps to one or more requirements and a DECISIONS.md entry.

---

## Tenancy model

**Requirement:** R-F1, R-F2, R-F3, R-F4
**Decision:** D-002, D-003, D-004

Postgres RLS with `FORCE ROW LEVEL SECURITY`. Session scoped via
`set_config('app.current_org_id', ..., true)`. Two-clause read policy:
owner OR participant. Write policy: owner only.

Separate provisioning connection for org creation (D-003).

## Verification state machine

**Requirement:** R-F12, R-F13, R-F14, R-F15, R-F16
**Decision:** D-005

Three states with DB-enforced constraint on financial→verified transition.
Corrections create new rows (supersession chain). Contradictions return to needs_review.

## Ingestion pipeline

**Requirement:** R-F9, R-F10, R-F11
**Decision:** D-007

HMAC-first verification. Address resolution on privileged session. Quarantine on no match.
Content-addressed storage with locally-computed SHA-256.

## Access model

**Requirement:** R-F5, R-F7, R-F8
**Decision:** D-004

`org.org_type` determines capabilities. `project_participant` grants scoped read access.
`data_scope` column future-proofs access widening as a data change with audit trail.

## Audit trail

**Requirement:** R-F17, R-F18
**Decision:** (implicit in D-002)

Hash-chained event log. No PII in application logs — IDs and counts only.
