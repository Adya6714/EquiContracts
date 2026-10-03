# Step 0: Install the kit into the existing repo

Keep the existing repo. Phase 0 is proven there (39/39 tests). Don't start over.

```
Task: install the documentation and rules kit into this repo without losing
anything repo-specific.

I have a folder `equicontracts-kit/` (copied into the repo root temporarily)
containing: AGENTS.md, HANDOFF.md, NEW_CHAT_PROMPT.md, .cursor/rules/*.mdc,
docs/WORKFLOW.md, docs/plans/*, docs/architecture/*, docs/prompts/*,
DECISIONS_ADDITIONS.md.

Do:
1. Compare the kit's AGENTS.md with the repo's current AGENTS.md. Replace it
   with the kit version, but first list anything in the old one that the kit
   version does not cover. Show me that list and wait for my OK before
   dropping anything.
2. Make CLAUDE.md a symlink to AGENTS.md (ln -s AGENTS.md CLAUDE.md). If a
   CLAUDE.md file exists, show me its content first.
3. Compare .cursor/rules/: keep the kit files. For any existing rule file not
   in the kit (e.g. 70-book.mdc), show me its content and ask whether to keep it.
4. Copy docs/WORKFLOW.md, docs/plans/*, docs/architecture/*, docs/prompts/*.
   If a file with the same name exists, show me a diff summary and ask.
5. Append the entries in DECISIONS_ADDITIONS.md to DECISIONS.md, renumbering
   them to continue after the current highest number.
6. Copy HANDOFF.md and NEW_CHAT_PROMPT.md to the repo root.
7. Confirm there is no .cursorrules file. If there is, show me and ask.
8. Delete the temporary equicontracts-kit/ folder.
9. Run make verify and show real output.

Only touch docs, rules, AGENTS.md, CLAUDE.md, DECISIONS.md. No code.
Commit as: "docs: install planning and workflow kit".
```
