Agent name: Extraction
Job: Read bank-guarantee fields from a classified document and propose them for human review.
Triggered by: document.classified when doc_type is bank_guarantee (or bg_document)
Reads (tools): read_document_pages, read_document_metadata
Writes (tools): none (proposals via runtime.emit_proposal only)
Can do alone: nothing final; never marks fields verified
Must ask a human for: every financial field; every proposal starts pending
Self-checks: claim_expiry >= expiry; real calendar dates; value > 0; bg_number present; source_quote in document text
If it fails: after at most 2 self-check retries, emit extraction.unreadable with reason; run status needs_human (proposals kept)
How we measure it: field accuracy on eval set; financial and non-financial reported separately
Model size: large (accuracy matters most here)
