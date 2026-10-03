-- Phase 0 Step 0.9: work orders and objective annexure completeness.

CREATE TABLE work_order (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id                uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  wo_number                 text NOT NULL,
  trade                     text,
  value                     numeric(18,2),
  certification_sla_days    integer CHECK (certification_sla_days > 0),
  bg_clause_conditionality  text
                            CHECK (bg_clause_conditionality IN (
                              'conditional', 'unconditional'
                            )),
  retention_bg_ratio_clause text,
  created_at                timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, wo_number)
);

CREATE TABLE annexure_requirement (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  work_order_id uuid NOT NULL REFERENCES work_order(id) ON DELETE CASCADE,
  annexure_name text NOT NULL,
  mandatory     boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (work_order_id, annexure_name)
);

CREATE TABLE proforma_invoice (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  work_order_id uuid NOT NULL REFERENCES work_order(id) ON DELETE CASCADE,
  number        text NOT NULL,
  value         numeric(18,2),
  submitted_at  date,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (work_order_id, number)
);

CREATE TABLE annexure_submission (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  proforma_invoice_id      uuid NOT NULL REFERENCES proforma_invoice(id) ON DELETE CASCADE,
  annexure_requirement_id  uuid NOT NULL REFERENCES annexure_requirement(id),
  status                   text NOT NULL CHECK (status IN ('present', 'missing', 'na')),
  created_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (proforma_invoice_id, annexure_requirement_id)
);

CREATE FUNCTION enforce_annexure_matches_work_order()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  proforma_work_order uuid;
  requirement_work_order uuid;
BEGIN
  SELECT work_order_id INTO proforma_work_order
  FROM public.proforma_invoice
  WHERE id = NEW.proforma_invoice_id;

  SELECT work_order_id INTO requirement_work_order
  FROM public.annexure_requirement
  WHERE id = NEW.annexure_requirement_id;

  IF proforma_work_order IS DISTINCT FROM requirement_work_order THEN
    RAISE EXCEPTION 'annexure requirement belongs to another work order'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER annexure_matches_work_order
BEFORE INSERT OR UPDATE OF proforma_invoice_id, annexure_requirement_id
ON annexure_submission
FOR EACH ROW EXECUTE FUNCTION enforce_annexure_matches_work_order();

REVOKE ALL ON FUNCTION enforce_annexure_matches_work_order() FROM PUBLIC;

CREATE FUNCTION work_order_project(target_work_order_id uuid)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT project_id FROM public.work_order WHERE id = target_work_order_id
$$;

CREATE FUNCTION proforma_project(target_proforma_id uuid)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT public.work_order_project(work_order_id)
  FROM public.proforma_invoice
  WHERE id = target_proforma_id
$$;

REVOKE ALL ON FUNCTION work_order_project(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION proforma_project(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION work_order_project(uuid) TO equicontracts_app;
GRANT EXECUTE ON FUNCTION proforma_project(uuid) TO equicontracts_app;

ALTER TABLE work_order ENABLE ROW LEVEL SECURITY;
ALTER TABLE work_order FORCE ROW LEVEL SECURITY;
CREATE POLICY work_order_read ON work_order FOR SELECT
  USING (can_read_project(project_id));
CREATE POLICY work_order_write ON work_order FOR ALL
  USING (owns_project(project_id))
  WITH CHECK (owns_project(project_id));

ALTER TABLE annexure_requirement ENABLE ROW LEVEL SECURITY;
ALTER TABLE annexure_requirement FORCE ROW LEVEL SECURITY;
CREATE POLICY annexure_requirement_read ON annexure_requirement FOR SELECT
  USING (can_read_project(work_order_project(work_order_id)));
CREATE POLICY annexure_requirement_write ON annexure_requirement FOR ALL
  USING (owns_project(work_order_project(work_order_id)))
  WITH CHECK (owns_project(work_order_project(work_order_id)));

ALTER TABLE proforma_invoice ENABLE ROW LEVEL SECURITY;
ALTER TABLE proforma_invoice FORCE ROW LEVEL SECURITY;
CREATE POLICY proforma_read ON proforma_invoice FOR SELECT
  USING (can_read_project(work_order_project(work_order_id)));
CREATE POLICY proforma_write ON proforma_invoice FOR ALL
  USING (owns_project(work_order_project(work_order_id)))
  WITH CHECK (owns_project(work_order_project(work_order_id)));

ALTER TABLE annexure_submission ENABLE ROW LEVEL SECURITY;
ALTER TABLE annexure_submission FORCE ROW LEVEL SECURITY;
CREATE POLICY annexure_submission_read ON annexure_submission FOR SELECT
  USING (can_read_project(proforma_project(proforma_invoice_id)));
CREATE POLICY annexure_submission_write ON annexure_submission FOR ALL
  USING (owns_project(proforma_project(proforma_invoice_id)))
  WITH CHECK (owns_project(proforma_project(proforma_invoice_id)));

GRANT SELECT, INSERT, UPDATE, DELETE ON
  work_order, annexure_requirement, proforma_invoice, annexure_submission
  TO equicontracts_app;
