# Test Execution Results — final audit, 2026-11-22

All times are America/Guayaquil (−05:00) unless marked Z (UTC). "Real system" = nobara-pc with the
production `RoseProductionDB`; "replica" = MySQL 8.0.46 in the cloud workspace loaded from the
2026-11-22 09:02 backup, schema fingerprint identical to the real DB (`9707b6b1…bd893bd`).

## 1. Which tests existed, which were added or corrected

| Origin | Tests |
|---|---|
| **Original project (before any of this work)** | `test_connection.py`, `test_read.py` (manual scripts, no assertions framework); test cases TC-01…TC-15 described in the project documentation |
| **First delivery (2026-11-22 morning), pre-existing for this audit** | pytest 226 (`tests/`), Vitest 57 (`frontend/src/__tests__/`), Playwright 23 (`frontend/e2e/`); evidence: `backups/pytest_real_db.xml` (nobara-pc, 09:18:50, `tests="226" failures="0" errors="0" skipped="0"`), `docs/TESTING.md` §3 |
| **Created during the final audit** | `scripts/audit/final_audit.py` (162 checks: environment, schema vs models, data quality, performance, constraints, security, CRUD matrix, FR checks, guards), `scripts/audit/backup_restore_check.sh` + `compare_restore.py`, `scripts/audit/run_host_audit.sh`; pytest `tests/test_api_consistency_rules.py` (5), `test_forecast_for_a_future_date_uses_past_history` (1), `test_request_body_too_large_is_413` (1); Vitest +3 (`crud.test.jsx`: 2 harvest-rule tests, 1 filtered empty state); axe-core scan of 11 views; real-system GUI workflow (30 steps); scale test (100,020 harvests); duplicate-harvest view reproduction |
| **Corrected during the final audit (with reason)** | see §4 |

Totals now: pytest **233** (226 + 7), Vitest **60** (57 + 3), Playwright **23** (3 workflows adjusted).

## 2. Executions on the real system (nobara-pc)

`bash scripts/audit/run_host_audit.sh` started by the user at 10:42:49 (`evidence/host_run.jsonl`,
`evidence/logs/`):

| Step | Command | Start | Exit | Result |
|---|---|---|---:|---|
| 00 | `uname -a; cat /etc/os-release; python --version; …` | 10:42:49 | 0 | Nobara 44, Linux 7.3.4, Python 3.14.8 (`.venv`) |
| 01 | `docker ps -a --filter name=Mysqlcontainer …` | 10:42:49 | 0 | `Mysqlcontainer · mysql:8.0.33 · Up 2 hours · 0.0.0.0:3306->3306/tcp` |
| 02 | `pip list | grep …` | 10:42:49 | 0 | Flask 3.1.3, Flask-SQLAlchemy 3.1.1, SQLAlchemy 2.1.9, PyMySQL 1.2.4, python-dotenv 1.2.4, Werkzeug 3.1.9 (no pytest, no cryptography) |
| 03 | `git status` of the folder | 10:42:49 | 0 | the folder is untracked inside the home-directory git repository (`?? ./`), no project commits |
| 04 | `python -m compileall -q -x '(\.venv|node_modules|backups)' .` | 10:42:49 | 0 | no syntax error |
| 05 | `python test_connection.py` (original) | 10:42:49 | 0 | "Connection successful! … MySQL version: 8.0.33" |
| 06 | `python test_read.py` (original) | 10:42:50 | 0 | Farm 1, Lot 3, RoseVariety 7, Crop 8, Season 3, Harvest 20, Forecast 8 |
| 07 | `curl -s http://127.0.0.1:7003/` | 10:42:50 | 0 | `"version": "1.1.0"` |
| 08 | `python -m pytest -q -p no:cacheprovider --junitxml=docs/final-audit/evidence/pytest_junit.xml` | 10:42:50 | **1** | **execution error, not a test failure**: pytest was not installed in the `.venv` |
| 08 (re-run) | same pytest command, after the user ran `pip install pytest` | 10:44:02 | – ¹ | **233 passed, 0 failed, 0 errors, 0 skipped** in 6.23 s (`pytest_junit.xml`, `hostname="nobara-pc"`) |
| 09 | `python scripts/audit/final_audit.py` | 10:42:50 | 0 | 162 checks: **154 PASS, 8 FINDING, 0 FAIL** (run `a820b749`, 6.7 s) |
| 10 | `bash scripts/audit/backup_restore_check.sh` | 10:42:57 | 0 | `"result": "PASS"` (dump 0.18 s, restore 0.683 s, structure + data + views equal) |
| 11 | secret scan (values of `API_KEY`, `DB_PASSWORD` from `.env`, never printed) | 10:42:58 | 0 | 160 files, none found |
| 12 | `.env` tracked by git? | 10:42:58 | 0 | not tracked; ignored by `.gitignore` |

¹ The exit code of the re-run is not recorded in `host_run.jsonl`; the JUnit file and the log show
233 tests with 0 failures and 0 errors.

The 8 **FINDING** results are defects detected in the data or schema (not failures of the
application code): `DQ-03` harvests before planting (16, 17, 18), `DQ-04` forecast before planting
(7), `DQ-05` future harvests (none), `DQ-06` duplicate crop/day harvests (none), `DQ-07` identical
varieties (6, 7), `DQ-08` identical crops (7, 8), `DQ-09` lots with area ≤ 0 (none), `NFR-02-20`
schema accepts two harvests for one crop and day (view duplicates a forecast row). `DQ-05`, `DQ-06`
and `DQ-09` are reported as FINDING-type checks even with zero rows because the schema does not
prevent them; the rows found are listed in `audit_results.json`.

Other real-system executions:

| What | Command / tool | Time | Exit | Result |
|---|---|---|---:|---|
| GUI workflow | browser pane, `evidence/gui_real_system_run.json` | 11:06–11:17 | – | **30 / 30 steps PASS**, 0 pre-existing rows changed |
| Page smoke check | browser pane, all 9 routes with bundle `index-CLqLDtTO.js` | ≈ 11:00 | – | 9 / 9 pages loaded with real counts, 0 error states |
| PATCH not implemented | `PATCH /farms/1` in the browser pane | 11:21 | – | 405 `METHOD_NOT_ALLOWED`, farm unchanged |
| Secret scan (after the last correction) | same logic as step 11, desktop-app VM | 16:05:26Z | 0 | 170 files, none found |
| Frontend in the desktop-app VM (Node 22.23.2) | `npm ci` · `npx vitest run` · `npx vite build` · `npm audit` | 16:05:30–16:05:49Z | 0 · 0 · 0 · 0 | 189 packages · **60/60** · build byte-identical to the shipped `dist` · 0 vulnerabilities (`evidence/frontend_on_user_machine.txt`) |

## 3. Executions on the replica / cloud workspace (final state of the code)

`/home/claude/work/run_cloud_regression.sh` (copy of the commands in
`evidence/cloud_regression/run_summary.txt`; logs and JSON reports in the same folder):

| Step | Command | Start | Exit | Passed | Failed | Skipped |
|---|---|---|---:|---:|---:|---:|
| 01 | `python -m compileall -q app.py … routes tests scripts/audit` | 11:02:59 | 0 | – | – | – |
| 02 | `python -m pytest -q --junitxml=…/pytest_junit.xml` | 11:02:59 | 0 | **233** | 0 | 0 |
| 03 | `npx vitest run --reporter=default --reporter=json` | 11:03:04 | 0 | **60** | 0 | 0 |
| 04 | `npx vite build --outDir /tmp/dist_check` + `cmp` with `frontend/dist` | 11:03:14 | 0 | 4 / 4 files identical | – | – |
| 05 | `npx playwright test --reporter=list,json` | 11:03:20 | 0 | **23** | 0 | 0 (flaky 0) |
| 06 | axe-core scan `axe_scan.cjs` (attempt 1) | 11:03:56 | **1** | – | – | – |
| 07 | `python scripts/audit/final_audit.py` on a copy (attempt 1) | 11:04:28 | **1** | – | – | – |
| 06 (re-run) | axe-core scan | 11:04:48 | 0 | 11 views, **0 violations** | – | – |
| 07 (re-run) | final audit against the replica | 11:05:04 | 0 | **154 PASS**, 8 FINDING | 0 | – |
| 08 | `python -m pip_audit -r requirements.txt -r requirements-dev.txt` | 11:14:22 | 0 | no known vulnerabilities | – | – |
| 09 | `npm audit --json` (frontend) | 11:14:34 | 0 | 0 vulnerabilities (239 dependencies) | – | – |

Attempts 1 of steps 06 and 07 failed **because of the audit harness**, not the project: the script
did not pass the replica's configuration to those two steps (axe could not sign in; the audit could
not build the database URL). The logs are kept as `06_axe_attempt1_no_credentials.log` and
`07_final_audit_replica_attempt1_no_credentials.log`; both steps passed after loading the
configuration.

Also on the replica: duplicate-harvest reproduction (rolled back) at 11:13:51
(`duplicate_harvest_view_effect_replica.json`); scale test with 100,020 harvests
(`scale_test_replica.json`).

## 4. Tests corrected during the audit and why

| Test | Change | Justification |
|---|---|---|
| `tests/conftest.py`, `test_api_original_contract.py` | isolated test seasons/harvests moved from 2098 to `TEST_YEAR = 2001` | the new rule "a harvest cannot be dated in the future" is a real business rule; harvests in 2098 became invalid input. Tests still use isolated seasons that no real data touches |
| `test_api_stats.py` | upcoming-season test uses 2097-02-01…14 | needs a season that is still in the future |
| `test_api_auth.py` | expects `"version": "1.1.0"`; new 413 test | API version and body-size limit added by the audit |
| `test_api_forecasting.py::test_reproduces_existing_moving_average_forecasts` (TC-07) | now recomputes **every** stored forecast with `forecasting.moving_average` (still 8/8 identical) and asserts that the endpoint **refuses** forecast 7's date with 400 `DATE_BEFORE_PLANTING` | forecast 7 (crop 6, 2026-01-25) predates the crop's planting (2026-02-15); the old assertion would have required the API to accept an inconsistent date. The changed expectation is documented, not hidden |
| `frontend/e2e/workflows.spec.js` (B, C, D) | crop planted on the start of a season that has already begun; harvest date = min(season end, today); forecast target chosen after the crop's planting date | the workflows previously used dates the new rules refuse |
| `crud.test.jsx` (duplicate 409 test) | uses `getAllByText` + `aria-invalid` | the 409 message is correctly shown twice (banner and field) |

No test was weakened to hide a defect: each changed expectation corresponds to a rule added on purpose
and listed in `FINAL_AUDIT_REPORT.md` §8.

## 5. Not executed

| Test | Reason | Replacement |
|---|---|---|
| Playwright E2E against the real system | Node.js is not installed on nobara-pc itself; the desktop-app VM (which has Node) cannot reach the host's `127.0.0.1:7003` | 30-step real-system GUI workflow (browser pane) + Playwright 23/23 on the replica |
| Direct SQL read-back during the GUI run | the audit shell cannot reach the host's MySQL port | independent API reads; direct SQL read-back of the same endpoints by the host harness |
| pytest on the host **after** the last (frontend-only) correction | the host pytest ran at 10:44, before the empty-state fix; the fix changed only `frontend/` | backend files are byte-identical (104 source files compared by SHA-256 between the user's folder and the cloud copy); pytest 233/233 re-run on the replica at 11:03; Vitest 60/60 and the reproducible build re-run on nobara-pc's VM; secret scan re-run on the new bundle |
| Load / concurrency tests | not required by the specification | scale test with 100,020 harvests (single client) |

## 6. Totals for the final state

| Environment | Suite | Executed | Passed | Failed | Skipped | Findings |
|---|---|---:|---:|---:|---:|---:|
| Real system | pytest | 233 | 233 | 0 | 0 | – |
| Real system | final audit harness | 162 | 154 | 0 | 0 | 8 |
| Real system | GUI workflow | 30 | 30 | 0 | 0 | – |
| Real system | backup/restore check | 1 | 1 | 0 | 0 | – |
| Real system | original scripts (`test_connection.py`, `test_read.py`) | 2 | 2 | 0 | 0 | – |
| nobara-pc VM | Vitest | 60 | 60 | 0 | 0 | – |
| Replica | pytest | 233 | 233 | 0 | 0 | – |
| Replica | Vitest | 60 | 60 | 0 | 0 | – |
| Replica | Playwright | 23 | 23 | 0 | 0 | – |
| Replica | final audit harness | 162 | 154 | 0 | 0 | 8 |
| Replica | axe (views) | 11 | 11 | 0 | 0 | – |
| **All** | | **977** | **961** | **0** | **0** | **16** |

Distinct test cases (each counted once): pytest 233 + Vitest 60 + Playwright 23 + audit checks 162 +
GUI steps 30 + axe views 11 + backup/restore 1 + original scripts 2 = **522**, of which 0 failed,
0 skipped and 8 are findings. Execution errors caused by the environment or the harness (host pytest
attempt 1, cloud steps 06/07 attempt 1) were re-run and are not counted as tests.
