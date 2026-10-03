# Pre-Launch Security Checklist — Mapped to EquiContracts

The 20-item "launch checklist" genre, assessed against what EquiContracts actually builds.
Three items are wrong for this project and one is dangerously misleading — flagged below.

**Caution about the framing.** "In under 25 seconds" is a video hook, not advice. Several of
these are genuinely quick config changes. Others — RLS, input validation, record-level
access — are architectural and take days. Treat this as a checklist to *verify*, not a
script to run.

Related: [project-map.md](../architecture/project-map.md), [runbook.md](../runbook.md),
ADR [0002-postgres-rls](../../specs/adr/0002-postgres-rls.md).

---

## Already done (verify, don't rebuild)

| # | Item | Status |
|---|---|---|
| 4 | Enable row-level security | **Done and forced** on tenant tables. `inbound_quarantine` is deliberately excluded — mail arrives before the tenant is known. Re-verify after migrations. |
| 7 | Lock record access | **Done via RLS**, plus the participant model for client/PMC read access. Same boundary as #4 for this architecture. |
| 13 | Parameterize queries | **Done.** Queries use `:param` binding via SQLAlchemy `text()`. Worth one grep to confirm no f-string SQL crept in. |
| 8 | Block field tampering | **Done, at the DB level.** Financial fields cannot reach `verified` without `verified_by` — stronger than a usual app-layer check. |
| 16 | Restrict file uploads | **Partially done.** Content-addressed storage, private bucket, SSE. Still need: file size cap, MIME allowlist, magic-byte PDF check. |
| 20 | Scan dependencies | **Partial.** gitleaks in CI for secrets. Add `pip-audit` and `npm audit` (below). |

---

## Wrong for this project — do not implement

**#3 "Use public DB key"** — Supabase-specific (`anon` key + RLS). EquiContracts uses plain
Postgres behind a server-side API. **No public database key — ever.** Skip.

**#10 "Hash passwords"** — only if building password auth. Prefer an auth provider (Clerk,
Auth0, WorkOS) or magic links. Rolling password storage for contractors' financial documents
is unnecessary risk. If passwords happen anyway: bcrypt or argon2 — never SHA-256 / MD5.

**#12 "Add bot protection"** — CAPTCHA matters for open consumer signup. Users here are
onboarded contractors. Relevant later for self-serve signup; not now.

---

## Genuinely needed — actual gaps

### Critical, before any real user touches this

**#6 Enforce server-side auth.** `auth.py` is a header stub (`X-Org-Id`, `X-User-Id`) marked
`TODO(phase-1)`. **Anyone can set those headers and become any org.** Fine for local
development; catastrophic on a public URL. Nothing public until this is real session auth.

**#1 Hide API keys / #2 Purge git secrets.** `.env` is gitignored and gitleaks runs in CI.
Also run `gitleaks detect --log-opts="--all"` across full history. A key committed then
removed is still compromised — rotate it.

**#19 Force HTTPS.** Handled by the host (Vercel/Railway) automatically. Add HSTS (see #18).

### Important, before the pilot

**#14 Validate all input.** Pydantic gives types, not semantics: positive contract values,
sane dates, length-capped `wo_number`. Audit every request model.

**#18 Add security headers.** One middleware:

```
Strict-Transport-Security, X-Content-Type-Options: nosniff,
X-Frame-Options: DENY, Content-Security-Policy, Referrer-Policy
```

**#11 Rate limit login** — and more importantly **rate limit `/inbound/email`**. Publicly
reachable. HMAC protects authenticity, not volume.

**#17 Trim API responses.** Especially client routes: no internal notes, raw confidence
scores, or unnecessary `verified_by` identifiers.

**#16 (completing) File upload restrictions.** Cap size. Allowlist MIME. Validate `%PDF`
magic bytes — never trust extension or declared content-type alone.

**#20 (completing) Dependency scanning.** Add to CI:

```yaml
- run: pip install pip-audit && pip-audit -r apps/api/requirements.txt
- run: cd apps/web && npm audit --audit-level=high
```

### Lower priority for this architecture

**#5 Encrypt sensitive data.** S3 SSE already. Managed DB encryption at rest + TLS in
transit is a reasonable stop for now. Column encryption complicates queries — revisit for
enterprise asks.

**#9 Secure session cookies** — when #6 is done: `HttpOnly`, `Secure`, `SameSite=Lax`.

**#15 Escape user content.** React escapes by default. Grep for `dangerouslySetInnerHTML`.
Resolution Statement HTML rendering of extracted text is the sensitive case.

---

## Three things this list misses that matter more here

**Prompt injection through ingested documents.** Documents often come from the adversarial
side of a dispute. Content must be extracted as data, never obeyed. Wrap document text in
explicit delimiters in prompts; add a test case.

**DPDP Act compliance.** Real names, emails, signatures. Needs retention policy, deletion
path, and data residency in an Indian region — a legal conversation, not a checkbox.

**Tested backups.** An untested backup is not a backup. Restore once before the pilot
([runbook.md](../runbook.md)).

---

## Ordered action list

**Before deployment anywhere public:**

1. Replace the auth stub with real session auth (#6)
2. Full-history secret scan and rotate anything found (#2)
3. Rate limit `/inbound/email` (#11)
4. Security headers middleware (#18)

**Before the pilot:**

5. Input validation audit across all request models (#14)
6. Response trimming audit, especially client-facing routes (#17)
7. File upload caps and magic-byte validation (#16)
8. `pip-audit` + `npm audit` in CI (#20)
9. Prompt injection test case
10. Backup restore drill

**Deliberately skipped:** #3, #10 (use a provider), #12.
