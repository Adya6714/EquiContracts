-- Site + engagement model (D-026) and lock inbound_quarantine.
-- Never edit 0001–0008. No DROP … CASCADE. No FOR ALL policies after this file.
--
-- Backfill rule: one site per distinct client org that appears as role='client'
-- in project_participant; attach every engagement that had that client; copy
-- client/pmc participant rows onto that site as site_member; then drop
-- project_participant.

-- ---------------------------------------------------------------------------
-- 1. site + site_member (provisioning writes; app SELECT only)
-- ---------------------------------------------------------------------------

CREATE TABLE site (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_org_id uuid NOT NULL REFERENCES org(id),
  name         text NOT NULL,
  city         text,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE site_member (
  site_id    uuid NOT NULL REFERENCES site(id) ON DELETE CASCADE,
  org_id     uuid NOT NULL REFERENCES org(id),
  role       text NOT NULL CHECK (role IN ('client', 'pmc')),
  data_scope text NOT NULL DEFAULT 'verified_only'
             CHECK (data_scope = 'verified_only'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (site_id, org_id)
);

-- Refuse a site whose owner is not a client org (trigger; org_type is also
-- immutable after insert — see enforce_org_type_immutable below).
CREATE FUNCTION enforce_site_owner_is_client()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM org
    WHERE id = NEW.owner_org_id AND org_type = 'client'
  ) THEN
    RAISE EXCEPTION 'site owner must be a client organisation'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER site_owner_is_client
BEFORE INSERT OR UPDATE OF owner_org_id ON site
FOR EACH ROW EXECUTE FUNCTION enforce_site_owner_is_client();

-- Refuse site_member whose org is not client/pmc, and keep role = org_type.
CREATE FUNCTION enforce_site_member_org_type()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  member_type text;
BEGIN
  SELECT org_type INTO member_type FROM org WHERE id = NEW.org_id;
  IF member_type IS NULL OR member_type NOT IN ('client', 'pmc') THEN
    RAISE EXCEPTION 'site_member org must be client or pmc'
      USING ERRCODE = '23514';
  END IF;
  IF member_type IS DISTINCT FROM NEW.role THEN
    RAISE EXCEPTION 'site_member role must match organisation type'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER site_member_org_type_matches
BEFORE INSERT OR UPDATE OF org_id, role ON site_member
FOR EACH ROW EXECUTE FUNCTION enforce_site_member_org_type();

REVOKE ALL ON FUNCTION enforce_site_owner_is_client() FROM PUBLIC;
REVOKE ALL ON FUNCTION enforce_site_member_org_type() FROM PUBLIC;

-- org_type is fixed at insert; changing it would invalidate site/member rules.
CREATE FUNCTION enforce_org_type_immutable()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  RAISE EXCEPTION 'org_type cannot change after insert'
    USING ERRCODE = '23514';
END
$$;

CREATE TRIGGER org_type_immutable
BEFORE UPDATE OF org_type ON org
FOR EACH ROW EXECUTE FUNCTION enforce_org_type_immutable();

REVOKE ALL ON FUNCTION enforce_org_type_immutable() FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- 2. Drop every policy that depends on can_read_project / owns_project
--    (by name; no CASCADE), then drop those helpers.
-- ---------------------------------------------------------------------------

DROP POLICY project_read ON project;
DROP POLICY project_insert ON project;
DROP POLICY project_update ON project;
DROP POLICY project_delete ON project;

DROP POLICY project_participant_read ON project_participant;
DROP POLICY project_participant_insert ON project_participant;
DROP POLICY project_participant_update ON project_participant;
DROP POLICY project_participant_delete ON project_participant;

DROP POLICY project_module_read ON project_module;
DROP POLICY project_module_write ON project_module;

DROP POLICY document_read ON document;
DROP POLICY document_write ON document;

DROP POLICY classification_read ON document_classification;
DROP POLICY classification_write ON document_classification;

DROP POLICY extracted_field_contractor_read ON extracted_field;
DROP POLICY extracted_field_write ON extracted_field;

DROP POLICY event_log_read ON event_log;
DROP POLICY event_log_write ON event_log;

DROP POLICY work_order_read ON work_order;
DROP POLICY work_order_write ON work_order;

DROP POLICY annexure_requirement_read ON annexure_requirement;
DROP POLICY annexure_requirement_write ON annexure_requirement;

DROP POLICY proforma_read ON proforma_invoice;
DROP POLICY proforma_write ON proforma_invoice;

DROP POLICY annexure_submission_read ON annexure_submission;
DROP POLICY annexure_submission_write ON annexure_submission;

DROP POLICY bank_guarantee_read ON bank_guarantee;
DROP POLICY bank_guarantee_write ON bank_guarantee;

DROP POLICY bg_event_read ON bg_event;
DROP POLICY bg_event_write ON bg_event;

DROP FUNCTION can_read_project(uuid);
DROP FUNCTION owns_project(uuid);
DROP FUNCTION document_project(uuid);
DROP FUNCTION work_order_project(uuid);
DROP FUNCTION proforma_project(uuid);
DROP FUNCTION bank_guarantee_project(uuid);
DROP FUNCTION resolve_inbound_project(text);

-- ---------------------------------------------------------------------------
-- 3. Rename project → engagement; children project_id → engagement_id
-- ---------------------------------------------------------------------------

ALTER TABLE project RENAME TO engagement;
ALTER TABLE engagement ADD COLUMN site_id uuid REFERENCES site(id);

ALTER TABLE project_module RENAME TO engagement_module;
ALTER TABLE engagement_module RENAME COLUMN project_id TO engagement_id;

ALTER TABLE document RENAME COLUMN project_id TO engagement_id;
ALTER TABLE event_log RENAME COLUMN project_id TO engagement_id;
ALTER TABLE work_order RENAME COLUMN project_id TO engagement_id;

ALTER TABLE project_participant RENAME COLUMN project_id TO engagement_id;

-- Rename owner trigger/function (drop by name; no CASCADE).
DROP TRIGGER project_owner_is_contractor ON engagement;
DROP FUNCTION enforce_project_owner_is_contractor();

CREATE FUNCTION enforce_engagement_owner_is_contractor()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM org
    WHERE id = NEW.owner_org_id AND org_type = 'contractor'
  ) THEN
    RAISE EXCEPTION 'engagement owner must be a contractor organisation'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER engagement_owner_is_contractor
BEFORE INSERT OR UPDATE OF owner_org_id ON engagement
FOR EACH ROW EXECUTE FUNCTION enforce_engagement_owner_is_contractor();

REVOKE ALL ON FUNCTION enforce_engagement_owner_is_contractor() FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- 4. Backfill site / site_member from project_participant, then drop it
-- ---------------------------------------------------------------------------

CREATE TEMP TABLE _client_site AS
SELECT gen_random_uuid() AS site_id, org_id AS owner_org_id
FROM (
  SELECT DISTINCT org_id
  FROM project_participant
  WHERE role = 'client'
) clients;

INSERT INTO site (id, owner_org_id, name)
SELECT site_id, owner_org_id, 'Migrated site'
FROM _client_site;

UPDATE engagement e
SET site_id = cs.site_id
FROM project_participant pp
JOIN _client_site cs ON cs.owner_org_id = pp.org_id
WHERE pp.engagement_id = e.id
  AND pp.role = 'client';

INSERT INTO site_member (site_id, org_id, role, data_scope)
SELECT DISTINCT e.site_id, pp.org_id, pp.role, pp.data_scope
FROM project_participant pp
JOIN engagement e ON e.id = pp.engagement_id
WHERE e.site_id IS NOT NULL;

DROP TABLE project_participant;
DROP FUNCTION enforce_participant_org_type();

DROP TABLE _client_site;

-- ---------------------------------------------------------------------------
-- 5. Helpers: owns_engagement / can_read_engagement (no old-name wrappers)
-- ---------------------------------------------------------------------------

CREATE FUNCTION owns_engagement(target_engagement_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.engagement
    WHERE id = target_engagement_id
      AND owner_org_id = public.current_org_id()
  )
$$;

-- Owner OR site owner OR site_member. Contractors cannot be site_members
-- (enforce_site_member_org_type), so membership never exposes peer contractors.
CREATE FUNCTION can_read_engagement(target_engagement_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.engagement e
    WHERE e.id = target_engagement_id
      AND (
        e.owner_org_id = public.current_org_id()
        OR (
          e.site_id IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM public.site s
            WHERE s.id = e.site_id
              AND s.owner_org_id = public.current_org_id()
          )
        )
        OR (
          e.site_id IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM public.site_member sm
            WHERE sm.site_id = e.site_id
              AND sm.org_id = public.current_org_id()
          )
        )
      )
  )
$$;

CREATE FUNCTION can_read_site(target_site_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.site s
    WHERE s.id = target_site_id
      AND (
        s.owner_org_id = public.current_org_id()
        OR EXISTS (
          SELECT 1 FROM public.site_member sm
          WHERE sm.site_id = s.id
            AND sm.org_id = public.current_org_id()
        )
      )
  )
$$;

CREATE FUNCTION document_engagement(target_document_id uuid)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT engagement_id FROM public.document WHERE id = target_document_id
$$;

CREATE FUNCTION work_order_engagement(target_work_order_id uuid)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT engagement_id FROM public.work_order WHERE id = target_work_order_id
$$;

CREATE FUNCTION proforma_engagement(target_proforma_id uuid)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT public.work_order_engagement(work_order_id)
  FROM public.proforma_invoice
  WHERE id = target_proforma_id
$$;

CREATE FUNCTION bank_guarantee_engagement(target_bg_id uuid)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT public.work_order_engagement(work_order_id)
  FROM public.bank_guarantee
  WHERE id = target_bg_id
$$;

CREATE FUNCTION resolve_inbound_engagement(target_recipient text)
RETURNS TABLE (id uuid, owner_org_id uuid)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT engagement.id, engagement.owner_org_id
  FROM public.engagement
  WHERE lower(engagement.inbound_alias) = lower(target_recipient)
$$;

-- Link only when engagement.site_id is null. System/provisioning only.
CREATE FUNCTION link_engagement_to_site(
  target_engagement_id uuid,
  target_site_id uuid
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  updated integer;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.site WHERE id = target_site_id) THEN
    RAISE EXCEPTION 'site not found' USING ERRCODE = '23503';
  END IF;

  UPDATE public.engagement
  SET site_id = target_site_id
  WHERE id = target_engagement_id
    AND site_id IS NULL;

  GET DIAGNOSTICS updated = ROW_COUNT;
  IF updated = 1 THEN
    RETURN;
  END IF;

  IF EXISTS (
    SELECT 1 FROM public.engagement
    WHERE id = target_engagement_id AND site_id IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'engagement already linked to a site'
      USING ERRCODE = '23514';
  END IF;

  RAISE EXCEPTION 'engagement not found' USING ERRCODE = '23503';
END
$$;

REVOKE ALL ON FUNCTION owns_engagement(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION can_read_engagement(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION can_read_site(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION document_engagement(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION work_order_engagement(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION proforma_engagement(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION bank_guarantee_engagement(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION resolve_inbound_engagement(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION link_engagement_to_site(uuid, uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION owns_engagement(uuid) TO equicontracts_app;
GRANT EXECUTE ON FUNCTION can_read_engagement(uuid) TO equicontracts_app;
GRANT EXECUTE ON FUNCTION can_read_site(uuid) TO equicontracts_app;
GRANT EXECUTE ON FUNCTION document_engagement(uuid) TO equicontracts_app;
GRANT EXECUTE ON FUNCTION work_order_engagement(uuid) TO equicontracts_app;
GRANT EXECUTE ON FUNCTION proforma_engagement(uuid) TO equicontracts_app;
GRANT EXECUTE ON FUNCTION bank_guarantee_engagement(uuid) TO equicontracts_app;
GRANT EXECUTE ON FUNCTION resolve_inbound_engagement(text)
  TO equicontracts_system;
GRANT EXECUTE ON FUNCTION link_engagement_to_site(uuid, uuid)
  TO equicontracts_system;

-- ---------------------------------------------------------------------------
-- 6. RLS: site / site_member / engagement / engagement_module + children
--    Every recreated write path is INSERT / UPDATE / DELETE (never FOR ALL).
-- ---------------------------------------------------------------------------

ALTER TABLE site ENABLE ROW LEVEL SECURITY;
ALTER TABLE site FORCE ROW LEVEL SECURITY;
CREATE POLICY site_read ON site FOR SELECT
  USING (can_read_site(id));
-- No INSERT/UPDATE/DELETE policies for app: provisioning/admin only.

ALTER TABLE site_member ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_member FORCE ROW LEVEL SECURITY;
CREATE POLICY site_member_read ON site_member FOR SELECT
  USING (can_read_site(site_id));
-- No write policies for app.

ALTER TABLE engagement FORCE ROW LEVEL SECURITY;
CREATE POLICY engagement_read ON engagement FOR SELECT
  USING (can_read_engagement(id));
CREATE POLICY engagement_insert ON engagement FOR INSERT
  WITH CHECK (owner_org_id = current_org_id());
CREATE POLICY engagement_update ON engagement FOR UPDATE
  USING (owns_engagement(id))
  WITH CHECK (owner_org_id = current_org_id() AND owns_engagement(id));
CREATE POLICY engagement_delete ON engagement FOR DELETE
  USING (owns_engagement(id));

ALTER TABLE engagement_module FORCE ROW LEVEL SECURITY;
CREATE POLICY engagement_module_read ON engagement_module FOR SELECT
  USING (can_read_engagement(engagement_id));
CREATE POLICY engagement_module_insert ON engagement_module FOR INSERT
  WITH CHECK (owns_engagement(engagement_id));
CREATE POLICY engagement_module_update ON engagement_module FOR UPDATE
  USING (owns_engagement(engagement_id))
  WITH CHECK (owns_engagement(engagement_id));
CREATE POLICY engagement_module_delete ON engagement_module FOR DELETE
  USING (owns_engagement(engagement_id));

CREATE POLICY document_read ON document FOR SELECT
  USING (can_read_engagement(engagement_id));
CREATE POLICY document_insert ON document FOR INSERT
  WITH CHECK (owns_engagement(engagement_id));
CREATE POLICY document_update ON document FOR UPDATE
  USING (owns_engagement(engagement_id))
  WITH CHECK (owns_engagement(engagement_id));
CREATE POLICY document_delete ON document FOR DELETE
  USING (owns_engagement(engagement_id));

CREATE POLICY classification_read ON document_classification FOR SELECT
  USING (can_read_engagement(document_engagement(document_id)));
CREATE POLICY classification_insert ON document_classification FOR INSERT
  WITH CHECK (owns_engagement(document_engagement(document_id)));
CREATE POLICY classification_update ON document_classification FOR UPDATE
  USING (owns_engagement(document_engagement(document_id)))
  WITH CHECK (owns_engagement(document_engagement(document_id)));
CREATE POLICY classification_delete ON document_classification FOR DELETE
  USING (owns_engagement(document_engagement(document_id)));

CREATE POLICY extracted_field_contractor_read ON extracted_field FOR SELECT
  USING (
    can_read_engagement(document_engagement(document_id))
    AND (
      owns_engagement(document_engagement(document_id))
      OR state = 'verified'
    )
  );
CREATE POLICY extracted_field_insert ON extracted_field FOR INSERT
  WITH CHECK (owns_engagement(document_engagement(document_id)));
CREATE POLICY extracted_field_update ON extracted_field FOR UPDATE
  USING (owns_engagement(document_engagement(document_id)))
  WITH CHECK (owns_engagement(document_engagement(document_id)));
CREATE POLICY extracted_field_delete ON extracted_field FOR DELETE
  USING (owns_engagement(document_engagement(document_id)));

CREATE POLICY event_log_read ON event_log FOR SELECT
  USING (can_read_engagement(engagement_id));
CREATE POLICY event_log_insert ON event_log FOR INSERT
  WITH CHECK (owns_engagement(engagement_id));

CREATE POLICY work_order_read ON work_order FOR SELECT
  USING (can_read_engagement(engagement_id));
CREATE POLICY work_order_insert ON work_order FOR INSERT
  WITH CHECK (owns_engagement(engagement_id));
CREATE POLICY work_order_update ON work_order FOR UPDATE
  USING (owns_engagement(engagement_id))
  WITH CHECK (owns_engagement(engagement_id));
CREATE POLICY work_order_delete ON work_order FOR DELETE
  USING (owns_engagement(engagement_id));

CREATE POLICY annexure_requirement_read ON annexure_requirement FOR SELECT
  USING (can_read_engagement(work_order_engagement(work_order_id)));
CREATE POLICY annexure_requirement_insert ON annexure_requirement FOR INSERT
  WITH CHECK (owns_engagement(work_order_engagement(work_order_id)));
CREATE POLICY annexure_requirement_update ON annexure_requirement FOR UPDATE
  USING (owns_engagement(work_order_engagement(work_order_id)))
  WITH CHECK (owns_engagement(work_order_engagement(work_order_id)));
CREATE POLICY annexure_requirement_delete ON annexure_requirement FOR DELETE
  USING (owns_engagement(work_order_engagement(work_order_id)));

CREATE POLICY proforma_read ON proforma_invoice FOR SELECT
  USING (can_read_engagement(work_order_engagement(work_order_id)));
CREATE POLICY proforma_insert ON proforma_invoice FOR INSERT
  WITH CHECK (owns_engagement(work_order_engagement(work_order_id)));
CREATE POLICY proforma_update ON proforma_invoice FOR UPDATE
  USING (owns_engagement(work_order_engagement(work_order_id)))
  WITH CHECK (owns_engagement(work_order_engagement(work_order_id)));
CREATE POLICY proforma_delete ON proforma_invoice FOR DELETE
  USING (owns_engagement(work_order_engagement(work_order_id)));

CREATE POLICY annexure_submission_read ON annexure_submission FOR SELECT
  USING (can_read_engagement(proforma_engagement(proforma_invoice_id)));
CREATE POLICY annexure_submission_insert ON annexure_submission FOR INSERT
  WITH CHECK (owns_engagement(proforma_engagement(proforma_invoice_id)));
CREATE POLICY annexure_submission_update ON annexure_submission FOR UPDATE
  USING (owns_engagement(proforma_engagement(proforma_invoice_id)))
  WITH CHECK (owns_engagement(proforma_engagement(proforma_invoice_id)));
CREATE POLICY annexure_submission_delete ON annexure_submission FOR DELETE
  USING (owns_engagement(proforma_engagement(proforma_invoice_id)));

CREATE POLICY bank_guarantee_read ON bank_guarantee FOR SELECT
  USING (can_read_engagement(work_order_engagement(work_order_id)));
CREATE POLICY bank_guarantee_insert ON bank_guarantee FOR INSERT
  WITH CHECK (owns_engagement(work_order_engagement(work_order_id)));
CREATE POLICY bank_guarantee_update ON bank_guarantee FOR UPDATE
  USING (owns_engagement(work_order_engagement(work_order_id)))
  WITH CHECK (owns_engagement(work_order_engagement(work_order_id)));
CREATE POLICY bank_guarantee_delete ON bank_guarantee FOR DELETE
  USING (owns_engagement(work_order_engagement(work_order_id)));

CREATE POLICY bg_event_read ON bg_event FOR SELECT
  USING (can_read_engagement(bank_guarantee_engagement(bank_guarantee_id)));
CREATE POLICY bg_event_insert ON bg_event FOR INSERT
  WITH CHECK (owns_engagement(bank_guarantee_engagement(bank_guarantee_id)));
CREATE POLICY bg_event_update ON bg_event FOR UPDATE
  USING (owns_engagement(bank_guarantee_engagement(bank_guarantee_id)))
  WITH CHECK (owns_engagement(bank_guarantee_engagement(bank_guarantee_id)));
CREATE POLICY bg_event_delete ON bg_event FOR DELETE
  USING (owns_engagement(bank_guarantee_engagement(bank_guarantee_id)));

-- ---------------------------------------------------------------------------
-- 7. Lock inbound_quarantine: ENABLE + FORCE RLS, no app policies, no grants
-- ---------------------------------------------------------------------------

ALTER TABLE inbound_quarantine ENABLE ROW LEVEL SECURITY;
ALTER TABLE inbound_quarantine FORCE ROW LEVEL SECURITY;
-- quarantine_inbound (SECURITY DEFINER, system EXECUTE) remains the only insert path.

-- ---------------------------------------------------------------------------
-- 8. Grants: site/site_member SELECT; engagement writes exclude site_id;
--    inbound_quarantine: no app grants at all
-- ---------------------------------------------------------------------------

GRANT SELECT ON site, site_member TO equicontracts_app;
REVOKE INSERT, UPDATE, DELETE ON site, site_member FROM equicontracts_app;

-- App must never write engagement.site_id. Column grants (not a trigger):
-- contractor INSERT omits site_id (defaults NULL) and still works.
-- UPDATE: apps/api never UPDATEs engagement today, so no UPDATE column grants
-- (never id, owner_org_id, created_at, site_id, project_code, inbound_alias).
-- link_engagement_to_site is SECURITY DEFINER and still sets site_id.
REVOKE INSERT, UPDATE ON engagement FROM equicontracts_app;
GRANT INSERT (
  id, owner_org_id, name, project_code, inbound_alias, created_at
) ON engagement TO equicontracts_app;
-- No GRANT UPDATE (…) — add a column here only when app code starts updating it.

-- No grants whatsoever for the app role on quarantine.
REVOKE ALL ON TABLE inbound_quarantine FROM equicontracts_app;
