#!/usr/bin/env bash
# Cloud regression run on the MySQL 8 replica (schema fingerprint identical to the real DB).
set -u
cd /home/claude/rose
while IFS= read -r -d '' kv; do case "$kv" in DB_*|API_KEY=*) export "$kv";; esac; done < /proc/$(pgrep -f "python app.py" | head -1)/environ
OUT=docs/final-audit/evidence/cloud_regression
PY=/home/claude/venv/bin/python
SUMMARY=$OUT/run_summary.txt
: > $SUMMARY
run() { # name, command...
  local name=$1; shift
  local start; start=$(date --iso-8601=seconds)
  "$@" > "$OUT/$name.log" 2>&1
  local rc=$?
  printf '%s | %s | exit=%s | %s\n' "$start" "$name" "$rc" "$*" >> $SUMMARY
}
run 01_python_syntax $PY -m compileall -q app.py auth.py config.py errors.py forecasting.py models.py serializers.py validators.py test_connection.py test_read.py routes tests scripts/audit
run 02_pytest $PY -m pytest -q --junitxml=$OUT/pytest_junit.xml
run 03_vitest bash -c "cd frontend && npx vitest run --reporter=default --reporter=json --outputFile=../$OUT/vitest.json"
run 04_vite_build_check bash -c "cd frontend && rm -rf /tmp/dist_check && npx vite build --outDir /tmp/dist_check --emptyOutDir && for f in index.html assets/index-CL6YbocT.css assets/index-CLqLDtTO.js favicon.svg; do cmp -s /tmp/dist_check/\$f dist/\$f && echo identical \$f || echo DIFFERENT \$f; done"
run 05_playwright bash -c "cd frontend && PLAYWRIGHT_JSON_OUTPUT_NAME=../$OUT/playwright.json npx playwright test --reporter=list,json"
run 06_axe bash -c "cd /home/claude/axe && KEY=\"\$API_KEY\" node axe_scan.cjs > /home/claude/rose/$OUT/axe_results.json && node -e \"const r=require('/home/claude/rose/$OUT/axe_results.json');for(const [k,v] of Object.entries(r.results))console.log(k, v.length, 'violations')\""
rm -rf /tmp/rose_audit_copy && mkdir -p /tmp/rose_audit_copy && tar -C /home/claude/rose --exclude=frontend/node_modules --exclude=.git -cf - . | tar -C /tmp/rose_audit_copy -xf - && rm -f /tmp/rose_audit_copy/docs/final-audit/evidence/audit_results.json /tmp/rose_audit_copy/docs/final-audit/evidence/audit_log.txt
run 07_final_audit_replica bash -c "cd /tmp/rose_audit_copy && $PY scripts/audit/final_audit.py && cp docs/final-audit/evidence/audit_results.json /home/claude/rose/$OUT/audit_results_replica_final.json && cp docs/final-audit/evidence/audit_log.txt /home/claude/rose/$OUT/audit_log_replica_final.txt"
echo done
