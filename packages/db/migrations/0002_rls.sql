-- Phase 0 Step 0.7: forced, fail-closed, participant-aware RLS.

CREATE FUNCTION current_org_id()
RETURNS uuid
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
  SELECT NULLIF(current_setting('app.current_org_id', true), '')::uuid
$$;

CREATE FUNCTION can_read_project(target_project_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.project p
    WHERE p.id = target_project_id
      AND (
        p.owner_org_id = public.current_org_id()
        OR EXISTS (
          SELECT 1
          FROM public.project_participant pp
          WHERE pp.project_id = p.id
            AND pp.org_id = public.current_org_id()
        )
      )
  )
$$;

CREATE FUNCTION owns_project(target_project_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.project
    WHERE id = target_project_id
      AND owner_org_id = public.current_org_id()
  )
$$;

REVOKE ALL ON FUNCTION can_read_project(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION owns_project(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION current_org_id() TO equicontracts_app;
GRANT EXECUTE ON FUNCTION can_read_project(uuid) TO equicontracts_app;
GRANT EXECUTE ON FUNCTION owns_project(uuid) TO equicontracts_app;

ALTER TABLE org ENABLE ROW LEVEL SECURITY;
ALTER TABLE org FORCE ROW LEVEL SECURITY;
CREATE POLICY org_read_own ON org FOR SELECT
  USING (id = current_org_id());

ALTER TABLE app_user ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_user FORCE ROW LEVEL SECURITY;
CREATE POLICY app_user_read_own_org ON app_user FOR SELECT
  USING (org_id = current_org_id());

ALTER TABLE project ENABLE ROW LEVEL SECURITY;
ALTER TABLE project FORCE ROW LEVEL SECURITY;
CREATE POLICY project_read ON project FOR SELECT
  USING (can_read_project(id));
CREATE POLICY project_insert ON project FOR INSERT
  WITH CHECK (owner_org_id = current_org_id());
CREATE POLICY project_update ON project FOR UPDATE
  USING (owner_org_id = current_org_id())
  WITH CHECK (owner_org_id = current_org_id());
CREATE POLICY project_delete ON project FOR DELETE
  USING (owner_org_id = current_org_id());

ALTER TABLE project_participant ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_participant FORCE ROW LEVEL SECURITY;
CREATE POLICY project_participant_read ON project_participant FOR SELECT
  USING (can_read_project(project_id));
CREATE POLICY project_participant_insert ON project_participant FOR INSERT
  WITH CHECK (owns_project(project_id));
CREATE POLICY project_participant_update ON project_participant FOR UPDATE
  USING (owns_project(project_id))
  WITH CHECK (owns_project(project_id));
CREATE POLICY project_participant_delete ON project_participant FOR DELETE
  USING (owns_project(project_id));

ALTER TABLE project_module ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_module FORCE ROW LEVEL SECURITY;
CREATE POLICY project_module_read ON project_module FOR SELECT
  USING (can_read_project(project_id));
CREATE POLICY project_module_write ON project_module FOR ALL
  USING (owns_project(project_id))
  WITH CHECK (owns_project(project_id));
