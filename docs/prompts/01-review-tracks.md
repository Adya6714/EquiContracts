# Step 1: Review Tracks A, B, C

Run once per track. Merge one at a time.

```
Task: report the state of Track <A / B / C> so I can decide whether to merge.
No code changes in this session.

Track A = BG extractor (packages/extraction/)
Track B = exceptions table + evaluate() + 5 BG rules (migration + apps/api/app/rules/)
Track C = real auth replacing the X-Org-Id header stub (apps/api/app/core/auth.py)

Do:
1. Find the branch or worktree for this track. Show git log for it and
   git diff --stat against main.
2. List every file changed. Flag anything outside the track's allowed folders.
3. Check: any test skipped, xfailed, deleted, or weakened? Anything under
   eval/eval_set_v0/ changed? Any applied migration edited?
4. Run make verify on that branch. Show the real pass/fail count and every
   failure by name.
5. Track-specific:
   - A: show the field-by-field comparison vs
     eval/eval_set_v0/expected/ for the GECPL case. Are expiry and
     claim_expiry both correct and 366 days apart? Are missing fields reported
     as unresolved rather than guessed?
   - B: what signal did bg_idle use, since milestone tables don't exist yet?
     Show the boundary tests (30 days fires, 31 doesn't).
   - C: prove the X-Org-Id header has zero effect when ENVIRONMENT is not
     test/development. Do all previous tests still pass?

Stop and show me everything. Do not merge.
```
