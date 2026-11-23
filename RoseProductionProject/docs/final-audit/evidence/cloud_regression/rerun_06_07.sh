#!/usr/bin/env bash
set -u
cd /home/claude/rose
set -a; . /home/claude/.env; set +a     # replica configuration (values never printed)
OUT=docs/final-audit/evidence/cloud_regression
PY=/home/claude/venv/bin/python
SUMMARY=$OUT/run_summary.txt
echo "# attempt 1 of 06/07 failed: the harness did not pass the replica configuration (fixed: variables loaded from the cloud .env); rerun below" >> $SUMMARY
run() { local name=$1; shift; local start; start=$(date --iso-8601=seconds); "$@" > "$OUT/$name.log" 2>&1; local rc=$?; printf '%s | %s | exit=%s | %s\n' "$start" "$name" "$rc" "$*" >> $SUMMARY; }
run 06_axe bash -c "cd /home/claude/axe && KEY=\"\$API_KEY\" node axe_scan.cjs > /home/claude/rose/$OUT/axe_results.json && node -e \"const r=require('/home/claude/rose/$OUT/axe_results.json');for(const [k,v] of Object.entries(r.results))console.log(k, v.length, 'violations')\""
rm -rf /tmp/rose_audit_copy && mkdir -p /tmp/rose_audit_copy && tar -C /home/claude/rose --exclude=frontend/node_modules --exclude=.git -cf - . | tar -C /tmp/rose_audit_copy -xf - && rm -f /tmp/rose_audit_copy/docs/final-audit/evidence/audit_results.json /tmp/rose_audit_copy/docs/final-audit/evidence/audit_log.txt
run 07_final_audit_replica bash -c "cd /tmp/rose_audit_copy && $PY scripts/audit/final_audit.py && cp docs/final-audit/evidence/audit_results.json /home/claude/rose/$OUT/audit_results_replica_final.json && cp docs/final-audit/evidence/audit_log.txt /home/claude/rose/$OUT/audit_log_replica_final.txt"
