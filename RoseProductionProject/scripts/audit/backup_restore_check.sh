#!/usr/bin/env bash
# NFR-04 evidence: back up RoseProductionDB and restore the backup into a NEW,
# isolated database on the same server, then compare both databases.
#
# Safety:
#   * the production database is only READ (mysqldump --single-transaction);
#   * the restore target is a brand-new database whose name contains a
#     timestamp; CREATE DATABASE fails if it already exists;
#   * the dump is checked for USE/CREATE DATABASE statements before restoring
#     (a single-database dump has none, so it cannot touch another schema);
#   * nothing is dropped. The recovery database is left for inspection; drop
#     it manually when no longer needed (command printed at the end).
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; source .env; set +a

TS=$(date +%Y%m%d_%H%M%S)
EVIDENCE=docs/final-audit/evidence
DUMP="backups/audit_backup_${TS}.sql"
RESTORE_DB="RoseProductionDB_AuditRestore_${TS}"
mkdir -p backups "$EVIDENCE"

if [ "$RESTORE_DB" = "$DB_NAME" ]; then echo "refusing: target equals source" >&2; exit 2; fi

t0=$(date +%s.%N)
docker exec -e MYSQL_PWD="$DB_PASSWORD" Mysqlcontainer \
  mysqldump -u "$DB_USER" --single-transaction --routines --triggers \
  --set-gtid-purged=OFF "$DB_NAME" > "$DUMP"
t1=$(date +%s.%N)
grep -q "Dump completed" "$DUMP" || { echo "dump incomplete" >&2; exit 3; }
if grep -Eiq '^(USE |CREATE DATABASE)' "$DUMP"; then
  echo "dump contains USE/CREATE DATABASE; refusing to restore" >&2; exit 4
fi

docker exec -e MYSQL_PWD="$DB_PASSWORD" Mysqlcontainer \
  mysql -u "$DB_USER" -e "CREATE DATABASE \`${RESTORE_DB}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
t2=$(date +%s.%N)
docker exec -i -e MYSQL_PWD="$DB_PASSWORD" Mysqlcontainer \
  mysql -u "$DB_USER" "$RESTORE_DB" < "$DUMP"
t3=$(date +%s.%N)

python scripts/audit/compare_restore.py "$RESTORE_DB" "$DUMP" \
  "$(python3 -c "print($t1 - $t0)")" "$(python3 -c "print($t3 - $t2)")" \
  > "$EVIDENCE/backup_restore.json"
cat "$EVIDENCE/backup_restore.json"
echo
echo "Recovery database kept for inspection: ${RESTORE_DB}"
echo "To remove it later (manual decision):"
echo "  docker exec -it Mysqlcontainer mysql -u root -p -e 'DROP DATABASE \`${RESTORE_DB}\`'"
