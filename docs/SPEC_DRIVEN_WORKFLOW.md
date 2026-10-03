# Spec-Driven Workflow (Kiro-style, for Claude Code / Cursor / manual use)

A phase-gated workflow for turning a feature request into code. Modeled on
Kiro's spec mode: requirements → design → tasks → one-task-at-a-time
execution, with an explicit human approval gate between every phase. The
value isn't the artifacts — it's refusing to let the agent skip ahead.

## Phase 0 — Steering (one-time, per project)

Keep a `CLAUDE.md` (or `.cursor/rules`) current with:

- What the product/service is, who it's for
- Stack, conventions, constraints
- Repo layout, naming patterns

This gets pulled into every prompt automatically so the agent doesn't
re-derive context each time.

## Phase 1 — Requirements

Create `docs/specs/<feature-name>/requirements.md`.

Prompt:

> Write requirements.md for [feature]. Use user stories (As a/I want/so
> that) and EARS-format acceptance criteria (WHEN/IF ... THE SYSTEM
> SHALL ...). Do not write any code. Stop after this file and wait for my
> approval.

**Gate:** review, edit, or reject. Do not proceed until approved.

## Phase 2 — Design

Only after requirements are approved, create `design.md` in the same
folder.

Prompt:

> Based on the approved requirements.md, research the existing codebase
> and write design.md — architecture, interfaces/data models, error
> handling, testing strategy. Reference which requirement each decision
> satisfies. No code yet. Stop for approval.

Use Plan Mode (`EnterPlanMode`) here if available — it forces read-only
research and a reviewable plan before any file is touched.

**Gate:** review, edit, or reject. Do not proceed until approved.

## Phase 3 — Tasks

Only after design is approved, create `tasks.md`.

Prompt:

> Based on the approved design.md, write tasks.md as a numbered
> checklist. Each task should be small, independently completable,
> buildable on prior tasks, and reference the requirement(s) it
> satisfies. No implementation yet.

**Gate:** review, edit, or reject. Do not proceed until approved.

## Phase 4 — Execution

Prompt:

> Implement tasks.md one task at a time. After each task, stop, show me
> the diff, and wait before starting the next.

Track progress as a visible todo list (e.g. Claude Code's `TodoWrite`)
rather than trusting one large uninterrupted response. This bounds the
blast radius of any single turn.

## Optional — Hooks

Event-driven automation outside the main conversation, e.g.: "on file
save in `src/api/`, regenerate the corresponding test stub" or "on
commit, scan for secrets." In Claude Code these map to hooks configured
in `settings.json`.

## Cursor notes

Same three files (`requirements.md`, `design.md`, `tasks.md`). Use
`.cursor/rules` for steering and a pinned context (e.g. a Notepad) to
keep the spec in scope across the session. Cursor has no native
EARS/spec mode — the phase discipline is entirely on the prompts above.

## The rule that matters most

Never ask for the whole feature in one shot. Always say "stop after
requirements/design/tasks, wait for approval." Skipping a gate collapses
this back into a single-prompt build with none of the benefit.
