-- Phase 0 Step 0.9: bank guarantees with separate expiry clocks.

CREATE TABLE bank_guarantee (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  work_order_id     uuid NOT NULL REFERENCES work_order(id) ON DELETE CASCADE,
  bg_number         text NOT NULL,
  bg_type           text NOT NULL
                    CHECK (bg_type IN ('mobilization', 'performance', 'retention')),
  value             numeric(18,2) NOT NULL CHECK (value >= 0),
  issuing_bank      text,
  expiry_date       date,
  claim_expiry_date date,
  status            text NOT NULL DEFAULT 'active'
                    CHECK (status IN (
                      'active', 'expiring', 'idle', 'redundant', 'released'
                    )),
  created_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT bg_claim_after_expiry CHECK (
    claim_expiry_date IS NULL
    OR expiry_date IS NULL
    OR claim_expiry_date >= expiry_date
  ),
  UNIQUE (work_order_id, bg_number)
);

CREATE TABLE bg_event (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bank_guarantee_id uuid NOT NULL REFERENCES bank_guarantee(id) ON DELETE CASCADE,
  event_type        text NOT NULL CHECK (event_type IN (
                      'issued', 'amended', 'renewed', 'invoked', 'released',
                      'expiry_alert', 'claim_expiry_alert'
                    )),
  event_date        date NOT NULL,
  document_id       uuid REFERENCES document(id),
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION bank_guarantee_project(target_bg_id uuid)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT public.work_order_project(work_order_id)
  FROM public.bank_guarantee
  WHERE id = target_bg_id
$$;

REVOKE ALL ON FUNCTION bank_guarantee_project(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION bank_guarantee_project(uuid) TO equicontracts_app;

ALTER TABLE bank_guarantee ENABLE ROW LEVEL SECURITY;
ALTER TABLE bank_guarantee FORCE ROW LEVEL SECURITY;
CREATE POLICY bank_guarantee_read ON bank_guarantee FOR SELECT
  USING (can_read_project(work_order_project(work_order_id)));
CREATE POLICY bank_guarantee_write ON bank_guarantee FOR ALL
  USING (owns_project(work_order_project(work_order_id)))
  WITH CHECK (owns_project(work_order_project(work_order_id)));

ALTER TABLE bg_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE bg_event FORCE ROW LEVEL SECURITY;
CREATE POLICY bg_event_read ON bg_event FOR SELECT
  USING (can_read_project(bank_guarantee_project(bank_guarantee_id)));
CREATE POLICY bg_event_write ON bg_event FOR ALL
  USING (owns_project(bank_guarantee_project(bank_guarantee_id)))
  WITH CHECK (owns_project(bank_guarantee_project(bank_guarantee_id)));

GRANT SELECT, INSERT, UPDATE, DELETE
  ON bank_guarantee, bg_event TO equicontracts_app;
