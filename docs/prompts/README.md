# Prompt Library

One prompt per START_HERE step when it exists. Paste into Cursor (Plan mode first)
or Claude Code. Steps without a prompt are marked below.

| START_HERE step | Prompt file | Notes |
|---|---|---|
| 1 BG extractor baseline | *(none — done)* | GECPL 4/4 already on main |
| 2 Docs cleanup | *(none — this session)* | |
| 3 Services and repositories | [02-service-layer.md](02-service-layer.md) | |
| 4 Site and engagement + quarantine | [03-site-engagement.md](03-site-engagement.md) | Same migration batch |
| 5 Agent foundation | [04-agent-foundation.md](04-agent-foundation.md) | |
| 6 Extraction, then Intake | [05-extraction-agent.md](05-extraction-agent.md), [06-intake-agent.md](06-intake-agent.md) | Run Extraction first |
| 7 Review screen and promotion | [07-review-screen.md](07-review-screen.md) | |
| 8 Phase 1 gate GECPL | [08-phase1-gate.md](08-phase1-gate.md) | Often run by hand |
| 9 Rules + exceptions, then Linking | *(none yet)* | |
| 10 Real login | *(none yet)* | Parallel; before go-live |
| Utility | [audit.md](audit.md) | Full repo audit when lost |

Rules for every prompt:
- Plan mode first for anything over one file
- Stop and show real output before merging
- Bring results to the planning chat before the next step
