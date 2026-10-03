# Step 8: Phase 1 gate (GECPL end to end)

Do this yourself, watching each stage. Use Claude Code only to inspect.

1. `make up`, `make reset`, `make verify` (green)
2. Start the API and the worker
3. Create an engagement through the website setup screen
4. Send the real GECPL email to its `projects+alias@` address (or post it to
   /inbound/email with a valid signature)
5. Watch, and note each:
   - [ ] document row created, file in MinIO
   - [ ] Intake: type = bank_guarantee
   - [ ] Extraction: fields proposed, self-checks passed
   - [ ] Review screen shows the fields with page and raw text
   - [ ] You confirm them
   - [ ] bank_guarantee record created
   - [ ] expiry 2023-04-23 and claim expiry 2024-04-23, 366 days apart
   - [ ] every step visible in agent_run / agent_step
6. Paste the results into the Claude chat

Inspection prompt for Claude Code:
```
No code changes. Show me, for the most recent document: its row, the
agent_run and agent_step rows for Intake and Extraction, the agent_proposal
rows, the review_decision rows, and the resulting bank_guarantee row.
```
