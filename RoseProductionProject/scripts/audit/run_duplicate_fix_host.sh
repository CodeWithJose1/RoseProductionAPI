#!/usr/bin/env bash
# Verification of the duplicate-prevention fix (2026-11-23) on the real
# system. Writes everything to docs/final-audit/evidence/duplicates/host/<ts>/
# and does NOT overwrite the final-audit evidence of 2026-11-22.
#
# Order:
#   1. bash scripts/db/add_unique_constraints.sh     (approved migration, once)
#   2. terminal 1: source .venv/bin/activate && python app.py   (new code, 1.2.0)
#   3. terminal 2: source .venv/bin/activate && bash scripts/audit/run_duplicate_fix_host.sh
#
# Nothing here modifies existing records or the schema: tests create their
# own AUDIT_/TEST_ rows and delete them by id; constraint tests are rolled
# back; the duplicate inspection is read-only.
set -uo pipefail
cd "$(dirname "$0")/../.."
TS=$(date +%Y%m%d_%H%M%S)
OUT=docs/final-audit/evidence/duplicates/host/$TS
mkdir -p "$OUT/logs"
RUNLOG=$OUT/host_run.jsonl
API=${ROSE_BASE_URL:-http://127.0.0.1:7003}

step() {  # step <name> <command...>
  local name=$1; shift
  local start end code
  start=$(date -Is)
  echo "=== [$start] $name: $*"
  "$@" > "$OUT/logs/$name.log" 2>&1
  code=$?
  end=$(date -Is)
  python3 - "$name" "$start" "$end" "$code" "$*" >> "$RUNLOG" <<'PY'
import json, sys
name, start, end, code, cmd = sys.argv[1:6]
print(json.dumps({"step": name, "command": cmd, "started": start,
                  "finished": end, "exit_code": int(code)}))
PY
  echo "    exit=$code (log: $OUT/logs/$name.log)"
  tail -n 3 "$OUT/logs/$name.log" | sed 's/^/    | /'
  return 0
}

step 00_host_info bash -c 'uname -n; python --version; date -Is'
step 01_docker_status docker ps -a --filter name=Mysqlcontainer --format '{{.Names}} | {{.Image}} | {{.Status}}'
step 02_api_version curl -s --max-time 5 "$API/"
if ! grep -q '"version":"1.2.0"' "$OUT/logs/02_api_version.log"; then
  echo "!! The API at $API is not running the new code (version 1.2.0)."
  echo "!! Restart it in terminal 1 (Ctrl+C, then: python app.py) and run this script again."
  exit 1
fi
step 03_unique_constraints bash -c 'set -a; source .env; set +a; docker exec -e MYSQL_PWD="$DB_PASSWORD" Mysqlcontainer mysql -u "$DB_USER" --batch "$DB_NAME" -e "SELECT TABLE_NAME, CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_TYPE = '"'"'UNIQUE'"'"' ORDER BY 1, 2"'
step 04_duplicate_inspection python scripts/audit/duplicate_inspection.py "$OUT/duplicate_inspection.json"
step 05_pytest python -m pytest -q -p no:cacheprovider --junitxml="$OUT/pytest_junit.xml"
step 06_final_audit env AUDIT_OUT_DIR="$OUT" python scripts/audit/final_audit.py
step 07_duplicate_inspection_after python scripts/audit/duplicate_inspection.py "$OUT/duplicate_inspection_after.json"

echo
echo "Evidence written to $OUT"
python3 - "$RUNLOG" <<'PY'
import json, sys
for line in open(sys.argv[1]):
    step = json.loads(line)
    print(f"  {step['step']:<30} exit={step['exit_code']}")
PY
