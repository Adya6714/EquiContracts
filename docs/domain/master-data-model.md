# Master Data Model

Every record in EquiContracts resolves to this backbone chain. If a record cannot be
placed on it, the record is malformed.

```
Project → Project ID → Work Order → Contractor → Module → Document Type → Date → Status → Action Owner
```

## The chain

| Level | Example | Key |
|-------|---------|-----|
| Project | Lodha Supremus | `project.name` |
| Project ID | EC-MUM-101 | `project.project_code` (globally unique) |
| Work Order | HVAC/WO/042 | `work_order.wo_number` |
| Contractor | Cool Air HVAC Pvt Ltd | `org.name` (where `org.org_type = 'contractor'`) |
| Module | BG Verify | `project_module.module_name` |
| Document Type | Retention BG | `document_classification.category` |
| Date | 2024-04-23 | Context-dependent (expiry, submission, certification) |
| Status | Expiring in 12 days | Computed by rules engine |
| Action Owner | Contractor | `exception.action_owner` |

## Action owner semantics

`action_owner` defaults to **contractor** on every exception. The contractor is the party
who feeds the platform, so they are the party who resolves gaps.

Client and PMC values exist for cases where the blockage genuinely sits with them:
- Certification ageing beyond SLA → `action_owner = 'client_pm'`
- PMC inspection delay → `action_owner = 'pmc'`

These are the cases the client dashboard surfaces honestly, because they're derived from
the work order's own SLA — not editorial judgement.

## Project code format

`EC-{CITY}-{SEQ}` where:
- `EC` = EquiContracts prefix
- `CITY` = 3-letter city code (MUM, DEL, BLR, HYD, etc.)
- `SEQ` = zero-padded 3-digit sequence

Examples: `EC-MUM-101`, `EC-DEL-042`, `EC-BLR-003`

The project code is globally unique and serves as the human-readable identifier. The
inbound email address is derived from the project name (slugified):
`LodhaSupremus042@equicontracts.ai`

## Module list

Modules are optional per project — the contractor enables only what applies.

| Module | What it tracks |
|--------|---------------|
| BG Verify | Expiry, claim expiry, idle detection, renewal |
| Milestone Validator | RA bill → certification → tax invoice → payment chain |
| Payment Mismatch | Certified vs invoiced vs received vs deducted |
| Evidence Locker | Document completeness per work order |
| Resolution Statement | AI-generated dispute summary (Phase 4) |
