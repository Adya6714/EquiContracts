# EquiContracts — Repository Plan (v2)

Updated for: dual-sided access (client and PMC are users), three-state verification,
Cursor + Claude Code rule files, and the living-document set (`DECISIONS.md`, `FLOW.md`).

---

## 1. Rule files — what goes where and why

`.cursorrules` is legacy and, worse, **silently ignored by Cursor Agent mode**. Do not
create one. Use this instead:

```
AGENTS.md                    single source of truth. Cursor Agent mode reads natively.
CLAUDE.md                    symlink → AGENTS.md, so Claude Code reads the same content
.cursor/rules/*.mdc          glob-scoped rules AGENTS.md cannot express
```

Create the symlink once:

```bash
ln -s AGENTS.md CLAUDE.md
git add AGENTS.md CLAUDE.md
```

### Why both, rather than just AGENTS.md

AGENTS.md is plain Markdown — no globs, no conditional loading. Everything in it loads on
every request, so it must stay lean. The `.mdc` files let a rule fire _only_ when the agent
touches a specific directory, which is exactly how the agent-ownership table becomes
mechanical rather than aspirational.

Budget: keep total always-apply content under ~2,000 tokens, and each `.mdc` under 500 lines.

### The `.mdc` set

| File                  | Frontmatter                             | Purpose                                                                   |
| --------------------- | --------------------------------------- | ------------------------------------------------------------------------- |
| `00-global.mdc`       | `alwaysApply: true`                     | The five non-negotiables only. Short.                                     |
| `10-db-schema.mdc`    | `globs: packages/db/**`                 | Migration conventions, RLS requirements, `numeric(18,2)`                  |
| `20-api.mdc`          | `globs: apps/api/app/{routers,core}/**` | Session scoping, error shapes, no PII in logs                             |
| `30-rules-engine.mdc` | `globs: apps/api/app/rules/**`          | **No LLM calls, ever.** Rules as YAML data                                |
| `40-extraction.mdc`   | `globs: packages/extraction/**`         | Schema-constrained output, decimal strings, day-first dates               |
| `50-web.mdc`          | `globs: apps/web/**`                    | Component conventions, ₹ formatting, verified-data-only on client screens |
| `60-tests.mdc`        | `globs: apps/api/tests/**`              | Never skip, never weaken, test intent not implementation                  |

Example — `30-rules-engine.mdc`:

```markdown
---
description: Rules engine conventions — deterministic risk logic
globs:
  - "apps/api/app/rules/**"
alwaysApply: false
---

# Rules engine

This directory is DETERMINISTIC. A wrong BG expiry alert costs real money, so
nothing here may depend on a model's judgement.

- MUST NOT import or call anthropic, openai, litellm, or any LLM client. CI enforces this.
- MUST express each rule as a YAML file in `definitions/`, not as Python branching.
- Every rule needs: id, when, severity, evidence_query, action_owner, autonomy_tier.
- `autonomy_tier` defaults to `draft`. Never ship a new rule at `auto_with_undo`.
- MUST use Decimal for money. Never float.
- Rules are pure functions of DB state. No network calls, no clock reads outside the
  injected `now` parameter — otherwise they aren't testable.
```

---

## 2. Living documents

Three files that change constantly and are read constantly. These are the ones you asked
for, plus notes on how to keep them from rotting.

### `DECISIONS.md` — the decision log

Append-only. Every meaningful choice, with the reasoning. The purpose is that in month four,
when you or an agent wonders "why Temporal and not a cron", the answer exists and you don't
relitigate it.

Entry format:

```markdown
## D-014 — Postgres RLS instead of application-layer tenancy

- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** Adya
- **Status:** accepted

**Context.** Contractors, clients, and PMCs share projects. One forgotten WHERE clause
leaks one contractor's rates to a rival on the same site.

**Options considered.**

1. Application-layer filtering — every query adds org scoping. Rejected: relies on
   remembering, and one miss is catastrophic.
2. Schema-per-tenant — strong isolation, but migrations across hundreds of schemas and
   cross-tenant client dashboards become painful.
3. Postgres RLS with FORCE — chosen.

**Decision.** RLS with `FORCE ROW LEVEL SECURITY`, session-scoped via
`set_config('app.current_org_id', ..., true)`.

**Why this approach.** The boundary lives in the database, so it holds even when
application code is wrong. `FORCE` matters because plain `ENABLE` exempts the table owner,
which would make our own tests pass vacuously.

**Trade-offs accepted.** Every session must set the org var; forgetting it returns zero
rows rather than erroring, so we added an explicit test for the unset case. Org creation
can't go through the app role at all, requiring a separate narrow provisioning connection.

**Revisit if.** We need cross-tenant analytics that RLS makes impractical.
```

Rule for agents, stated in AGENTS.md: **any PR that introduces a library, changes a
boundary, or picks between two viable approaches must append a `DECISIONS.md` entry.**
Small entries are fine. Silence is not.

### `FLOW.md` — execution flow map

Answers "where does control actually go" without reading the whole codebase. Sections:

1. **Entry points** — table of every way execution starts (HTTP route, Temporal schedule, webhook, CLI)
2. **Request lifecycle** — the standard path, middleware order, where org scoping is applied
3. **Call graphs per flow** — mermaid, one per major flow (ingestion, verification, rule evaluation, dashboard read)
4. **Data mutation map** — which module is allowed to write which table. Makes unexpected writes obvious in review.
5. **Session change log** — what AI changed, when, in which session

### `BOOK.md` — complete technical report

Long-form report for a technical reader. Must contain every HLD and LLD mermaid in full,
cite code, report numbers, and **not omit** unwired modules or failed gates (Appendix D).
Agents update BOOK in the same pass as FLOW/DECISIONS when architecture or runtime status
changes. Length is expected.

The FLOW session log needs a defined format or it degrades into noise:

```markdown
## Session log

### 2026-08-14 · session 07 · Cursor · api-agent

- **Task:** Add claim_expiry countdown to BG list endpoint
- **Files touched:** `routers/bg.py`, `rules/definitions/bg_claim_expiry.yaml`
- **New call path:** `GET /bg` → `bg_service.list_with_countdowns()` →
  `rules.evaluate('bg_claim_expiry')`
- **Not changed:** extraction, schema
- **Verify run:** pass (74 tests)
- **Decision logged:** D-018
```

Keep this trimmed to the last ~20 sessions and archive the rest to
`docs/history/flow-archive-YYYY-MM.md`. An unbounded log stops being read, and a document
nobody reads is worse than none because it creates false confidence.

### `docs/plans/` — the implementation plans

```
docs/
├── plans/
│   ├── 00-repo-implementation-plan.md   # this file's content, in-repo
│   ├── phase-0-foundation.md            # detailed, gated
│   ├── phase-1-bg-verify.md
│   ├── phase-2-milestone-validator.md
│   ├── phase-3-evidence-locker.md
│   ├── phase-4-payment-mismatch.md
│   ├── phase-5-resolution.md
│   └── cross-phase-conventions.md
├── architecture/
│   ├── project-map.md                   # orientation: modules, layers, flows
│   ├── HLD.md                           # mermaid, system + access model
│   └── LLD.md                           # mermaid, ER + state machines + sequences
├── domain/
│   ├── glossary.md                      # BG, WCC, DLP, RA bill, TDS, WCT, PMC, annexure
│   ├── dataset-findings.md              # what the 11 real documents revealed
│   └── master-data-model.md             # the Project→...→Action Owner backbone
├── security/
│   └── pre-launch-checklist.md          # mapped launch security gaps
├── runbook.md                           # deploy, rollback, restore-from-backup
DECISIONS.md
FLOW.md
BOOK.md                               # complete technical report + all HLD/LLD diagrams
```

Each phase plan carries the same five sections: **Scope** (in and explicitly out),
**Prerequisites**, **Steps with gates**, **Exit criteria**, **Agent assignments**.

---

## 3. Full tree

```
equicontracts/
├── AGENTS.md
├── CLAUDE.md                       → symlink to AGENTS.md
├── DECISIONS.md
├── FLOW.md
├── README.md
├── Makefile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .gitleaks.toml
│
├── .cursor/rules/
│   ├── 00-global.mdc
│   ├── 10-db-schema.mdc
│   ├── 20-api.mdc
│   ├── 30-rules-engine.mdc
│   ├── 40-extraction.mdc
│   ├── 50-web.mdc
│   └── 60-tests.mdc
│
├── .github/workflows/
│   ├── ci.yml
│   └── eval.yml
│
├── docs/                           (as above)
├── specs/
│   ├── 00-foundation/{requirements,design,tasks}.md
│   ├── 01-bg-verify/ … 05-payment-mismatch/
│   └── adr/
│
├── packages/
│   ├── db/
│   │   ├── migrations/
│   │   │   ├── 0001_orgs_and_access.sql      # org types + project_participant
│   │   │   ├── 0002_rls.sql
│   │   │   ├── 0003_documents_extraction.sql # three-state verification
│   │   │   ├── 0004_work_orders_annexures.sql
│   │   │   ├── 0005_bg_verify.sql
│   │   │   ├── 0006_milestone_chain.sql
│   │   │   ├── 0007_exceptions.sql
│   │   │   └── 0008_resolution.sql
│   │   ├── seed/dev_seed.sql
│   │   └── README.md
│   └── extraction/
│       ├── schemas/                # 5 doc types first
│       │   ├── proforma_invoice.json
│       │   ├── certified_ra_bill.json
│       │   ├── bank_guarantee.json
│       │   ├── warranty_certificate.json
│       │   └── work_completion_certificate.json
│       ├── prompts/                # versioned per extractor
│       ├── router.py
│       ├── vision_extractor.py
│       ├── structured_extractor.py
│       ├── classifier.py           # 10 email categories
│       ├── confidence.py
│       ├── eval_harness.py
│       └── tests/
│
├── apps/
│   ├── api/
│   │   ├── pyproject.toml
│   │   ├── requirements{,-dev}.txt
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── core/
│   │   │   │   ├── config.py
│   │   │   │   ├── db.py            # org_scoped / participant_scoped / provisioning
│   │   │   │   ├── auth.py          # 6 roles
│   │   │   │   ├── storage.py
│   │   │   │   ├── financial_fields.py
│   │   │   │   ├── verification.py  # the 3-state machine
│   │   │   │   ├── event_log.py
│   │   │   │   ├── project_code.py
│   │   │   │   └── errors.py
│   │   │   ├── routers/
│   │   │   │   ├── projects.py
│   │   │   │   ├── inbound.py
│   │   │   │   ├── documents.py
│   │   │   │   ├── review.py        # contractor Inbox Review
│   │   │   │   ├── bg.py
│   │   │   │   ├── milestones.py
│   │   │   │   ├── exceptions.py
│   │   │   │   ├── client_dashboard.py   # read-only, verified-only
│   │   │   │   ├── imports.py       # Excel/CSV accounting
│   │   │   │   └── advisor.py
│   │   │   ├── rules/
│   │   │   │   ├── engine.py
│   │   │   │   ├── definitions/*.yaml
│   │   │   │   ├── aging_clock.py
│   │   │   │   ├── reconcile.py
│   │   │   │   ├── idle_bg.py
│   │   │   │   └── scoring.py
│   │   │   ├── workflows/
│   │   │   └── generation/
│   │   └── tests/
│   └── web/
│       ├── app/
│       │   ├── (contractor)/        # Setup · Inbox Review · Modules · Exceptions
│       │   └── (client)/            # read-only dashboard
│       ├── components/
│       └── lib/
│
├── eval/eval_set_v0/
├── scripts/
│   ├── check_agent_rules.py
│   ├── new_migration.sh
│   └── eval_fetch.sh
└── docs/
```

Note the web route groups: `(contractor)` and `(client)` as separate Next.js groups, not
one app with conditional rendering. Different layouts, different navigation, and — most
importantly — it makes "did we leak unverified data to a client screen" answerable by
looking at one directory.

---

## 4. Schema corrections from the product spec

Four changes from my earlier plan. Each one is expensive to retrofit.

**1. `org.org_type` + `project_participant`.** The client and PMC are users, not just
entities the contractor tracks. RLS policy becomes two-clause:

```sql
CREATE POLICY project_access ON project
  USING (
    owner_org_id = current_org_id()
    OR EXISTS (SELECT 1 FROM project_participant pp
               WHERE pp.project_id = project.id
                 AND pp.org_id = current_org_id())
  );
```

**2. Three-state verification, not a boolean.**

```sql
state text NOT NULL DEFAULT 'ai_extracted'
     CHECK (state IN ('ai_extracted','needs_review','verified')),
CONSTRAINT financial_needs_human
  CHECK (NOT (is_financial AND state = 'verified' AND verified_by IS NULL))
```

**3. `annexure_requirement` / `annexure_submission`.** Annexures are defined per work order
and tracked against each proforma. This is what makes "incomplete submission" checkable
rather than a vibe.

**4. `exception.action_owner`.** Defaults to contractor. Client/PMC values exist for genuine
client-side blockages, which is what makes certification ageing honest rather than
accusatory.

---

## 5. Agent ownership

| Agent              | Owns                                       | `.mdc` that auto-attaches | Isolation             |
| ------------------ | ------------------------------------------ | ------------------------- | --------------------- |
| `schema-agent`     | `packages/db/**`                           | `10-db-schema`            | worktree + own dev DB |
| `extraction-agent` | `packages/extraction/**`                   | `40-extraction`           | worktree              |
| `api-agent`        | `apps/api/app/{routers,core,workflows}/**` | `20-api`                  | worktree              |
| `rules-agent`      | `apps/api/app/rules/**`                    | `30-rules-engine`         | worktree              |
| `web-agent`        | `apps/web/**`                              | `50-web`                  | worktree              |
| `test-agent`       | `apps/api/tests/**`                        | `60-tests`                | worktree              |
| `security-agent`   | reviews diffs only                         | `00-global`               | none                  |

3 concurrent code-writing agents maximum.

---

## 6. Commit sequence

```
 1. chore: scaffold, Makefile, docker-compose
 2. docs: AGENTS.md + CLAUDE.md symlink + .cursor/rules/*.mdc
 3. docs: DECISIONS.md, FLOW.md with first entries
 4. docs: HLD, LLD, glossary, master data model
 5. docs: phase-0 plan + foundation spec + ADRs
 6. feat(db): orgs, access model, project_participant
 7. feat(db): RLS — forced, fail-closed, participant-aware
 8. test: tenancy suite (contractor isolation + client read-only + unset-org)
 9. feat(db): documents + three-state extraction
10. feat(api): config, session types, auth (6 roles), storage
11. feat(api): financial field registry + verification state machine
12. ci: rule enforcement, lint, types, tests, secret scan
13. test: freeze eval_set_v0 from 11 real documents
14. feat: eval harness (extractor unwired)
15. feat: walking skeleton — project setup → email → review queue
16. refactor: reference vertical slice
    ─────── agents start here ───────
```
