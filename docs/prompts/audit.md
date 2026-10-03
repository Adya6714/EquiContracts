# Full repo audit (when lost)

Paste into Cursor Ask mode.

```
Act as an auditor. Read the actual files, not the plans. No code changes.

1. Tree of the repo (skip node_modules, .git, __pycache__, .next, .venv).
2. Which step of docs/plans/START_HERE.md are we on, based on real code?
3. For each folder in AGENTS.md "Code layout": exists / stub / missing,
   and one line on what it actually does.
4. Migrations in order, one line each. Tables with RLS enabled and forced.
5. Tests: list by file. Do tenancy tests run as the app role?
6. Run make verify. Real pass/fail count, every failure by name.
7. Agents: which exist, which tools each can call, which autonomy levels.
8. Anything that contradicts AGENTS.md or FLOW.md.
9. Uncommitted or unmerged work.
10. The single next task, which files it touches, and why.

Be blunt about gaps.
```
