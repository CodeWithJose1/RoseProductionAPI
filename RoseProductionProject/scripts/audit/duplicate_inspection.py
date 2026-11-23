"""Read-only inspection of duplicate-looking records in RoseProductionDB.

Usage (project root, virtual environment active, MySQL running):

    python scripts/audit/duplicate_inspection.py [output.json]

Only SELECT statements are executed; nothing is inserted, updated or
deleted. Text comparisons are made the way the API now normalizes text:
surrounding whitespace removed, internal runs of whitespace collapsed to
one space and case ignored (LOWER). Results are printed as JSON and, when
a path is given, written to that file.
"""

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from sqlalchemy import create_engine, text  # noqa: E402

from config import Config  # noqa: E402


def norm(column):
    """SQL expression equivalent to the API's normalize_text()."""
    return (f"LOWER(TRIM(REGEXP_REPLACE({column}, '[[:space:]]+', ' ')))")


QUERIES = {
    "Farm: same name and location": f"""
        SELECT {norm('name')} AS name_key, {norm('location')} AS location_key,
               COUNT(*) AS n, GROUP_CONCAT(farm_id ORDER BY farm_id) AS ids,
               GROUP_CONCAT(CONCAT('[', name, ' | ', location, ']')
                            ORDER BY farm_id SEPARATOR ' ') AS raw_values
        FROM Farm GROUP BY name_key, location_key HAVING n > 1""",
    "Farm: same name (different location)": f"""
        SELECT {norm('name')} AS name_key, COUNT(*) AS n,
               GROUP_CONCAT(farm_id ORDER BY farm_id) AS ids
        FROM Farm GROUP BY name_key HAVING n > 1""",
    "Lot: same name inside the same farm": f"""
        SELECT farm_id, {norm('name')} AS name_key, COUNT(*) AS n,
               GROUP_CONCAT(lot_id ORDER BY lot_id) AS ids,
               GROUP_CONCAT(CONCAT('[', name, ' | ', area, ']')
                            ORDER BY lot_id SEPARATOR ' ') AS raw_values
        FROM Lot GROUP BY farm_id, name_key HAVING n > 1""",
    "RoseVariety: same name and color": f"""
        SELECT {norm('name')} AS name_key, {norm('color')} AS color_key,
               COUNT(*) AS n, GROUP_CONCAT(variety_id ORDER BY variety_id) AS ids,
               GROUP_CONCAT(CONCAT('[', name, ' | ', color, ']')
                            ORDER BY variety_id SEPARATOR ' ') AS raw_values
        FROM RoseVariety GROUP BY name_key, color_key HAVING n > 1""",
    "RoseVariety: same name (any color)": f"""
        SELECT {norm('name')} AS name_key, COUNT(*) AS n,
               GROUP_CONCAT(variety_id ORDER BY variety_id) AS ids,
               GROUP_CONCAT(DISTINCT color) AS colors
        FROM RoseVariety GROUP BY name_key HAVING n > 1""",
    "Crop: same lot, variety and planting date": """
        SELECT lot_id, variety_id, planting_date, COUNT(*) AS n,
               GROUP_CONCAT(crop_id ORDER BY crop_id) AS ids
        FROM Crop GROUP BY lot_id, variety_id, planting_date HAVING n > 1""",
    "Crop: same lot and variety (different planting dates)": """
        SELECT lot_id, variety_id, COUNT(*) AS n,
               GROUP_CONCAT(crop_id ORDER BY crop_id) AS ids,
               GROUP_CONCAT(planting_date ORDER BY crop_id) AS planting_dates
        FROM Crop GROUP BY lot_id, variety_id HAVING n > 1""",
    "Season: same name": f"""
        SELECT {norm('name')} AS name_key, COUNT(*) AS n,
               GROUP_CONCAT(season_id ORDER BY season_id) AS ids,
               GROUP_CONCAT(CONCAT(start_date, '..', end_date)
                            ORDER BY season_id) AS ranges
        FROM Season GROUP BY name_key HAVING n > 1""",
    "Season: same name with overlapping dates": f"""
        SELECT a.season_id AS id_a, b.season_id AS id_b, a.name AS name_a,
               b.name AS name_b, a.start_date AS start_a, a.end_date AS end_a,
               b.start_date AS start_b, b.end_date AS end_b
        FROM Season a JOIN Season b
          ON a.season_id < b.season_id
         AND {norm('a.name')} = {norm('b.name')}
         AND a.start_date <= b.end_date AND b.start_date <= a.end_date""",
    "Season: same date range (any name)": """
        SELECT start_date, end_date, COUNT(*) AS n,
               GROUP_CONCAT(season_id ORDER BY season_id) AS ids,
               GROUP_CONCAT(name ORDER BY season_id SEPARATOR ' | ') AS names
        FROM Season GROUP BY start_date, end_date HAVING n > 1""",
    "Harvest: same crop and day": """
        SELECT crop_id, harvest_date, COUNT(*) AS n,
               GROUP_CONCAT(harvest_id ORDER BY harvest_id) AS ids,
               GROUP_CONCAT(quantity ORDER BY harvest_id) AS quantities,
               GROUP_CONCAT(season_id ORDER BY harvest_id) AS seasons
        FROM Harvest GROUP BY crop_id, harvest_date HAVING n > 1""",
    "Harvest: same crop, day and quantity": """
        SELECT crop_id, harvest_date, quantity, COUNT(*) AS n,
               GROUP_CONCAT(harvest_id ORDER BY harvest_id) AS ids
        FROM Harvest GROUP BY crop_id, harvest_date, quantity HAVING n > 1""",
    "Harvest: same day and quantity on different crops (informative)": """
        SELECT harvest_date, quantity, COUNT(*) AS n,
               GROUP_CONCAT(CONCAT(harvest_id, '(crop ', crop_id, ')')
                            ORDER BY harvest_id) AS ids
        FROM Harvest GROUP BY harvest_date, quantity HAVING n > 1""",
    "Forecast: same crop and date": """
        SELECT crop_id, forecast_date, COUNT(*) AS n,
               GROUP_CONCAT(forecast_id ORDER BY forecast_id) AS ids
        FROM Forecast GROUP BY crop_id, forecast_date HAVING n > 1""",
    "Forecast: same crop, season, estimate and method on different dates (informative)": """
        SELECT crop_id, season_id, estimated_quantity, method, COUNT(*) AS n,
               GROUP_CONCAT(CONCAT(forecast_id, '@', forecast_date)
                            ORDER BY forecast_id) AS ids
        FROM Forecast GROUP BY crop_id, season_id, estimated_quantity, method
        HAVING n > 1""",
}

UNIQUE_INDEXES = """
    SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE,
           GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS columns
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
    GROUP BY TABLE_NAME, INDEX_NAME, NON_UNIQUE
    ORDER BY TABLE_NAME, INDEX_NAME"""

COLLATIONS = """
    SELECT TABLE_NAME, COLUMN_NAME, COLLATION_NAME
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND COLLATION_NAME IS NOT NULL
      AND TABLE_NAME IN ('Farm', 'Lot', 'RoseVariety', 'Season', 'Forecast')
    ORDER BY TABLE_NAME, COLUMN_NAME"""


def rows(conn, sql):
    return [{k: (v.isoformat() if hasattr(v, "isoformat") else
                 (str(v) if v is not None and not isinstance(v, (int, str))
                  else v))
             for k, v in row._mapping.items()}
            for row in conn.execute(text(sql))]


def main():
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
    out = {"database": Config.DB_NAME if hasattr(Config, "DB_NAME") else None,
           "run_at": dt.datetime.now().astimezone().isoformat(),
           "read_only": True, "checks": {}}
    with engine.connect() as conn:
        conn.execute(text("SET SESSION TRANSACTION READ ONLY"))
        conn.execute(text("START TRANSACTION READ ONLY"))
        out["database"] = conn.execute(text("SELECT DATABASE()")).scalar()
        out["row_counts"] = {
            t: conn.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar()
            for t in ("Farm", "Lot", "RoseVariety", "Crop", "Season",
                      "Harvest", "Forecast")}
        for title, sql in QUERIES.items():
            out["checks"][title] = rows(conn, sql)
        out["indexes"] = rows(conn, UNIQUE_INDEXES)
        out["text_collations"] = rows(conn, COLLATIONS)
        conn.execute(text("ROLLBACK"))
    report = json.dumps(out, indent=1, ensure_ascii=False)
    print(report)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as handle:
            handle.write(report + "\n")


if __name__ == "__main__":
    main()
