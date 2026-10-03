# Phase 4 — Payment Mismatch Import

**Status:** Not started  
**Duration:** ~3 weeks  
**Prerequisites:** Phase 2 milestone chain complete (certified amounts exist to compare)

**Goal:** compare what was certified against what was actually paid.

> Firm on scope and sequence; step detail will tighten after Phase 2.
> See also [cross-phase-conventions.md](./cross-phase-conventions.md).

---

## Scope

### In

- Excel/CSV import of accounting data (Tally, Zoho, SAP, Busy formats)
- Column mapping UI with preview and confirmation
- Comparison: Certified Amount vs Tax Invoice vs Payment Received vs Deductions vs Outstanding
- Variance detection by component (not one lump "short by ₹8L")
- Saved import templates per accounting package (Phase 4b)

### Explicitly out

- Live API connectors to accounting systems (Phase 4c, post-pilot only)
- Automated payment reminders
- Deduction dispute resolution workflows

---

## Deliberately Excel-first

Building Tally/SAP API connectors before pilot validation is three months of plumbing for an
unconfirmed workflow.

- **Phase 4a:** contractor uploads an Excel/CSV export. Column mapping UI with a preview.
- **Phase 4b:** saved import templates per accounting package (Tally, Zoho, SAP, Busy).
- **Phase 4c (post-pilot only):** live API connectors.

## The comparison

```
Certified Amount vs Tax Invoice vs Payment Received vs Deductions vs Outstanding
```

Flag variance beyond tolerance, broken down by which component disagrees. "Payment short by
₹8L" is much less useful than "retention deducted at 10% where the WO says 5%."

---

## Exit criteria

- [ ] Real Tally-format export imports with mapping preview
- [ ] Unmapped columns warn rather than silently drop
- [ ] Mismatches identify *which component* disagrees
- [ ] `make test-phase4` green
