# Phase 5 — Resolution Statement

**Status:** Not started  
**Duration:** ~4 weeks  
**Prerequisites:** Phase 3 evidence locker populated; verified project memory exists

**Goal:** one sentence describing a dispute produces a cited chronology.

> Firm on scope and sequence; step detail will tighten after earlier phases.
> See also [cross-phase-conventions.md](./cross-phase-conventions.md).

---

## Scope

### In

- AI-generated resolution narratives from verified evidence
- Deterministic `citation_guard` so uncited claims never reach the PDF
- Citation typing (prefer client admissions)
- Gaps section ("what is missing")
- Claim composition: `work_value` / `customs_duty` / `interest` / `other`
- Draft → review → final workflow for resolution documents

### Explicitly out

- Automated dispatch to client (always human-reviewed first)
- Legal template generation / arbitration formatting

---

## Last for a reason

Only as good as the project memory beneath it. Built early, it produces confident,
thinly-sourced narratives — worse than nothing in a dispute.

## The architecture that prevents hallucination

Not a prompt instruction. A deterministic post-processor:

```
generate() → LLM produces timeline entries with citation references
           ↓
citation_guard() → drops any entry whose citation doesn't resolve
                   to a real stored artifact
           ↓
render_pdf() → only cited claims reach the page
```

The model *physically cannot* smuggle an uncited claim into the output, because the renderer
never sees it.

## Two features from the real documents

**Citation typing.** The GECPL statement's strongest evidence is the client's own Payment
Status Note — the client confirming dues owed. That's worth more than any contractor claim.
Track `client_admission_citation_count` separately and have retrieval prefer them.

**The gaps section.** "No QC record found for Block B between Feb 20 and Mar 14." A PM
walking into a meeting knowing what's *missing* is better prepared than one with a confident
narrative. Nobody builds this. It's also what makes the tool trustworthy — it admits what it
doesn't have.

## Claim composition

From the HCC statement: `work_value` / `customs_duty` / `interest` / `other`. Not one number.

---

## Exit criteria

- [ ] Generated statement for a real historical dispute is structurally comparable to the
      actual GECPL/HCC documents
- [ ] Zero uncited claims reach the PDF — verified by test
- [ ] Gaps section populates
- [ ] Someone who lived through the actual dispute judges it sound
- [ ] `make test-phase5` green
