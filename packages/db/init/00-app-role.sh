#!/bin/sh
set -eu

psql --set ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set app_password="$APP_DATABASE_PASSWORD" \
  --set system_password="$SYSTEM_DATABASE_PASSWORD" \
  --set agent_password="${AGENT_DATABASE_PASSWORD:-$APP_DATABASE_PASSWORD}" <<'SQL'
DO $block$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'equicontracts_app') THEN
    CREATE ROLE equicontracts_app
      LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'equicontracts_system') THEN
    CREATE ROLE equicontracts_system
      LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'equicontracts_agent') THEN
    CREATE ROLE equicontracts_agent
      LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END
$block$;

ALTER ROLE equicontracts_app PASSWORD :'app_password';
ALTER ROLE equicontracts_system PASSWORD :'system_password';
ALTER ROLE equicontracts_agent PASSWORD :'agent_password';
SQL
