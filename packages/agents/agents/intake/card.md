Agent name: Intake
Job: Sort each new document (type + evidence weight + dispute signals); handoff to Extraction is plain-code follow-up, not this agent.
Triggered by: document.received
Reads (tools): read_document_pages, read_document_metadata
Writes (tools): none (proposals via runtime.emit_proposal only)
Can do alone: nothing final — classification stays Level 2
Must ask a human for: low-confidence or unknown (other) types; confirmation of type/weight (Step 7 writes document columns)
Self-checks: doc_type must be a known document_type code else other; evidence_weight judged from content (dispute_score >= 0.40 forces potential_dispute)
If it fails: emit propose_classification then finish_needs_human when low confidence or other; no follow-up handoff
How we measure it: type accuracy on eval_set_v0; weight accuracy on labelled cases; dispute recall
Model size: small and fast (LLM_MODEL_INTAKE, else LLM_MODEL)
