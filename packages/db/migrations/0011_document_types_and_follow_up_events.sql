-- Step 6b Part 1: document type reference, classification columns (human-only
-- later), event chain fields, and locked-down follow-up event creation.
-- Split policies only. No FOR ALL. No DROP … CASCADE.

-- ---------------------------------------------------------------------------
-- 1. document_type reference (seeded; SELECT-only for app + agent)
-- ---------------------------------------------------------------------------

CREATE TABLE document_type (
  code  text PRIMARY KEY,
  label text NOT NULL
);

INSERT INTO document_type (code, label) VALUES
  ('bank_guarantee', 'Bank guarantee'),
  ('work_order', 'Work order'),
  ('proforma_invoice', 'Proforma invoice'),
  ('certified_ra_bill', 'Certified RA bill'),
  ('measurement_sheet_annexure', 'Measurement sheet / annexure'),
  ('work_completion_certificate', 'Work completion certificate'),
  ('warranty_document', 'Warranty document'),
  ('payment_reconciliation', 'Payment reconciliation'),
  ('delay_site_instruction_mom', 'Delay / site instruction / MOM'),
  ('email', 'Email'),
  ('resolution_statement', 'Resolution statement'),
  ('other', 'Other');

ALTER TABLE document_type ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_type FORCE ROW LEVEL SECURITY;
CREATE POLICY document_type_read ON document_type FOR SELECT
  USING (true);
-- No INSERT / UPDATE / DELETE policies.

GRANT SELECT ON document_type TO equicontracts_app;
GRANT SELECT ON document_type TO equicontracts_agent;
REVOKE INSERT, UPDATE, DELETE ON document_type
  FROM equicontracts_app, equicontracts_agent;

-- ---------------------------------------------------------------------------
-- 2. document.doc_type + document.evidence_weight (nullable; no UPDATE yet)
-- ---------------------------------------------------------------------------

ALTER TABLE document
  ADD COLUMN doc_type text REFERENCES document_type(code),
  ADD COLUMN evidence_weight text
    CHECK (
      evidence_weight IS NULL
      OR evidence_weight IN (
        'routine', 'core_evidence', 'potential_dispute'
      )
    );

-- App code only UPDATEs received_at (inbound re-accept upsert). Grant that
-- column alone; never identity, storage, or human-only classification fields.
REVOKE UPDATE ON document FROM equicontracts_app;
GRANT UPDATE (received_at) ON document TO equicontracts_app;
-- Agent already has no UPDATE on document (0010); keep it that way.
REVOKE UPDATE ON document FROM equicontracts_agent;

-- ---------------------------------------------------------------------------
-- 3. event chain: caused_by_event_id + chain_depth
-- ---------------------------------------------------------------------------

ALTER TABLE event
  ADD COLUMN caused_by_event_id uuid REFERENCES event(id),
  ADD COLUMN chain_depth integer NOT NULL DEFAULT 0
    CHECK (chain_depth >= 0);

CREATE INDEX event_caused_by_idx ON event (caused_by_event_id)
  WHERE caused_by_event_id IS NOT NULL;

-- App may only insert root producer events. Follow-up / classified children
-- go through create_follow_up_event (DEFINER). Keep same-org checks.
DROP POLICY event_insert ON event;
CREATE POLICY event_insert ON event FOR INSERT
  WITH CHECK (
    owns_agent_org(org_id)
    AND (engagement_id IS NULL OR owns_engagement(engagement_id))
    AND caused_by_event_id IS NULL
    AND chain_depth = 0
    AND event_type IN ('document.received', 'test.echo')
  );

-- ---------------------------------------------------------------------------
-- 4. create_follow_up_event — agent-only DEFINER; proves Intake proposal
-- ---------------------------------------------------------------------------

CREATE FUNCTION create_follow_up_event(
  parent_event_id uuid,
  proposal_id uuid
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  parent_row record;
  proposal_row record;
  run_row record;
  doc_type text;
  document_id uuid;
  parent_document_id uuid;
  child_depth integer;
  child_id uuid;
  idem_key text;
  payload jsonb;
BEGIN
  IF parent_event_id IS NULL OR proposal_id IS NULL THEN
    RAISE EXCEPTION 'follow_up_missing_args' USING ERRCODE = '22023';
  END IF;

  SELECT e.id, e.org_id, e.engagement_id, e.event_type, e.chain_depth, e.payload
  INTO parent_row
  FROM public.event e
  WHERE e.id = parent_event_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'follow_up_parent_missing' USING ERRCODE = 'P0002';
  END IF;

  IF parent_row.org_id IS DISTINCT FROM public.current_org_id() THEN
    RAISE EXCEPTION 'follow_up_org_mismatch' USING ERRCODE = '42501';
  END IF;

  IF parent_row.event_type IS DISTINCT FROM 'document.received' THEN
    RAISE EXCEPTION 'follow_up_transition_denied' USING ERRCODE = '42501';
  END IF;

  child_depth := parent_row.chain_depth + 1;
  IF child_depth > 3 THEN
    RAISE EXCEPTION 'follow_up_depth_exceeded' USING ERRCODE = '42501';
  END IF;

  SELECT p.id, p.org_id, p.run_id, p.proposal_type, p.content
  INTO proposal_row
  FROM public.agent_proposal p
  WHERE p.id = proposal_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'follow_up_proposal_missing' USING ERRCODE = 'P0002';
  END IF;

  IF proposal_row.org_id IS DISTINCT FROM parent_row.org_id THEN
    RAISE EXCEPTION 'follow_up_org_mismatch' USING ERRCODE = '42501';
  END IF;

  IF proposal_row.proposal_type IS DISTINCT FROM 'propose_classification' THEN
    RAISE EXCEPTION 'follow_up_bad_proposal_type' USING ERRCODE = '42501';
  END IF;

  SELECT r.id, r.event_id, r.org_id, r.agent_name
  INTO run_row
  FROM public.agent_run r
  WHERE r.id = proposal_row.run_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'follow_up_run_missing' USING ERRCODE = 'P0002';
  END IF;

  IF run_row.event_id IS DISTINCT FROM parent_event_id THEN
    RAISE EXCEPTION 'follow_up_proposal_wrong_run' USING ERRCODE = '42501';
  END IF;

  IF run_row.org_id IS DISTINCT FROM parent_row.org_id THEN
    RAISE EXCEPTION 'follow_up_org_mismatch' USING ERRCODE = '42501';
  END IF;

  IF run_row.agent_name IS DISTINCT FROM 'intake' THEN
    RAISE EXCEPTION 'follow_up_wrong_agent' USING ERRCODE = '42501';
  END IF;

  doc_type := proposal_row.content ->> 'doc_type';
  IF doc_type IS DISTINCT FROM 'bank_guarantee' THEN
    RAISE EXCEPTION 'follow_up_doc_type_denied' USING ERRCODE = '42501';
  END IF;

  BEGIN
    document_id := (proposal_row.content ->> 'document_id')::uuid;
  EXCEPTION
    WHEN invalid_text_representation THEN
      RAISE EXCEPTION 'follow_up_bad_document_id' USING ERRCODE = '22P02';
  END;

  IF document_id IS NULL THEN
    RAISE EXCEPTION 'follow_up_bad_document_id' USING ERRCODE = '22023';
  END IF;

  BEGIN
    parent_document_id := (parent_row.payload ->> 'document_id')::uuid;
  EXCEPTION
    WHEN invalid_text_representation THEN
      RAISE EXCEPTION 'follow_up_document_mismatch' USING ERRCODE = '42501';
  END;

  IF parent_document_id IS NULL
     OR document_id IS DISTINCT FROM parent_document_id THEN
    RAISE EXCEPTION 'follow_up_document_mismatch' USING ERRCODE = '42501';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.document d
    WHERE d.id = document_id
      AND d.engagement_id IS NOT DISTINCT FROM parent_row.engagement_id
  ) THEN
    RAISE EXCEPTION 'follow_up_document_mismatch' USING ERRCODE = '42501';
  END IF;

  -- Payload is built only from the proposal — never from caller input.
  payload := jsonb_build_object(
    'document_id', document_id::text,
    'doc_type', doc_type
  );
  idem_key := 'document.classified:' || document_id::text || ':' || doc_type;

  INSERT INTO public.event (
    org_id,
    engagement_id,
    event_type,
    payload,
    idempotency_key,
    caused_by_event_id,
    chain_depth
  ) VALUES (
    parent_row.org_id,
    parent_row.engagement_id,
    'document.classified',
    payload,
    idem_key,
    parent_event_id,
    child_depth
  )
  ON CONFLICT (org_id, idempotency_key) DO NOTHING
  RETURNING id INTO child_id;

  IF child_id IS NOT NULL THEN
    RETURN child_id;
  END IF;

  SELECT e.id INTO child_id
  FROM public.event e
  WHERE e.org_id = parent_row.org_id
    AND e.idempotency_key = idem_key;

  IF child_id IS NULL THEN
    RAISE EXCEPTION 'follow_up_insert_failed' USING ERRCODE = 'P0001';
  END IF;

  RETURN child_id;
END
$$;

REVOKE ALL ON FUNCTION create_follow_up_event(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION create_follow_up_event(uuid, uuid)
  TO equicontracts_agent;
-- equicontracts_app must not execute this function.
