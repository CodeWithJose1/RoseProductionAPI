# Testing

## 1. Strategy

| Layer | Tool | Location | Database |
|---|---|---|---|
| Database structure and constraints | pytest + SQLAlchemy | `tests/test_database.py` | real `RoseProductionDB`; behavioural checks inside a transaction that is always rolled back |
| REST API (auth, CRUD ×7, forecasting, statistics, original contract) | pytest + Flask test client | `tests/test_api_*.py` | real `RoseProductionDB`; isolated `TEST_` records deleted by id |
| GUI serving and secret exposure | pytest | `tests/test_gui_and_secrets.py` | – |
| GUI components and pages | Vitest + React Testing Library (jsdom) | `frontend/src/__tests__/` | none (fetch is mocked inside the tests only) |
| End-to-end workflows | Playwright (Chromium, desktop + Pixel 7) | `frontend/e2e/` | real API + MySQL, results verified with SQL |

**Data safety.** No test modifies or deletes a pre-existing row:

- tests create their own rows (`TEST_…`, `E2E_…`, test seasons in year 2098) and delete them by id;
- the Python session snapshots every row of the 7 tables first; the last test
  (`test_zz_production_data_guard.py`) fails if any pre-existing row was changed or deleted, or if a
  test row remains. Playwright does the same in `global-setup.js` / `global-teardown.js`;
- constraint tests run in a rolled-back transaction with savepoints.

Side effect: `AUTO_INCREMENT` counters advance (MySQL never reuses ids). A backup was taken before
the first run (`backups/RoseProductionDB_backup_20261122_090222.sql`).

## 2. How to run

```bash
source .venv/bin/activate && pip install -r requirements-dev.txt
python -m pytest                       # 256 tests
cd frontend && npm install && npm test # 72 tests
npx playwright install chromium        # once
npx playwright test                    # 26 tests — needs `python app.py` running
```

## 3. Results

> **Duplicate prevention (2026-11-23).** New suites: `tests/test_api_duplicates.py` (23),
> `frontend/src/__tests__/duplicates.test.jsx` (11, plus 1 in `crud.test.jsx`),
> `frontend/e2e/duplicates.spec.js` (3) and the DUP section of the audit harness (23 checks).
> Real database after the approved migration: pytest **256/256**, harness **178 PASS / 7 FINDING /
> 0 FAIL**, GUI 20/20; replica: Vitest 72/72, Playwright 26/26. Details and commands:
> [`docs/final-audit/DUPLICATE_DATA_PREVENTION_REPORT.md`](final-audit/DUPLICATE_DATA_PREVENTION_REPORT.md).

> **Final audit (2026-11-22, 10:42–11:21 −05:00).** The audit added 7 backend tests (226 → 233) and
> 3 GUI tests (57 → 60) and adjusted the E2E workflows to the new harvest rules. Latest results:
> pytest **233/233** on the real database (nobara-pc) and on the replica; Vitest **60/60** in the
> cloud workspace and on nobara-pc; Playwright **23/23** on the replica; independent HTTP+SQL audit
> **154 PASS + 8 findings** on the real system; backup/restore check PASS; GUI workflow of 30 steps on
> the real system PASS. Commands, times and exit codes: [`docs/final-audit/TEST_EXECUTION_RESULTS.md`](final-audit/TEST_EXECUTION_RESULTS.md).
> Sections 3.1–3.6 below are the results of the first delivery and are kept for history.

### 3.1 Summary

| Component | Tests executed | Passed | Failed | Status | Where it ran |
|---|---:|---:|---:|---|---|
| Database (`test_database.py` + data guard) | 38 | 38 | 0 | PASS | **real DB on nobara-pc** (MySQL 8.0.33), 2026-11-22 09:18 −05:00; also on the replica |
| API (`test_api_*.py`) | 174 | 174 | 0 | PASS | **real DB on nobara-pc**; also on the replica |
| GUI serving & secrets (`test_gui_and_secrets.py`) | 14 | 14 | 0 | PASS | **nobara-pc**; also in the cloud workspace |
| GUI components (Vitest) | 57 | 57 | 0 | PASS | cloud workspace (Node 22) |
| Integration / E2E (Playwright) | 23 | 23 | 0 | PASS | cloud workspace against the replica |
| Workflows A–D on the real system (driven step by step in the desktop app's browser) | 4 workflows + start/clean-up, 20 checks | 20 | 0 | PASS | **nobara-pc**, real API + real DB (§3.5) |

The *replica* is a MySQL 8.0.46 server in the development workspace loaded from the 2026-11-22 backup
of `RoseProductionDB` (identical tables, views, triggers, procedures and 49 rows). The pytest suite
gave the same result (226/226) on the replica and on the real database. Evidence:
`backups/pytest_real_db.txt` and `backups/pytest_real_db.xml` (JUnit, `hostname="nobara-pc"`,
`tests="226" failures="0" errors="0" skipped="0"`).

### 3.2 Backend test inventory (226)

| File | Tests | What is verified |
|---|---:|---|
| `test_database.py` | 37 | 7 InnoDB tables, 2 views (queryable), PKs, 7 FKs, 3 CHECK constraints, `unique_crop_forecast_date`, `idx_harvest_crop_date` (+ EXPLAIN uses it), 4 triggers (INSERT+UPDATE on Harvest and Forecast), no orphans in 7 relations, existing rows satisfy the rules, valid inserts accepted, FK violation (1452), delete of referenced parent (1451), quantity 0/−5 (3819), season end < start (3819), negative forecast (3819), harvest/forecast outside season on INSERT and UPDATE (1644), duplicate forecast (1062), NOT NULL (1048), AUTO_INCREMENT, 6 stored procedures (exist, `sp_production_by_variety` matches SQL, `sp_validate_variety` signals 1644) |
| `test_api_auth.py` | 43 | public `/`; 401 without key and with a wrong key on 10 protected endpoints; 200 with the key; non-ASCII key → 401 (not 500); unknown route; JSON 405; session login/read/write/logout; cookie HttpOnly + SameSite=Strict without the key; 403 without the GUI header; forged cookie rejected; throttling → 429; security headers, no CORS |
| `test_api_crud.py` | 98 | for each of the 7 resources: 404 on GET/PUT/DELETE of a missing id, invalid JSON, JSON array, missing fields, list count; full create → list → get → update → delete → 404 cycle per resource; invalid values (empty, too long, wrong type, area ≤ 0, quantity 0/−10/1.5/"many"/2³¹, invalid dates); invalid FKs; 409 when deleting a farm with lots, a lot/variety with crops, a crop or season with harvests; season shrink conflict; duplicate forecast 409; out-of-season harvest/forecast 400; filters |
| `test_api_forecasting.py` | 14 | moving average of the 3 previous harvests (independent calculation), preview does not write, only earlier harvests used, custom window, insufficient history 400, invalid window, date outside season, save → stored + duplicate 409 + pending until a real harvest exists, view endpoints, **reproduces all 7 stored forecasts** (TC-07), **summary view MAE/MAPE consistent with status view** (TC-08) |
| `test_api_stats.py` | 11 | dashboard counts = `COUNT(*)` per table, totals per variety/season/date = `SUM(quantity)`, forecast vs actual only from the view, grouping by 6 dimensions sums to the overall total, statistics for a filtered variety (total 3,900, avg 1,300, min 1,000, max 1,600), invalid `group_by`, upcoming seasons |
| `test_api_original_contract.py` | 8 | the 7 original GET endpoints keep their keys and nested keys; field types |
| `test_gui_and_secrets.py` | 14 | GUI build exists, `/app/` public, SPA fallback, asset caching, path traversal blocked (4 cases), API key absent from built assets and front-end sources, no Vite `.env` with secrets, `.env` git-ignored and not tracked, `.env.example` has no real value |
| `test_zz_production_data_guard.py` | 1 | every pre-existing row unchanged, no test row left |

### 3.3 GUI tests (Vitest, 57)

| File | Tests | What is verified |
|---|---:|---|
| `client.test.js` | 13 | same-origin credentials and no API key, CSRF header and JSON body on writes, error JSON → `ApiError` (status, code, details), readable messages for 403/404/409/500/503, 401 notifies the app, failed login is not a session expiry, network failure (status 0), GET de-duplication, query strings |
| `utils.test.js` | 8 | date/quantity/estimate rules, first failing rule per field, date inside season, formatting, season status, colour swatches |
| `components.test.jsx` | 11 | DataTable pagination, search, empty search, sorting asc/desc, empty state; loading/empty/error states with retry; ConfirmDialog confirm/cancel and server error; form modal blocks invalid submit, submits valid values, maps API field errors |
| `app.test.jsx` | 17 | login screen, wrong key message, key cleared from the form, nothing in local/session storage, empty key blocked, 401 → back to login, API down, sign out, dashboard figures, empty states, error + retry, navigation to all 8 sections from the sidebar, mobile menu open/close |
| `crud.test.jsx` | 8 | variety create/edit/delete through the API client, 409 delete reason shown, harvest out-of-season and quantity messages (nothing sent), harvest POST payload and server rule message, filters sent as query parameters, season end < start, forecast preview + save payloads, insufficient-history message |

### 3.4 End-to-end tests (Playwright, 23)

| Test | Steps | Expected | Actual | Status |
|---|---|---|---|---|
| Auth: wrong key | type a wrong key | "Invalid access key" | as expected | PASS |
| Auth: API without session | `GET /farms` | 401 | 401 | PASS |
| Auth: sign in / reload / sign out | sign in, check cookie, reload, sign out, reload | HttpOnly + Strict cookie, session survives reload, login after sign-out | as expected | PASS |
| Auth: key never exposed | sign in, inspect storage, HTML and every JS/CSS/JSON response | key absent | absent | PASS |
| Dashboard with real data | open dashboard | totals equal `SUM(quantity)` and `COUNT(*)` from MySQL, 5 panels and charts, no console errors | as expected | PASS |
| 7 modules list every row | open Farms … Forecasts | record counter = `COUNT(*)` of each table | as expected | PASS (×7) |
| Production analysis | group by season | total = `SUM(quantity)` | as expected | PASS |
| Harvest filter | filter by season | count = SQL count for that season | as expected | PASS |
| **Workflow A** | create `E2E_Variety_…` (Purple) → listed → SQL check → edit (Red) → SQL check → delete with confirmation → SQL check | row created, updated, removed | as expected | PASS |
| **Workflow B** | select first lot and first variety, planting date 2026-11-20, create → SQL check → reload page → still listed | crop persisted | as expected | PASS |
| **Workflow C** | select the new crop, the longest season, date = season end, quantity 777 → SQL check; then date = season end + 1 and quantity 0 | first saved; second shows "The date must be inside …" and "Quantity must be greater than zero", nothing saved (SQL) | as expected | PASS |
| Workflow C (edit) | move the harvest to a season that excludes its date | refused with the season message, row unchanged (SQL) | as expected | PASS |
| **Workflow D** | pick a real crop with ≥ 3 harvests and a free date in a season, *Calculate estimate* → value equals the independently computed average and 3 harvests are listed → *Save forecast* → SQL check (`method = 'Moving Average (3 records)'`) → row visible with status from `vw_forecast_status` → delete through the GUI | as described | as expected | PASS |
| Clean-up | delete the test harvest and crop through the GUI | rows removed (SQL) | as expected | PASS |
| Mobile: menu and pages | Pixel 7: menu hidden → open → navigate; tables as cards; no horizontal scroll; dialog fits | as described | as expected | PASS |
| Mobile: dashboard | Pixel 7 dashboard and forecasts | no horizontal scroll | as expected | PASS |
| Narrow window | 685 px wide, forecast wizard with a calculated result | dialog has no horizontal overflow | as expected (added after the real-system run revealed the overflow, see §3.5) | PASS |

Global teardown: *"Production data guard: all pre-existing rows unchanged, no test rows left."*

### 3.5 Workflows A–D on the real system (nobara-pc, 2026-11-22)

Executed through the GUI served by `python app.py` on nobara-pc, in the Claude desktop app's
browser pane (685 px wide, so the collapsed-menu layout was used). Sign-in was done by the user.
Each result was checked by reading the record back through the API (`fetch` from the signed-in
page → Flask → MySQL); direct SQL access to the container was not available from the automation
environment.

| Workflow | Steps and checks | Result |
|---|---|---|
| Start | dashboard shows 1 farm, 3 lots, 7 varieties, 8 crops, 20 harvests, 26,480 stems, 7 forecasts (1 evaluated · 6 pending) | PASS (1 check) |
| A — variety | create `E2E_REAL_Variety_A` / Purple → listed, toast, `GET /varieties/69` = Purple; edit to `…_Updated` / Red → `GET` shows the new values; delete with confirmation → toast, `GET /varieties/69` = 404, list back to 7 | PASS (5 checks) |
| B — crop | New crop: Lot A, Freedom, 2026-11-20 → toast, crop #57 listed and returned by `GET /crops?lot_id=1&variety_id=1` | PASS (2 checks) |
| C — harvest | crop #57, Normal Production 2026, 2026-11-21, 777 → harvest #83 stored; then Valentines Day 2026 + 2026-03-01 + quantity 0 → "The date must be inside Valentines Day 2026 (2026-02-01 to 2026-02-14)" and "Quantity must be greater than zero", nothing stored; direct API calls with the same data → 400 `DATE_OUTSIDE_SEASON`, 400 `VALIDATION_ERROR`, and 403 `CSRF_CHECK_FAILED` without the GUI header | PASS (6 checks) |
| D — forecast | crop #1, Valentines Day 2026, 2026-02-12 → estimate **1,550 stems** = (1500 + 1600 + 1550)/3 from harvests #20, #19, #3; saved as forecast #25 with method `Moving Average (3 records)`, status *Pending* (no harvest on that date), visible in the list and in `vw_forecast_summary` (8 total); deleted through the GUI → `GET /forecasts/25` = 404, summary back to 7 / 1 / 6, MAE 50, MAPE 3.13 | PASS (4 checks) |
| Clean-up | harvest #83 and crop #57 deleted through the GUI; final counts 1/3/7/8/3/20/7 (49 rows) and 26,480 stems, identical to the start | PASS (2 checks) |

Issue found and fixed during this run: at a 685 px window the result panel of the forecast wizard
overflowed horizontally. The panel now stacks below 900 px and its table scrolls; a Playwright test
(“Narrow window”) covers it.

### 3.6 Original project test cases (TC-01 … TC-15) re-checked

| ID | Re-checked by | Result |
|---|---|---|
| TC-01 Variety management | `test_variety_crud`, Workflow A | PASS |
| TC-02 Lot management | `test_lot_crud`, `test_lot_invalid_farm_is_400`, `test_invalid_foreign_key_rejected` | PASS |
| TC-03 Harvest management | `test_harvest_crud_and_filters`, quantity/season tests, Workflow C | PASS |
| TC-04 Season management | `test_season_crud`, `test_season_end_before_start_is_400`, DB CHECK test | PASS |
| TC-05 Historical queries | harvest filters (API + E2E), `/stats/production` | PASS |
| TC-06 Statistics | `test_statistics_for_filtered_variety`, `test_procedure_production_by_variety_matches_sql`; Freedom = 10,900 / 8 records in the data | PASS |
| TC-07 Forecast generation | `test_reproduces_existing_moving_average_forecasts`, Workflow D | PASS |
| TC-08 Forecast evaluation | `test_summary_view_matches_status_view` (1 evaluated, AE 50, MAPE 3.13 %) | PASS |
| TC-09 Referential integrity | FK/orphan tests, 409 delete tests | PASS |
| TC-10 Query performance | `test_index_used_for_crop_and_date_query` | PASS |
| TC-11 Constraints and triggers | CHECK, FK, UNIQUE and trigger tests (INSERT and UPDATE) | PASS |
| TC-12 Organization | table/view/key structure tests | PASS |
| TC-13 Backup and recovery | backup of 2026-11-22 restored into a separate server: 7 tables, 2 views, 4 triggers, 6 procedures, 49 rows | PASS |
| TC-14 Extensibility | every CRUD test inserts new rows without schema changes | PASS |
| TC-15 API access control | `test_api_auth.py` | PASS |

## 4. Known limitations

- **E2E automation location.** Playwright was executed in the development workspace (Node 22)
  against the replica, because Node.js is not installed on nobara-pc itself (Vitest and the
  production build were also run in the desktop app's Linux VM on nobara-pc, which cannot reach the
  API on the host). To run them on the
  real system: install Node ≥ 22.12, then `npm install && npx playwright install chromium && npx playwright test`.
- The data set is small (20 harvests); index and response-time checks are not load tests.
- Only one stored forecast can currently be evaluated (one matching harvest); MAE/MAPE describe that
  single case, not the general accuracy of the method.
- The moving average does not model trend or seasonality.
- GUI sessions use an in-memory signing key unless `SECRET_KEY` is set, so they end when the API restarts.
- The login throttle is per process and in memory (sufficient for a single local server).
- `AUTO_INCREMENT` values advance during tests (ids are never reused); this does not affect existing rows.
