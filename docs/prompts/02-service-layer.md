# Step 2: Routers, services, repositories

```
Task: reorganise apps/api/app into routers, services, repositories, domain,
ports, adapters. No behaviour change.

Read first: AGENTS.md "Code layout", .cursor/rules/20-api.mdc, and every file
in apps/api/app/routers/.

Do (Plan mode first, show me the plan):
1. Create apps/api/app/{services,repositories,domain,ports,adapters}/
2. Move every SQL statement out of routers into repositories/, one file per
   area (projects, documents, review, inbound).
3. Move business logic into services/. Routers become: read request, check
   role, call one service, return.
4. Move pure logic (verification state machine, financial field registry,
   project code helpers) into domain/.
5. Define ports for storage, mail provider, LLM, clock. Existing S3 and email
   code becomes adapters.
6. Add a check to scripts/check_agent_rules.py: no SQL text() or session
   execute calls inside apps/api/app/routers/.
7. Update FLOW.md entry points and call paths. Add a DECISIONS.md entry.

Only touch: apps/api/app/, scripts/check_agent_rules.py, FLOW.md, DECISIONS.md
Do not change: migrations, tests' assertions, extraction, web

Done when: make verify passes with the same tests, and no router contains SQL.
Show me real output and the new folder tree.
```
