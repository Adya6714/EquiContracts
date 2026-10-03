#!/usr/bin/env bash
set -euo pipefail

NAME="${1:?usage: new_migration.sh <name>}"
NUM=$(printf "%04d" $(($(ls -1 packages/db/migrations/*.sql 2>/dev/null | wc -l | tr -d ' ') + 1)))
FILE="packages/db/migrations/${NUM}_${NAME}.sql"
echo "-- ${NAME}" > "$FILE"
echo "Created $FILE"
