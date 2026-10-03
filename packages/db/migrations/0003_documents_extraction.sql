-- Phase 0 Step 0.8: documents, extraction, review and audit.

CREATE TABLE document (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id               uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  filename                 text NOT NULL,
  storage_uri              text NOT NULL,
  sha256                   text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  source                   text NOT NULL
                           CHECK (source IN ('email_forward', 'manual_upload')),
  sender_email             text,
  reminder_sequence_number integer,
  received_at              timestamptz NOT NULL DEFAULT now(),
  created_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, sha256)
);

CREATE TABLE document_classification (
  document_id   uuid PRIMARY KEY REFERENCES document(id) ON DELETE CASCADE,
  category      text NOT NULL CHECK (category IN (
                  'routine', 'core_evidence', 'potential_dispute', 'bg_document',
                  'proforma_invoice', 'certified_invoice', 'wcc_handover',
                  'warranty_document', 'payment_advice',
                  'delay_site_instruction_mom'
                )),
  confidence    numeric(4,3) CHECK (confidence BETWEEN 0 AND 1),
  model_version text,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE extracted_field (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id   uuid NOT NULL REFERENCES document(id) ON DELETE CASCADE,
  field_name    text NOT NULL,
  field_value   text,
  state         text NOT NULL DEFAULT 'ai_extracted'
                CHECK (state IN ('ai_extracted', 'needs_review', 'verified')),
  is_financial  boolean NOT NULL DEFAULT false,
  confidence    numeric(4,3) CHECK (confidence BETWEEN 0 AND 1),
  model_version text,
  verified_by   uuid REFERENCES app_user(id),
  verified_at   timestamptz,
  superseded_by uuid REFERENCES extracted_field(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT financial_needs_human CHECK (
    NOT (is_financial AND state = 'verified' AND verified_by IS NULL)
  ),
  CONSTRAINT verification_metadata_consistent CHECK (
    (state = 'verified' AND verified_at IS NOT NULL)
    OR (state <> 'verified')
  ),
  CONSTRAINT no_self_supersession CHECK (superseded_by IS DISTINCT FROM id)
);

CREATE INDEX extracted_field_review_idx
  ON extracted_field (created_at, is_financial)
  WHERE state = 'needs_review';

CREATE TABLE inbound_quarantine (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  recipient    text NOT NULL,
  payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
  reason       text NOT NULL,
  received_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE event_log (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  event_type    text NOT NULL,
  actor_user_id uuid REFERENCES app_user(id),
  entity_type   text NOT NULL,
  entity_id     uuid NOT NULL,
  metadata      jsonb NOT NULL DEFAULT '{}'::jsonb,
  previous_hash text,
  event_hash    text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION resolve_inbound_project(target_recipient text)
RETURNS TABLE (id uuid, owner_org_id uuid)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT project.id, project.owner_org_id
  FROM public.project
  WHERE lower(project.inbound_email) = lower(target_recipient)
$$;

CREATE FUNCTION quarantine_inbound(
  target_recipient text,
  target_payload_hash text,
  target_reason text
)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  INSERT INTO public.inbound_quarantine (recipient, payload_hash, reason)
  VALUES (target_recipient, target_payload_hash, target_reason)
$$;

CREATE FUNCTION document_project(target_document_id uuid)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT project_id FROM public.document WHERE id = target_document_id
$$;

REVOKE ALL ON FUNCTION document_project(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION resolve_inbound_project(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION quarantine_inbound(text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION document_project(uuid) TO equicontracts_app;
GRANT EXECUTE ON FUNCTION resolve_inbound_project(text) TO equicontracts_system;
GRANT EXECUTE ON FUNCTION quarantine_inbound(text, text, text)
  TO equicontracts_system;

ALTER TABLE document ENABLE ROW LEVEL SECURITY;
ALTER TABLE document FORCE ROW LEVEL SECURITY;
CREATE POLICY document_read ON document FOR SELECT
  USING (owns_project(project_id));
CREATE POLICY document_write ON document FOR ALL
  USING (owns_project(project_id))
  WITH CHECK (owns_project(project_id));

ALTER TABLE document_classification ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_classification FORCE ROW LEVEL SECURITY;
CREATE POLICY classification_read ON document_classification FOR SELECT
  USING (owns_project(document_project(document_id)));
CREATE POLICY classification_write ON document_classification FOR ALL
  USING (owns_project(document_project(document_id)))
  WITH CHECK (owns_project(document_project(document_id)));

ALTER TABLE extracted_field ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_field FORCE ROW LEVEL SECURITY;
CREATE POLICY extracted_field_contractor_read ON extracted_field FOR SELECT
  USING (
    owns_project(document_project(document_id))
    OR (
      state = 'verified'
      AND can_read_project(document_project(document_id))
    )
  );
CREATE POLICY extracted_field_write ON extracted_field FOR ALL
  USING (owns_project(document_project(document_id)))
  WITH CHECK (owns_project(document_project(document_id)));

ALTER TABLE event_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_log FORCE ROW LEVEL SECURITY;
CREATE POLICY event_log_read ON event_log FOR SELECT
  USING (owns_project(project_id));
CREATE POLICY event_log_write ON event_log FOR INSERT
  WITH CHECK (owns_project(project_id));

GRANT SELECT, INSERT, UPDATE, DELETE
  ON document, document_classification, extracted_field TO equicontracts_app;
GRANT SELECT, INSERT ON event_log TO equicontracts_app;
