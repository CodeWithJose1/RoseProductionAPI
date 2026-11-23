-- Migration 2026-11-23: duplicate prevention (approved by the project owner
-- on 2026-11-23). Adds four UNIQUE constraints; no table, column or row is
-- removed or changed. Each statement fails with error 1062 and changes
-- nothing if duplicates exist, so run scripts/db/add_unique_constraints.sh,
-- which takes a backup and checks for duplicates first.
--
-- Comparisons follow the column collation (utf8mb4_unicode_ci): case- and
-- trailing-space-insensitive, as the API's checks.

ALTER TABLE Farm
  ADD CONSTRAINT unique_farm_name_location UNIQUE (name, location),
  ALGORITHM=INPLACE, LOCK=NONE;

ALTER TABLE Lot
  ADD CONSTRAINT unique_lot_farm_name UNIQUE (farm_id, name),
  ALGORITHM=INPLACE, LOCK=NONE;

ALTER TABLE Season
  ADD CONSTRAINT unique_season_name_dates UNIQUE (name, start_date, end_date),
  ALGORITHM=INPLACE, LOCK=NONE;

ALTER TABLE Harvest
  ADD CONSTRAINT unique_harvest_crop_date UNIQUE (crop_id, harvest_date),
  ALGORITHM=INPLACE, LOCK=NONE;

-- Side effect observed on the real server (MySQL 8.0.33, 2026-11-23): when
-- unique_lot_farm_name (farm_id, name) was added, MySQL automatically
-- removed the index `farm_id` that it had created implicitly for the foreign
-- key Lot_ibfk_1, because the new index starts with farm_id and can serve
-- the foreign key. No data is affected and the foreign key is still enforced.
--
-- Revert (only if ever needed; removes indexes, never data):
--   ALTER TABLE Farm    DROP INDEX unique_farm_name_location;
--   ALTER TABLE Lot     ADD INDEX farm_id (farm_id);           -- first, for the FK
--   ALTER TABLE Lot     DROP INDEX unique_lot_farm_name;
--   ALTER TABLE Season  DROP INDEX unique_season_name_dates;
--   ALTER TABLE Harvest DROP INDEX unique_harvest_crop_date;
