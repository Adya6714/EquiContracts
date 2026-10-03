-- Idempotent local-development identities.
-- Project data is created through the API so RLS paths remain exercised.

INSERT INTO org (id, name, org_type)
VALUES
  ('00000000-0000-4000-8000-000000000001', 'Demo Contractor', 'contractor'),
  ('00000000-0000-4000-8000-000000000002', 'Demo Client', 'client'),
  ('00000000-0000-4000-8000-000000000003', 'Demo PMC', 'pmc')
ON CONFLICT (id) DO NOTHING;

INSERT INTO app_user (id, org_id, email, role)
VALUES
  (
    '10000000-0000-4000-8000-000000000001',
    '00000000-0000-4000-8000-000000000001',
    'contractor@example.invalid',
    'contractor_admin'
  ),
  (
    '10000000-0000-4000-8000-000000000002',
    '00000000-0000-4000-8000-000000000002',
    'client@example.invalid',
    'client_pm'
  ),
  (
    '10000000-0000-4000-8000-000000000003',
    '00000000-0000-4000-8000-000000000003',
    'pmc@example.invalid',
    'pmc_user'
  )
ON CONFLICT (id) DO NOTHING;
