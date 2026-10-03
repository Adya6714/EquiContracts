# Phase 2 — Milestone Validator

**Status:** Not started  
**Duration:** ~6 weeks — the largest phase  
**Prerequisites:** Phase 1 complete, extraction pipeline stable

**Goal:** the full payment journey visible and its failures flagged.

> Less granular than Phases 0 and 1 deliberately: what you learn in Phase 1 will change
> this. Firm on scope and sequence, looser on step-level detail.
> See also [cross-phase-conventions.md](./cross-phase-conventions.md).

---

## Why this is the commercial heart

The founder doc calls it that, and the sample documents confirm it. Every dispute thread in
the eval set traces back to a payment that didn't happen when it should have. This is where
both sides see the most value.

## The chain being modelled

```
Work done → Proforma submitted → Annexures complete → Certification pending
→ Certified → Tax Invoice raised → Payment received → Short payment / deductions
→ WCC → Warranty linked to Final Tax Invoice
```

Each arrow is a place where money gets stuck. Each is a rule.

## Scope

### In

- Proforma → certification → tax invoice → payment chain tracking
- Annexure completeness checking per submission
- Certification ageing (Client Clock) and contractor-side Proforma Aging Clock
- RA bill extraction (structured parser for xlsx)
- Five-component deduction breakdown
- WCC and warranty 3-point reconcile
- Shantigram / Runwal eval cases

### Explicitly out

- Payment mismatch import (Phase 4)
- Resolution statement generation (Phase 5)
- Live accounting API connectors

---

## Build order — tab by tab, not all at once

All four tabs reuse the same `reconcile.py` and `AgingClock` component, so the first tab is
expensive and the rest are cheap.

### 2.1 Proforma tab (~2 weeks)

- Extraction schema for RA bills
- `annexure_requirement` per work order, `annexure_submission` per proforma — this is what
  makes "Incomplete Submission" checkable. Seed the item list from the Shantigram RA-01
  sheet's 13 items.
- Proforma Aging Clock — counts *contractor* delay when documents are incomplete
- Completeness score: applicable items present / applicable items total (exclude NA)

### 2.2 Certified Bills tab (~2 weeks)

- **Structured extractor, not vision.** The Runwal/indiabulls files are genuine xlsx with
  formulas. `openpyxl` reads them precisely and cheaply; a vision model is slower, more
  expensive, and less accurate on data that's already structured.
- `payment_reconciliation` + `deduction_line` — five components (TDS, WCT, retention,
  advance recovery, categorized debits), not one lump figure
- Certification Aging Clock — counts *client* delay against the WO's SLA. This is the
  "Client Clock" and it's the politically sensitive one, which is exactly why it must be
  derived mechanically from the contract's own terms rather than asserted
- Interest exposure: `value × overdue_days × rate / 365`
- Bucketed aging (0-30 / 31-60 / 61-90 / 91-180 / 181-365 / 365+) alongside the single
  overdue number

### 2.3 WCC tab (~1 week)

- 3-point reconcile: scope/quantity match, date alignment, financial value match
- The real check from the mockup: `WCC completion date > final bill period date` → conflict

### 2.4 Warranty tab (~1 week)

- Same 3-point pattern: tenure, date alignment, financial value
- Retention release due = WCC date + DLP months
- New flag type from the Nathani thread: **format rejection** — the client rejecting a
  document's format rather than disputing its content. Distinct from a data mismatch.

---

## Exit criteria

- [ ] Shantigram checklist sheet parses into `annexure_submission` rows without retyping
- [ ] Runwal reconciliation sheet produces correct five-component deduction breakdown
- [ ] Both aging clocks run independently and correctly
- [ ] All four tabs render with real data
- [ ] `make test-phase2` green
