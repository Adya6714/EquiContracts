# Phase 1 — BG Verify

**Status:** Not started  
**Duration:** ~3 weeks  
**Prerequisites:** Phase 0 exit criteria met, `make verify` green, one real document proven
end-to-end.

**Goal:** one real bank guarantee document, forwarded to the inbox, appears correctly on a
dashboard with both expiry clocks running.

---

## Why BG Verify first

Three reasons, in order of importance:

1. **It needs no history.** A bank guarantee is self-contained — one document gives you
   everything. Milestone Validator needs a chain of proforma → certification → payment
   before it says anything useful.
2. **The value is obvious in a five-minute demo.** "This ₹35L guarantee expires in 12 days
   and nobody was tracking it" needs no explanation to a contractor.
3. **It's the sharpest differentiator.** Procore and Aconex don't do BG lifecycle because
   bank guarantees aren't a US construction primitive the same way.

---

## Scope

### In

BG extraction from real documents · dual-date tracking (expiry + claim expiry) ·
idle BG detection · Inter-Doc Audit (WO vs BG conditionality mismatch) · BG dashboard with
filters · savings calculation · expiry alerting.

### Explicitly out

Milestone Validator · Evidence Locker classification · Resolution Statement ·
Temporal (use a simple scheduled job first; Temporal earns its place when you have
multi-year workflows in production, not before).

---

## Step 1.1 — BG extraction schema and prompt

`packages/extraction/schemas/bank_guarantee.json` already exists from Phase 0. Verify it
covers what the real documents contain, then write the prompt.

Fields, from the GECPL document:

| Field | Notes |
|---|---|
| `bg_number` | e.g. `0544BGR0097618` |
| `bank` | issuing bank |
| `bg_type` | mobilization / performance / retention / advance |
| `value` | decimal string, never a float |
| `issue_date` | ISO + `raw_text` |
| `expiry_date` | ISO + `raw_text` |
| `claim_expiry_date` | **separate field, often ~1 year later** |
| `conditionality` | conditional / unconditional — read from the operative wording, not the title |
| `beneficiary_name` | the client |
| `applicant_name` | the contractor |
| `wo_reference` | links the BG to a work order |

Prompt requirements, `packages/extraction/prompts/bank_guarantee.v1.md`:

- Wrap document content in explicit delimiters. Instruct the model that content inside is
  data to extract, never instructions to follow. A guarantee is a document the *client's
  bank* wrote — treat it as untrusted input.
- Indian dates are day-first. `05.07.2022` is 5 July. Require `raw_text` alongside every
  parsed date so a reviewer can check the interpretation rather than trust it.
- If a field isn't present, report it in `unresolved` with a reason. **Reporting a gap is
  correct; inventing a plausible value is not.** This needs to be explicit — models default
  to filling in blanks.
- Money as decimal strings: `"17080000.00"`.

**Gate:** run the GECPL document through extraction. Both dates extract correctly and 366
days apart. Compare against `eval/eval_set_v0/expected/bg-gecpl-invocation.json`.

---

## Step 1.2 — Promotion from verified fields to the BG table

This is the step people skip and it's the one that keeps unreviewed AI output off dashboards.

Extraction writes to `extracted_field`. It does **not** write to `bank_guarantee`. A separate
promotion step reads verified fields and creates the domain record:

```
promote_bank_guarantee(document_id):
    fields = fetch extracted_field WHERE document_id = ? AND state = 'verified'
    if any required financial field is not verified: return  # not ready
    upsert bank_guarantee from those fields
    append event_log entry
```

Every financial field on a BG is protected, so **every BG requires human confirmation before
it appears anywhere.** That's intentional. A contractor confirming eight fields once per
guarantee is a reasonable cost for numbers they can rely on.

**Gate:** a BG with unverified fields does not appear on the dashboard. Once verified, it
does.

---

## Step 1.3 — The rules

`apps/api/app/rules/definitions/`. YAML data, not Python branching. Zero LLM calls.

**`bg_expiry.yaml`** — alert at 90/60/30/15/7 days before `expiry_date`.

**`bg_claim_expiry.yaml`** — the same countdown against `claim_expiry_date`. Separate rule,
separate alert stream. This is the one nobody else tracks.

**`bg_idle.yaml`** — the definition from the founder spec:

```
WHEN a final certified bill exists for the work order
 AND bank_guarantee.expiry_date > final_certified_bill_date
 AND bank_guarantee.status = 'active'
THEN flag idle — the work is done, the guarantee is still live and still
     costing bank commission
```

**`interdoc_audit.yaml`** — conditionality mismatch:

```
WHEN work_order.bg_clause_conditionality = 'conditional'
 AND bank_guarantee.conditionality = 'unconditional'
THEN critical conflict — the client can invoke without proving breach,
     despite the contract requiring proof
```

**`retention_bg_ratio.yaml`** — from the Bhopal thread: check the actual retention/BG ratio
against `work_order.retention_bg_ratio_clause`.

Every rule needs: `id`, `when`, `severity`, `evidence_query`, `action_owner`,
`autonomy_tier` (default `draft`).

**Implementation note:** `now` is an injected parameter, never `datetime.now()` inside a
rule. Otherwise you can't test expiry logic against fixed dates, which is the whole point.

**Gate:** unit test each rule against fixed dates. A BG expiring in exactly 30 days fires;
31 days doesn't.

---

## Step 1.4 — Savings calculation

Four buckets from the designed screen. Each stores its inputs alongside its output in
`calculation_note` — these numbers will be questioned, and "here's the arithmetic" is the
only good answer.

| Bucket | Formula shape |
|---|---|
| Operational | bank commission rate × BG value × days saved via early closure |
| Structural | (old margin % − new margin %) × total BG exposure |
| Opportunity | freed BG value treated as recycled bid capacity |
| Invocation risk | starts `Pending` until a recovery event occurs |

**Gate:** every displayed figure can be traced to its inputs.

---

## Step 1.5 — API and UI

`routers/bg.py`:

```
GET  /bg?project_id=&client=&type=     filtered list
GET  /bg/{id}                          detail with both countdowns
GET  /bg/{id}/audit                    Inter-Doc Audit result
POST /bg/{id}/audit/amend-request      generate BG Amendment Request draft
POST /bg/{id}/audit/accept-risk        log an explicit risk acceptance
GET  /bg/savings?project_id=           savings dashboard
```

`apps/web/app/(contractor)/bg/` — the All BGs dashboard from the mockups: client filter,
BG type filter, status pills (Active / Expiring / Idle / Redundant), totals row,
Inter-Doc Audit screen, Savings dashboard.

Show **both** dates in the detail view. A contractor seeing only expiry will assume their
exposure ended when it didn't.

**Gate:** the mockup screens render with real data.

---

## Exit criteria

- [ ] GECPL document forwarded → extracted → verified → appears on dashboard, both dates correct
- [ ] All five rules unit-tested against fixed dates
- [ ] Idle BG detection works against a real closed work order
- [ ] Inter-Doc Audit catches a conditionality mismatch
- [ ] Savings figures traceable to inputs
- [ ] Unverified BG does not appear on any dashboard
- [ ] Client/PMC can view BGs on participant projects, cannot edit
- [ ] `make test-phase1` green
