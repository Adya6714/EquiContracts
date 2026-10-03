# Foundation Requirements (EARS notation)

Phase 0 requirements. Format: `R-F{N}` = Foundation requirement number N.

---

## Access control

**R-F1** WHEN a contractor user authenticates, the system SHALL scope all queries to
their org via RLS session variable.

**R-F2** WHEN a client or PMC user authenticates, the system SHALL scope queries to
projects where their org is a participant.

**R-F3** IF a request references a project the principal's org neither owns nor
participates in, THEN the system SHALL respond identically to a non-existent project.

**R-F4** A contractor org SHALL NOT be able to read any record belonging to another
contractor org, including on a shared project.

**R-F5** WHEN a client or PMC user reads any project data, the system SHALL return
only records in state 'verified'.

---

## Project onboarding

**R-F6** WHEN a contractor admin creates a project, the system SHALL generate a unique
project code and dedicate an inbound email address.

**R-F7** WHEN a project is created, the system SHALL allow adding client and PMC
organisations as participants with `data_scope = 'verified_only'`.

**R-F8** The project owner org MUST be of type 'contractor'. The system SHALL reject
project creation by any other org type.

---

## Ingestion

**R-F9** WHEN the inbound email webhook receives a message, the system SHALL verify
the provider HMAC signature before any processing.

**R-F10** IF the recipient address does not match any project's inbound email, THEN
the system SHALL quarantine the message without creating a document record.

**R-F11** WHEN a valid email is received, the system SHALL store attachments immutably
in object storage with a locally-computed SHA-256 hash.

**R-F12** WHEN an extracted field is financial, the system SHALL set state
'needs_review' regardless of confidence score.

---

## Verification

**R-F13** The system SHALL support three verification states: `ai_extracted`,
`needs_review`, `verified`.

**R-F14** A financial field SHALL NOT transition to `verified` without a non-null
`verified_by` referencing a human user. The database SHALL enforce this constraint.

**R-F15** WHEN a contractor corrects a field value during review, the system SHALL
create a new extracted_field row and link the old row via `superseded_by`.

**R-F16** WHEN a verified field is contradicted by a later document, the system SHALL
return it to 'needs_review' rather than overwriting the verified value.

---

## Audit

**R-F17** The system SHALL maintain an append-only event log for all verification
state transitions, linked by hash chain.

**R-F18** The system SHALL NOT log document contents, field values, personal names,
or email addresses in application logs.
