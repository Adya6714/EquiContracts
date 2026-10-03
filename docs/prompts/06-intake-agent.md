# Step 6: Intake Agent

```
Task: build the Intake Agent.

Read first: AGENTIC_DESIGN.md Part 5.1, MASTER_PLAN_v2.md Part 4.3 (two
fields: document type and evidence weight).

Do (Plan mode first):
1. If not already present, migration adding document.doc_type (10 values)
   and document.evidence_weight (routine | core_evidence | potential_dispute).
2. packages/agents/agents/intake/: card, prompt, code. Small, fast model.
3. Triggered by document.received. Reads subject, sender, attachment names,
   first page. Proposes doc_type, evidence_weight, and work order link.
4. Autonomy: setting type and weight is Level 3 (applied, with undo).
   Work order link with low confidence is Level 1 (suggest).
5. Emits document.classified when done.
6. Eval: on eval_set_v0, the GECPL BG must be bank_guarantee; DMRC and Jai
   Vijay must be potential_dispute (note: Jai Vijay never uses the word
   "dispute").

Done when: make verify green, eval results shown per case. Show real output.
```
