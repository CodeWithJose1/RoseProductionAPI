# Duplicate Data Prevention Report

| | |
|---|---|
| Date | 2026-11-23 |
| System | `~/Documentos/DockerMySQL/RoseProductionAPI` on nobara-pc · MySQL 8.0.33 `RoseProductionDB` in `Mysqlcontainer` |
| Code | API **1.2.0** (was 1.1.0) · GUI bundle `index-57GBSTBk.js` (was `index-CLqLDtTO.js`) |
| Schema change | 4 UNIQUE constraints, **approved by the project owner on 2026-11-23**, applied 12:43 −05:00 with a backup first |
| Data safety | no existing row was modified, merged or deleted; every test row was created and removed by id; row counts before = after |
| Evidence | `docs/final-audit/evidence/duplicates/` (`host/` real database, `host_gui/` real GUI, `replica/` cloud replica) |

## 1. Root cause

Duplicates were possible because **nothing at any layer defined what "the same record" is**, except
for forecasts:

| Layer | Before (API 1.1.0, verified) |
|---|---|
| Database | Only `Forecast` had a UNIQUE key (`unique_crop_forecast_date`). Farm, Lot, RoseVariety, Crop, Season and Harvest accepted identical rows. |
| API | `POST`/`PUT` validated types, foreign keys and dates, then inserted. No duplicate check for Farm, Lot, RoseVariety, Crop or Season. Harvest had a check (added 2026-11-22) and Forecast relied on the DB key, but both were *check-then-insert* without serialization, so concurrent requests could pass the check together. |
| Text | Values were only trimmed; `"Lot  A"` and `"Lot A"` were stored as different values, and no comparison ignored case. |
| GUI | The submit button was disabled through React state only. A normal double click or double Enter sent one request, but two activations handled before React re-rendered (same task: fast repeated activation, synthetic/scripted clicks, `requestSubmit`) sent **two** POSTs, and the API stored both rows. |

Reproduced evidence (replica, before the fix):

- the same body POSTed twice → `201, 201` (and a case/space variant → `201`) for Farm, Lot, RoseVariety,
  Crop and Season (`evidence/duplicates/replica/before_after_sequential_api.json`);
- the GUI probe created rows 706/707 and 708/709 as identical pairs from one form
  (`gui_double_submit_probe_before.json`);
- with the new check but without serialization (locks disabled) and without DB keys, 8 identical
  concurrent POSTs under READ COMMITTED created several rows per round — up to 5 for Farm and
  RoseVariety, 4 for Lot and Season, 3 for Harvest, 2 for Crop
  (`concurrency_no_db_constraints_read_committed.json`).

The pre-existing duplicates (varieties 6/7, crops 7/8, see §5) date from before this work; with the
rules above they could have come from a repeated submission or a repeated script/SQL insert — the exact
origin cannot be determined from the data.

## 2. Uniqueness rules (business rules confirmed with the project owner)

Text comparison: surrounding spaces removed, internal runs of spaces collapsed, **case-insensitive**
(and the MySQL collation `utf8mb4_unicode_ci` is also accent-insensitive). Stored text is normalized the
same way (`"  Lot   A "` → `"Lot A"`); case is kept as typed.

| Entity | A duplicate is… | Legitimate (still accepted) | Enforced by |
|---|---|---|---|
| Farm | same **name + location** | same name in another location | API + DB `unique_farm_name_location (name, location)` |
| Lot | same **name inside the same farm** | same name in another farm | API + DB `unique_lot_farm_name (farm_id, name)` |
| RoseVariety | same **name** (any colour) — owner's decision | different name | API only (DB key blocked by existing 6/7, §6) |
| Crop | same **lot + variety + planting date** | same variety in the same lot on another date (new crop cycle) | API only (DB key blocked by existing 7/8, §6) |
| Season | same **name with an overlapping period** | same name for another period (e.g. next year); another name for the same dates | API (overlap) + DB `unique_season_name_dates (name, start_date, end_date)` (exact repeat) |
| Harvest | same **crop + day** — one daily record per crop (owner's decision, FR-03 "daily harvests") | same quantity another day; same day/quantity on another crop | API + DB `unique_harvest_crop_date (crop_id, harvest_date)` |
| Forecast | same **crop + date** — repeated generation is **rejected**, never overwritten or versioned (existing project design) | another date | API + DB `unique_crop_forecast_date` (pre-existing) |

Updates (`PUT`): a record may always keep its own identifying values (so the pre-existing duplicates
6/7 and 7/8 remain editable); changing them to another record's values is refused; an update never
creates a record.

## 3. Backend changes

| File | Change |
|---|---|
| `validators.py` | `name_text()`: trims and collapses internal whitespace (used for farm name/location, lot name, variety name/colour, season name) |
| `routes/common.py` | `normalized()`, `text_key()` (SQL `LOWER(TRIM(REGEXP_REPLACE(col,'[[:space:]]+',' ')))`), `lock_parent()`, `lock_table()`, `find_duplicate()` (locking read), `raise_duplicate()` |
| `routes/farms.py`, `lots.py`, `varieties.py`, `crops.py`, `seasons.py`, `harvests.py`, `forecasts.py` | `_ensure_unique_*()` called by `POST` and `PUT`: (1) skip when an edited record keeps its key; (2) take an exclusive row lock — the parent row (farm for lots, lot for crops, crop for harvests/forecasts) or the first row of the table (farms, varieties, seasons); (3) locking read for an equivalent row; (4) 409 `DUPLICATE_RECORD` with the existing record in the message and a field-level `details` entry |
| `routes/forecasts.py` | preview (`save:false`) returns `existing_forecast_id`; save of an existing crop/date → 409, the stored forecast is untouched |
| `errors.py` | MySQL 1062 on the new keys → 409 with a readable message and the form field; 1213 (deadlock) → 409 `CONCURRENT_UPDATE` |
| `models.py` | the 4 new `UniqueConstraint`s (model = schema, audit check SCH-03) |
| `app.py` | `API_VERSION = "1.2.0"` |

Why the lock: the duplicate check alone is not concurrency-safe. The row lock makes every writer of the
same group wait for the previous one; the locking read then sees the committed row. Measured on the
replica **without** the DB constraints (`concurrency_no_db_constraints_*.json`, 8 identical concurrent
POSTs × 5 rounds × 7 entities):

| Isolation | Locks enabled | Locks disabled |
|---|---|---|
| READ COMMITTED | always exactly 1 row; 7 × `409 DUPLICATE_RECORD` | duplicates created (2–5 rows in a round, every entity except Forecast, which has a DB key) |
| REPEATABLE READ (MySQL default) | always exactly 1 row; 7 × `409 DUPLICATE_RECORD` | 1 row, but 6–21 of 35 refusals were deadlocks (`409 CONCURRENT_UPDATE`) instead of a clear duplicate message |

With the approved DB constraints the database is a second, independent guarantee for Farm, Lot, Season,
Harvest and Forecast, also against direct SQL.

## 4. Frontend changes (React GUI)

| File | Change |
|---|---|
| `components/ResourceFormModal.jsx` | synchronous `useRef` lock: a second submit while one is in flight is ignored (also Enter/`requestSubmit`); button disabled with `aria-busy`; on error the dialog stays open with the typed values, the API message as banner and on the field; button re-enabled for retry |
| `components/CrudPage.jsx` | passes the loaded rows and the record being edited to the page validator; synchronous lock on the delete confirmation |
| `utils/validation.js` | `normalizeText`, `textKey`, `findClash`, `withDuplicate` |
| `pages/Varieties.jsx`, `Lots.jsx`, `Farms.jsx`, `Seasons.jsx`, `Crops.jsx`, `Harvests.jsx`, `Forecasts.jsx` | client-side duplicate hints mirroring §2 (immediate message, no request sent); payload text normalized |
| `pages/Forecasts.jsx` | Generate dialog: request lock; if the preview reports `existing_forecast_id`, a warning is shown and **Save forecast** is disabled |

Messages: "A rose variety with this name already exists." · "This lot already exists in the selected
farm." · "A farm with this name already exists at this location." · "A season with this name already
exists for an overlapping period." · "This variety is already planted in this lot on this date." ·
"This crop already has a harvest on this date. Edit that record instead." · "This forecast already
exists for the selected crop and date." The client hint only sees loaded rows; the API remains the
authority (shown when another user created the duplicate meanwhile).

## 5. Existing duplicate-looking records (read-only inspection, real database)

`scripts/audit/duplicate_inspection.py` (only `SELECT`, read-only transaction) on 2026-11-23 12:43 −05:00,
58 rows: Farm 2, Lot 6, RoseVariety 7, Crop 8, Season 5, Harvest 22, Forecast 8
(`evidence/duplicates/host/20261123_124335/duplicate_inspection.json`).

| Table | Columns | IDs | Values | Why it may be a duplicate | Assessment |
|---|---|---|---|---|---|
| RoseVariety | name, color | **6, 7** | Quicksand · Peach (both) | identical name and colour; violates the name rule | **Duplicate by the confirmed rule; manual review.** Variety 6 is used by crops 7 and 8; variety 7 has no crops |
| Crop | lot_id, variety_id, planting_date | **7, 8** | Lot C (3) · Quicksand (6) · 2026-11-15 | identical crop | **Duplicate by the confirmed rule; manual review.** Neither has harvests or forecasts |
| Farm | name, location | – | none (farms 1 and 203 differ) | – | – |
| Lot | farm_id, name | – | none | – | – |
| Season | name / overlap / dates | – | none (165 "Normal Production 2027" and 166 "Navidad" are new, distinct) | – | – |
| Harvest | crop_id, harvest_date | – | none; no same-day/same-quantity pairs either | – | – |
| Forecast | crop_id, forecast_date | – | none (protected by the existing key) | – | – |

None of these rows was modified, merged or deleted. See §8 for the optional clean-up that needs approval.

## 6. Database constraints

| Rule | Constraint before | Decision | Existing data | Status |
|---|---|---|---|---|
| Farm (name, location) | none | add `unique_farm_name_location` | 0 conflicts | **applied** |
| Lot (farm_id, name) | none | add `unique_lot_farm_name` | 0 conflicts | **applied** |
| Season (name, start, end) | none | add `unique_season_name_dates` | 0 conflicts | **applied** |
| Harvest (crop_id, harvest_date) | non-unique index only | add `unique_harvest_crop_date` | 0 conflicts | **applied** |
| Forecast (crop_id, forecast_date) | `unique_crop_forecast_date` | keep | – | unchanged |
| RoseVariety (name) | none | **not applied**: would fail on varieties 6/7 | 1 conflict | API only; needs clean-up approval |
| Crop (lot_id, variety_id, planting_date) | none | **not applied**: would fail on crops 7/8 | 1 conflict | API only; needs clean-up approval |

Migration (`database/migrations/2026-11-23_add_unique_constraints.sql`, run by
`scripts/db/add_unique_constraints.sh` through `scripts/apply_duplicate_fix.sh`), real database,
2026-11-23 12:43:30 −05:00 (`evidence/duplicates/host/apply_20261123_124330.log`):

1. backup `backups/before_unique_constraints_20261123_124330.sql` (28,364 bytes, SHA-256 `fd17743f…89baba`);
2. row counts before: Farm 2, Lot 6, RoseVariety 7, Crop 8, Season 5, Harvest 22, Forecast 8;
3. duplicate pre-check: 0 groups for each of the 4 rules;
4. 4 × `ALTER TABLE … ADD CONSTRAINT … UNIQUE …, ALGORITHM=INPLACE, LOCK=NONE` → added;
5. verification: 5 UNIQUE constraints present; row counts after identical.

**Side effect (disclosed).** MySQL removed the index `farm_id` on `Lot`, which it had created
implicitly for the foreign key `Lot_ibfk_1`, because the new `unique_lot_farm_name (farm_id, name)` can
serve the foreign key. No data is affected and the foreign key is still enforced (pytest and the audit
FK tests passed afterwards). The revert procedure (re-create `farm_id` before dropping the new index) is
in the migration file. `database/schema.sql` was updated to the new structure; the replica was aligned
and its schema fingerprint now equals the real one (`66c606e0…36601`).

Also: `idx_harvest_crop_date` and `unique_harvest_crop_date` now have the same columns; the optimizer
uses either (EXPLAIN: `range` on `unique_harvest_crop_date`). The old index is redundant but was kept
(dropping it would be a further change needing approval; it costs only some write overhead).

The migration was tested first on the replica: normal run, second run (all "already present, skipped")
and abort path with an injected duplicate (stopped with exit 2, nothing added) —
`evidence/duplicates/replica/unique_constraints_migration_*.log`, `migration_abort_path_test.log`.

## 7. API behaviour before and after

Same requests twice (and a case/space variant), database copy **without** the new constraints, so the
result shows the API alone (`before_after_sequential_api.json`):

| Entity | Before (1.1.0) | After (1.2.0) |
|---|---|---|
| Farm | 201, 201, 201 | 201, 409, 409 |
| Lot | 201, 201, 201 | 201, 409, 409 |
| RoseVariety | 201, 201, 201 | 201, 409, 409 |
| Crop | 201, 201 | 201, 409 |
| Season | 201, 201, 201 | 201, 409, 409 |
| Harvest | 201, 409 | 201, 409 |
| Forecast | 201, 409 | 201, 409 |

Every 409 has `code: "DUPLICATE_RECORD"`, a message naming the existing record and `details` for the
form field; the row count does not change. A rejected insertion never returns 201.

## 8. Changes that still require approval (not executed)

1. **Clean-up of the pre-existing duplicates** — the data owner should decide, e.g. remove variety 7
   (no crops) and one of crops 7/8 (no harvests/forecasts), or rename them if they are meant to be
   different. Nothing was changed.
2. After that clean-up, optionally:
   `ALTER TABLE RoseVariety ADD CONSTRAINT unique_variety_name UNIQUE (name);` and
   `ALTER TABLE Crop ADD CONSTRAINT unique_crop_lot_variety_date UNIQUE (lot_id, variety_id, planting_date);`
   (the API already enforces both rules; these would also protect against direct SQL).
3. Optionally drop the redundant `idx_harvest_crop_date`.

## 9. Tests executed

### Real system (nobara-pc, real `RoseProductionDB`, after the migration)

`bash scripts/apply_duplicate_fix.sh` (run by the user, 12:43:30–12:44:22 −05:00), which ran
`scripts/audit/run_duplicate_fix_host.sh` against the new API on port 7004
(`evidence/duplicates/host/20261123_124335/`):

| Step | Exit | Result |
|---|---:|---|
| migration (backup, pre-check, 4 constraints, verification) | 0 | constraints added, row counts unchanged |
| 03 UNIQUE constraints | 0 | Farm, Forecast, Harvest, Lot, Season |
| 04 duplicate inspection (read-only) | 0 | §5 |
| 05 pytest | 0 | **256 passed, 0 failed, 0 skipped** (24.1 s) |
| 06 audit harness (HTTP + SQL) | 0 | **185 checks: 178 PASS, 7 FINDING, 0 FAIL**; incl. DUP-DB, DUP-01…08 (each rule, SQL counts before/after, legitimate variants accepted), DUP-R1…R7 (8 truly concurrent identical requests per entity → exactly 1 row), NFR-02-20 (DB refuses a second harvest for a crop/day: 1062), FR-01-01, FR-03-04, GUARD-01 (every pre-existing row unchanged, no test row left) |
| 07 duplicate inspection again | 0 | unchanged |

GUI on the real database (browser pane, port 7004, 17:45–17:48 UTC;
`evidence/duplicates/host_gui/gui_duplicates_real_system.json`, 2 screenshots): **20 steps, 20 PASS** —
duplicate hints for every entity without a request, API 409 for a duplicate the page could not see with
the typed values kept and no success toast, one POST for repeated activations, legitimate variants
accepted (same lot name in another farm, same season name next year, new crop cycle, same-quantity
harvests on another day or crop), forecast duplicate warning with Save disabled, edit keeping its own
name accepted, all 16 test rows deleted, snapshot of all 7 tables identical to the start.

### Cloud replica (schema fingerprint equal to the real database) and nobara-pc VM

`evidence/duplicates/replica/regression/run_summary.txt` (11 steps, all exit 0) and
`frontend` re-run on nobara-pc's desktop-app VM (Node 22.23.2, 17:37–17:38 UTC):

| Suite | Result |
|---|---|
| pytest (incl. 23 new tests in `tests/test_api_duplicates.py`) | 256 / 256 |
| Vitest (incl. 11 new tests in `duplicates.test.jsx`, 1 new and 1 adapted in `crud.test.jsx`) | 72 / 72 (cloud) · 72 / 72 (nobara-pc VM) |
| Production build | byte-identical to the shipped `dist` (cloud and nobara-pc VM) |
| Playwright (incl. 3 new tests in `e2e/duplicates.spec.js`, verified with SQL) | 26 / 26, production-data guard satisfied |
| axe-core (11 views) | 0 violations |
| Audit harness | 178 PASS, 7 FINDING, 0 FAIL |
| pip-audit / npm audit | 0 known vulnerabilities |
| GUI probe after the fix | 1 POST and 1 row for every activation pattern (`gui_double_submit_probe_after.json`) |
| Concurrency experiments, before/after sequential test | §3, §7 |

The 7 FINDINGs are the known data-quality items (DQ-03…09: harvests 16–18 and forecast 7 before
planting; varieties 6/7; crops 7/8; and three checks with zero rows) — reported, not failures.

### Coverage of the requested scenarios

| # | Scenario | Where |
|---|---|---|
| 1–2 | valid insert, exact duplicate | pytest `test_*_duplicates`, harness DUP-01…07, GUI RG-01…19 |
| 3 | same name with different legitimate attributes | lot in another farm, farm in another location, season next year, crop new date, harvest another day/crop |
| 4–5 | whitespace and case variants | pytest, harness DUP-01…05, GUI RG-02/03/07/09/11 |
| 6 | two identical requests rapidly | `test_rapid_identical_requests` (201, 409, 409, 409, 409), GUI RG-06 |
| 7 | concurrent requests | `test_concurrent_identical_posts_create_one_record[7 entities]`, harness DUP-R1…R7 (real server) |
| 8–9 | update keeping / taking unique values | pytest, harness DUP-08, GUI RG-05 |
| 10 | duplicate through the GUI | GUI RG-*, Playwright `duplicates.spec.js`, Vitest |
| 11 | duplicate directly through the API | harness, pytest, GUI RG-17 |
| 12 | MySQL record counts before/after | every pytest and harness case; migration log |
| Harvest | legitimate repeats preserved | `test_harvest_duplicates_and_legitimate_repeats`, DUP-06L, RG-16 |
| Forecast | reject, no overwrite | `test_forecast_duplicates_are_rejected_not_overwritten`, DUP-07G, RG-19 |

### Corrected tests (with reason)

- `test_api_crud.py::test_variety_duplicate_names_allowed` → `test_variety_duplicate_names_rejected`:
  the business rule changed on 2026-11-23 (owner's decision).
- `test_api_auth.py`: expects API version 1.2.0.
- `crud.test.jsx` "duplicate-day conflict (409)": now uses a date the page cannot see (the client
  check correctly blocks visible duplicates before the request); a new test covers the visible case.
- `final_audit.py`: FR-01-01 now expects 409; NFR-02-20 now expects the database to refuse (1062);
  PERF-01/02 accept either index on (crop_id, harvest_date); new section DUP.

## 10. Regression of the requirements

FR-01, FR-02, FR-03, FR-04, FR-08, FR-09 and NFR-02, NFR-05, NFR-06 checks of the audit harness all
PASS on the real database after the change; the full CRUD matrix (35 operations), security probes and
production-data guard are unchanged. NFR-02 improves (a second harvest for one crop and day is now
refused by the database); it stays PARTIAL because the schema still accepts harvest/forecast dates
before a crop's planting date (existing rows 16, 17, 18, forecast 7) and `Lot.area` has no CHECK.

## 11. Remaining limitations

- RoseVariety and Crop rules are enforced by the API (with locks) but not by the database until the
  clean-up in §8 is approved; rows inserted directly with SQL can still duplicate them.
- `lock_table()` serializes writers through the first row of the table; on an empty table there is
  nothing to lock (the DB keys still protect Farm and Season; RoseVariety would rely on the check alone).
- Client-side hints see only the rows loaded in the page; the API is the authority.
- Accent-insensitivity comes from the MySQL collation; the client hint compares case-insensitively but
  not accent-insensitively (the API still refuses such a duplicate).
- The GUI on the real system was driven with DOM events; real-input browser tests ran on the replica.
- **Still to do on your machine:** stop the verification API on port 7004
  (`kill $(cat docs/final-audit/evidence/duplicates/host/api_7004.pid)`) and restart the usual API on
  port 7003 (Ctrl+C, `python app.py`) so that it runs version 1.2.0.
