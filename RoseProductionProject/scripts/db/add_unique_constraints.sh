#!/usr/bin/env bash
# Apply the UNIQUE constraints approved on 2026-11-23 to RoseProductionDB.
#
#   Farm    unique_farm_name_location (name, location)
#   Lot     unique_lot_farm_name      (farm_id, name)
#   Season  unique_season_name_dates  (name, start_date, end_date)
#   Harvest unique_harvest_crop_date  (crop_id, harvest_date)
#
# Safety:
#   1. a full backup (mysqldump --single-transaction --routines --triggers)
#      is written to backups/ and checked before anything else;
#   2. every rule is checked for existing duplicates with the same comparison
#      the index will use; if any exist the script stops and changes nothing;
#   3. constraints that already exist are skipped (safe to run twice);
#   4. only ADD CONSTRAINT ... UNIQUE is executed: no DROP, no TRUNCATE, no
#      UPDATE/DELETE of rows; row counts are compared before and after.
#      Note: MySQL itself drops the index it had created implicitly for the
#      foreign key Lot.farm_id once unique_lot_farm_name (farm_id, name) can
#      serve that foreign key (observed on 2026-11-23; no data affected).
# Evidence: docs/final-audit/evidence/unique_constraints_migration_<ts>.log
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; source .env; set +a

TS=$(date +%Y%m%d_%H%M%S)
EVIDENCE=docs/final-audit/evidence
LOG="$EVIDENCE/unique_constraints_migration_${TS}.log"
DUMP="backups/before_unique_constraints_${TS}.sql"
mkdir -p backups "$EVIDENCE"
exec > >(tee "$LOG") 2>&1

sql() {  # run one statement, tab-separated output without headers
  docker exec -i -e MYSQL_PWD="$DB_PASSWORD" Mysqlcontainer \
    mysql -u "$DB_USER" --batch --skip-column-names "$DB_NAME" -e "$1"
}

echo "== $(date -Is) migration 2026-11-23 on database $DB_NAME"
echo "== 1. backup -> $DUMP"
docker exec -e MYSQL_PWD="$DB_PASSWORD" Mysqlcontainer \
  mysqldump -u "$DB_USER" --single-transaction --routines --triggers \
  --set-gtid-purged=OFF "$DB_NAME" > "$DUMP"
grep -q "Dump completed" "$DUMP" || { echo "ABORT: backup incomplete"; exit 3; }
grep -q 'CREATE TABLE `Harvest`' "$DUMP" || { echo "ABORT: backup has no Harvest table"; exit 3; }
echo "backup bytes: $(wc -c < "$DUMP")  sha256: $(sha256sum "$DUMP" | cut -d' ' -f1)"

COUNTS="SELECT 'Farm',COUNT(*) FROM Farm UNION ALL SELECT 'Lot',COUNT(*) FROM Lot
 UNION ALL SELECT 'RoseVariety',COUNT(*) FROM RoseVariety UNION ALL SELECT 'Crop',COUNT(*) FROM Crop
 UNION ALL SELECT 'Season',COUNT(*) FROM Season UNION ALL SELECT 'Harvest',COUNT(*) FROM Harvest
 UNION ALL SELECT 'Forecast',COUNT(*) FROM Forecast"
echo "== 2. row counts before"
BEFORE=$(sql "$COUNTS"); echo "$BEFORE"

echo "== 3. duplicate pre-check (groups that would violate each new constraint)"
declare -A CHECK=(
  [unique_farm_name_location]="SELECT COUNT(*) FROM (SELECT 1 FROM Farm GROUP BY name, location HAVING COUNT(*) > 1) d"
  [unique_lot_farm_name]="SELECT COUNT(*) FROM (SELECT 1 FROM Lot GROUP BY farm_id, name HAVING COUNT(*) > 1) d"
  [unique_season_name_dates]="SELECT COUNT(*) FROM (SELECT 1 FROM Season GROUP BY name, start_date, end_date HAVING COUNT(*) > 1) d"
  [unique_harvest_crop_date]="SELECT COUNT(*) FROM (SELECT 1 FROM Harvest GROUP BY crop_id, harvest_date HAVING COUNT(*) > 1) d"
)
BLOCKED=0
for name in unique_farm_name_location unique_lot_farm_name unique_season_name_dates unique_harvest_crop_date; do
  n=$(sql "${CHECK[$name]}")
  echo "$name: $n duplicate group(s)"
  [ "$n" = "0" ] || BLOCKED=1
done
if [ "$BLOCKED" != "0" ]; then
  echo "ABORT: existing duplicates would violate a constraint. Nothing was changed."
  exit 2
fi

echo "== 4. add constraints"
declare -A DDL=(
  [unique_farm_name_location]="ALTER TABLE Farm ADD CONSTRAINT unique_farm_name_location UNIQUE (name, location), ALGORITHM=INPLACE, LOCK=NONE"
  [unique_lot_farm_name]="ALTER TABLE Lot ADD CONSTRAINT unique_lot_farm_name UNIQUE (farm_id, name), ALGORITHM=INPLACE, LOCK=NONE"
  [unique_season_name_dates]="ALTER TABLE Season ADD CONSTRAINT unique_season_name_dates UNIQUE (name, start_date, end_date), ALGORITHM=INPLACE, LOCK=NONE"
  [unique_harvest_crop_date]="ALTER TABLE Harvest ADD CONSTRAINT unique_harvest_crop_date UNIQUE (crop_id, harvest_date), ALGORITHM=INPLACE, LOCK=NONE"
)
for name in unique_farm_name_location unique_lot_farm_name unique_season_name_dates unique_harvest_crop_date; do
  exists=$(sql "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_NAME = '$name' AND CONSTRAINT_TYPE = 'UNIQUE'")
  if [ "$exists" != "0" ]; then echo "$name: already present, skipped"; continue; fi
  sql "${DDL[$name]}"
  echo "$name: added"
done

echo "== 5. verification"
sql "SELECT TABLE_NAME, CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_TYPE = 'UNIQUE' ORDER BY TABLE_NAME, CONSTRAINT_NAME"
AFTER=$(sql "$COUNTS"); echo "row counts after:"; echo "$AFTER"
if [ "$BEFORE" != "$AFTER" ]; then echo "ERROR: row counts changed"; exit 5; fi
echo "row counts unchanged"
echo "== done $(date -Is). Backup kept in $DUMP"
