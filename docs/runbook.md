# Runbook

Operational procedures for EquiContracts.

**Also see:** [security/pre-launch-checklist.md](./security/pre-launch-checklist.md) before any
public deploy; [architecture/project-map.md](./architecture/project-map.md) for orientation.

---

## Deploy

_To be documented when deployment target is chosen (Phase 0 Step 0.13)._

## Rollback

### Database migration rollback

Migrations are forward-only SQL. To roll back:

1. Identify the problematic migration
2. Write a new migration that reverses the change
3. Apply via `make migrate`

Never edit a previously-applied migration file.

### Application rollback

Revert to previous container image / git commit.

## Backup and restore

### Database backup

```bash
docker compose exec postgres pg_dump -U postgres equicontracts > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Database restore

```bash
docker compose exec -T postgres psql -U postgres -c "DROP DATABASE IF EXISTS equicontracts;"
docker compose exec -T postgres psql -U postgres -c "CREATE DATABASE equicontracts;"
docker compose exec -T postgres psql -U postgres -d equicontracts < backup_file.sql
```

### Object storage backup

MinIO data lives in a Docker volume. For production, configure MinIO replication
or use a managed S3-compatible service.

## Incident response

### Cross-tenant data leak

1. Immediately disable the affected endpoint
2. Check `pg_stat_activity` for sessions missing `app.current_org_id`
3. Review recent migrations for missing RLS policies
4. Audit `event_log` for any reads by wrong org

### Unverified data exposed to client

1. Check the `(client)` route handler for missing `state = 'verified'` filter
2. CI should catch this — investigate why it didn't
3. Notify affected client org
