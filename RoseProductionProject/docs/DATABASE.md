# Database — RoseProductionDB

MySQL 8.0.33 running in the Docker container `Mysqlcontainer`. Storage engine InnoDB,
character set `utf8mb4` / collation `utf8mb4_unicode_ci`.

The API and GUI were built on the existing schema without changing it. The only schema change
since then is the **approved migration of 2026-11-23** that added four UNIQUE constraints for
duplicate prevention (§11; `database/migrations/2026-11-23_add_unique_constraints.sql`). The structure below was
read from the backup taken on 2026-11-22 (`mysqldump --routines --triggers`); a schema-only copy is
in [`database/schema.sql`](../database/schema.sql).

## 1. Entity–relationship model

```
Farm 1 ──< Lot 1 ──< Crop >── 1 RoseVariety
                      │ 1
          ┌───────────┴───────────┐
          ▼ *                     ▼ *
       Harvest >── 1 Season 1 ──< Forecast
```

| Relationship | Cardinality | Foreign key |
|---|---|---|
| Farm – Lot | 1 : N | `Lot.farm_id → Farm.farm_id` (`Lot_ibfk_1`) |
| Lot – Crop | 1 : N | `Crop.lot_id → Lot.lot_id` (`Crop_ibfk_1`) |
| RoseVariety – Crop | 1 : N | `Crop.variety_id → RoseVariety.variety_id` (`Crop_ibfk_2`) |
| Crop – Harvest | 1 : N | `Harvest.crop_id → Crop.crop_id` (`Harvest_ibfk_1`) |
| Season – Harvest | 1 : N | `Harvest.season_id → Season.season_id` (`Harvest_ibfk_2`) |
| Crop – Forecast | 1 : N | `Forecast.crop_id → Crop.crop_id` (`Forecast_ibfk_1`) |
| Season – Forecast | 1 : N | `Forecast.season_id → Season.season_id` (`Forecast_ibfk_2`) |

All foreign keys use the default `ON DELETE/UPDATE RESTRICT`: a parent row that still has
children cannot be deleted (MySQL error 1451). The API checks this first and answers
`409 RECORD_IN_USE` with the number of dependent rows.

## 2. Tables

| Table | Column | Type | Constraints |
|---|---|---|---|
| **Farm** | farm_id | INT AUTO_INCREMENT | PK |
| | name | VARCHAR(100) | NOT NULL |
| | location | VARCHAR(150) | NOT NULL |
| | | | `UNIQUE unique_farm_name_location (name, location)` (2026-11-23) |
| **Lot** | lot_id | INT AUTO_INCREMENT | PK |
| | farm_id | INT | NOT NULL, FK → Farm |
| | name | VARCHAR(100) | NOT NULL |
| | area | DECIMAL(10,2) | NOT NULL |
| | | | `UNIQUE unique_lot_farm_name (farm_id, name)` (2026-11-23; also serves the FK) |
| **RoseVariety** | variety_id | INT AUTO_INCREMENT | PK |
| | name | VARCHAR(100) | NOT NULL (no DB key; the API refuses a second variety with the same name since 2026-11-23 — varieties 6 and 7 already share one) |
| | color | VARCHAR(50) | NOT NULL |
| **Crop** | crop_id | INT AUTO_INCREMENT | PK |
| | lot_id | INT | NOT NULL, FK → Lot |
| | variety_id | INT | NOT NULL, FK → RoseVariety |
| | planting_date | DATE | NOT NULL |
| **Season** | season_id | INT AUTO_INCREMENT | PK |
| | name | VARCHAR(100) | NOT NULL |
| | start_date | DATE | NOT NULL |
| | end_date | DATE | NOT NULL, `Season_chk_1: end_date >= start_date` |
| **Harvest** | harvest_id | INT AUTO_INCREMENT | PK |
| | crop_id | INT | NOT NULL, FK → Crop |
| | season_id | INT | NOT NULL, FK → Season |
| | harvest_date | DATE | NOT NULL (must lie inside the season — triggers) |
| | quantity | INT | NOT NULL, `Harvest_chk_1: quantity > 0` (stems) |
| **Forecast** | forecast_id | INT AUTO_INCREMENT | PK |
| | crop_id | INT | NOT NULL, FK → Crop |
| | season_id | INT | NOT NULL, FK → Season |
| | forecast_date | DATE | NOT NULL (must lie inside the season — triggers) |
| | estimated_quantity | DECIMAL(12,2) | NOT NULL, `Forecast_chk_1: estimated_quantity >= 0` |
| | method | VARCHAR(100) | NOT NULL |
| | | | `UNIQUE unique_crop_forecast_date (crop_id, forecast_date)` |

### Data at the time of the audit (backup 2026-11-22)

| Table | Rows |
|---|---:|
| Farm | 1 |
| Lot | 3 |
| RoseVariety | 7 |
| Crop | 8 |
| Season | 3 |
| Harvest | 20 |
| Forecast | 7 |
| **Total** | **49** |

Production: 26,480 stems in 20 harvest records. Freedom: 8 records, 10,900 stems,
average 1,362.50, minimum 1,000, maximum 1,600 (same figures as TC-06).

## 3. Indexes

| Table | Index | Columns | Purpose |
|---|---|---|---|
| all | PRIMARY | `<table>_id` | primary keys |
| Harvest | `idx_harvest_crop_date` | (crop_id, harvest_date) | history of a crop by date range (forecasting, filters) |
| Harvest | `unique_harvest_crop_date` (UNIQUE, 2026-11-23) | (crop_id, harvest_date) | one harvest per crop and day; same columns as the index above, used interchangeably by the optimizer |
| Forecast | `unique_crop_forecast_date` | (crop_id, forecast_date) | one forecast per crop and date |
| Farm | `unique_farm_name_location` (UNIQUE, 2026-11-23) | (name, location) | no repeated farm |
| Lot | `unique_lot_farm_name` (UNIQUE, 2026-11-23) | (farm_id, name) | lot names unique per farm; also used by the FK `Lot_ibfk_1` (MySQL dropped the former implicit `farm_id` index) |
| Season | `unique_season_name_dates` (UNIQUE, 2026-11-23) | (name, start_date, end_date) | no exact repeated season |
| Crop / Harvest / Forecast | `lot_id`, `variety_id`, `season_id` | FK columns | created by InnoDB for the foreign keys |

`EXPLAIN` on the 2026-11-22 data:

```sql
EXPLAIN SELECT * FROM Harvest
WHERE crop_id = 1 AND harvest_date BETWEEN '2026-02-01' AND '2026-02-28';
-- type=range  key=idx_harvest_crop_date  rows=5  Extra=Using index condition

EXPLAIN SELECT * FROM Harvest WHERE harvest_date BETWEEN '2026-02-01' AND '2026-02-28';
-- type=ALL (full scan): the index cannot be used without its leftmost column crop_id
```

## 4. Triggers

All four are `BEFORE` triggers that read the season of the new row and raise
`SIGNAL SQLSTATE '45000'` (MySQL error **1644**) when the date is outside `[start_date, end_date]`.

| Trigger | Event | Message |
|---|---|---|
| `validate_harvest_season` | BEFORE INSERT ON Harvest | `Harvest date is outside the season period` |
| `validate_harvest_season_update` | BEFORE UPDATE ON Harvest | `Harvest date is outside the season period` |
| `validate_forecast_season` | BEFORE INSERT ON Forecast | `Forecast date is outside the season period` |
| `validate_forecast_season_update` | BEFORE UPDATE ON Forecast | `Forecast date is outside the season period` |

The API performs the same check before writing so that the user gets a message that names the
season and its dates; the triggers remain the final guarantee (tested directly in
`tests/test_database.py`). Because the triggers only run when a harvest/forecast row is written,
the API also refuses to shrink a season's dates if existing harvests or forecasts would end up
outside it (`409 SEASON_RANGE_CONFLICT`).

## 5. Views

### `vw_forecast_status`

One row per forecast with the actual harvest of the **same crop on the same date** (LEFT JOIN):

| Column | Meaning |
|---|---|
| forecast_id, crop_id, variety, season, forecast_date, estimated_quantity, method | forecast data |
| actual_quantity | `Harvest.quantity` of the matching harvest, `NULL` if none |
| forecast_status | `Evaluated` if a matching harvest exists, otherwise `Pending` |
| absolute_error | `ABS(estimated_quantity − actual_quantity)`, `NULL` when pending |

### `vw_forecast_summary`

| Column | Meaning |
|---|---|
| total_forecasts, evaluated_forecasts, pending_forecasts | counts |
| MAE | mean absolute error of evaluated forecasts (2 decimals) |
| MAPE | mean absolute percentage error of evaluated forecasts (2 decimals) |

On the 2026-11-22 data: 7 forecasts, 1 evaluated (forecast 1: estimate 1,550, actual 1,600),
6 pending, MAE = 50.00, MAPE = 3.13 %. A single evaluated forecast is not a general measure of
accuracy.

The API exposes both views (`GET /forecasts/status`, `GET /forecasts/summary`) and the GUI uses
them for the forecast status, the "Actual" and "Abs. error" columns and the summary panel.

## 6. Stored procedures (found in the schema)

Read-only analytics procedures; the API does not depend on them.

| Procedure | Parameters | Result |
|---|---|---|
| `sp_production_by_variety` | IN name | records, total, average for the variety |
| `sp_get_variety_production` | IN name, OUT total | total stems |
| `sp_add_variety_production` | IN name, INOUT total | adds the variety's total to the accumulator |
| `sp_check_variety` | IN name | totals, or a message if the variety does not exist |
| `sp_validate_variety` | IN name | totals, or `SIGNAL 45000 'Variety does not exist'` |
| `sp_safe_variety_query` | IN name | as above, with an EXIT HANDLER that returns a message |

```sql
CALL sp_production_by_variety('Freedom');   -- Freedom | 8 | 10900 | 1362.50
CALL sp_get_variety_production('Freedom', @t); SELECT @t;   -- 10900
```

## 7. Normalization

Every non-key attribute depends on the whole key of its own table and on nothing else
(e.g. the variety of a harvest is reached through `Harvest → Crop → RoseVariety`, never copied).
Derived data (totals, averages, forecast status) is computed in queries and views instead of
being stored, so the schema is in third normal form for the documented dependencies. This is a
design review, not a formal proof.

## 8. Example queries

```sql
-- Harvest history with variety, lot and season (FR-05)
SELECT h.harvest_id, h.harvest_date, rv.name AS variety, l.name AS lot, s.name AS season, h.quantity
FROM Harvest h
JOIN Crop c        ON c.crop_id = h.crop_id
JOIN RoseVariety rv ON rv.variety_id = c.variety_id
JOIN Lot l         ON l.lot_id = c.lot_id
JOIN Season s      ON s.season_id = h.season_id
WHERE h.harvest_date BETWEEN '2026-02-01' AND '2026-02-14'
ORDER BY h.harvest_date;

-- Statistics per variety (FR-06)
SELECT rv.name, COUNT(*) AS records, SUM(h.quantity) AS total,
       ROUND(AVG(h.quantity), 2) AS average, MIN(h.quantity) AS minimum, MAX(h.quantity) AS maximum
FROM Harvest h JOIN Crop c USING (crop_id) JOIN RoseVariety rv USING (variety_id)
GROUP BY rv.variety_id, rv.name ORDER BY total DESC;

-- Production per season
SELECT s.name, SUM(h.quantity) AS total FROM Harvest h JOIN Season s USING (season_id)
GROUP BY s.season_id, s.name;
-- Valentines Day 2026 14930 · Mothers Day 2026 8400 · Normal Production 2026 3150

-- Moving average of the 3 harvests before a date (FR-07) — crop 1, 2026-02-09 → 1550.00
SELECT ROUND(AVG(quantity), 2) FROM (
  SELECT quantity FROM Harvest
  WHERE crop_id = 1 AND harvest_date < '2026-02-09'
  ORDER BY harvest_date DESC, harvest_id DESC LIMIT 3) AS last3;

-- Forecast evaluation (FR-08)
SELECT * FROM vw_forecast_status;
SELECT * FROM vw_forecast_summary;

-- Orphan check (must return 0)
SELECT COUNT(*) FROM Harvest h LEFT JOIN Crop c ON c.crop_id = h.crop_id WHERE c.crop_id IS NULL;
```

## 9. Backup and recovery (NFR-04)

```bash
./scripts/backup_db.sh       # writes backups/RoseProductionDB_backup_<date>.sql (git-ignored)
```

To verify a backup without touching the real database, restore it into a separate database
(as in TC-13):

```bash
set -a; source .env; set +a
docker exec -e MYSQL_PWD="$DB_PASSWORD" Mysqlcontainer mysql -u "$DB_USER" \
  -e "CREATE DATABASE RoseProductionDB_RecoveryTest"
docker exec -i -e MYSQL_PWD="$DB_PASSWORD" Mysqlcontainer mysql -u "$DB_USER" \
  RoseProductionDB_RecoveryTest < backups/RoseProductionDB_backup_YYYYMMDD_HHMMSS.sql
```

The backup taken before this work (`backups/RoseProductionDB_backup_20261122_090222.sql`,
SHA-256 `8d861d4f…7267fd2`) was restored successfully into a separate MySQL 8.0 server and
contained the 7 tables, 2 views, 4 triggers, 6 procedures and 49 rows listed above.

## 10. Final audit findings (2026-11-22) — no schema change applied

The schema was re-read from `information_schema` of the running server and compared with
`models.py` (columns, types, nullability, keys, named constraints): no mismatch. Schema fingerprint
(SHA-256 of the normalized structure) `9707b6b1…bd893bd`, unchanged before and after every audit run.
Data at the time of the audit: 50 rows (Farm 1, Lot 3, RoseVariety 7, Crop 8, Season 3, Harvest 20,
Forecast 8; forecast #40 was added by the user after the first delivery).

### Normalization (NFR-03), checked against the actual schema

- Every table has a single-column surrogate primary key, so 2NF holds trivially (no partial dependency).
- No non-key attribute determines another non-key attribute: the variety and lot of a harvest are
  reached through `Harvest → Crop`, never stored in `Harvest`; totals, averages and forecast status
  are computed (queries and views), not stored.
- `Harvest.season_id` is **not** derivable from `harvest_date`, because seasons overlap
  (*Normal Production 2026* covers 2026-01-01…2026-12-31 and contains *Valentines Day 2026* and
  *Mothers Day 2026*); it is an independent classification chosen by the user, not a transitive dependency.
- Result: 3NF for the documented functional dependencies. What the schema does **not** prevent is
  duplicate *data* (no natural-key uniqueness), see DQ-07/DQ-08 below.

### Data-quality findings in the existing rows (reported, not modified)

| ID | Finding | Rows | Severity |
|---|---|---|---|
| DQ-03 | harvests dated before their crop's planting date | harvests 16, 17, 18 (crop 6 planted 2026-02-15; dated 2026-01-20/22/24) | MEDIUM |
| DQ-04 | forecast dated before its crop's planting date | forecast 7 (crop 6, 2026-01-25) | MEDIUM |
| DQ-05 | harvests in the future | none | – |
| DQ-06 | two harvests for the same crop and day | none | – |
| DQ-07 | identical varieties (same name and colour) | varieties 6 and 7 (Quicksand, Peach) | LOW |
| DQ-08 | identical crops (same lot, variety, planting date) | crops 7 and 8 (lot 3, variety 6, 2026-11-15) | LOW |
| DQ-09 | lots with area ≤ 0 | none (no CHECK in the schema; the API enforces `area > 0`) | LOW |

### Schema weakness demonstrated (inside a rolled-back transaction)

`Harvest` allows two rows for the same crop and day. `vw_forecast_status` joins a forecast with the
harvest of the same crop **and date**, so a second harvest duplicates the forecast row (`1 → 2` rows
for one forecast, check NFR-02-20) and changes the `vw_forecast_summary` figures (on the replica:
total forecasts 7 → 8, MAE 50.00 → 750.00, MAPE 3.13 → 726.56;
`docs/final-audit/evidence/cloud_regression/duplicate_harvest_view_effect_replica.json`). Severity **HIGH** for the evaluation feature. Mitigation applied
in the API (not in the schema): `POST`/`PUT /harvests` refuse a second harvest for the same crop and day
(409 `DUPLICATE_RECORD`); rows inserted directly with SQL are not covered.

### Proposed schema changes — status

Item 1 below (one harvest per crop and day) was **approved and applied on 2026-11-23** together with
three other UNIQUE keys (§11). Items 2 and 3 remain proposals that need approval.


```sql
-- 1. One harvest per crop and day (fixes the view duplication at the database level).
--    Precondition: DQ-06 returns no rows (true on 2026-11-22). Take a backup first.
ALTER TABLE Harvest ADD CONSTRAINT unique_crop_harvest_date UNIQUE (crop_id, harvest_date);

-- 2. Positive lot area at the database level (today only the API checks it).
ALTER TABLE Lot ADD CONSTRAINT Lot_chk_area CHECK (area > 0);

-- 3. Only if the data grows a lot: date-only history filters scan the table
--    (35 ms at 100,020 harvests on the replica).
CREATE INDEX idx_harvest_date ON Harvest (harvest_date);
```

The planting-date rules (DQ-03/DQ-04) could also be enforced by triggers; they are enforced by the
API for new and edited rows. Existing rows 16, 17, 18 and forecast 7 should be corrected by the
data owner (change the crop or the date); the audit did not modify them.

### Backup and recovery check (NFR-04)

`scripts/audit/backup_restore_check.sh` (run on nobara-pc, 2026-11-22 10:42) dumped
`RoseProductionDB` (28,080 bytes, SHA-256 `d5b5ce9c…162bec4a`, 0.18 s) and restored it into the new
database `RoseProductionDB_AuditRestore_20261122_104257` (0.68 s). Tables, views, triggers, routines,
constraints, indexes, columns, every row of the 7 tables and the output of both views were identical
(`result: PASS`). The production database was never written. The recovery database was left for
inspection; drop it manually when no longer needed.

## 11. Duplicate prevention (2026-11-23)

Rules confirmed by the project owner and their enforcement (details, evidence and tests:
[`docs/final-audit/DUPLICATE_DATA_PREVENTION_REPORT.md`](final-audit/DUPLICATE_DATA_PREVENTION_REPORT.md)):

| Entity | Duplicate when | Database | API |
|---|---|---|---|
| Farm | same name + location | `unique_farm_name_location` | ✔ |
| Lot | same name in the same farm | `unique_lot_farm_name` | ✔ |
| RoseVariety | same name | – (blocked by existing varieties 6/7) | ✔ |
| Crop | same lot + variety + planting date | – (blocked by existing crops 7/8) | ✔ |
| Season | same name, overlapping period | `unique_season_name_dates` (exact) | ✔ (overlap) |
| Harvest | same crop + day | `unique_harvest_crop_date` | ✔ |
| Forecast | same crop + date | `unique_crop_forecast_date` | ✔ |

Applied with `scripts/apply_duplicate_fix.sh` → `scripts/db/add_unique_constraints.sh` on
2026-11-23 12:43 −05:00: backup `backups/before_unique_constraints_20261123_124330.sql`, duplicate
pre-check (0 conflicts), 4 × `ADD CONSTRAINT … UNIQUE` (online, `ALGORITHM=INPLACE, LOCK=NONE`), row
counts before = after (Farm 2, Lot 6, RoseVariety 7, Crop 8, Season 5, Harvest 22, Forecast 8). The
comparisons follow the column collation `utf8mb4_unicode_ci` (case- and trailing-space-insensitive).
Pending (needs approval): clean-up of varieties 6/7 and crops 7/8, then UNIQUE keys for those rules.
