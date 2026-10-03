-- Fix participant read access for document-derived tables.
--
-- can_read_project() was introduced in 0002 and already gates project /
-- work_order / bank_guarantee reads. document, document_classification, and
-- event_log incorrectly used owns_project() for SELECT, so client/PMC
-- participants could never join documents (client dashboard counted zeros).
-- Write policies stay owner-only. Policies are altered in place (DROP POLICY
-- is blocked by scripts/check_agent_rules.py).

CREATE OR REPLACE FUNCTION can_read_project(target_project_id uuid)
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

ALTER POLICY project_read ON project
  USING (can_read_project(id));

ALTER POLICY document_read ON document
  USING (can_read_project(project_id));

ALTER POLICY classification_read ON document_classification
  USING (can_read_project(document_project(document_id)));

-- Participants may read verified fields only; owners retain full read.
ALTER POLICY extracted_field_contractor_read ON extracted_field
  USING (
    can_read_project(document_project(document_id))
    AND (
      owns_project(document_project(document_id))
      OR state = 'verified'
    )
  );

ALTER POLICY event_log_read ON event_log
  USING (can_read_project(project_id));

-- work_order, annexure_*, proforma_invoice, bank_guarantee, and bg_event
-- already use can_read_project() for SELECT in 0004/0005; no change.
