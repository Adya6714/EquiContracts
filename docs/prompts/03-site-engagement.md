# Step 3: Site and engagement (only if D5 = yes)

Plain meaning: a **site** is the client's building (Lodha Supremus). An
**engagement** is one contractor's job on that site (Cool Air HVAC on Lodha
Supremus). Today's `project` table becomes `engagement`.

```
Task: introduce site and engagement. One agent only (it runs migrations).

Read first: docs/plans/MASTER_PLAN_v2.md Part 3 and Part 9.1,
packages/db/migrations/0001, 0002, 0007, 0008, and
apps/api/tests/test_access_control.py.

Do (Plan mode first, show me the plan):
1. New migration (next number):
   - site table: id, owner_org_id (client org), name, city, created_at
   - site_member: site_id, org_id, role (client | pmc), data_scope
     ('verified_only')
   - rename project -> engagement, add site_id (nullable)
   - move project_participant rows to site_member where possible; explain
     what happens to existing rows before doing it
   - update RLS: contractor reads own engagements; client/PMC read
     engagements on sites where they are site_member, verified only; writes
     owner only. One shared helper function for "can this org read this
     engagement".
2. Update repositories, services, routers, and the web app to use engagement.
3. New tests (as the app role):
   - two contractors on one site cannot see each other's engagements or documents
   - client sees both engagements on its site, verified data only
   - client cannot write to either
   - engagement without a site still works (contractor-led path)
4. All existing tenancy tests still pass.
5. DECISIONS.md entry and FLOW.md update.

Done when: make reset applies clean, make verify green, new tests pass.
Show me the migration file, the new tests, and real output.
```
