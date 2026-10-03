# Step 4: Agent foundation

```
Task: build the engine all agents run on. No real agents yet.

Read first: docs/architecture/AGENTIC_DESIGN.md Parts 4, 6.3, 7, 8, 9, 10,
and .cursor/rules/45-agents.mdc.

Do (Plan mode first, show me the plan):
1. Migration (next number): event, agent_run, agent_step, agent_proposal,
   review_decision tables, with RLS like other tenant tables.
2. packages/agents/router.py: a plain table mapping event_type -> agent name.
   No AI.
3. packages/agents/runtime.py: runs one agent for one event. Enforces max
   steps (10), max retries (2), cost cap, and logs every step.
4. Job queue: Postgres-backed worker that picks unprocessed events. Must be
   idempotent: processing the same event twice does not create duplicates.
5. packages/agents/guardrails/: allowlist.py (agent -> allowed tools),
   autonomy.py (action -> level 0 to 4, default 2), number_check.py (every
   number in a text appears in a given set of source values), limits.py.
6. packages/agents/tools/: two read-only tools calling services:
   get_engagement_context, read_document_metadata.
7. One fake agent "echo" that receives a test event, calls one tool, and
   creates one agent_proposal. No LLM call (use a stub model adapter).
8. CI rule: no SQL or repository imports inside packages/agents/.
9. Tests:
   - echo agent runs end to end, every step logged
   - agent calling a tool not on its allowlist is blocked
   - level 4 action is never auto-applied
   - number_check rejects a text with a number not in the source
   - same event processed twice gives one run
10. DECISIONS.md (queue choice, LangGraph usage) and FLOW.md.

Done when: make verify green, all tests above pass. Show me real output.
```
