-- Shared inbox plus-addressing: store alias only on project.
-- Full recipient form is projects+{alias}@{inbound_email_domain}.
-- Plus-address parse lives in routers/inbound.extract_inbound_alias; this
-- function looks up the already-extracted alias.

ALTER TABLE project RENAME COLUMN inbound_email TO inbound_alias;

-- Existing rows may hold a full address; keep only the routing alias.
UPDATE project
SET inbound_alias = lower(
  CASE
    WHEN position('@' IN inbound_alias) > 0 THEN
      CASE
        WHEN position('+' IN split_part(inbound_alias, '@', 1)) > 0
          THEN split_part(split_part(inbound_alias, '@', 1), '+', 2)
        ELSE split_part(inbound_alias, '@', 1)
      END
    ELSE inbound_alias
  END
);

-- CREATE OR REPLACE cannot rename target_recipient → another name.
-- Original signature (0003): resolve_inbound_project(target_recipient text).
DROP FUNCTION IF EXISTS resolve_inbound_project(text);

CREATE FUNCTION resolve_inbound_project(target_recipient text)
RETURNS TABLE (id uuid, owner_org_id uuid)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT project.id, project.owner_org_id
  FROM public.project
  WHERE lower(project.inbound_alias) = lower(target_recipient)
$$;

REVOKE ALL ON FUNCTION resolve_inbound_project(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION resolve_inbound_project(text) TO equicontracts_system;
