# Professor's Project Advance Checklist

Evaluation of the three criteria exactly as written by the professor, with the evidence gathered in
the final audit of 2026-11-22. Each verdict is based on executed tests on the real system
(nobara-pc, MySQL 8.0.33 `RoseProductionDB`, API `http://127.0.0.1:7003`, GUI `/app/`), not on
earlier results alone.

| # | Criterion | Final verdict |
|---|---|---|
| A | Database Design and Implemented in MySQL / SQLite / Other | **MET — implemented in MySQL 8.0.33** (one schema weakness documented; fix awaiting approval) |
| B | APIDB CRUD operations partially implemented (100%) — Test Cases Passed | **MET — 100 % (35 / 35 operations), all test cases passed** |
| C | GUI Design partially implemented (100%) and integrated with APIDB | **MET — 100 % (46 / 46 verified GUI items), integrated with the real API and MySQL** |

---

## A. Database Design and Implemented in MySQL / SQLite / Other

**DBMS and database.** MySQL **8.0.33** (Docker image `mysql:8.0.33`, container `Mysqlcontainer`,
port 3306, data bind-mounted from `/home/jose/Documentos/DockerMySQL/Mysql-data`), database
**`RoseProductionDB`**, InnoDB, `utf8mb4_unicode_ci`, `sql_mode` strict
(`STRICT_TRANS_TABLES`, `ONLY_FULL_GROUP_BY`, …). Read from the running server (`ENV-03`,
`logs/01_docker_status.log`, `logs/05_original_test_connection.log`).

**Design (verified with `information_schema`, `SCH-01…03`).**

```
Farm 1 ──< Lot 1 ──< Crop >── 1 RoseVariety
                      │ 1
          ┌───────────┴───────────┐
          ▼ *                     ▼ *
       Harvest >── 1 Season 1 ──< Forecast
```

| Object | Implementation |
|---|---|
| Tables (7) | Farm, Lot, RoseVariety, Crop, Season, Harvest, Forecast — each with an `AUTO_INCREMENT` integer PK |
| Foreign keys (7) | `Lot_ibfk_1` Lot→Farm · `Crop_ibfk_1` Crop→Lot · `Crop_ibfk_2` Crop→RoseVariety · `Harvest_ibfk_1` Harvest→Crop · `Harvest_ibfk_2` Harvest→Season · `Forecast_ibfk_1` Forecast→Crop · `Forecast_ibfk_2` Forecast→Season — all NOT NULL, `RESTRICT` |
| CHECK (3) | `Harvest_chk_1` quantity > 0 · `Season_chk_1` end_date ≥ start_date · `Forecast_chk_1` estimated_quantity ≥ 0 |
| UNIQUE (1) | `unique_crop_forecast_date (crop_id, forecast_date)` |
| Indexes | PKs; FK indexes (`farm_id`, `lot_id`, `variety_id`, `season_id`); `idx_harvest_crop_date (crop_id, harvest_date)` — used by history and forecasting queries (`PERF-01`, `PERF-02`) |
| Triggers (4) | `validate_harvest_season`, `validate_harvest_season_update`, `validate_forecast_season`, `validate_forecast_season_update` — `SIGNAL 45000` when a date is outside its season |
| Views (2) | `vw_forecast_status` (forecast vs actual harvest, status, absolute error), `vw_forecast_summary` (counts, MAE, MAPE) |
| Procedures (6) | `sp_production_by_variety`, `sp_get_variety_production`, `sp_add_variety_production`, `sp_check_variety`, `sp_validate_variety`, `sp_safe_variety_query` |

**Integrity (executed on the real DB inside rolled-back transactions).** FK inserts with missing
parents → 1452; deleting/updating referenced parents → 1451; the three CHECKs → 3819; duplicate
forecast → 1062; the four triggers → 1644; NOT NULL; INT range — all refused (`NFR-02-01…19`), no row
left (`NFR-02-21`). No orphan rows in the 7 relationships (`DQ-01`); every existing row satisfies
the declared rules (`DQ-02`).

**Backend connection and persistence.** Flask-SQLAlchemy + PyMySQL connect with the `.env`
configuration (`test_connection.py`: "Connection successful! … 8.0.33"); `GET /` reports the
database; every CRUD write of the audit was read back with SQL (`API_CRUD_TEST_MATRIX.md`).

**Schema = models = documentation.** `models.py` matches MySQL column by column (types, nullability,
PK, FK, named constraints) — `SCH-03`: no mismatch. `docs/DATABASE.md` matches the schema; it was
updated with the current row counts (50) and the audit findings. Schema fingerprint unchanged by the
whole audit (`NFR-05-01`).

**Normalization.** 3NF for the documented dependencies (analysis in
`NON_FUNCTIONAL_REQUIREMENTS_TRACEABILITY.md`, NFR-03).

**Backup and recovery.** Dump + restore into a separate database, identical structure, data and views
(`backup_restore.json`, `result: PASS`).

**What is not perfect (does not change the verdict, must be disclosed).** The schema accepts two
harvests for the same crop and day, which duplicates rows of `vw_forecast_status` (HIGH, mitigated in
the API with 409), and accepts harvest/forecast dates before the crop's planting date (existing rows
16, 17, 18 and forecast 7). The definitive fix is a schema change proposed in `docs/DATABASE.md §10`,
**not applied** because it needs your approval. This is why NFR-02 is PARTIAL.

**Verdict A: MET.** The database is designed (7 related entities, keys, constraints, triggers, views,
procedures) and implemented in MySQL, connected to the backend and holding the real data.

---

## B. APIDB CRUD operations partially implemented (100%) — Test Cases Passed

| Entity | GET all | GET by ID | POST | PUT | DELETE |
|---|---|---|---|---|---|
| Farm | PASS | PASS | PASS | PASS | PASS |
| Lot | PASS | PASS | PASS | PASS | PASS |
| RoseVariety | PASS | PASS | PASS | PASS | PASS |
| Crop | PASS | PASS | PASS | PASS | PASS |
| Season | PASS | PASS | PASS | PASS | PASS |
| Harvest | PASS | PASS | PASS | PASS | PASS |
| Forecast | PASS | PASS | PASS | PASS | PASS |

- **Calculation:** 35 required operations (7 entities × 5) implemented and verified on the real system
  with SQL read-back → **35 / 35 = 100 %**. Update is `PUT` (`PATCH` → 405, verified).
- **Invalid input / conflicts / not found:** 26 negative cases, all with the expected 400/404/409 and no
  database change (`NEG-DB`).
- **Authentication:** 105 requests with no/wrong/empty key on every CRUD operation → 105 × 401, no
  database change; valid key and GUI session accepted; CSRF and logout checked (`SEC-01…08`).
- **Test cases:** pytest **233/233** on the real DB (0 failed, 0 skipped); audit harness 154 PASS,
  0 FAIL (8 data/schema findings); same results on the replica; Playwright 23/23 on the replica.
- Details: `API_CRUD_TEST_MATRIX.md`, `TEST_EXECUTION_RESULTS.md`.

**Verdict B: MET — 100 %, test cases passed.**

---

## C. GUI Design partially implemented (100%) and integrated with APIDB

- **GUI implemented:** React 19 + Vite SPA served by Flask at `/app/`: Login, Dashboard, Production
  analysis, Farms, Lots, Rose varieties, Crops, Seasons, Harvests, Forecasts (+ Generate forecast).
- **Integrated with the real API and MySQL:** on the real system the GUI created, edited and deleted
  records of all 7 entities; each change was confirmed by an independent API read of MySQL; the
  dashboard moved 26,480 → 31,480 → 26,480 stems with the test data; a record created through the API
  appeared in the GUI and was deleted from it; 36 GUI writes, 0 outside the test records
  (`GUI_INTEGRATION_TEST_REPORT.md`, `evidence/gui_real_system_run.json`).
- **Validation and errors:** client rules (season dates, quantity) and API refusals (409 duplicate
  harvest, 400 insufficient history, 409 delete in use) shown in the forms and dialogs.
- **Forecasting integrated:** generate (preview with formula and harvests used) → save → register the
  actual harvest → Evaluated with absolute error, for a future date (2097) and a past date.
- **No mock data:** all figures come from the API; fixtures exist only in the test folder.
- **Automated GUI tests:** Vitest 60/60 (cloud and nobara-pc), Playwright 23/23 (replica), axe 0
  violations on 11 views.
- **Calculation:** 10 screens + 28 GUI CRUD cells (7 entities × create/read/update/delete) + 8
  integrated behaviours = **46 / 46 = 100 %**.

**Verdict C: MET — 100 %, workflows demonstrated on the real system.**

---

## Overall position with respect to the 15 official requirements

Functional 9/9 PASS (100 %); non-functional 5/6 PASS, NFR-02 PARTIAL (83.33 %); overall
**14 / 15 = 93.33 %**. The three Project Advance criteria are met; the project should not be
presented as "100 % compliant with all requirements" until the schema change for NFR-02 is approved
and applied (or the professor accepts the API-level mitigation).
