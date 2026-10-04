Agent name: Echo
Job: Prove the agent runtime path end to end without an LLM.
Triggered by: test.echo events
Reads (tools): get_engagement_context, read_document_metadata
Writes (tools): none (proposals via runtime.emit_proposal only)
Can do alone: nothing that changes domain data
Must ask a human for: echo.note proposals (autonomy level 2)
Self-checks: engagement_id present on the run context
If it fails: leave the event for claim retry; never mark processed
How we measure it: one pending proposal and processed event on success
Model size: none (deterministic stub)
