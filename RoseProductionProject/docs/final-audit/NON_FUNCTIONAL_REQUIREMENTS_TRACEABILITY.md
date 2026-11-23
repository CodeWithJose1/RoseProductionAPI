# Non-Functional Requirements Traceability — NFR-01 … NFR-06

Audit date: 2026-11-22 · Real system: nobara-pc, MySQL 8.0.33 `RoseProductionDB` (50 rows at the
time of the audit: Farm 1, Lot 3, RoseVariety 7, Crop 8, Season 3, Harvest 20, Forecast 8), Flask
API 1.1.0. Evidence references (H-AUD, H-PYT, H-GUI, C-REG) are defined in
[FUNCTIONAL_REQUIREMENTS_TRACEABILITY.md](FUNCTIONAL_REQUIREMENTS_TRACEABILITY.md#evidence-sources).

The requirement texts are the official ones, copied without changes. The specification defines
**no numeric performance threshold**; none was invented.

## Non-Functional Requirements Matrix

| ID | Original Requirement | Verification Method | Actual Measurement or Evidence | Result | Status |
|---|---|---|---|---|---|
| NFR-01 | Database queries must return production and forecasting information efficiently for the expected amount of data in the project. | (1) 8 representative SQL queries (history by crop+dates, history by dates only, statistics by variety/lot/season, moving-average history, both forecast views), 30 timed runs each + `EXPLAIN`/`EXPLAIN ANALYZE`, on the **real DB**; (2) 13 API read endpoints incl. forecast preview, 15 timed HTTP runs each, **real system**; (3) the same on a replica scaled to 100,020 harvests (×5,000) to see how the design behaves beyond the project's volume | **Real DB (20 harvests, 8 forecasts):** SQL medians 0.19–1.36 ms, highest p95 2.81 ms. History by crop+date and the moving-average history (`Q1`, `Q6`) use `idx_harvest_crop_date` (`type=range`, `PERF-01`, `PERF-02`); forecast views use PK/FK indexes for every join except the 3-row `Season` scan. API medians 2.98–32.19 ms, highest p95 52.0 ms (`GET /harvests`); `POST /forecasts/generate` preview median 17.2 ms. All 13 endpoints answered 200 (`PERF-03`). **Scale replica (100,020 harvests):** Q1 0.28 ms and Q6 0.32 ms (index), Q2 date-only 35 ms (full scan), statistics by variety 164 ms, forecast views ≤ 15 ms; API `/stats/dashboard` 703 ms, `/stats/production` 271 ms, unpaginated `GET /harvests` 3.0 s / 25 MB | No threshold exists. Evaluated against the requirement's own terms — production and forecasting information, at the project's expected data volume: every query returns correct results in milliseconds and the access paths used for history and forecasting are indexed. Two weaknesses appear only far above the project's volume (date-only filter scans the table; the full harvest list is not paginated) → LOW findings | **PASS** (basis stated; no numeric threshold invented) |
| NFR-02 | Database operations must enforce constraints and referential integrity to prevent inconsistent production records. | 21 constraint probes executed **on the real DB inside transactions that were rolled back** (`NFR-02-01…21`); data-quality queries over all existing rows (`DQ-01…09`); API negative tests; reproduction of the view effect on the replica (rolled back) | **Enforced by MySQL:** FK on insert (Lot→Farm, Crop→Variety, Harvest→Season, Forecast→Crop) → 1452; RESTRICT on delete/update of referenced parents → 1451; CHECK `Harvest_chk_1` (quantity 0 and < 0), `Season_chk_1`, `Forecast_chk_1` → 3819; `UNIQUE unique_crop_forecast_date` → 1062; 4 triggers (INSERT/UPDATE of Harvest and Forecast outside the season) → 1644; NOT NULL; INT range; no rows left (`NFR-02-21`); no orphans (`DQ-01`); existing rows satisfy all declared rules (`DQ-02`). **Not prevented by the schema (findings):** (a) two harvests for the same crop and day are accepted; `vw_forecast_status` then returns 2 rows for one forecast (`NFR-02-20`, real DB, rolled back) and on the replica the summary changes from 7 forecasts / MAE 50.00 / MAPE 3.13 to 8 / 750.00 / 726.56 (`cloud_regression/duplicate_harvest_view_effect_replica.json`) — HIGH; (b) harvests/forecasts dated before the crop's planting date are accepted — the real data contains harvests 16, 17, 18 and forecast 7 (`DQ-03`, `DQ-04`) — MEDIUM; (c) `Lot.area` has no CHECK (`DQ-09`: no bad rows) — LOW | Referential integrity and every declared constraint are enforced. Some inconsistent production records are still accepted by the database itself; the API now refuses them (409 `DUPLICATE_RECORD`, 400 `DATE_BEFORE_PLANTING`, 400 `FUTURE_HARVEST_DATE`), but direct SQL writes bypass the API. Closing the gap needs a schema change (unique key on `Harvest(crop_id, harvest_date)`, optionally a CHECK on `Lot.area` and planting-date triggers) that was **not applied** because it requires explicit approval | **PARTIAL** |
| NFR-03 | The database structure must be organized and normalized to reduce unnecessary data redundancy and maintain data consistency. | `information_schema` inspection on the real DB (`SCH-01…03`: 7 InnoDB tables, 2 views, keys, constraints; SQLAlchemy models vs MySQL: columns, types, nullability, PK, FK, named constraints); functional-dependency review of every table; duplicate-data queries (`DQ-07`, `DQ-08`) | One table per entity, surrogate single-column PKs (2NF holds trivially); no non-key attribute depends on another non-key attribute: lot and variety of a harvest reached via `Crop`, never copied; totals, averages, forecast status and errors computed in queries/views, not stored; `Harvest.season_id` is not derivable from `harvest_date` because seasons overlap (Normal Production 2026 contains the other two), so it is not a transitive dependency → **3NF** for the documented dependencies. Models match the schema (`SCH-03`: no mismatch). Redundant *data* found: varieties 6/7 identical (Quicksand, Peach), crops 7/8 identical (lot 3, variety 6, 2026-11-15) — the schema has no natural-key uniqueness for them (LOW) | The structure is organized and normalized; redundancy in two pairs of rows is a data-entry issue the schema does not block, reported for the data owner | **PASS** |
| NFR-04 | The database must support backup and recovery of the stored production information. | `scripts/audit/backup_restore_check.sh` on nobara-pc: `mysqldump --single-transaction --routines --triggers` of `RoseProductionDB`, restore into a **new** database, structural and row-by-row comparison, both views compared | 2026-11-22 10:42:57 −05:00: dump 28,080 bytes, SHA-256 `d5b5ce9c329bc18c…62bec4a`, 0.18 s; restore into `RoseProductionDB_AuditRestore_20261122_104257` 0.683 s; source and restored: 7 tables, 2 views, 4 triggers, 6 routines, 50 rows; tables, views, triggers, routines, constraints, indexes, columns, the data of all 7 tables and the output of both views **equal**; `"result": "PASS"` (`evidence/backup_restore.json`, `logs/10_backup_restore.log`). Production DB never written | Backup and recovery demonstrated end to end. Backups are manual (`scripts/backup_db.sh`); no schedule exists (not required by the text) | **PASS** |
| NFR-05 | The database design must allow additional rose varieties, cultivation lots, harvest records, and seasons to be added without requiring a redesign of the entire database. | Schema fingerprint (SHA-256 of tables, columns, keys, constraints, indexes, triggers, views, routines) before and after the audit inserted and managed new varieties, lots, crops, seasons, harvests and forecasts on the **real DB** (`NFR-05-01`); GUI run on the real system; scale replica | Fingerprint `9707b6b1b1a69e41…bd893bd` identical before and after (`NFR-05-01`); 2 farms, 3 lots, 6 varieties, 3 crops, 5 seasons, 8 harvests and 2 forecasts created and removed by the harness, 1 farm/1 lot/2 varieties/1 crop/2 seasons/4 harvests/3 forecasts by the GUI run, all through the existing schema; replica loaded with 100,020 harvests, 58 crops, 2,007 forecasts with the same schema; no residue (`GUARD-01`, GUI-25) | New records of every kind are added and managed without any schema change | **PASS** |
| NFR-06 | Database operations through the API must provide controlled access to the available CRUD operations. | Security probes on the **real system** (`SEC-01…16`): every protected operation with no key / wrong key / empty key, valid key, GUI session flow, CSRF, logout, CORS, injection probes, malformed JSON, body size, bundle and path-traversal secret checks, headers; browser storage check (GUI-26); pytest `test_api_auth` (44); secret scans of the project folder | 105 protected requests (7 resources × 5 CRUD operations × 3 bad credentials) → 105 × 401 and **no table changed** (`SEC-01`, `SEC-02`); valid key reads all 7 resources (`SEC-03`); wrong GUI login refused (`SEC-04`); session cookie `HttpOnly`, `SameSite=Strict`, does not contain the key (`SEC-05`); session write without `X-Requested-With: RoseProductionGUI` → 403 (`SEC-06`), with it → accepted (`SEC-07`); logout ends the session (`SEC-08`); no `Access-Control-Allow-Origin` (`SEC-09`); SQL-injection probes harmless, SQL text stored literally (`SEC-10.1–10.4`, `SEC-11`); malformed JSON → JSON 400 without trace (`SEC-12`); > 1 MiB → 413 (`SEC-13`); API key absent from served HTML/JS/CSS (`SEC-14`), `.env` not served (`SEC-15`); `nosniff`, `DENY`, `no-store` (`SEC-16`); browser: no localStorage/sessionStorage keys, no JS-readable cookie, 401 without session, 403 without the GUI header (GUI-26); secret scan of 170 files: no `API_KEY`/`DB_PASSWORD` value outside `.env`; `.env` not tracked by git | Access to every CRUD operation is authenticated and controlled; credentials never reach the browser. Authorization is a single shared key (no per-user roles), which the requirement does not ask for — noted as a limitation | **PASS** |

## Result

| Status | Count |
|---|---:|
| PASS | 5 (NFR-01, NFR-03, NFR-04, NFR-05, NFR-06) |
| PARTIAL | 1 (NFR-02) |
| FAIL | 0 |
| NOT VERIFIABLE | 0 |

**Non-functional compliance = 5 / 6 × 100 = 83.33 %.**

## What would turn NFR-02 into PASS

1. Approve and apply (after a backup) the unique key
   `ALTER TABLE Harvest ADD CONSTRAINT unique_crop_harvest_date UNIQUE (crop_id, harvest_date);`
   — precondition `DQ-06` (no existing duplicates) was true on 2026-11-22.
2. Optionally: `CHECK (area > 0)` on `Lot`, and triggers that refuse harvest/forecast dates before
   the crop's planting date.
3. The data owner corrects harvests 16, 17, 18 and forecast 7 (change the crop or the date); the audit
   did not modify existing rows.
4. Re-run `scripts/audit/run_host_audit.sh`.

Proposed SQL and the reasoning are in [docs/DATABASE.md §10](../DATABASE.md#10-final-audit-findings-2026-11-22--no-schema-change-applied).
None of it was executed.

## Measurement detail (NFR-01, real DB, 30 runs per query)

| Query | Median ms | p95 ms | Plan (main table) |
|---|---:|---:|---|
| Q1 harvest history: crop + date range | 1.361 | 2.543 | `range` on `idx_harvest_crop_date` |
| Q2 harvest history: date range only | 0.997 | 2.051 | `ALL` (20 rows) |
| Q3 production statistics by variety | 1.128 | 2.808 | `ALL` on Harvest + `eq_ref` PK joins |
| Q4 production by lot | 0.248 | 0.292 | `ref` on `idx_harvest_crop_date` |
| Q5 production by season | 0.219 | 0.251 | `ref` on `season_id` |
| Q6 moving-average history (last 3 before a date) | 0.192 | 0.241 | `range` on `idx_harvest_crop_date`, backward index scan |
| Q7 `vw_forecast_status` | 0.449 | 0.486 | PK/FK joins, harvest via `idx_harvest_crop_date` |
| Q8 `vw_forecast_summary` | 0.435 | 0.618 | as Q7 |

API (15 HTTP runs each, real system): `/farms` 10.3 ms median · `/lots` 14.6 · `/varieties` 13.5 ·
`/crops` 19.7 · `/seasons` 13.4 · `/harvests` 32.2 (p95 52.0) · `/forecasts` 11.8 ·
`/forecasts/status` 3.0 · `/forecasts/summary` 3.3 · `/stats/dashboard` 29.4 ·
`/stats/production?group_by=variety` 12.4 · filtered harvests 6.4 · `POST /forecasts/generate`
(preview) 17.2. Source: `evidence/audit_results.json → sections.performance`; scale figures:
`evidence/scale_test_replica.json`.

## Addendum 2026-11-23

Step 1 above was approved and applied: `unique_harvest_crop_date` (plus `unique_farm_name_location`,
`unique_lot_farm_name`, `unique_season_name_dates`) exists in the real database since 2026-11-23
12:43 −05:00, and NFR-02-20 now passes (the database refuses a second harvest for the same crop and
day with error 1062). NFR-02 remains **PARTIAL** until steps 2–3 are decided (pre-planting dates and
`Lot.area` are still not constrained by the schema). See
[`DUPLICATE_DATA_PREVENTION_REPORT.md`](DUPLICATE_DATA_PREVENTION_REPORT.md).
