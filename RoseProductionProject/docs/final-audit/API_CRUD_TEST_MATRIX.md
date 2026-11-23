# API CRUD Test Matrix — seven entities

Run on the **real system** (nobara-pc, `http://127.0.0.1:7003`, MySQL 8.0.33 `RoseProductionDB`) by
`scripts/audit/final_audit.py`, run id `a820b749`, 2026-11-22 10:42:50–10:42:57 −05:00, with the
backend `X-API-Key` read from `.env` on that machine (never printed). Every created row carries the
tag `AUDIT_a820b749_…`, lives in isolated seasons of the year 2001 (past) or 2097 (future) and was
deleted by id; the guard `GUARD-01` then confirmed that every pre-existing row was unchanged and that
no audit row remained. The same harness gave the same result on the replica at 11:05
(`evidence/cloud_regression/audit_results_replica_final.json`).

Raw data: `evidence/audit_results.json → sections.crud_matrix` (68 rows) and `checks`.

## 1. Summary matrix (required operations)

| Entity | GET all | GET by ID | POST | PUT (update) | DELETE | Operations verified |
|---|---|---|---|---|---|---:|
| Farm `/farms` | PASS (200) | PASS (200) | PASS (201) | PASS (200) | PASS (200) | 5/5 |
| Lot `/lots` | PASS (200) | PASS (200) | PASS (201) | PASS (200) | PASS (200) | 5/5 |
| RoseVariety `/varieties` | PASS (200) | PASS (200) | PASS (201) | PASS (200) | PASS (200) | 5/5 |
| Crop `/crops` | PASS (200) | PASS (200) | PASS (201) | PASS (200) | PASS (200) | 5/5 |
| Season `/seasons` | PASS (200) | PASS (200) | PASS (201) | PASS (200) | PASS (200) | 5/5 |
| Harvest `/harvests` | PASS (200) | PASS (200) | PASS (201) | PASS (200) | PASS (200) | 5/5 |
| Forecast `/forecasts` | PASS (200) | PASS (200) | PASS (201) | PASS (200) | PASS (200) | 5/5 |
| **Total** | | | | | | **35/35** |

**API CRUD completion = 35 / 35 × 100 = 100 %.** Denominator: 7 entities × 5 required operations
(GET all, GET by ID, POST, PUT/PATCH, DELETE). A cell is PASS only if the HTTP status was the expected
one **and** the database effect was confirmed with SQL (POST/PUT: the row read back with the sent
values; DELETE: `COUNT(*)` for the id = 0 and a following `GET` → 404).

- **Update method.** Updates are implemented with `PUT` (full replacement; all fields required).
  `PATCH` is not implemented: on the real system `PATCH /farms/1` (session + GUI header, empty body)
  answered `405 {"code": "METHOD_NOT_ALLOWED"}` and farm 1 was unchanged (2026-11-22 11:21 −05:00,
  browser pane). The requirement "PUT or PATCH" is met by `PUT`.
- **GET all.** The CRUD cell checks the status; the list content was verified separately: list counts
  equal the SQL counts read by `test_read.py` at 10:42 (1/3/7/8/3/20/8) and shown by the GUI; every
  variety/lot/season filter of `GET /harvests` on the full data set equals an independent SQL count
  (`FR-05-07`); `GET` by id of the first real row of every table equals SQL (`REAL-GET`).

## 2. Endpoint inventory (from `routes/*.py`, all protected except `/`, `/auth/*`, `/app/*`)

| Resource | GET list (filters) | GET by id | POST | PUT | DELETE | Extra |
|---|---|---|---|---|---|---|
| Farm | `/farms` | `/farms/{id}` (lots, total area) | `/farms` | `/farms/{id}` | `/farms/{id}` (409 with lots) | – |
| Lot | `/lots` (`farm_id`) | `/lots/{id}` | `/lots` | `/lots/{id}` | `/lots/{id}` (409 with crops) | – |
| RoseVariety | `/varieties` | `/varieties/{id}` | `/varieties` | `/varieties/{id}` | `/varieties/{id}` (409 with crops) | – |
| Crop | `/crops` (`lot_id`, `variety_id`) | `/crops/{id}` | `/crops` | `/crops/{id}` (409 `PLANTING_DATE_CONFLICT`) | `/crops/{id}` (409 with harvests/forecasts) | – |
| Season | `/seasons` | `/seasons/{id}` | `/seasons` | `/seasons/{id}` (409 `SEASON_RANGE_CONFLICT`) | `/seasons/{id}` (409 in use) | – |
| Harvest | `/harvests` (`crop_id`, `season_id`, `variety_id`, `lot_id`, `date_from`, `date_to`) | `/harvests/{id}` | `/harvests` | `/harvests/{id}` | `/harvests/{id}` | – |
| Forecast | `/forecasts` (same filters) | `/forecasts/{id}` (+ evaluation) | `/forecasts` | `/forecasts/{id}` | `/forecasts/{id}` | `/forecasts/status`, `/forecasts/summary`, `POST /forecasts/generate` |
| Statistics | `/stats/production`, `/stats/dashboard` | | | | | |
| Auth / public | `GET /` (public), `POST /auth/login`, `POST /auth/logout`, `GET /auth/status`, GUI files `/app/…` | | | | | |

## 3. Invalid-input, conflict and not-found tests (real system)

26 negative cases, all PASS; after them `NEG-DB` confirmed that the row counts of the 7 tables were
exactly those expected (no partial write):

| Entity | Case | Expected → actual |
|---|---|---|
| Farm | missing fields `{}` | 400 → 400 |
| Farm | wrong type (`name: 5`) | 400 → 400 |
| Farm | GET / PUT missing id 999999999 | 404 → 404 (×2) |
| Farm | DELETE with a lot | 409 → 409 |
| Lot | invalid FK farm | 400 → 400 |
| Lot | area 0 | 400 → 400 |
| Lot | DELETE missing id | 404 → 404 |
| Lot | DELETE with a crop | 409 → 409 |
| RoseVariety | name of 101 characters | 400 → 400 |
| RoseVariety | DELETE with a crop | 409 → 409 |
| Crop | invalid FK variety | 400 → 400 |
| Crop | impossible date 2001-02-30 | 400 → 400 |
| Crop | DELETE with harvests | 409 → 409 |
| Season | end before start | 400 → 400 |
| Season | DELETE with harvests | 409 → 409 |
| Harvest | quantity 0 | 400 → 400 |
| Harvest | quantity 1.5 | 400 → 400 |
| Harvest | date outside the season | 400 → 400 |
| Harvest | invalid FK crop | 400 → 400 |
| Harvest | second harvest same crop and day | 409 → 409 |
| Harvest | malformed JSON body | 400 → 400 |
| Forecast | negative estimate | 400 → 400 |
| Forecast | duplicate crop + date | 409 → 409 |
| Forecast | invalid FK season | 400 → 400 |
| Forecast | PUT missing id | 404 → 404 |

Further API rule checks on the real system: harvest before planting → 400 `DATE_BEFORE_PLANTING`
(`FR-03-02`); future harvest → 400 `FUTURE_HARVEST_DATE` (`FR-03-03`); invalid references on
update → 400 (`FR-09-01`); season shrink → 409 (`FR-04-01`); body > 1 MiB → 413 (`SEC-13`).

## 4. Authentication tests (real system)

| Test | Result |
|---|---|
| `SEC-01` 7 resources × 5 operations (GET list, GET id, POST, PUT, DELETE) × 3 bad credentials (no key, wrong key, empty key) | 105 / 105 → 401 |
| `SEC-02` database after the 105 refused requests | unchanged |
| `SEC-03` valid key on the 7 resources | 200 |
| `SEC-04` … `SEC-08` GUI session: wrong key refused, HttpOnly + SameSite=Strict cookie without the key, CSRF header required (403 without), accepted with it, logout ends the session | PASS |
| `SEC-09` … `SEC-16` CORS absent, injection probes, malformed JSON without trace, 413, key absent from the GUI bundles, `.env` not served, security headers | PASS |

pytest `test_api_auth.py` (44 tests) repeats these checks through the Flask test client on the real
DB (H-PYT, 233/233).

## 5. API behaviour vs GUI expectations

The GUI calls exactly these endpoints (request log in `evidence/gui_real_system_run.json`):
`POST/PUT/DELETE` on all seven resources, the harvest/forecast filters, `POST /forecasts/generate`
with `save:false` then `save:true`, `/stats/production`, `/stats/dashboard`. The API error format
`{"error", "code", "details"}` is what the GUI displays: the field-level `details` appear under the
form field (e.g. the 409 duplicate harvest on *Harvest date*), the `error` sentence in the dialog
banner (e.g. the 409 on deleting a farm with lots). Vitest (`client.test.js`, 13 tests) checks that the
client sends no API key, adds the CSRF header on writes, turns error JSON into an error with status,
code and details, handles 401 (expired session) and reports network failures.

## 6. Individual test evidence (68 rows, in execution order)

| # | Entity | Operation | Method + endpoint | Test input | Expected | Actual | Database effect (read back with SQL) | Time (ms) | Result |
|---:|---|---|---|---|---:|---:|---|---:|---|
| 1 | Farm | POST | `POST /farms` | `{"name": "AUDIT_a820b749_Farm", "location": "Audit location"}` | 201 | 201 | `{"farm_id": 129, "name": "AUDIT_a820b749_Farm", "location": "Audit location"}` | 12.1 | PASS |
| 2 | Farm | GET all | `GET /farms` | — | 200 | 200 | read only | 5.1 | PASS |
| 3 | Farm | GET by id | `GET /farms/129` | — | 200 | 200 | read only | 7.3 | PASS |
| 4 | Farm | PUT | `PUT /farms/129` | `{"name": "AUDIT_a820b749_Farm2", "location": "Updated"}` | 200 | 200 | `{"farm_id": 129, "name": "AUDIT_a820b749_Farm2", "location": "Updated"}` | 12.1 | PASS |
| 5 | Lot | POST | `POST /lots` | `{"farm_id": 129, "name": "AUDIT_a820b749_Lot", "area": 2.5}` | 201 | 201 | `{"lot_id": 122, "farm_id": 129, "name": "AUDIT_a820b749_Lot", "area": 2.5}` | 14.1 | PASS |
| 6 | Lot | GET all | `GET /lots` | — | 200 | 200 | read only | 9.1 | PASS |
| 7 | Lot | GET by id | `GET /lots/122` | — | 200 | 200 | read only | 14.3 | PASS |
| 8 | Lot | PUT | `PUT /lots/122` | `{"farm_id": 129, "name": "AUDIT_a820b749_Lot2", "area": 3.75}` | 200 | 200 | `{"lot_id": 122, "farm_id": 129, "name": "AUDIT_a820b749_Lot2", "area": 3.75}` | 24.5 | PASS |
| 9 | RoseVariety | POST | `POST /varieties` | `{"name": "AUDIT_a820b749_Variety", "color": "Purple"}` | 201 | 201 | `{"variety_id": 132, "name": "AUDIT_a820b749_Variety", "color": "Purple"}` | 13.3 | PASS |
| 10 | RoseVariety | GET all | `GET /varieties` | — | 200 | 200 | read only | 5.8 | PASS |
| 11 | RoseVariety | GET by id | `GET /varieties/132` | — | 200 | 200 | read only | 6.6 | PASS |
| 12 | RoseVariety | PUT | `PUT /varieties/132` | `{"name": "AUDIT_a820b749_Variety2", "color": "Red"}` | 200 | 200 | `{"variety_id": 132, "name": "AUDIT_a820b749_Variety2", "color": "Red"}` | 16.5 | PASS |
| 13 | Crop | POST | `POST /crops` | `{"lot_id": 122, "variety_id": 132, "planting_date": "2000-06-01"}` | 201 | 201 | `{"crop_id": 108, "lot_id": 122, "variety_id": 132, "planting_date": "2000-06-01"}` | 29.9 | PASS |
| 14 | Crop | GET all | `GET /crops` | — | 200 | 200 | read only | 17.8 | PASS |
| 15 | Crop | GET by id | `GET /crops/108` | — | 200 | 200 | read only | 8.9 | PASS |
| 16 | Crop | PUT | `PUT /crops/108` | `{"lot_id": 122, "variety_id": 132, "planting_date": "2000-05-01"}` | 200 | 200 | `{"planting_date": "2000-05-01"}` | 15.8 | PASS |
| 17 | Season | POST | `POST /seasons` | `{"name": "AUDIT_a820b749_Season", "start_date": "2001-02-01", "end_date": "2001-02-14"}` | 201 | 201 | `{"season_id": 102, "name": "AUDIT_a820b749_Season", "start_date": "2001-02-01", "end_date": "2001-02-14"}` | 11.3 | PASS |
| 18 | Season | GET all | `GET /seasons` | — | 200 | 200 | read only | 8.6 | PASS |
| 19 | Season | GET by id | `GET /seasons/102` | — | 200 | 200 | read only | 10.5 | PASS |
| 20 | Season | PUT | `PUT /seasons/102` | `{"name": "AUDIT_a820b749_Season2", "start_date": "2001-02-01", "end_date": "2001-02-28"}` | 200 | 200 | `{"season_id": 102, "name": "AUDIT_a820b749_Season2", "start_date": "2001-02-01", "end_date": "2001-02-28"}` | 40.8 | PASS |
| 21 | Harvest | POST | `POST /harvests` | `{"crop_id": 108, "season_id": 102, "harvest_date": "2001-02-05", "quantity": 1234}` | 201 | 201 | `{"harvest_id": 149, "crop_id": 108, "season_id": 102, "harvest_date": "2001-02-05", "quantity": 1234}` | 37.3 | PASS |
| 22 | Harvest | GET all | `GET /harvests` | — | 200 | 200 | read only | 15.7 | PASS |
| 23 | Harvest | GET by id | `GET /harvests/149` | — | 200 | 200 | read only | 5.2 | PASS |
| 24 | Harvest | PUT | `PUT /harvests/149` | `{"crop_id": 108, "season_id": 102, "harvest_date": "2001-02-06", "quantity": 1300}` | 200 | 200 | `{"harvest_id": 149, "crop_id": 108, "season_id": 102, "harvest_date": "2001-02-06", "quantity": 1300}` | 26.8 | PASS |
| 25 | Forecast | POST | `POST /forecasts` | `{"crop_id": 108, "season_id": 102, "forecast_date": "2001-02-20", "estimated_quantity": 1500.5, "method": "Aud…` | 201 | 201 | `{"forecast_id": 44, "crop_id": 108, "season_id": 102, "forecast_date": "2001-02-20", "estimated_quantity": 1500.5, "method": "Audit manual"}` | 40.4 | PASS |
| 26 | Forecast | GET all | `GET /forecasts` | — | 200 | 200 | read only | 50.1 | PASS |
| 27 | Forecast | GET by id | `GET /forecasts/44` | — | 200 | 200 | read only | 22.3 | PASS |
| 28 | Forecast | PUT | `PUT /forecasts/44` | `{"crop_id": 108, "season_id": 102, "forecast_date": "2001-02-21", "estimated_quantity": 0, "method": "Audit ma…` | 200 | 200 | `{"forecast_id": 44, "crop_id": 108, "season_id": 102, "forecast_date": "2001-02-21", "estimated_quantity": 0.0, "method": "Audit manual v2"}` | 50.7 | PASS |
| 29 | Farm | POST missing fields | `POST /farms` | `{}` | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 5.3 | PASS |
| 30 | Farm | POST invalid type | `POST /farms` | `{"name": 5, "location": "x"}` | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 5.7 | PASS |
| 31 | Farm | GET missing id | `GET /farms/999999999` | — | 404 | 404 | no change (verified by NEG-DB: all 7 table counts unchanged) | 9.1 | PASS |
| 32 | Farm | PUT missing id | `PUT /farms/999999999` | `{"name": "x", "location": "y"}` | 404 | 404 | no change (verified by NEG-DB: all 7 table counts unchanged) | 8.7 | PASS |
| 33 | Farm | DELETE in use (has lot) | `DELETE /farms/129` | — | 409 | 409 | no change (verified by NEG-DB: all 7 table counts unchanged) | 16.8 | PASS |
| 34 | Lot | POST invalid FK farm | `POST /lots` | `{"farm_id": 999999999, "name": "x", "area": 1}` | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 10.7 | PASS |
| 35 | Lot | POST area <= 0 | `POST /lots` | `{"farm_id": 129, "name": "x", "area": 0}` | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 5.6 | PASS |
| 36 | Lot | DELETE missing id | `DELETE /lots/999999999` | — | 404 | 404 | no change (verified by NEG-DB: all 7 table counts unchanged) | 10.3 | PASS |
| 37 | Lot | DELETE in use (has crop) | `DELETE /lots/122` | — | 409 | 409 | no change (verified by NEG-DB: all 7 table counts unchanged) | 13.1 | PASS |
| 38 | RoseVariety | POST too long | `POST /varieties` | `{"name": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx…` | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 2.5 | PASS |
| 39 | RoseVariety | DELETE in use (has crop) | `DELETE /varieties/132` | — | 409 | 409 | no change (verified by NEG-DB: all 7 table counts unchanged) | 12.2 | PASS |
| 40 | Crop | POST invalid FK variety | `POST /crops` | `{"lot_id": 122, "variety_id": 999999999, "planting_date": "2000-01-01"}` | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 7.1 | PASS |
| 41 | Crop | POST invalid date | `POST /crops` | `{"lot_id": 122, "variety_id": 132, "planting_date": "2001-02-30"}` | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 4.5 | PASS |
| 42 | Crop | DELETE in use (has harvest) | `DELETE /crops/108` | — | 409 | 409 | no change (verified by NEG-DB: all 7 table counts unchanged) | 16.7 | PASS |
| 43 | Season | POST end before start | `POST /seasons` | `{"name": "x", "start_date": "2001-05-10", "end_date": "2001-05-01"}` | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 3.4 | PASS |
| 44 | Season | DELETE in use (has harvest) | `DELETE /seasons/102` | — | 409 | 409 | no change (verified by NEG-DB: all 7 table counts unchanged) | 18.4 | PASS |
| 45 | Harvest | POST quantity 0 | `POST /harvests` | `{"crop_id": 108, "season_id": 102, "harvest_date": "2001-02-07", "quantity": 0}` | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 4.3 | PASS |
| 46 | Harvest | POST quantity not integer | `POST /harvests` | `{"crop_id": 108, "season_id": 102, "harvest_date": "2001-02-07", "quantity": 1.5}` | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 3.3 | PASS |
| 47 | Harvest | POST outside season | `POST /harvests` | `{"crop_id": 108, "season_id": 102, "harvest_date": "2001-03-15", "quantity": 5}` | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 9.2 | PASS |
| 48 | Harvest | POST invalid FK crop | `POST /harvests` | `{"crop_id": 999999999, "season_id": 102, "harvest_date": "2001-02-07", "quantity": 5}` | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 8.3 | PASS |
| 49 | Harvest | POST duplicate crop+day | `POST /harvests` | `{"crop_id": 108, "season_id": 102, "harvest_date": "2001-02-06", "quantity": 5}` | 409 | 409 | no change (verified by NEG-DB: all 7 table counts unchanged) | 22.2 | PASS |
| 50 | Forecast | POST negative estimate | `POST /forecasts` | `{"crop_id": 108, "season_id": 102, "forecast_date": "2001-02-22", "estimated_quantity": -1, "method": "x"}` | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 4.0 | PASS |
| 51 | Forecast | POST duplicate crop+date | `POST /forecasts` | `{"crop_id": 108, "season_id": 102, "forecast_date": "2001-02-21", "estimated_quantity": 1, "method": "x"}` | 409 | 409 | no change (verified by NEG-DB: all 7 table counts unchanged) | 16.2 | PASS |
| 52 | Forecast | POST invalid FK season | `POST /forecasts` | `{"crop_id": 108, "season_id": 999999999, "forecast_date": "2001-02-22", "estimated_quantity": 1, "method": "x"…` | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 13.3 | PASS |
| 53 | Forecast | PUT missing id | `PUT /forecasts/999999999` | `{}` | 404 | 404 | no change (verified by NEG-DB: all 7 table counts unchanged) | 5.9 | PASS |
| 54 | Harvest | POST invalid JSON | `POST /harvests` | — | 400 | 400 | no change (verified by NEG-DB: all 7 table counts unchanged) | 4.4 | PASS |
| 55 | Forecast | DELETE | `DELETE /forecasts/44` | — | 200 | 200 | row count for the id after DELETE: 0 | 14.5 | PASS |
| 56 | Forecast | GET after DELETE | `GET /forecasts/44` | — | 404 | 404 | read only | 6.0 | PASS |
| 57 | Harvest | DELETE | `DELETE /harvests/149` | — | 200 | 200 | row count for the id after DELETE: 0 | 15.5 | PASS |
| 58 | Harvest | GET after DELETE | `GET /harvests/149` | — | 404 | 404 | read only | 4.1 | PASS |
| 59 | Crop | DELETE | `DELETE /crops/108` | — | 200 | 200 | row count for the id after DELETE: 0 | 19.6 | PASS |
| 60 | Crop | GET after DELETE | `GET /crops/108` | — | 404 | 404 | read only | 7.5 | PASS |
| 61 | Season | DELETE | `DELETE /seasons/102` | — | 200 | 200 | row count for the id after DELETE: 0 | 24.7 | PASS |
| 62 | Season | GET after DELETE | `GET /seasons/102` | — | 404 | 404 | read only | 8.2 | PASS |
| 63 | Lot | DELETE | `DELETE /lots/122` | — | 200 | 200 | row count for the id after DELETE: 0 | 14.4 | PASS |
| 64 | Lot | GET after DELETE | `GET /lots/122` | — | 404 | 404 | read only | 4.8 | PASS |
| 65 | RoseVariety | DELETE | `DELETE /varieties/132` | — | 200 | 200 | row count for the id after DELETE: 0 | 17.0 | PASS |
| 66 | RoseVariety | GET after DELETE | `GET /varieties/132` | — | 404 | 404 | read only | 7.2 | PASS |
| 67 | Farm | DELETE | `DELETE /farms/129` | — | 200 | 200 | row count for the id after DELETE: 0 | 13.6 | PASS |
| 68 | Farm | GET after DELETE | `GET /farms/129` | — | 404 | 404 | read only | 6.8 | PASS |

`row count for the id after DELETE: 0` = `SELECT COUNT(*) … WHERE <id> = :id` returned 0.
