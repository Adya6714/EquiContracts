# EquiContracts: Handoff Summary

Everything a new chat needs. Attach this file plus the docs in section 10.

## Paste this as the first message in a new chat

```
I'm Adya, founding engineer at EquiContracts. This is a continuation.
Read HANDOFF.md fully first, then docs/plans/START_HERE.md.
Other attached docs are reference.

How I want you to work:
- Plain, beginner-friendly language. Bullets over paragraphs. No em dashes.
- Explain every system design decision and why, simply.
- One step at a time. I approve each step before we move on.
- Do not run code in your own sandbox. I run everything in Cursor and Claude Code.
- When I paste output, read the real output carefully. Don't assume tests passed.
- I'm the final decision maker. Recommend clearly, but let me decide.

First: confirm you've understood the product and current state in 10 bullets.
Then: we continue from the current START_HERE step.
```

---

## 1. Who and how

**Adya** is the founding engineer. Owns all technical decisions.
- Co-founder: construction domain expert. Owns rule thresholds, terminology, business decisions.
- Designer: owns the app screens.

**How Adya wants to work**
- Plain, beginner-friendly language. Bullets, not paragraphs. No em dashes.
- Explain every system design decision and why
- One step at a time. Adya approves each step before the next.
- **Claude does not run code in its own sandbox.** Adya runs everything in Cursor / Claude Code.
- Show real output, not summaries

## 2. The product

**Contractor feeds. Client sees. Platform structures, verifies, and surfaces exceptions.**

Four problems it solves:
1. Documents scattered → **Evidence Locker**, one inbox
2. Nobody gets reminded → **rules + agents** watch dates and chase people
3. No view of project health → **health rollup**
4. Different truths → **same verified data** for both sides

Modules: Evidence Locker, BG Verify, Milestone Validator, Command Centre / Health, Payment Mismatch, Resolution + Q&A. Clause Clarify is **out of scope**.

**Agentic platform:** 8 AI agents (Intake, Extraction, Linking, Gap Finder, Follow-up, Briefing, Q&A, Resolution). Contractor approves.

## 3. Stack

- One repo (monorepo)
- Postgres with RLS, FastAPI (Python 3.11 locally / 3.12 in CI), Next.js
- MinIO locally / S3 later
- YAML rules engine, no AI inside it
- Agents: event table + plain-code router + job queue; LangGraph when an agent pauses for a human
- **Website first**. Native mobile app later.
- Inbox: `projects+alias@equicontracts.in`

## 4. Current repo state

**Phase 0 foundation (except real auth):**
- Migrations 0001–0008, RLS proven, walking API + web skeleton
- `make verify` green on last local run (45 pytest after LLM settings)
- Auth is still the `X-Org-Id` header stub — **must** be replaced before anything goes online (START_HERE Step 10)

**Extraction / eval:**
- BG extractor on main with **provider-selectable LLM settings**: `LLM_PROVIDER`, `LLM_MODEL`, one key slot per provider (`GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`; Ollama uses placeholder `ollama`)
- GECPL baseline **4/4** vs `eval/eval_set_v0/expected/gecpl-bg-invocation.json`, `model_version` **gemini-2.5-flash**
- Track A (BG extractor) landed. Tracks B (exceptions + BG rules) and C (real auth) **not built**
- Answer key filename is `gecpl-bg-invocation.json` (not `gecpl.json`)

**Not built yet:** services/repositories split, site/engagement migration, agents, Intake, promotion UI, money-chain tables beyond stubs

## 5. Decisions

Canonical log: `DECISIONS.md` (D-001 onward). Do not invent informal D1/D5 labels.

**Recent accepted (excerpt)**

| Id | Decision |
|---|---|
| D-018 | Routers / services / repositories |
| D-019 | Website first |
| D-020 | Eight agents, phase by phase |
| D-021 | LangGraph for pause-for-human agents |
| D-022 | Reader AI separate from actor AI |
| D-023 | New actions start at autonomy Level 2 |
| D-024 | Provider-selectable LLM settings; one key slot per provider |
| D-025 | Free/local model in dev; record `model_version` |
| D-026 | Site + engagement model |
| D-027 | Event-table handoff; plain-code router |
| D-028 | ADR stubs retired; DECISIONS.md only |
| D-029 | EquiAdvisor Facts + separate Advice mode |
| D-030 | Docs: one index, one decision log, no BOOK |

**Waiting on co-founder:** Q1–Q10 in `docs/plans/MASTER_PLAN_v2.md` (module order, who pays, Idle vs Redundant, Seals, trophy, interest, compliance score, warranty window, reminder ladders, more documents).

**Waiting on designer:** S8 interest 10x wrong; S15 savings vs capacity; claim expiry column; Attention state; Review screen and related missing screens.

## 6. Plan

Phases: 0 Foundation → 1 Capture → 2 Remind → 3 Milestone Validator → 4 Health → 5 Payment mismatch → 6 Resolution/Q&A → 7 Pilot hardening → Pilot.

**START_HERE steps**
1. BG extractor baseline — **done** (GECPL 4/4)
2. Docs cleanup — current
3. Services and repositories
4. Site and engagement + lock `inbound_quarantine`
5. Agent foundation
6. Extraction Agent, then Intake Agent
7. Review screen and promotion
8. Phase 1 gate: GECPL end to end
9. Rules and exceptions, then Linking Agent
10. Real login (parallel any time; required before go-live)

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

- `SET LOCAL x = :param` is a Postgres syntax error. Use `SELECT set_config(...)`.
- `ENABLE` RLS is not enough; use `FORCE`, and run tests as the app role
- Creating an org needs a provisioning connection
- `CREATE OR REPLACE FUNCTION` cannot rename a parameter; drop and recreate
- CI checkout needs `fetch-depth: 0` for eval-immutability
- Docker Desktop must be open before `make up`
- Test fixtures with fixed codes collide; generate unique codes
- Enforce agent rules in CI, not only in AGENTS.md text
- Split read and write RLS policies for participants
- No `.cursorrules` — use AGENTS.md + `.cursor/rules/*.mdc`

## 9. Data

- 11 real documents catalogued in `eval/eval_set_v0/cases.json` (raw files not in git; private bucket / local reference folder)
- Human answer keys today: `gecpl-bg-invocation.json`, `raheja-tax-invoice.json`
- Key findings: BG dual dates 366 days apart (GECPL); GST CGST/SGST with IGST null (Raheja); 13-item checklist (Shantigram); 5-part deductions (Runwal); reminder escalation in subjects; dispute emails without the word "dispute"

## 10. Documents to attach to the new chat

- `HANDOFF.md` (this file)
- `docs/plans/START_HERE.md`
- `docs/plans/MASTER_PLAN_v2.md`
- `docs/architecture/AGENTIC_DESIGN.md`
- `docs/WORKFLOW.md`
- `docs/README.md`
