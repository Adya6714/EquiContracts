# EquiContracts: Handoff Summary

Everything a new chat needs to continue without losing context. Paste NEW_CHAT_PROMPT.md as the first message and attach this file plus the docs listed in section 10.

---

## 1. Who and how

**Adya** is the founding engineer. Owns all technical decisions.
- Co-founder: construction domain expert. Owns rule thresholds, terminology, business decisions.
- Designer: owns the app screens.

**How Adya wants to work**
- Plain, beginner-friendly language. Bullets, not paragraphs. No em dashes.
- Explain every system design decision and why
- One step at a time. Adya approves each step before the next.
- **Claude does not run code in its own sandbox.** Adya runs everything in Cursor / Claude Code. Claude gives plans, prompts, and explanations.
- Show real output, not summaries

## 2. The product

**Contractor feeds. Client sees. Platform structures, verifies, and surfaces exceptions.**

Four problems it solves:
1. Documents scattered (email, WhatsApp, laptops) → **Evidence Locker**, one inbox
2. Nobody gets reminded → **rules + agents** watch every date and chase people
3. No view of project health → **health rollup** item to portfolio
4. Contractor and client see different truths → **same verified data** for both, every number linked to its source

Modules: Evidence Locker, BG Verify, Milestone Validator, Command Centre / Health, Payment Mismatch, Resolution + Q&A. Clause Clarify is **out of scope**.

It is an **agentic platform**: 8 AI agents (Intake, Extraction, Linking, Gap Finder, Follow-up, Briefing, Q&A, Resolution) do the work, the contractor approves.

## 3. Stack

- One repo (monorepo)
- Postgres with row-level security (RLS), FastAPI (Python 3.11 locally), Next.js
- MinIO locally / S3 later for documents
- YAML rules engine, no AI inside it
- Agents: event table + plain-code router + job queue, LangGraph for agents that pause for a human, Claude via an adapter
- Tools: Cursor and Claude Code, Docker Desktop
- **Website first** (responsive, works on phone browsers). Native mobile app later.
- Inbox: one shared mailbox with plus-addressing, `projects+alias@equicontracts.in`

## 4. Current repo state

**Phase 0 is done (except real auth):**
- Migrations 0001 to 0008 apply clean (`make reset`)
- `make verify` green, 39/39 tests
- RLS proven live: contractor isolation, client read-only, verified-only, unset org returns zero rows
- DB constraints proven: financial field needs a human to verify; BG claim expiry must be on/after expiry
- Endpoints: health, projects, inbound email (HMAC, plus-alias, quarantine), review queue, client dashboard
- Docs: AGENTS.md, DECISIONS.md (D-001 to D-016), FLOW.md, BOOK.md, .cursor/rules

**Three parallel tracks were queued. Results not yet reviewed:**
- Track A: BG extractor + eval comparison on GECPL
- Track B: exceptions table + `evaluate()` + 5 BG rules
- Track C: real auth replacing the `X-Org-Id` header stub

**Not built yet:** agents, extraction pipeline beyond Track A, money chain tables (0006 is a stub), most screens, site/engagement model.

## 5. Decisions

**Made**
| # | Decision |
|---|---|
| D1 | Organise code into routers, services, repositories (folders inside the one repo) |
| D8 | Website first, mobile-friendly. Native app later. |
| D15 | Adopt the 8-agent design, built phase by phase |
| D17 | LangGraph for agents that need to pause for a human |
| D18 | Reader AI (sees documents, no tools) separate from actor AI (has tools, never sees raw documents) |
| D19 | New agent actions start at autonomy Level 2 (draft, human sends) |
| Earlier | One repo. Plus-addressed single inbox. Three-state verification. Two BG dates. Rules have no AI. Eval set frozen. |

**Waiting on Adya (explained in plain words, recommendation yes)**
| # | Question |
|---|---|
| D5 | Site + engagement model. Site = the building (client's). Engagement = one contractor's job on it. Needed for the client view. |
| D9 | EquiAdvisor gives facts from data + drafted letters only, no advice, for now |
| D16 | Agents hand off work through a shared event board, not by calling each other |

**Waiting on co-founder**
- BG Verify or Milestone Validator first
- Who pays: contractor, client, or both
- Idle vs Redundant BG; what "Seals" BG type means; what the trophy icon means
- Interest rate default (screens use 12%); compliance score definition
- Warranty alert window (60 days or 6 months)
- Real thresholds for every rule (all current numbers are guesses)
- 20 to 30 more varied documents, plus a terminology map

**Waiting on designer**
- S8 interest exposure is 10x wrong: shows ₹14.5L, formula gives ₹1.45L, correct per-bill ₹1.17L
- S15 savings mixes money saved with bid capacity (₹3.98 Cr of ₹4.78 Cr is capacity)
- BG dashboard needs claim expiry column; totals must follow filters
- Command Centre needs Attention and Needs Verification states
- Missing screens: Review/confirm, BG detail, Notifications, Exceptions, Drafts inbox, Agent activity, client site view, payment import, settings

## 6. Plan

Phases: 0 Foundation (done) → 1 Capture → 2 Remind → 3 Milestone Validator → 4 Health and transparency → 5 Payment mismatch → 6 Resolution and Q&A → 7 Pilot hardening → Pilot.

Each phase ends with a **real-document gate** (real document through the live system).

**Next steps (from START_HERE.md)**
- Step 0: Install this kit into the repo (prompt `docs/prompts/00-install-kit.md`), confirm D5, D9, D16
- Step 1: Review Tracks A, B, C, merge one at a time
- Step 2: Service and repository layers
- Step 3: Site and engagement (if D5 yes)
- Step 4: Agent foundation
- Step 5: Extraction Agent on BGs
- Step 6: Intake Agent
- Step 7: Review screen and promotion
- Step 8: Phase 1 gate on GECPL
- Step 9: Linking Agent, then Phase 2

## 7. Safety rules that never change

1. Agents propose, humans approve money and anything sent to the client
2. Agents act only through tools, never the database directly
3. Code does the maths, AI does the words; every number in AI text is checked
4. AI reading client documents has no tools; AI with tools never sees raw documents
5. Rules have no AI
6. Database refuses to verify a money field without a named human
7. Unverified data never reaches a dashboard
8. Eval set `eval/eval_set_v0/` is never edited

## 8. Gotchas already learned (don't repeat)

- `SET LOCAL x = :param` is a Postgres syntax error. Use `SELECT set_config('app.current_org_id', :org, true)`.
- `ENABLE` RLS is not enough; use `FORCE`, and run tests as the app role, not postgres
- Creating an org needs a separate provisioning connection (RLS blocks the app role, correctly)
- `CREATE OR REPLACE FUNCTION` cannot rename a parameter; drop and recreate
- CI checkout needs `fetch-depth: 0` for the eval-immutability check
- Docker Desktop must be open (daemon running) before `make up`
- Test fixtures with fixed codes collide across runs; generate unique codes
- Agents read AGENTS.md and still drift; enforce rules in CI, not just in text
- A single read+write RLS policy lets participants write; split read and write policies
- `.cursorrules` is ignored by Cursor Agent mode; use AGENTS.md + `.cursor/rules/*.mdc`

## 9. Data

- 11 real documents from Nina Percept in `eval/eval_set_v0/` (raw files in a private bucket, not git)
- Only 2 of 11 expected outputs transcribed
- Key real-data findings: BG expiry and claim expiry ~1 year apart (GECPL: 366 days); GST split CGST/SGST/IGST with IGST null not zero (Raheja); 13-item submission checklist (Shantigram); 5-part deductions (Runwal); "Reminder - 02" escalation in subjects; dispute emails that never say "dispute" (Jai Vijay)

## 10. Documents to attach to the new chat

- `HANDOFF.md` (this file)
- `docs/plans/START_HERE.md`
- `docs/plans/MASTER_PLAN_v2.md`
- `docs/architecture/AGENTIC_DESIGN.md`
- `docs/WORKFLOW.md`
- Optional: latest Cursor repo audit output
