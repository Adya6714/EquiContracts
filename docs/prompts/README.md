# Prompt Library

One prompt per step in docs/plans/START_HERE.md. Paste into Cursor (Plan mode first, then Agent) or Claude Code.

| File | Step | Tool |
|---|---|---|
| 00-install-kit.md | Install this kit into the repo | Claude Code |
| 01-review-tracks.md | Review Tracks A, B, C | Claude Code |
| 02-service-layer.md | Routers, services, repositories | Claude Code |
| 03-site-engagement.md | Site + engagement model | Claude Code (schema only, one agent) |
| 04-agent-foundation.md | Router, runtime, guardrails, fake agent | Claude Code |
| 05-extraction-agent.md | Extraction Agent on BGs | Claude Code |
| 06-intake-agent.md | Intake Agent | Claude Code |
| 07-review-screen.md | Review screen + promotion | Cursor (web) + Claude Code (API) |
| 08-phase1-gate.md | GECPL end-to-end gate | You, by hand, with Claude Code |
| audit.md | Full repo audit when lost | Cursor Ask mode |

Rules for every prompt:
- Plan mode first for anything over one file
- Stop and show real output before merging
- Bring results to the Claude chat before the next step
