# Phase 0 — Foundation

**Duration:** ~3 weeks
**Agents:** none. Steps 0.1–0.13 are hand-written. Reasoning in Step 0.13.

---

## Scope

### In
Repo scaffold · rule files · living documents · access model (contractor + client + PMC) ·
RLS · document ingestion by dedicated project email · three-state verification skeleton ·
eval set frozen · CI enforcement · walking skeleton · reference slice.

### Explicitly out
Clause Clarify (dropped) · real extraction accuracy tuning (Phase 1) · WhatsApp
ingestion · client dashboard (Phase 5 — contractor flow must work first) · Resolution
Statement · accounting API connectors · Temporal (Phase 1).

### Prerequisites
- Docker, Python 3.12, Node 20, pnpm
- An inbound-email provider account (Postmark or SendGrid) with a catch-all on a test subdomain
- The 11 sample documents, in a private bucket

---

## Step 0.1 — Scaffold

```bash
mkdir equicontracts && cd equicontracts && git init

mkdir -p apps/api/app/{core,routers,rules/definitions,workflows,generation}
mkdir -p apps/api/tests
mkdir -p apps/web/app/{"(contractor)","(client)"} apps/web/{components,lib}
mkdir -p packages/db/{migrations,seed}
mkdir -p packages/extraction/{schemas,prompts,tests}
mkdir -p specs/00-foundation specs/adr
mkdir -p docs/{plans,architecture,domain,history}
mkdir -p eval/eval_set_v0/{expected,documents}
mkdir -p .cursor/rules .github/workflows scripts

find apps/api -type d -exec touch {}/__init__.py \;
touch eval/eval_set_v0/documents/.gitkeep
```

`.gitignore` — the important line:

```gitignore
# Real client documents: names, emails, contract values, signatures.
# DPDP Act applies. Once in git history, effectively permanent.
eval/eval_set_v0/documents/*
!eval/eval_set_v0/documents/.gitkeep
.env
```

**Gate 0.1** — `git status` clean of `.env`; tree matches the repo plan.

---

## Step 0.2 — Local services + Makefile

`docker-compose.yml` with Postgres 16 and MinIO. One line that is not decoration:

```yaml
mc anonymous set none local/equicontracts-documents;
```

A public bucket holding contractors' bank guarantees is the worst-case incident for this
product.

`Makefile` targets: `up`, `down`, `migrate`, `reset`, `rules`, `lint`, `fmt`, `typecheck`,
`test`, `verify`, `dev`.

`make verify` = `rules lint typecheck test`. Keep it under ~60 seconds. If it's slow, agents
skip it and so will you.

**Gate 0.2** — `make up`, both containers healthy, MinIO console shows the bucket, bucket
is not public.

---

## Step 0.3 — Rule files

Create three things, not one.

**`AGENTS.md`** — lean, since it loads on every request. Sections: what the system is
(including that contractor writes / client reads); the ~12 absolute rules as MUST NOT with
`[CI]` tags; agent roster; working method; domain glossary.

**`CLAUDE.md`** — `ln -s AGENTS.md CLAUDE.md`. Claude Code reads only CLAUDE.md; Cursor
Agent mode reads AGENTS.md. The symlink means one file serves both.

**`.cursor/rules/*.mdc`** — the seven scoped files from the repo plan. Do **not** create
`.cursorrules`; Cursor Agent mode ignores it, so rules there would silently do nothing.

Rules to enforce in CI (tag these `[CI]` in AGENTS.md):

```
MUST NOT query a tenant table without org scoping
MUST NOT set state='verified' on a financial field without verified_by
MUST NOT add pytest.skip / xfail / delete a failing test
MUST NOT modify anything under eval/eval_set_v0/
MUST NOT use float for money — Decimal only
MUST NOT import or call an LLM from apps/api/app/rules/
MUST NOT log document contents, field values, names, or emails
MUST NOT commit secrets
MUST NOT expose non-verified data on any (client) route
```

That last one is new and specific to the dual-sided model. It's checkable: grep `(client)`
route handlers for queries lacking a `state = 'verified'` filter.

**Gate 0.3** — Open Cursor, ask the agent "what are the rules in this repo?" It should
recite them. Edit a file under `apps/api/app/rules/` and confirm `30-rules-engine.mdc`
auto-attaches.

---

## Step 0.4 — Living documents

`DECISIONS.md` — seed with the Phase 0 decisions you've already made, so the format is
established before agents start appending:

- D-001 Monorepo over split repos
- D-002 Postgres RLS over application-layer tenancy
- D-003 Dual-sided access via `project_participant`, not separate deployments
- D-004 Three-state verification over a boolean
- D-005 Email-first ingestion, WhatsApp deferred
- D-006 Financial fields never auto-verify
- D-007 FastAPI + Next.js
- D-008 `.cursor/rules` + AGENTS.md, no `.cursorrules`

Each with Context / Options considered / Decision / Why / Trade-offs / Revisit-if.

`FLOW.md` — five sections: entry points, request lifecycle, call graphs (mermaid),
data mutation map, session log. Seed the session log with your own Phase 0 sessions so the
format exists.

`docs/plans/` — this file plus stubs for phases 1–5. `docs/architecture/` — HLD.md and
LLD.md. `docs/domain/` — glossary, dataset findings, master data model.

**Gate 0.4** — a new agent session, given only `docs/`, can explain what the product does
and where code lives.

---

## Step 0.5 — Foundation spec

`specs/00-foundation/requirements.md` in EARS notation. ~18 requirements across: access
control (5), project onboarding (3), ingestion (4), verification (4), audit (2).

The ones carrying the most weight:

```
R-F3   IF a request references a project the principal's org neither owns nor
       participates in, THEN the system SHALL respond identically to a
       non-existent project.

R-F5   WHEN a client or PMC user reads any project data, the system SHALL return
       only records in state 'verified'.

R-F7   A contractor org SHALL NOT be able to read any record belonging to another
       contractor org, including on a shared project.

R-F12  WHEN an extracted field is financial, the system SHALL set state
       'needs_review' regardless of confidence.

R-F16  WHEN a verified field is contradicted by a later document, the system SHALL
       return it to 'needs_review' rather than overwriting it.
```

R-F3's phrasing matters: identical responses, not just both-denied. Different status codes
for "missing" and "forbidden" build an existence oracle across tenants.

Plus `design.md`, `tasks.md`, and ADRs 0001–0008 mirroring the DECISIONS entries.

**Gate 0.5** — every requirement answers "what test proves this?"

---

## Step 0.6 — Orgs and access model

`packages/db/migrations/0001_orgs_and_access.sql`

```sql
CREATE TABLE org (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name      text NOT NULL,
  org_type  text NOT NULL CHECK (org_type IN ('contractor','client','pmc','internal'))
);

CREATE TABLE app_user (
  id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id  uuid NOT NULL REFERENCES org(id),
  email   text NOT NULL UNIQUE,
  role    text NOT NULL CHECK (role IN (
            'contractor_admin','contractor_user',
            'client_mgmt','client_pm','pmc_user','ec_admin'))
);

CREATE TABLE project (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_org_id   uuid NOT NULL REFERENCES org(id),
  name           text NOT NULL,
  project_code   text NOT NULL UNIQUE,       -- EC-MUM-101
  inbound_email  text NOT NULL UNIQUE,
  created_at     timestamptz NOT NULL DEFAULT now()
);

-- Grants client/PMC read access WITHOUT making them tenants of contractor data.
CREATE TABLE project_participant (
  project_id  uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  org_id      uuid NOT NULL REFERENCES org(id),
  role        text NOT NULL CHECK (role IN ('client','pmc')),
  data_scope  text NOT NULL DEFAULT 'verified_only'
              CHECK (data_scope IN ('verified_only')),
  PRIMARY KEY (project_id, org_id)
);
```

`data_scope` has one legal value today. It exists as a column so that widening access later
is a data change with an explicit audit trail, rather than a code change someone makes
casually.

Add a constraint worth having: `owner_org_id` must reference an org of type `contractor`.
Enforce via trigger, since CHECK can't do subqueries.

**Gate 0.6** — `make reset` applies clean. Inserting a project owned by a `client`-type org
fails.

---

## Step 0.7 — RLS, participant-aware

`0002_rls.sql`. The two-clause policy is the part that differs from a standard single-tenant
setup.

```sql
CREATE OR REPLACE FUNCTION current_org_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.current_org_id', true), '')::uuid;
$$;

ALTER TABLE project ENABLE ROW LEVEL SECURITY;
ALTER TABLE project FORCE  ROW LEVEL SECURITY;

CREATE POLICY project_read ON project FOR SELECT
  USING (
    owner_org_id = current_org_id()
    OR EXISTS (SELECT 1 FROM project_participant pp
               WHERE pp.project_id = project.id
                 AND pp.org_id = current_org_id())
  );

-- Writes are owner-only. Clients and PMCs never write project data.
CREATE POLICY project_write ON project FOR ALL
  USING (owner_org_id = current_org_id())
  WITH CHECK (owner_org_id = current_org_id());
```

Three things to get right:

- **`FORCE`, not just `ENABLE`.** Plain ENABLE exempts the table owner, so tests run as
  superuser pass vacuously and you'd ship believing you're isolated.
- **Separate read and write policies.** A single `FOR ALL` policy with the participant
  clause would let a client *write* to the contractor's project.
- **`current_setting(..., true)`** returns NULL when unset rather than erroring. NULL makes
  every comparison false, so an unscoped session sees nothing. Fail closed.

For child tables (`work_order`, `document`, etc.), scope through the project rather than
duplicating the participant subquery everywhere — a helper function
`can_read_project(uuid)` keeps the policies short and consistent.

**Gate 0.7** — connect **as `equicontracts_app`**, never postgres, and verify all seven:

```sql
SET ROLE equicontracts_app;
SET app.current_org_id = '<contractor-A>';
SELECT count(*) FROM project;                              -- only A's projects
SELECT count(*) FROM project WHERE id='<contractor-B-project>';  -- 0

SET app.current_org_id = '<client-org>';
SELECT count(*) FROM project;                              -- participant projects, >0
UPDATE project SET name='x' WHERE id='<participant-project>';    -- 0 rows

SET app.current_org_id = '<contractor-B>';
SELECT count(*) FROM project WHERE id='<contractor-A-project>';  -- 0, shared site or not

RESET app.current_org_id;
SELECT count(*) FROM project;                              -- 0 ← the critical one
```

The last one is the catastrophic default. A forgotten middleware, a background job, a new
code path — all land there.

---

## Step 0.8 — Documents and three-state verification

`0003_documents_extraction.sql`

```sql
CREATE TABLE document (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     uuid NOT NULL REFERENCES project(id),
  filename       text NOT NULL,
  storage_uri    text NOT NULL,
  sha256         text NOT NULL,
  source         text NOT NULL CHECK (source IN ('email_forward','manual_upload')),
  sender_email   text,
  reminder_sequence_number integer,   -- parsed from "Reminder - 02"
  received_at    timestamptz
);

CREATE TABLE document_classification (
  document_id uuid PRIMARY KEY REFERENCES document(id),
  category    text NOT NULL CHECK (category IN (
                'routine','core_evidence','potential_dispute','bg_document',
                'proforma_invoice','certified_invoice','wcc_handover',
                'warranty_document','payment_advice','delay_site_instruction_mom')),
  confidence  numeric(4,3),
  model_version text
);

CREATE TABLE extracted_field (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id   uuid NOT NULL REFERENCES document(id),
  field_name    text NOT NULL,
  field_value   text,
  state         text NOT NULL DEFAULT 'ai_extracted'
                CHECK (state IN ('ai_extracted','needs_review','verified')),
  is_financial  boolean NOT NULL DEFAULT false,
  confidence    numeric(4,3),
  model_version text,
  verified_by   uuid REFERENCES app_user(id),
  verified_at   timestamptz,
  superseded_by uuid REFERENCES extracted_field(id),   -- R-F16
  CONSTRAINT financial_needs_human
    CHECK (NOT (is_financial AND state='verified' AND verified_by IS NULL))
);
```

That last CHECK is the highest-value line in the schema. The database now **physically
refuses** to mark a ₹1.7 crore BG value as verified without a named human, at any model
confidence. Not a policy anyone can forget.

`superseded_by` implements R-F16: a corrected value creates a new row and points the old one
at it, so the original AI output and the correction both survive. That history is your
training signal.

Also: partial index on the review queue, it's a hot path.

```sql
CREATE INDEX extracted_field_review_idx
  ON extracted_field (state, is_financial, created_at)
  WHERE state = 'needs_review';
```

**Gate 0.8** — three inserts: financial + high confidence + `needs_review` succeeds;
financial + `verified` + NULL `verified_by` **fails**; non-financial + `verified` +
NULL `verified_by` succeeds.

---

## Step 0.9 — Work orders, annexures, BG

`0004_work_orders_annexures.sql` and `0005_bg_verify.sql`.

Fields the real documents proved necessary:

```sql
-- work_order
certification_sla_days     integer,      -- the "Client Clock" baseline
bg_clause_conditionality   text CHECK (... IN ('conditional','unconditional')),
retention_bg_ratio_clause  text,         -- "10% retention against 5% BG"

-- annexures are defined PER work order, tracked per proforma
CREATE TABLE annexure_requirement (
  id uuid PRIMARY KEY, work_order_id uuid REFERENCES work_order(id),
  annexure_name text NOT NULL, mandatory boolean NOT NULL DEFAULT true
);

-- bank_guarantee
expiry_date        date,
claim_expiry_date  date,   -- SEPARATE and LATER
CONSTRAINT bg_claim_after_expiry
  CHECK (claim_expiry_date IS NULL OR expiry_date IS NULL
         OR claim_expiry_date >= expiry_date)
```

On the dual dates: your GECPL document has expiry `2023-04-23` and claim expiry
`2024-04-23` — **366 days apart**. A single-date schema silently discards a full year during
which claim exposure is still live. This is the single most consequential field in the BG
model, and it's the kind of thing only real documents reveal.

**Gate 0.9** — GECPL's real values insert successfully; inverted dates rejected; annexure
requirements can be attached to a WO.

---

## Step 0.10 — API core

`app/core/db.py` — **three** session types, and two non-obvious gotchas.

```python
@contextlib.contextmanager
def org_scoped_session(org_id: UUID):
    session = SessionFactory()
    try:
        # set_config(..., is_local => true) is the parameterised equivalent of
        # SET LOCAL. `SET LOCAL x = :param` is a SYNTAX ERROR — SET does not take
        # bind parameters. And f-stringing the org_id here would put an injection
        # point on the tenancy boundary itself.
        session.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(org_id)},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback(); raise
    finally:
        session.close()
```

`is_local => true` scopes it to the transaction, so a pooled connection can't leak one
tenant's org into the next request. Get this wrong and you have an intermittent
cross-tenant leak that is nearly impossible to reproduce.

**The second gotcha:** creating an org can't go through the app role at all — RLS correctly
blocks it, since there's no org to scope to yet. That's the right behaviour (the app can't
invent tenants mid-request), but it means signup and test fixtures need a separate
`provisioning_session()` on an admin connection, guarded at the call site.

Other core modules:
- `auth.py` — 6 roles, `Principal(org_id, org_type, role)`. Phase 0 uses a header stub
  marked `TODO(phase-1)`. Invariant that must survive replacement: **org_id from the
  authenticated principal only, never from a request body.**
- `verification.py` — the state machine. One function, `next_state(field, confidence)`,
  heavily unit-tested. Every transition in one place.
- `financial_fields.py` — explicit registry plus substring hints so an unregistered
  money-shaped field from a future extractor is still caught. Deliberately over-inclusive:
  a false positive costs ten seconds of review, a false negative commits a wrong BG expiry.
- `storage.py` — content-addressed keys, hash computed locally, `ServerSideEncryption`,
  300-second signed URLs, validate the URI belongs to your bucket before signing.

**Gate 0.10** — `make dev`, `curl localhost:8000/health`, and `verification.py` has a test
per transition including `verified → needs_review`.

---

## Step 0.11 — Test suites

`tests/test_access_control.py` — nine tests, superset of Gate 0.7:

```python
test_contractor_sees_only_own_projects
test_contractor_cannot_see_rival_on_shared_site      # the existential one
test_client_sees_participant_projects
test_client_cannot_write_project_data
test_client_sees_only_verified_records               # R-F5
test_pmc_read_access_matches_client_scope
test_direct_uuid_lookup_across_orgs_returns_nothing
test_unset_org_id_returns_zero_rows                  # fail-closed
test_rls_enabled_and_forced_on_every_tenant_table    # catches future drift
```

Fixture notes:
- Create orgs via `provisioning_session()` — RLS blocks the app role, correctly.
- `project_code` and `inbound_email` are globally unique, so a fixed literal collides on
  the second run. Generate a per-run suffix.
- **Run as `equicontracts_app`**, never postgres.

The last test queries `pg_class` for `relrowsecurity AND relforcerowsecurity` on every
tenant table. When someone adds a table in Phase 3 and forgets RLS, it fails that day
rather than six weeks later.

Also: `test_verification_states.py`, `test_financial_fields.py`, `test_inbound.py`,
`test_project_code.py`.

**Gate 0.11** — `make test` green, run as the app role.

---

## Step 0.12 — CI enforcement

`scripts/check_agent_rules.py`. AGENTS.md is advisory — agents read rules and drift anyway.
This is the part that holds.

| Check | Detects |
|---|---|
| `no_skipped_tests` | `pytest.skip`, `xfail`, `@mark.skip` under tests/ |
| `eval_set_untouched` | any diff under `eval/eval_set_v0/` vs main |
| `no_float_money` | `float(...)` near money-named identifiers |
| `no_rls_bypass` | `BYPASSRLS`, `DISABLE ROW LEVEL SECURITY`, `DROP POLICY` |
| `no_pii_logging` | logger calls referencing field_value, subject, filename, sender, email |
| `no_secrets` | `sk-ant-…`, `AKIA…`, hardcoded key assignments |
| `rules_engine_deterministic` | LLM imports under `app/rules/` |
| `client_routes_verified_only` | `(client)` handlers missing a `state='verified'` filter |
| `decisions_log_updated` | PR adds a dependency or migration but no `DECISIONS.md` entry |

Two implementation notes worth knowing in advance:

**Skip comment lines.** A naive `no_rls_bypass` check flags the comment in `0002_rls.sql`
that *describes* the rule. Add an `_is_comment()` guard for `--`, `#`, `*`, `/*`.

**The eval check needs history.** It diffs `origin/main...HEAD`, so CI checkout must use
`fetch-depth: 0`. Without it, the check silently passes on a shallow clone — worse than not
having it, because you'd trust it.

CI step order: rules → lint → format → typecheck → tests → gitleaks. Cheapest and
most-likely-to-fail first.

**Gate 0.12** — deliberately introduce each violation, watch CI catch it, remove it. A
guardrail you have never seen fail is a guardrail you do not know works.

---

## Step 0.13 — Eval set, walking skeleton, reference slice

### Eval set (highest-value manual hour of Phase 0)

`cases.json`: 11 entries with `id`, `sha256`, `doc_type`, `expected_category`, `extractor`
(`vision` | `structured`), and a `why` line. Hashes let CI verify it's testing the right
bytes without the bytes living in git.

`expected/*.json`: hand-transcribed. Assertions worth encoding:

- **GECPL** — PBG `0544BGR0097618` ₹1,70,80,000, expiry `2023-04-23`, claim expiry
  `2024-04-23`. Plus the client-admission citation (the Payment Status Note where the
  client itself confirmed dues owed) — highest-weight citation type for Phase 4.
- **Raheja invoice** — both GSTINs state code 27, so CGST+SGST apply and **IGST must
  extract as `null`, not `0.00`**. A model that fills zeros for absent fields fails this
  case. That is the point.
- **Shantigram RA-01** — the 13-item annexure checklist. Workbook has 60+ sheets, so this
  also tests that the structured parser *finds* CHECKLIST rather than scanning everything.
- **Runwal Greens** — per-WO gross/TDS/WCT/retention plus categorized debit lines, with
  cross-foot assertions to the stated totals.
- **Jai Vijay** — `potential_dispute`, `reminder_sequence_number: 2`. Note in the fixture
  that the word "dispute" never appears: this tests that classification reads intent, not
  vocabulary.
- **DMRC** — debit-note ref, deadline, six lettered defect locations, and
  `third_party_pressure` as a distinct signal.

Conventions to fix here because they bite in Phase 1: money as **decimal strings**
(`"17080000.00"`, never a JSON number — floats lose precision); dates ISO **plus
`raw_text`** (Indian documents are day-first; `05.07.2022` is 5 July, and keeping the raw
string lets a reviewer verify rather than trust).

`eval_harness.py` — write it now, with `run_extraction()` raising `NotImplementedError`.
Reports **financial vs non-financial accuracy separately**; an aggregate hides regressions
in exactly the fields that cost money. Accepts `--fail-under`. Existing first means there is
never a window where extraction is tuned without a scoreboard.

### Walking skeleton

```
Project Setup form → POST /projects → project + WO + participant rows
                   → inbound_email displayed (LodhaSupremus042@equicontracts.ai)
Forward a document → POST /inbound/email → S3 object + document row
                   → appears in contractor Inbox Review
```

Deliberately unstyled. Its only job is proving deployment, auth, storage, and DB are wired.

For `inbound.py`: verify the provider HMAC **first** (an unsigned endpoint is an open door
into any contractor's project); resolve the address on a privileged session; quarantine on
no match; parse reminder sequence from the subject; log IDs and counts only.

### Reference slice

One complete example in exactly the style you want everything to read: one migration, one
endpoint, one YAML rule, one screen, one test. Comment the non-obvious choices.

**This is why 0.1–0.13 are hand-written.** Agents extend existing patterns well and invent
poor ones from a blank page. The reference slice is the pattern every agent copies for the
next four months. Two weeks of manual work here is the difference between agents amplifying
a good foundation and multiplying a bad one across three branches at once.

---

## Exit criteria

- [ ] `make verify` green
- [ ] All 9 access-control tests pass, run as the app role
- [ ] Contractor B cannot see Contractor A's records on a shared project
- [ ] Client can read participant projects, cannot write, sees verified only
- [ ] Unset `app.current_org_id` returns zero rows
- [ ] BG dual-date constraint accepts GECPL values, rejects inverted
- [ ] Financial field cannot reach `verified` without `verified_by`
- [ ] `verified → needs_review` transition implemented and tested
- [ ] Real PDF forwarded → S3 object + document row + appears in Inbox Review
- [ ] Unknown inbound address → quarantine, no document row
- [ ] `eval_set_v0` frozen, 11 cases listed, CI blocks modification
- [ ] Each CI guardrail observed failing at least once
- [ ] `DECISIONS.md` has 8+ entries; `FLOW.md` documents entry points and the ingestion path
- [ ] Reference slice reads the way you want the codebase to read
- [ ] Backup taken and **restore actually tested**

---

## Then agents

Bring in `schema-agent`, `extraction-agent`, `api-agent`, `rules-agent`, `web-agent` with
`isolation: worktree`. Three concurrent maximum.

Brief each with: spec file + reference-code path + **one** task. "Add claim_expiry countdown
following the pattern in `rules/bg_expiry.py`" — not "build BG Verify."

Review each diff as it lands. Merge one branch at a time, full suite between merges. That
last part is the direct lesson from the Grit postmortem: the author nearly abandoned a
45-billion-token project because one parallel agent broke the test harness and batched
merges made the regression untraceable.

If you wire a Postgres MCP server for agents: worktrees isolate *files*, not your database.
Give each worktree its own DB, or route all migrations through `schema-agent` alone.
