Agent name: Intake
Job: Sort each new document (type + evidence weight); handoff to Extraction is code, not this agent.
Triggered by: document.received
Reads (tools): none yet (stub in 6b.1; read_document_pages / read_document_metadata in 6b.2)
Writes (tools): none (proposals via runtime.emit_proposal only, in 6b.2)
Can do alone: nothing final in 6b.1
Must ask a human for: classification confirmation (Level 2); type/weight not written to document until Step 7
Self-checks: none yet
If it fails: document stays unsorted (6b.2)
How we measure it: type accuracy on eval_set_v0; dispute recall high
Model size: small and fast
