# Decision Log

Append-only. Newest at the bottom. Never edit a past entry — supersede it with a new one
and set the old entry's status to `superseded by D-0NN`.

**Rule for agents (also in AGENTS.md):** any change that introduces a dependency, alters a
boundary, or picks between two viable approaches MUST append an entry here. Small entries
are fine. Silence is not.

Template:

```markdown
## D-0NN — <one-line decision>
- **Date:** YYYY-MM-DD
- **Phase:** N
- **Decided by:** <name or agent>
- **Status:** accepted | superseded by D-0NN | reversed

**Context.** What forced a choice.

**Options considered.**
1. … — why rejected
2. … — why rejected
3. … — chosen

**Decision.** What we're doing, specifically.

**Why this approach.** The reasoning that would otherwise be lost.

**Trade-offs accepted.** What this costs us. Be honest here; this section is what makes
the log worth reading in month six.

**Revisit if.** The condition that should reopen this.
```

---

## D-001 — Monorepo, not separate repos
- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** Adya
- **Status:** accepted

**Context.** Schema, API, and web all change together in early development. Solo builder.

**Options considered.**
1. Three repos (db, api, web) — rejected: a single feature spans all three, so every change
   becomes three PRs and a version-coordination problem.
2. Monorepo — chosen.

**Decision.** Single repo, `apps/` and `packages/` workspaces.

**Why this approach.** One PR can carry a migration, its endpoint, and its screen, so the
change is reviewable as a unit. Splitting a monorepo later is mechanical; merging separate
repos with divergent histories is not.

**Trade-offs accepted.** CI runs more than strictly necessary on small changes. Acceptable
while the test suite is fast.

**Revisit if.** Team grows past ~6 engineers, or CI exceeds ~10 minutes.

---

## D-002 — Postgres RLS for tenancy, not application-layer filtering
- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** Adya
- **Status:** accepted

**Context.** Contractors, clients, and PMCs share projects. Two subcontractors on the same
tower must never see each other's rates. One forgotten `WHERE` clause is a
company-ending incident, not a bug.

**Options considered.**
1. Application-layer org filtering — rejected: correctness depends on remembering, in every
   query, forever, including in code an agent writes at 2am.
2. Schema-per-tenant — rejected: migrations across hundreds of schemas, and the client
   dashboard genuinely needs to span contractors on a shared project.
3. Postgres RLS with `FORCE` — chosen.

**Decision.** RLS on every tenant table, `FORCE ROW LEVEL SECURITY`, session scoped via
`set_config('app.current_org_id', ..., true)`.

**Why this approach.** The boundary lives in the database, so it holds even when the
application layer is wrong. `FORCE` specifically, because plain `ENABLE` exempts the table
owner — meaning tests run as superuser would pass vacuously and we'd ship believing we were
isolated.

**Trade-offs accepted.** Every session must set the org variable; forgetting it returns zero
rows rather than raising, which is silent. Mitigated by an explicit test for the unset case.
Org creation cannot go through the app role at all, requiring a separate provisioning
connection (see D-003).

**Revisit if.** We need cross-tenant analytics that RLS makes impractical.

---

## D-003 — A separate provisioning connection for org creation
- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** Adya
- **Status:** accepted

**Context.** Creating an org is a pre-tenant operation — there is no `org_id` to scope to
yet — so RLS correctly blocks the app role from doing it.

**Options considered.**
1. Grant the app role `BYPASSRLS` — rejected outright: defeats D-002 entirely.
2. Exempt the `org` table from RLS — rejected: leaks the customer list across tenants.
3. A separate, narrow admin connection used only for org creation — chosen.

**Decision.** `provisioning_session()` on `ADMIN_DATABASE_URL`, guarded at the call site,
used only by signup and test fixtures.

**Why this approach.** Keeps the strong default (the application cannot invent tenants
mid-request) while making the one legitimate exception explicit and auditable.

**Trade-offs accepted.** A second credential to manage. A code path that, if misused,
bypasses tenancy — so it needs a CI check that no router imports it.

**Revisit if.** Signup moves to a separate service with its own credentials.

---

## D-004 — Client and PMC are users, via `project_participant`
- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** Adya
- **Status:** accepted

**Context.** The product spec gives the Client and PMC their own dashboards and roles. An
earlier draft of the schema assumed `org = contractor`, which cannot express this.

**Options considered.**
1. Separate client-facing deployment reading a replica — rejected: two systems to keep in
   sync, and the whole value proposition is one shared record.
2. Duplicate verified data into a client-visible table — rejected: divergence, and doubles
   the surface for a leak.
3. `project_participant` grants + a two-clause RLS policy — chosen.

**Decision.** `org.org_type` in (contractor, client, pmc, internal). `project.owner_org_id`
is always a contractor. `project_participant(project_id, org_id, role, data_scope)` grants
read access. Read and write policies are separate so participants can never write.

**Why this approach.** One record, two audiences, one boundary. `data_scope` currently has a
single legal value (`verified_only`), so widening access later is a data change with an
audit trail rather than a casual code change.

**Trade-offs accepted.** Policies are more complex than a single `org_id` match, so a
`can_read_project()` helper is needed to keep them readable. Requires a dedicated test that
a contractor cannot see a rival on a shared project.

**Revisit if.** Clients need write access (e.g. certifying directly in-platform), which
would be a significant product change, not a schema tweak.

---

## D-005 — Three-state verification, not a boolean
- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** Adya
- **Status:** accepted

**Context.** A boolean `verified` cannot distinguish "extracted, confident, not yet
reviewed" from "extracted, uncertain, awaiting a human."

**Decision.** `state in ('ai_extracted','needs_review','verified')`, plus a CHECK
constraint: a financial field cannot be `verified` without a non-null `verified_by`.

**Why this approach.** The constraint makes the most expensive failure mode —
auto-committing a wrong BG expiry — physically impossible rather than merely forbidden. And
only `verified` records are visible to clients, so the state machine doubles as the
client-visibility rule.

**Trade-offs accepted.** More states to test. Requires a `verified → needs_review`
transition for when a later document contradicts a confirmed value, which is easy to forget.

**Revisit if.** Review queue volume makes a fourth state (e.g. `auto_verified_provisional`)
worth the complexity.

---

## D-006 — BG expiry and claim expiry are separate fields
- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** Adya
- **Status:** accepted

**Context.** Discovered from real data. The GECPL bank guarantee has expiry `2023-04-23` and
claim expiry `2024-04-23` — 366 days apart.

**Decision.** Two date columns, with `CHECK (claim_expiry_date >= expiry_date)`, and two
independent countdown clocks.

**Why this approach.** Claim exposure survives expiry. A single-date model silently discards
a full year during which the client can still invoke. This is the highest-consequence field
in the BG model and would not have been discovered without real documents.

**Trade-offs accepted.** Two alert streams per BG instead of one; needs care to avoid
notification fatigue.

**Revisit if.** Never. This is a property of the instrument, not of our model.

---

## D-007 — Email-first ingestion; WhatsApp deferred
- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** Adya
- **Status:** accepted

**Context.** The designed UX is a dedicated per-project address
(`LodhaSupremus042@equicontracts.ai`). WhatsApp is where much Indian site communication
actually lives, but personal-group scraping is a ToS violation and legal exposure.

**Decision.** Inbound email via a provider webhook for v0. WhatsApp Business API considered
for a later phase, with a per-project number.

**Why this approach.** Email needs no platform approval, no template restrictions, and
matches what is already designed. WhatsApp Business would additionally require contractors
to change behaviour (message a bot number instead of a group), which is an unvalidated
assumption and should not block v0.

**Trade-offs accepted.** Some project memory lives in WhatsApp groups we cannot reach, so
early evidence coverage is incomplete.

**Revisit if.** Pilot feedback shows email forwarding compliance is poor.

---

## D-008 — AGENTS.md + `.cursor/rules/*.mdc`; no `.cursorrules`
- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** Adya
- **Status:** accepted

**Context.** Using both Cursor and Claude Code. Cursor Agent mode reads AGENTS.md and
`.cursor/rules/*.mdc` but **not** root `.cursorrules`. Claude Code reads only CLAUDE.md.

**Decision.** `AGENTS.md` as the single source of truth; `CLAUDE.md` as a symlink to it;
`.cursor/rules/*.mdc` for glob-scoped rules.

**Why this approach.** A `.cursorrules` file would be silently ignored in Agent mode —
worse than absent, because we would believe rules were active. The `.mdc` glob scoping is
what turns the agent-ownership table into something mechanical: a rule scoped to
`apps/api/app/rules/**` loads exactly when that directory is edited.

**Trade-offs accepted.** Two formats to maintain. Mitigated by keeping AGENTS.md
authoritative and `.mdc` files thin and path-specific.

**Revisit if.** Claude Code adds native AGENTS.md support, making the symlink unnecessary.

---

## D-009 — Rules engine is deterministic; no model calls
- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** Adya
- **Status:** accepted

**Context.** BG expiry, certification ageing, and payment mismatch are arithmetic over
dates and amounts. A model in that path adds nondeterminism to numbers that must be
defensible in a dispute.

**Decision.** `apps/api/app/rules/` contains no LLM imports, enforced by CI. Rules are YAML
data with an evaluator. LLM use is confined to `packages/extraction/` and
`apps/api/app/generation/`.

**Why this approach.** Makes "where can a hallucination reach a user" answerable by pointing
at two directories. Also makes rules trivially unit-testable, which matters because they are
the product's core value.

**Trade-offs accepted.** Some judgement-shaped rules (is this defect the contractor's fault)
cannot live here and must go through extraction plus human review instead.

**Revisit if.** Never for financial rules.

---

## D-010 — `eval_set_v0` is frozen and CI-protected
- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** Adya
- **Status:** accepted

**Context.** 11 real historical documents with known outcomes are the only objective measure
of extraction quality available.

**Decision.** Hand-verified expected output committed; raw documents kept in a private
bucket and referenced by SHA-256; CI blocks any diff under `eval/eval_set_v0/`.

**Why this approach.** The documented failure mode with coding agents is "fix" a failing test
by editing the expectation. Applied here, that silently destroys the quality baseline and
would not be noticed for weeks. Adding new cases is permitted; altering existing expectations
requires an explicit commit message naming the source of truth.

**Trade-offs accepted.** Contributors need bucket access to run extraction evals locally.

**Revisit if.** A transcription error is proven, in which case correct it with a commit that
documents the evidence.

---

## D-011 — Boto3 for the S3-compatible storage boundary
- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** GPT-5.6 Sol
- **Status:** accepted

**Context.** The walking skeleton must store immutable attachments in MinIO locally and
remain compatible with managed S3 in production. It also needs server-side encryption and
short-lived signed downloads.

**Options considered.**
1. Direct HTTP calls to MinIO — rejected: this would duplicate signing and retry logic and
   couple the API to MinIO-specific behavior.
2. MinIO's Python client — viable locally, but less direct for an eventual AWS S3 target.
3. Boto3 behind `DocumentStorage` — chosen.

**Decision.** Use Boto3 only inside `core/storage.py`. Application code receives storage
URIs and SHA-256 values, not a provider client.

**Why this approach.** The provider-specific surface remains one small adapter while the
object contract (private bucket, content-addressed key, encryption, five-minute URL) stays
stable.

**Trade-offs accepted.** Boto3 and botocore add dependency weight to the API process.

**Revisit if.** Deployment chooses a non-S3 object store or cold-start cost becomes
material.

---

## D-012 — Separate limited system role for inbound address resolution
- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** GPT-5.6 Sol
- **Status:** accepted

**Context.** An inbound webhook has no authenticated tenant yet. It must resolve a
recipient address before opening an org-scoped transaction, but using the provisioning
credential would violate D-003 and make the public webhook an admin-code path.

**Options considered.**
1. Use `provisioning_session()` — rejected: excessive privilege on an unauthenticated entry
   point.
2. Give the system role direct table reads or `BYPASSRLS` — rejected: broadens the blast
   radius and defeats the database boundary.
3. A no-table-grant system role with two `SECURITY DEFINER` functions — chosen.

**Decision.** `equicontracts_system` may execute only address resolution and quarantine
functions. A matched message then switches to `org_scoped_session(owner_org_id)` for all
tenant writes.

**Why this approach.** The unauthenticated path can perform exactly two pre-tenant actions,
and cannot query arbitrary projects or documents.

**Trade-offs accepted.** Two additional database functions and a third local credential
must be maintained and tested.

**Revisit if.** Inbound processing moves into a separately deployed service with its own
database interface.

---

## D-013 — Next.js App Router for the walking-skeleton web app
- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** GPT-5.6 Sol
- **Status:** accepted

**Context.** Phase 0 needs one deployable web application while preserving a visibly hard
boundary between contractor write screens and client read-only screens.

**Options considered.**
1. A single conditional dashboard — rejected: unverified-data leakage becomes difficult to
   review structurally.
2. Separate frontend deployments — rejected for Phase 0 operational overhead.
3. Next.js App Router with `(contractor)` and `(client)` route groups — chosen.

**Decision.** Use Next.js and React with TypeScript. Keep client-side contractor API calls
in `lib/api.ts`; keep client-organisation credentials and verified-only reads in the
server-only `lib/client-api.ts`. Use the newest TypeScript major supported by the current
Next.js lint toolchain rather than an incompatible prerelease.

**Why this approach.** Route groups provide different layouts and make the client surface
auditable as a directory while retaining one deployment.

**Trade-offs accepted.** The Phase 0 header-auth stub is visible in contractor browser
requests and is strictly local-development scaffolding; signed authentication replaces it
in Phase 1.

**Revisit if.** Client and contractor release cycles or security controls require separate
deployments.

---

## D-014 — YAML definitions parsed with safe loading
- **Date:** 2026-08-12
- **Phase:** 0
- **Decided by:** GPT-5.6 Sol
- **Status:** accepted

**Context.** Deterministic rule definitions are data, not Python branching, and need a
small validated loader. The test stack also needs the transport package required by the
current Starlette TestClient.

**Options considered.**
1. A custom YAML subset parser — rejected as unnecessary parsing and security risk.
2. JSON rule files — viable, but less readable for operational rule review.
3. `yaml.safe_load` with typed `RuleDefinition` construction — chosen.

**Decision.** Declare PyYAML as a direct runtime dependency and use `safe_load` only.
Declare `types-PyYAML` and the current `httpx2` TestClient transport as development-only
dependencies.

**Why this approach.** Rule files remain concise and human-reviewable, while typed
construction rejects missing or unexpected definition structure during tests.

**Trade-offs accepted.** YAML has more syntax surface than JSON and therefore must never be
loaded with object-construction-capable APIs.

**Revisit if.** Rule definitions require schema versioning substantial enough to justify a
formal JSON Schema.

---

## D-015 — Participant-aware document reads via can_read_project()
- **Date:** 2026-08-13
- **Phase:** 0
- **Decided by:** GPT-5.6 Sol
- **Status:** accepted

**Context.** The 2026-08-12 audit found that `document`, `document_classification`, and
`event_log` SELECT policies used `owns_project()` only, while `project` and later
project-child tables already used `can_read_project()`. Client/PMC participants therefore
could not see documents. The client dashboard `LEFT JOIN document` silently counted zero
verified items instead of surfacing an error.

**Options considered.**
1. Change the dashboard query to avoid joining `document` (e.g. count via
   `document_project` SECURITY DEFINER) — rejected: papers over a tenancy hole that any
   future document-aware client query would rediscover.
2. Duplicate owner-OR-participant logic inline in each policy — rejected: diverges from
   the existing `can_read_project()` helper and invites drift.
3. Align document-chain SELECT policies on `can_read_project()`, keep writes owner-only —
   chosen.

**Decision.** Migration `0007_document_participant_read.sql` reaffirms
`can_read_project()` as the single participant-aware read gate, switches
`document` / `document_classification` / `event_log` reads to it, and restates
`extracted_field` read as `can_read_project()` plus the verified-only filter for
non-owners. Write policies remain `owns_project()`.

**Why this approach.** Matches the pattern already proven on `project`, `work_order`, and
`bank_guarantee`. Verified-only exposure of financial field *values* stays on
`extracted_field`; document row visibility is required for joins.

**Trade-offs accepted.** Participants can see document metadata (filename, storage URI,
hash) for all project documents, not only those with verified fields. That is broader
than verified-only field values; acceptable for Phase 0 dashboards, revisit if metadata
itself becomes sensitive.

**Revisit if.** Client surfaces must hide unverified document existence entirely, or
document metadata is treated as confidential relative to participants.

---

## D-016 — Shared inbox with plus-address project routing
- **Date:** 2026-08-13
- **Phase:** 0
- **Decided by:** GPT-5.6 Sol
- **Status:** accepted

**Context.** Phase 0 minted a unique full email per project (`name042@domain`). That forces
provider-side address provisioning and DNS/mailbox sprawl for every new site. Providers
already support plus-addressing on a single catch-all or shared mailbox.

**Options considered.**
1. Keep per-project unique mailboxes — rejected: operational cost scales with project
   count and complicates provider setup.
2. Shared mailbox with opaque tokens in the subject — rejected: subject rewriting and
   forwarding habits are unreliable for contractors.
3. One mailbox (`projects@domain`) with `projects+{alias}@domain` routing — chosen.

**Decision.** Store only `project.inbound_alias` (unique). API display uses
`display_inbound_address(alias)` → `{inbound_mailbox}+{alias}@{inbound_email_domain}`.
Inbound webhook parses the local-part on `+`, looks up the alias via
`resolve_inbound_project`, and quarantines recipients with no `+` (bare mailbox) the same
as an unknown alias.

**Why this approach.** One real inbox to monitor and authenticate; project identity travels
in the standard plus-address suffix without per-project mailbox creation.

**Trade-offs accepted.** Routing depends on the `+alias` surviving delivery. Some mail
clients strip plus-addressing when a user *manually forwards* a message (they rewrite
`To:` / use their own address) rather than the provider delivering the original recipient
envelope to our webhook. Direct provider inbound (Postmark/SendGrid original recipient)
is fine; human forward-from-outlook-style flows are a real misroute risk and must be
called out in onboarding copy, not silently accepted.

**Revisit if.** Provider original-recipient headers prove unreliable, or contractor
forwarding habits force a subject-token / Reply-To fallback.

---

## D-017 — Anthropic/OpenAI primary, Ollama fallback for BG extraction
- **Date:** 2026-09-09
- **Phase:** 1
- **Decided by:** Composer
- **Status:** accepted

**Context.** Phase 1 needs a real model call for bank-guarantee extraction. Cloud keys
are not always present in local/dev; the package must still be runnable for the GECPL
eval gate.

**Options considered.**
1. Anthropic-only — rejected: blocks local eval without `ANTHROPIC_API_KEY`.
2. OpenAI-only — same key problem.
3. `EXTRACTION_PROVIDER` with anthropic → openai → ollama (OpenAI-compatible) — chosen.

**Decision.** `packages/extraction/bg_extractor.py` selects provider via
`EXTRACTION_PROVIDER`, defaulting to anthropic if `ANTHROPIC_API_KEY` is set, else openai
if `OPENAI_API_KEY` is set, else ollama at `OLLAMA_BASE_URL` (default
`http://127.0.0.1:11434/v1`). Model id from `EXTRACTION_MODEL`.

**Why this approach.** One extraction code path; cloud in CI/pilot; local Ollama for
offline comparison against frozen eval expectations.

**Trade-offs accepted.** Local models may miss dual-date accuracy; cloud remains the
quality bar for release.

## D-018 — Organise backend into routers, services, repositories
- **Date:** 2026-10-03
- **Phase:** 1 prep
- **Decided by:** Adya
- **Status:** accepted

**Context.** Some routers contain SQL. Agents will call services through tools, so services must exist.

**Decision.** Routers handle HTTP only; services hold logic; repositories hold all SQL; domain holds pure logic and metric definitions; ports and adapters wrap external systems. Same single repo.

**Why this approach.** One place for each kind of code; agents and the website use the same services.

**Trade-offs accepted.** One refactor now, more files.

**Revisit if.** Never, for this repo.

---

## D-019 — Website first, mobile-friendly; native app later
- **Date:** 2026-10-03
- **Phase:** 1 prep
- **Decided by:** Adya
- **Status:** accepted

**Context.** Designs are phone screens; prototype must be reachable by URL.

**Decision.** Responsive Next.js website that works on phone browsers. No native app yet.

**Trade-offs accepted.** No push notifications or offline mode until the native app.

**Revisit if.** Pilot users need offline site capture or push.

---

## D-020 — Agentic platform with eight agents, built phase by phase
- **Date:** 2026-10-03
- **Phase:** 1 prep
- **Decided by:** Adya
- **Status:** accepted

**Decision.** Intake, Extraction, Linking, Gap Finder, Follow-up, Briefing, Q&A, Resolution. Built in phase order, never all at once.

**Why this approach.** Contractor stops typing and becomes the reviewer; problems arrive with a draft fix.

**Trade-offs accepted.** More moving parts; needs runtime, guardrails, and evals per agent.

**Revisit if.** An agent's approval rate stays low; merge or drop it.

---

## D-021 — LangGraph for agents that pause for a human
- **Date:** 2026-10-03
- **Phase:** 1 prep
- **Decided by:** Adya
- **Status:** accepted

**Decision.** Use LangGraph where an agent must wait for approval mid-run (Extraction, Follow-up, Resolution). Simple single-step agents may run without it.

**Why this approach.** Built-in checkpoints and resume after human input.

**Revisit if.** The runtime needs outgrow it.

---

## D-022 — Reader AI separate from actor AI
- **Date:** 2026-10-03
- **Phase:** 1 prep
- **Decided by:** Adya
- **Status:** accepted

**Context.** Documents come from clients, sometimes the other side in a dispute; they can hide instructions.

**Decision.** The AI that reads raw documents has no write tools. The AI with tools only sees validated, structured fields.

**Why this approach.** Hidden instructions can't reach an AI with power to act.

**Trade-offs accepted.** Two model calls in some flows.

**Revisit if.** Never.

---

## D-023 — New agent actions start at autonomy Level 2
- **Date:** 2026-10-03
- **Phase:** 1 prep
- **Decided by:** Adya
- **Status:** accepted

**Decision.** Levels: 0 watch, 1 suggest, 2 draft (human sends), 3 act with undo, 4 never automatic. New actions start at 2. Promotion to 3 only with review data showing few corrections. Verifying money and accepting risk stay at 4.

**Why this approach.** Trust is earned with data, not assumed.

**Revisit if.** Review data supports promoting a specific action.
