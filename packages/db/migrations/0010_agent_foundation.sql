-- Agent foundation schema (Step 5 Part A). No packages/agents yet.
-- Split policies only. No FOR ALL. No DROP … CASCADE.

-- ---------------------------------------------------------------------------
-- 0. Worker role (password set by packages/db/init/00-app-role.sh)
-- ---------------------------------------------------------------------------

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'equicontracts_agent') THEN
    CREATE ROLE equicontracts_agent
      LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO equicontracts_agent;

-- ---------------------------------------------------------------------------
-- 1. Tables
-- ---------------------------------------------------------------------------

CREATE TABLE event (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          uuid NOT NULL REFERENCES org(id),
  engagement_id   uuid REFERENCES engagement(id),
  event_type      text NOT NULL,
  payload         jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text NOT NULL,
  status          text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'claimed', 'processed', 'failed')),
  attempts        integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  last_error      text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  claimed_at      timestamptz,
  processed_at    timestamptz,
  UNIQUE (org_id, idempotency_key)
);

CREATE INDEX event_claim_idx
  ON event (status, created_at)
  WHERE status IN ('pending', 'claimed');

CREATE TABLE agent_run (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id        uuid NOT NULL REFERENCES event(id),
  org_id          uuid NOT NULL REFERENCES org(id),
  engagement_id   uuid REFERENCES engagement(id),
  agent_name      text NOT NULL,
  agent_version   text NOT NULL,
  model_version   text,
  attempt         integer NOT NULL DEFAULT 1 CHECK (attempt >= 1),
  status          text NOT NULL DEFAULT 'running'
                  CHECK (status IN (
                    'running', 'succeeded', 'failed', 'needs_human'
                  )),
  steps_used      integer NOT NULL DEFAULT 0 CHECK (steps_used >= 0),
  retries_used    integer NOT NULL DEFAULT 0 CHECK (retries_used >= 0),
  cost            numeric NOT NULL DEFAULT 0 CHECK (cost >= 0),
  started_at      timestamptz NOT NULL DEFAULT now(),
  finished_at     timestamptz,
  UNIQUE (event_id, agent_name, attempt)
);

CREATE TABLE agent_step (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id      uuid NOT NULL REFERENCES agent_run(id),
  org_id      uuid NOT NULL REFERENCES org(id),
  step_no     integer NOT NULL CHECK (step_no >= 1),
  tool_called text,
  input       jsonb NOT NULL DEFAULT '{}'::jsonb,
  output      jsonb NOT NULL DEFAULT '{}'::jsonb,
  outcome     text NOT NULL
              CHECK (outcome IN ('ok', 'blocked', 'error', 'retry')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, step_no)
);

CREATE TABLE agent_proposal (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id          uuid NOT NULL REFERENCES agent_run(id),
  org_id          uuid NOT NULL REFERENCES org(id),
  engagement_id   uuid REFERENCES engagement(id),
  proposal_type   text NOT NULL,
  content         jsonb NOT NULL,
  confidence      numeric(4,3) CHECK (confidence IS NULL OR (
                    confidence >= 0 AND confidence <= 1
                  )),
  autonomy_level  integer NOT NULL CHECK (autonomy_level BETWEEN 0 AND 4),
  state           text NOT NULL DEFAULT 'pending'
                  CHECK (state IN (
                    'pending', 'approved', 'corrected', 'rejected'
                  )),
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE review_decision (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  proposal_id uuid NOT NULL UNIQUE REFERENCES agent_proposal(id),
  org_id      uuid NOT NULL REFERENCES org(id),
  decided_by  uuid NOT NULL REFERENCES app_user(id),
  decision    text NOT NULL CHECK (decision IN (
                'approved', 'corrected', 'rejected'
              )),
  correction  jsonb NOT NULL DEFAULT '{}'::jsonb,
  reason      text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 2. Triggers: proposal state via review_decision; same-org parents; decided_by
-- ---------------------------------------------------------------------------

CREATE FUNCTION enforce_review_decision_parents()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  proposal_org uuid;
  user_org uuid;
BEGIN
  SELECT org_id INTO proposal_org
  FROM agent_proposal
  WHERE id = NEW.proposal_id;

  IF proposal_org IS NULL OR proposal_org IS DISTINCT FROM NEW.org_id THEN
    RAISE EXCEPTION 'review_decision proposal must belong to decision org'
      USING ERRCODE = '23514';
  END IF;

  SELECT org_id INTO user_org FROM app_user WHERE id = NEW.decided_by;
  IF user_org IS NULL OR user_org IS DISTINCT FROM NEW.org_id THEN
    RAISE EXCEPTION 'decided_by user must belong to decision org'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER review_decision_parents
BEFORE INSERT OR UPDATE OF proposal_id, decided_by, org_id ON review_decision
FOR EACH ROW EXECUTE FUNCTION enforce_review_decision_parents();

-- Proposal state changes ONLY through review_decision INSERT (no role UPDATE).
CREATE FUNCTION apply_review_decision_to_proposal()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  new_state text;
BEGIN
  new_state := CASE NEW.decision
    WHEN 'approved' THEN 'approved'
    WHEN 'corrected' THEN 'corrected'
    WHEN 'rejected' THEN 'rejected'
  END;

  UPDATE agent_proposal
  SET state = new_state
  WHERE id = NEW.proposal_id
    AND org_id = NEW.org_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'proposal not found for review_decision'
      USING ERRCODE = '23503';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER review_decision_updates_proposal_state
AFTER INSERT ON review_decision
FOR EACH ROW EXECUTE FUNCTION apply_review_decision_to_proposal();

REVOKE ALL ON FUNCTION enforce_review_decision_parents() FROM PUBLIC;
REVOKE ALL ON FUNCTION apply_review_decision_to_proposal() FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- 3. claim_next_event — cross-org claim for the worker role only
-- ---------------------------------------------------------------------------

CREATE FUNCTION claim_next_event(
  claim_timeout interval DEFAULT interval '10 minutes',
  max_attempts integer DEFAULT 3
)
RETURNS TABLE (
  event_id uuid,
  org_id uuid,
  engagement_id uuid,
  event_type text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF max_attempts < 1 THEN
    RAISE EXCEPTION 'max_attempts must be >= 1'
      USING ERRCODE = '22023';
  END IF;

  -- Exhausted pending or stuck-claimed events fail instead of being claimed.
  UPDATE public.event e
  SET status = 'failed',
      last_error = 'max attempts reached',
      claimed_at = NULL
  WHERE e.attempts >= max_attempts
    AND (
      e.status = 'pending'
      OR (
        e.status = 'claimed'
        AND e.claimed_at IS NOT NULL
        AND e.claimed_at < clock_timestamp() - claim_timeout
      )
    );

  -- Reclaim stuck claimed events that still have attempts remaining.
  UPDATE public.event e
  SET status = 'pending',
      claimed_at = NULL
  WHERE e.status = 'claimed'
    AND e.claimed_at IS NOT NULL
    AND e.claimed_at < clock_timestamp() - claim_timeout
    AND e.attempts < max_attempts;

  RETURN QUERY
  WITH picked AS (
    SELECT e.id
    FROM public.event e
    WHERE e.status = 'pending'
      AND e.attempts < max_attempts
    -- created_at is transaction-stable; ctid preserves insert order ties.
    ORDER BY e.created_at ASC, e.ctid ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
  )
  UPDATE public.event e
  SET status = 'claimed',
      claimed_at = clock_timestamp(),
      attempts = e.attempts + 1
  FROM picked
  WHERE e.id = picked.id
  RETURNING e.id, e.org_id, e.engagement_id, e.event_type;
END
$$;

REVOKE ALL ON FUNCTION claim_next_event(interval, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION claim_next_event(interval, integer)
  TO equicontracts_agent;

-- ---------------------------------------------------------------------------
-- 4. RLS helpers + policies (split; no FOR ALL; same-org parents on INSERT)
-- ---------------------------------------------------------------------------

CREATE FUNCTION owns_agent_org(target_org_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT target_org_id IS NOT NULL
     AND target_org_id = public.current_org_id()
$$;

REVOKE ALL ON FUNCTION owns_agent_org(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION owns_agent_org(uuid) TO equicontracts_app;
GRANT EXECUTE ON FUNCTION owns_agent_org(uuid) TO equicontracts_agent;
GRANT EXECUTE ON FUNCTION current_org_id() TO equicontracts_agent;
GRANT EXECUTE ON FUNCTION can_read_engagement(uuid) TO equicontracts_agent;
GRANT EXECUTE ON FUNCTION owns_engagement(uuid) TO equicontracts_agent;
GRANT EXECUTE ON FUNCTION document_engagement(uuid) TO equicontracts_agent;

ALTER TABLE event ENABLE ROW LEVEL SECURITY;
ALTER TABLE event FORCE ROW LEVEL SECURITY;
CREATE POLICY event_read ON event FOR SELECT
  USING (owns_agent_org(org_id));
CREATE POLICY event_insert ON event FOR INSERT
  WITH CHECK (
    owns_agent_org(org_id)
    AND (engagement_id IS NULL OR owns_engagement(engagement_id))
  );
CREATE POLICY event_update ON event FOR UPDATE
  USING (owns_agent_org(org_id))
  WITH CHECK (
    owns_agent_org(org_id)
    AND (engagement_id IS NULL OR owns_engagement(engagement_id))
  );
-- No DELETE policy for app/agent.

ALTER TABLE agent_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_run FORCE ROW LEVEL SECURITY;
CREATE POLICY agent_run_read ON agent_run FOR SELECT
  USING (owns_agent_org(org_id));
CREATE POLICY agent_run_insert ON agent_run FOR INSERT
  WITH CHECK (
    owns_agent_org(org_id)
    AND EXISTS (
      SELECT 1 FROM event e
      WHERE e.id = event_id AND e.org_id = org_id
    )
    AND (engagement_id IS NULL OR owns_engagement(engagement_id))
  );
CREATE POLICY agent_run_update ON agent_run FOR UPDATE
  USING (owns_agent_org(org_id))
  WITH CHECK (owns_agent_org(org_id));

ALTER TABLE agent_step ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_step FORCE ROW LEVEL SECURITY;
CREATE POLICY agent_step_read ON agent_step FOR SELECT
  USING (owns_agent_org(org_id));
CREATE POLICY agent_step_insert ON agent_step FOR INSERT
  WITH CHECK (
    owns_agent_org(org_id)
    AND EXISTS (
      SELECT 1 FROM agent_run r
      WHERE r.id = run_id AND r.org_id = org_id
    )
  );
-- Append-only: no UPDATE/DELETE policies.

ALTER TABLE agent_proposal ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_proposal FORCE ROW LEVEL SECURITY;
CREATE POLICY agent_proposal_read ON agent_proposal FOR SELECT
  USING (owns_agent_org(org_id));
CREATE POLICY agent_proposal_insert ON agent_proposal FOR INSERT
  WITH CHECK (
    owns_agent_org(org_id)
    AND EXISTS (
      SELECT 1 FROM agent_run r
      WHERE r.id = run_id AND r.org_id = org_id
    )
    AND (engagement_id IS NULL OR owns_engagement(engagement_id))
  );
-- No UPDATE policy: state changes only via review_decision trigger.

ALTER TABLE review_decision ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_decision FORCE ROW LEVEL SECURITY;
CREATE POLICY review_decision_read ON review_decision FOR SELECT
  USING (owns_agent_org(org_id));
CREATE POLICY review_decision_insert ON review_decision FOR INSERT
  WITH CHECK (
    owns_agent_org(org_id)
    AND EXISTS (
      SELECT 1 FROM agent_proposal p
      WHERE p.id = proposal_id AND p.org_id = org_id
    )
  );
-- Append-only. Parent/decided_by also enforced by trigger (sees past RLS).

-- ---------------------------------------------------------------------------
-- 5. Grants
-- ---------------------------------------------------------------------------

-- App (contractor UI / producers / human review): no UPDATE on event.
GRANT SELECT, INSERT ON event TO equicontracts_app;
GRANT SELECT ON agent_run, agent_step, agent_proposal TO equicontracts_app;
GRANT SELECT, INSERT ON review_decision TO equicontracts_app;

-- Agent worker: read what tools need; write run/step/proposal; limited updates.
-- No SELECT on app_user (PII).
GRANT SELECT ON org, engagement, document, site, site_member
  TO equicontracts_agent;
GRANT SELECT ON event, agent_run, agent_step, agent_proposal
  TO equicontracts_agent;
GRANT INSERT ON agent_run, agent_step, agent_proposal TO equicontracts_agent;
GRANT UPDATE (
  status, steps_used, retries_used, cost, finished_at, model_version
) ON agent_run TO equicontracts_agent;
GRANT UPDATE (status, processed_at, last_error, claimed_at, attempts)
  ON event TO equicontracts_agent;

-- Explicit denials / no grants for agent on human-decision and domain writes
REVOKE ALL ON TABLE review_decision FROM equicontracts_agent;
REVOKE UPDATE ON agent_proposal FROM equicontracts_agent;
REVOKE SELECT ON app_user FROM equicontracts_agent;
REVOKE INSERT, UPDATE, DELETE ON extracted_field FROM equicontracts_agent;
REVOKE INSERT, UPDATE, DELETE ON document FROM equicontracts_agent;
REVOKE INSERT, UPDATE, DELETE ON engagement FROM equicontracts_agent;
REVOKE INSERT, UPDATE, DELETE ON work_order FROM equicontracts_agent;
REVOKE INSERT, UPDATE, DELETE ON bank_guarantee FROM equicontracts_agent;

-- Identity columns: no UPDATE grant for any non-superuser role
REVOKE UPDATE (org_id) ON event FROM equicontracts_app, equicontracts_agent;
REVOKE UPDATE (org_id, event_id) ON agent_run
  FROM equicontracts_app, equicontracts_agent;
REVOKE UPDATE (org_id, run_id) ON agent_step
  FROM equicontracts_app, equicontracts_agent;
REVOKE UPDATE (org_id, run_id) ON agent_proposal
  FROM equicontracts_app, equicontracts_agent;
REVOKE UPDATE (org_id, proposal_id) ON review_decision
  FROM equicontracts_app, equicontracts_agent;
