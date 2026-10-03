# Step 7: Review screen and promotion

Two parts. Run API first (Claude Code), then web (Cursor).

```
PART A (API). Task: review endpoints and BG promotion.

1. GET /review/proposals: agent proposals for this org, financial first.
   Each item: field name, proposed value, raw_text, page, confidence,
   document id, signed URL to the page.
2. POST /review/proposals/{id}: approve | correct (with new value) | reject
   (with reason). Saves review_decision. Corrections create a new row and
   supersede the old one.
3. Promotion service: when all required BG fields for a document are
   verified, create or update the bank_guarantee record. Idempotent.
4. Emits fields.verified and record.updated events.
5. Tests: unverified BG never appears in any BG list; promotion runs once
   even if triggered twice; client can't call review endpoints.
```

```
PART B (web). Task: Review screen in apps/web/app/(contractor)/review/.

1. List of documents with pending proposals.
2. For one document: document page on one side, proposed fields on the
   other. Each field shows value, the exact text read, confidence.
3. Approve, Correct (inline edit), Reject (reason required).
4. "Approve all" for one document only if every field has confidence above
   the threshold, and still records each field's decision individually.
5. Mobile-friendly: on phone, fields stack under the page preview.
Goal: a contractor confirms 8 BG fields in under a minute.
```
