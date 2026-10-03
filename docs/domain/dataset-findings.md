# Dataset Findings

What the 11 real historical documents revealed. These findings drove schema corrections
and extraction conventions that would not have been discovered from the product spec alone.

---

## Documents analysed

| # | Source | Type | Key finding |
|---|--------|------|-------------|
| 1 | GECPL BG invocation | Bank guarantee | Dual dates: expiry vs claim expiry 366 days apart |
| 2 | GECPL resolution statement | Dispute evidence | Client-admission citation (payment status note) |
| 3 | Raheja tax invoice | Tax invoice | Same-state GSTINs → CGST+SGST; IGST must be null, not 0 |
| 4 | Shantigram RA-01 | Certified RA bill | 13-item annexure checklist; workbook with 60+ sheets |
| 5 | Runwal Greens statement | Payment reconciliation | Per-WO gross/TDS/WCT/retention + categorized debit lines |
| 6 | Jai Vijay correspondence | Potential dispute | Reminder sequence 2; word "dispute" never appears |
| 7 | DMRC debit note | Debit note | Deadline, six lettered defect locations, third-party pressure |
| 8–11 | Various | Mixed | Supporting evidence for classification categories |

---

## Schema corrections driven by findings

### 1. BG expiry vs claim expiry (GECPL)

A single `expiry_date` field discards a full year of live claim exposure. The GECPL BG
has expiry `2023-04-23` and claim expiry `2024-04-23`. Two separate columns, two separate
countdown clocks.

### 2. Null vs zero for absent tax fields (Raheja)

Both GSTINs have state code 27 (Maharashtra), so CGST+SGST apply and IGST is absent.
Extracting IGST as `0.00` is incorrect — it implies the field was present and zero. Must
extract as `null`.

### 3. Annexure checklist as structured data (Shantigram)

Annexures are defined per work order and tracked per proforma submission. The checklist is
not free text — it's a completeness assertion against a known list.

### 4. Cross-foot assertions (Runwal Greens)

Payment reconciliation has per-line amounts that must sum to stated totals. The eval
harness must assert cross-footing, not just individual field accuracy.

### 5. Intent-based classification (Jai Vijay)

The document never uses the word "dispute" but its intent is clearly adversarial. Category
assignment must read intent, not vocabulary.

### 6. Reminder sequence parsing (Jai Vijay)

Subject lines like "Reminder - 02" carry semantic weight — the sequence number indicates
escalation and affects urgency scoring.

### 7. Third-party pressure as a signal (DMRC)

When a government body issues a debit note with a deadline and third-party references,
this is a distinct escalation pattern that the rules engine should detect.

---

## Conventions established

- Money as decimal strings in extraction output (`"17080000.00"`)
- Dates as ISO-8601 plus `raw_text` (Indian day-first formats)
- Financial vs non-financial accuracy reported separately in eval
- `null` for absent fields, never `0.00`
