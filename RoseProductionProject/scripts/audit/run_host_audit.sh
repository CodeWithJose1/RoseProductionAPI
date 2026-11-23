#!/usr/bin/env bash
# Runs every final-audit check that needs the real MySQL container and the
# running API, and stores the evidence in docs/final-audit/evidence/.
#
# Prerequisites (see docs/final-audit/TEST_EXECUTION_RESULTS.md):
#   terminal 1:  source .venv/bin/activate && python app.py     (keep running)
#   terminal 2:  source .venv/bin/activate && bash scripts/audit/run_host_audit.sh
#
# Nothing here modifies existing records or the schema: tests create their
# own AUDIT_/TEST_ rows and delete them by id; constraint tests are rolled
# back; the backup is restored into a NEW database.
set -uo pipefail
cd "$(dirname "$0")/../.."
EVIDENCE=docs/final-audit/evidence
LOGS=$EVIDENCE/logs
mkdir -p "$LOGS"
RUNLOG=$EVIDENCE/host_run.jsonl
: > "$RUNLOG"

step() {  # step <name> <command...>
  local name=$1; shift
  local start end code
  start=$(date -Is)
  echo "=== [$start] $name: $*"
  "$@" > "$LOGS/$name.log" 2>&1
  code=$?
  end=$(date -Is)
  python3 - "$name" "$start" "$end" "$code" "$*" >> "$RUNLOG" <<'PY'
import json, sys
name, start, end, code, cmd = sys.argv[1:6]
print(json.dumps({"step": name, "command": cmd, "started": start,
                  "finished": end, "exit_code": int(code)}))
PY
  echo "    exit=$code (log: $LOGS/$name.log)"
  tail -n 3 "$LOGS/$name.log" | sed 's/^/    | /'
  return 0
}

API=${ROSE_BASE_URL:-http://127.0.0.1:7003}

step 00_host_info bash -c 'uname -a; cat /etc/os-release | head -3; python --version; which python; date -Is; hostname'
step 01_docker_status docker ps -a --filter name=Mysqlcontainer --format '{{.Names}} | {{.Image}} | {{.Status}} | {{.Ports}}'
step 02_python_packages bash -c 'pip list 2>/dev/null | grep -iE "^(flask|flask-sqlalchemy|sqlalchemy|pymysql|python-dotenv|cryptography|pytest|werkzeug) "'
step 03_git_status bash -c 'git -C "$PWD" rev-parse --show-toplevel; git -C "$PWD" status --short -- . | head -300; echo "--- last commit"; git -C "$PWD" log -1 --format="%h %ad %s" --date=iso -- . 2>/dev/null'
step 04_syntax_check python -m compileall -q -x '(\.venv|node_modules|backups)' .
step 05_original_test_connection python test_connection.py
step 06_original_test_read python test_read.py
step 07_api_version curl -s --max-time 5 "$API/"
if ! grep -q '"version":"1.2.0"' "$LOGS/07_api_version.log"; then
  echo
  echo "!! The API at $API is not running the audited code (version 1.2.0)."
  echo "!! Restart it in terminal 1 (Ctrl+C, then: python app.py) and run this script again."
  exit 1
fi
step 08_pytest python -m pytest -q -p no:cacheprovider --junitxml="$EVIDENCE/pytest_junit.xml"
step 09_final_audit python scripts/audit/final_audit.py
step 10_backup_restore bash scripts/audit/backup_restore_check.sh
step 11_secret_scan python3 - <<'PY'
import os, re
env = {}
for line in open(".env", encoding="utf-8"):
    m = re.match(r"\s*([A-Z_]+)\s*=\s*(.*)\s*$", line)
    if m:
        env[m.group(1)] = m.group(2).strip().strip("'\"")
secrets = {k: v for k, v in env.items() if k in ("API_KEY", "DB_PASSWORD") and len(v) >= 4}
hits, scanned = [], 0
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in (".venv", "node_modules", "__pycache__", ".pytest_cache", ".git")]
    for name in files:
        path = os.path.join(root, name)
        if path == "./.env":
            continue
        data = open(path, "rb").read()
        scanned += 1
        for key, value in secrets.items():
            if value.encode() in data:
                hits.append(f"{key} in {path}")
print(f"files scanned: {scanned}")
print("secret values found outside .env:", hits or "none")
raise SystemExit(1 if hits else 0)
PY
step 12_env_tracking bash -c 'git -C "$PWD" ls-files --error-unmatch .env >/dev/null 2>&1 && echo ".env IS TRACKED BY GIT" && exit 1; echo ".env not tracked by git"; git -C "$PWD" check-ignore -v .env || echo "note: .env not matched by any .gitignore rule"'

echo
echo "Evidence written to $EVIDENCE"
python3 - <<'PY'
import json
for line in open("docs/final-audit/evidence/host_run.jsonl"):
    step = json.loads(line)
    print(f"  {step['step']:<28} exit={step['exit_code']}")
PY
