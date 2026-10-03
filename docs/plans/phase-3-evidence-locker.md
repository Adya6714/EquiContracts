# Phase 3 — Evidence Locker

**Status:** Not started  
**Duration:** ~4 weeks  
**Prerequisites:** Phase 2 complete, milestone chain working

**Goal:** project communication auto-files itself.

> Firm on scope and sequence; step detail will tighten after Phase 2.
> See also [cross-phase-conventions.md](./cross-phase-conventions.md).

---

## Scope

### In

- Classification into Routine / Core Evidence / Potential Dispute (and related categories)
- Reminder sequence extraction
- Manual category override
- Evidence Locker screen with filters (category, contractor, date)
- Signals: third-party pressure, defect location lists

### Explicitly out

- Full deep extraction/linking of every ₹ amount to milestones (hard problem — stage later)
- Resolution statement (Phase 5)
- Payment mismatch import (Phase 4)

---

## Two sub-problems people conflate

**Classification is easy.** Routine / Core Evidence / Potential Dispute, from a prompt with
20-30 few-shot examples. Seed those examples from your own documents — the DMRC and Jai
Vijay threads are ground truth for Potential Dispute.

**Extraction and linking is hard.** Attaching a ₹ amount from a compressed photo of a
printed invoice to the right milestone. This is where months go.

Ship classification first; it delivers most of the visible value.

## Signals worth extracting specifically

From the real data:

- **Reminder sequence** — "Reminder - 02" in subject lines. Regex, five minutes, real signal.
- **Third-party pressure** — the client citing *their* client's deadline (DMRC pressuring
  L&T). Strong aggravating factor in a dispute.
- **Defect location lists** — the DMRC thread has six lettered locations in prose.

## The hard classification case

The Jai Vijay email never uses the word "dispute." A keyword classifier fails it. This is
your test that classification reads intent, not vocabulary — keep it as the acceptance case.

---

## Exit criteria

- [ ] DMRC and Jai Vijay threads both classify as Potential Dispute
- [ ] Reminder sequence extracts correctly
- [ ] Manual category override always available regardless of confidence
- [ ] Evidence Locker screen filters by category, contractor, date
- [ ] `make test-phase3` green
