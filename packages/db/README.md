# packages/db

Database migrations and seed data for EquiContracts.

## Migrations

Sequential SQL files in `migrations/`, applied in filename order.
Format: `NNNN_short_description.sql`

```bash
make migrate   # apply all migrations in order
make reset     # drop + recreate + migrate + seed
```

## Conventions

- All tenant tables have `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`
- Money columns: `numeric(18,2)`, never float/double
- UUIDs: `gen_random_uuid()` as default
- State columns: `text` with `CHECK` constraints (not enums)
- Financial fields: `is_financial boolean NOT NULL DEFAULT false`

## Seed data

`seed/dev_seed.sql` provides development fixtures. Must be idempotent
(`ON CONFLICT DO NOTHING`).

## Creating a new migration

```bash
./scripts/new_migration.sh "description_of_change"
```
