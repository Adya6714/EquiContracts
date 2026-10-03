-- Phase 0 Step 0.6: organisations, users, projects and participant access.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'equicontracts_app') THEN
    CREATE ROLE equicontracts_app
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'equicontracts_system') THEN
    CREATE ROLE equicontracts_system
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END
$$;

CREATE TABLE org (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL,
  org_type   text NOT NULL
             CHECK (org_type IN ('contractor', 'client', 'pmc', 'internal')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app_user (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     uuid NOT NULL REFERENCES org(id),
  email      text NOT NULL UNIQUE,
  role       text NOT NULL CHECK (role IN (
               'contractor_admin', 'contractor_user',
               'client_mgmt', 'client_pm', 'pmc_user', 'ec_admin'
             )),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE project (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_org_id  uuid NOT NULL REFERENCES org(id),
  name          text NOT NULL,
  project_code  text NOT NULL UNIQUE,
  inbound_email text NOT NULL UNIQUE,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE project_participant (
  project_id uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  org_id     uuid NOT NULL REFERENCES org(id),
  role       text NOT NULL CHECK (role IN ('client', 'pmc')),
  data_scope text NOT NULL DEFAULT 'verified_only'
             CHECK (data_scope = 'verified_only'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, org_id)
);

CREATE TABLE project_module (
  project_id  uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  module_name text NOT NULL CHECK (module_name IN (
                'bg_verify', 'milestone_validator', 'payment_mismatch',
                'evidence_locker', 'resolution_statement'
              )),
  enabled     boolean NOT NULL DEFAULT true,
  PRIMARY KEY (project_id, module_name)
);

CREATE FUNCTION enforce_project_owner_is_contractor()
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
    RAISE EXCEPTION 'project owner must be a contractor organisation'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER project_owner_is_contractor
BEFORE INSERT OR UPDATE OF owner_org_id ON project
FOR EACH ROW EXECUTE FUNCTION enforce_project_owner_is_contractor();

CREATE FUNCTION enforce_participant_org_type()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  participant_type text;
BEGIN
  SELECT org_type INTO participant_type FROM org WHERE id = NEW.org_id;
  IF participant_type IS DISTINCT FROM NEW.role THEN
    RAISE EXCEPTION 'participant role must match organisation type'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER participant_org_type_matches
BEFORE INSERT OR UPDATE OF org_id, role ON project_participant
FOR EACH ROW EXECUTE FUNCTION enforce_participant_org_type();

REVOKE ALL ON FUNCTION enforce_project_owner_is_contractor() FROM PUBLIC;
REVOKE ALL ON FUNCTION enforce_participant_org_type() FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO equicontracts_app;
GRANT USAGE ON SCHEMA public TO equicontracts_system;
GRANT SELECT ON org, app_user TO equicontracts_app;
GRANT SELECT, INSERT, UPDATE, DELETE
  ON project, project_participant, project_module TO equicontracts_app;
