# ADR 0005 — Three-state verification

- **Status:** Accepted
- **Decision:** D-005

Extracted fields move through `ai_extracted`, `needs_review` and `verified`. Financial
fields cannot be verified without a human identity, and later contradictions return a
verified field to review rather than overwriting history.
