#!/usr/bin/env bash
# Creates a full logical backup (schema, data, triggers, procedures, views)
# of RoseProductionDB from the Docker container, using the credentials in .env.
# Usage: ./scripts/backup_db.sh            -> backups/RoseProductionDB_backup_<date>.sql
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
mkdir -p backups
out="backups/RoseProductionDB_backup_$(date +%Y%m%d_%H%M%S).sql"
docker exec -e MYSQL_PWD="$DB_PASSWORD" Mysqlcontainer \
  mysqldump -u "$DB_USER" --single-transaction --routines --triggers \
  --set-gtid-purged=OFF "$DB_NAME" > "$out"
grep -q "Dump completed" "$out" || { echo "Backup looks incomplete: $out" >&2; exit 1; }
echo "Backup written to $out ($(wc -c < "$out") bytes)"
sha256sum "$out"
