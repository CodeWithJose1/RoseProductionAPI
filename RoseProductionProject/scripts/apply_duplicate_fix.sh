#!/usr/bin/env bash
# One-command application and verification of the duplicate-prevention fix
# (2026-11-23) on this machine:
#
#   cd ~/Documentos/DockerMySQL/RoseProductionAPI && bash scripts/apply_duplicate_fix.sh
#
#   1. starts the MySQL container if it is stopped;
#   2. runs scripts/db/add_unique_constraints.sh (backup, duplicate pre-check,
#      the 4 approved UNIQUE constraints, verification; stops if anything is
#      wrong and changes nothing in that case);
#   3. starts a SECOND API with the new code on http://127.0.0.1:7004 (your
#      usual API on port 7003 is not touched);
#   4. runs scripts/audit/run_duplicate_fix_host.sh against it (pytest,
#      HTTP+SQL audit incl. concurrency, read-only duplicate inspection);
#   5. leaves the port-7004 API running for the GUI check and prints the
#      command to stop it.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p docs/final-audit/evidence/duplicates/host
exec > >(tee -a "docs/final-audit/evidence/duplicates/host/apply_$(date +%Y%m%d_%H%M%S).log") 2>&1
echo "== $(date -Is) apply_duplicate_fix.sh started in $PWD"
[ -f .venv/bin/activate ] && source .venv/bin/activate

echo "== 1. MySQL container"
if [ "$(docker inspect -f '{{.State.Running}}' Mysqlcontainer 2>/dev/null)" != "true" ]; then
  docker start Mysqlcontainer || { echo "!! could not start Mysqlcontainer"; exit 1; }
  for i in $(seq 1 30); do python test_connection.py >/dev/null 2>&1 && break; sleep 2; done
fi
python test_connection.py || { echo "!! MySQL is not reachable"; exit 1; }

echo "== 2. approved migration"
bash scripts/db/add_unique_constraints.sh || { echo "!! migration stopped (see the log above); nothing else was run"; exit 2; }

echo "== 3. API with the new code on 127.0.0.1:7004"
mkdir -p docs/final-audit/evidence/duplicates/host
LOG=docs/final-audit/evidence/duplicates/host/api_7004_$(date +%Y%m%d_%H%M%S).log
if curl -s --max-time 2 http://127.0.0.1:7004/ | grep -q '"version":"1.2.0"'; then
  echo "an API with version 1.2.0 is already running on 7004"
else
  nohup python -c "from app import app; app.run(host='127.0.0.1', port=7004, debug=False)" > "$LOG" 2>&1 &
  echo $! > docs/final-audit/evidence/duplicates/host/api_7004.pid
  for i in $(seq 1 30); do curl -s --max-time 1 http://127.0.0.1:7004/ | grep -q '"version":"1.2.0"' && break; sleep 1; done
fi
curl -s http://127.0.0.1:7004/; echo
curl -s http://127.0.0.1:7004/ | grep -q '"version":"1.2.0"' || { echo "!! the new API did not start (see $LOG)"; exit 3; }

echo "== 4. verification"
ROSE_BASE_URL=http://127.0.0.1:7004 bash scripts/audit/run_duplicate_fix_host.sh

echo
echo "The verification API keeps running on http://127.0.0.1:7004 (PID $(cat docs/final-audit/evidence/duplicates/host/api_7004.pid 2>/dev/null || echo "?"))."
echo "Stop it when the GUI check is done:   kill \$(cat docs/final-audit/evidence/duplicates/host/api_7004.pid)"
echo "Then restart your usual API (Ctrl+C in its terminal, then: python app.py) to use the new code on port 7003."
