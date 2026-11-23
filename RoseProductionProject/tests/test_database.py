"""Database structure and integrity tests (MySQL, RoseProductionDB).

Structural tests only read information_schema. Behavioural tests insert
rows inside a transaction that is always rolled back (``db_conn``), using
savepoints for every statement that is expected to fail.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

EXPECTED_TABLES = {"Farm", "Lot", "RoseVariety", "Crop", "Season",
                   "Harvest", "Forecast"}
EXPECTED_VIEWS = {"vw_forecast_status", "vw_forecast_summary"}
EXPECTED_FKS = {
    ("Lot", "farm_id", "Farm", "farm_id"),
    ("Crop", "lot_id", "Lot", "lot_id"),
    ("Crop", "variety_id", "RoseVariety", "variety_id"),
    ("Harvest", "crop_id", "Crop", "crop_id"),
    ("Harvest", "season_id", "Season", "season_id"),
    ("Forecast", "crop_id", "Crop", "crop_id"),
    ("Forecast", "season_id", "Season", "season_id"),
}


def scalar(conn, sql, **params):
    return conn.execute(text(sql), params).scalar()


def rows(conn, sql, **params):
    return conn.execute(text(sql), params).all()


def mysql_code(exc):
    return exc.orig.args[0]


def expect_error(conn, sql, codes, **params):
    """Run ``sql`` in a savepoint and assert MySQL rejects it."""
    savepoint = conn.begin_nested()
    with pytest.raises(DBAPIError) as info:
        conn.execute(text(sql), params)
    savepoint.rollback()
    assert mysql_code(info.value) in codes, info.value
    return info.value


def insert_id(conn, sql, **params):
    conn.execute(text(sql), params)
    return scalar(conn, "SELECT LAST_INSERT_ID()")


@pytest.fixture
def fixture_rows(db_conn):
    """Farm -> Lot -> Variety -> Crop -> Season created in the rolled-back
    transaction."""
    farm = insert_id(db_conn, "INSERT INTO Farm (name, location) VALUES "
                     "('TEST_DB_Farm', 'TEST')")
    lot = insert_id(db_conn, "INSERT INTO Lot (farm_id, name, area) VALUES "
                    "(:f, 'TEST_DB_Lot', 1.00)", f=farm)
    variety = insert_id(db_conn, "INSERT INTO RoseVariety (name, color) "
                        "VALUES ('TEST_DB_Variety', 'Red')")
    crop = insert_id(db_conn, "INSERT INTO Crop (lot_id, variety_id, "
                     "planting_date) VALUES (:l, :v, '2097-06-01')",
                     l=lot, v=variety)
    season = insert_id(db_conn, "INSERT INTO Season (name, start_date, "
                       "end_date) VALUES ('TEST_DB_Season', '2098-02-01', "
                       "'2098-02-14')")
    return {"farm": farm, "lot": lot, "variety": variety, "crop": crop,
            "season": season}


# ----------------------------------------------------------------------
# Structure
# ----------------------------------------------------------------------

def test_connected_to_expected_database(db_conn):
    assert scalar(db_conn, "SELECT DATABASE()") is not None
    version = scalar(db_conn, "SELECT VERSION()")
    assert version.startswith("8."), version


def test_seven_tables_exist_and_are_innodb(db_conn):
    found = rows(db_conn, """
        SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'""")
    names = {name for name, _ in found}
    assert EXPECTED_TABLES <= names
    engines = {name: engine for name, engine in found}
    assert all(engines[t] == "InnoDB" for t in EXPECTED_TABLES)


def test_both_views_exist(db_conn):
    names = {r[0] for r in rows(db_conn, """
        SELECT TABLE_NAME FROM information_schema.VIEWS
        WHERE TABLE_SCHEMA = DATABASE()""")}
    assert EXPECTED_VIEWS <= names


@pytest.mark.parametrize("view", sorted(EXPECTED_VIEWS))
def test_views_are_queryable(db_conn, view):
    db_conn.execute(text(f"SELECT * FROM {view} LIMIT 5")).all()


def test_every_table_has_a_primary_key(db_conn):
    pks = {r[0] for r in rows(db_conn, """
        SELECT TABLE_NAME FROM information_schema.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_TYPE = 'PRIMARY KEY'
    """)}
    assert EXPECTED_TABLES <= pks


def test_expected_foreign_keys(db_conn):
    found = set(rows(db_conn, """
        SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME,
               REFERENCED_COLUMN_NAME
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL
    """))
    assert EXPECTED_FKS <= {tuple(r) for r in found}


def test_check_constraints_exist(db_conn):
    found = {(r[0], r[1]) for r in rows(db_conn, """
        SELECT tc.TABLE_NAME, cc.CHECK_CLAUSE
        FROM information_schema.CHECK_CONSTRAINTS cc
        JOIN information_schema.TABLE_CONSTRAINTS tc
          ON tc.CONSTRAINT_SCHEMA = cc.CONSTRAINT_SCHEMA
         AND tc.CONSTRAINT_NAME = cc.CONSTRAINT_NAME
        WHERE cc.CONSTRAINT_SCHEMA = DATABASE()""")}
    tables = {table for table, _ in found}
    assert {"Season", "Harvest", "Forecast"} <= tables
    clauses = " ".join(clause for _, clause in found)
    assert "end_date" in clauses and "start_date" in clauses
    assert "quantity" in clauses
    assert "estimated_quantity" in clauses


def test_unique_crop_forecast_date(db_conn):
    columns = [r[0] for r in rows(db_conn, """
        SELECT COLUMN_NAME FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Forecast'
          AND INDEX_NAME = 'unique_crop_forecast_date' AND NON_UNIQUE = 0
        ORDER BY SEQ_IN_INDEX""")]
    assert columns == ["crop_id", "forecast_date"]


def test_harvest_crop_date_index(db_conn):
    columns = [r[0] for r in rows(db_conn, """
        SELECT COLUMN_NAME FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Harvest'
          AND INDEX_NAME = 'idx_harvest_crop_date'
        ORDER BY SEQ_IN_INDEX""")]
    assert columns == ["crop_id", "harvest_date"]


def test_season_validation_triggers_installed(db_conn):
    found = {(r[0], r[1], r[2]) for r in rows(db_conn, """
        SELECT EVENT_OBJECT_TABLE, EVENT_MANIPULATION, ACTION_TIMING
        FROM information_schema.TRIGGERS
        WHERE TRIGGER_SCHEMA = DATABASE()""")}
    for table in ("Harvest", "Forecast"):
        assert (table, "INSERT", "BEFORE") in found
        assert (table, "UPDATE", "BEFORE") in found


def test_index_used_for_crop_and_date_query(db_conn):
    plan = db_conn.execute(text("""
        EXPLAIN SELECT * FROM Harvest
        WHERE crop_id = 1 AND harvest_date BETWEEN '2026-02-01'
                                             AND '2026-02-28'""")).mappings()
    plan = list(plan)
    possible = " ".join(str(r.get("possible_keys") or "") for r in plan)
    assert "idx_harvest_crop_date" in possible


# ----------------------------------------------------------------------
# Referential integrity of the existing data
# ----------------------------------------------------------------------

ORPHAN_QUERIES = {
    "Lot->Farm": "SELECT COUNT(*) FROM Lot l LEFT JOIN Farm f "
                 "ON f.farm_id = l.farm_id WHERE f.farm_id IS NULL",
    "Crop->Lot": "SELECT COUNT(*) FROM Crop c LEFT JOIN Lot l "
                 "ON l.lot_id = c.lot_id WHERE l.lot_id IS NULL",
    "Crop->RoseVariety": "SELECT COUNT(*) FROM Crop c LEFT JOIN RoseVariety v"
                         " ON v.variety_id = c.variety_id "
                         "WHERE v.variety_id IS NULL",
    "Harvest->Crop": "SELECT COUNT(*) FROM Harvest h LEFT JOIN Crop c "
                     "ON c.crop_id = h.crop_id WHERE c.crop_id IS NULL",
    "Harvest->Season": "SELECT COUNT(*) FROM Harvest h LEFT JOIN Season s "
                       "ON s.season_id = h.season_id "
                       "WHERE s.season_id IS NULL",
    "Forecast->Crop": "SELECT COUNT(*) FROM Forecast f LEFT JOIN Crop c "
                      "ON c.crop_id = f.crop_id WHERE c.crop_id IS NULL",
    "Forecast->Season": "SELECT COUNT(*) FROM Forecast f LEFT JOIN Season s "
                        "ON s.season_id = f.season_id "
                        "WHERE s.season_id IS NULL",
}


@pytest.mark.parametrize("relation", sorted(ORPHAN_QUERIES))
def test_no_orphan_rows(db_conn, relation):
    assert scalar(db_conn, ORPHAN_QUERIES[relation]) == 0


def test_existing_rows_satisfy_business_rules(db_conn):
    assert scalar(db_conn, "SELECT COUNT(*) FROM Harvest "
                           "WHERE quantity <= 0") == 0
    assert scalar(db_conn, "SELECT COUNT(*) FROM Forecast "
                           "WHERE estimated_quantity < 0") == 0
    assert scalar(db_conn, "SELECT COUNT(*) FROM Season "
                           "WHERE end_date < start_date") == 0
    assert scalar(db_conn, """
        SELECT COUNT(*) FROM Harvest h JOIN Season s
          ON s.season_id = h.season_id
        WHERE h.harvest_date NOT BETWEEN s.start_date AND s.end_date""") == 0
    assert scalar(db_conn, """
        SELECT COUNT(*) FROM Forecast f JOIN Season s
          ON s.season_id = f.season_id
        WHERE f.forecast_date NOT BETWEEN s.start_date AND s.end_date""") == 0


# ----------------------------------------------------------------------
# Constraint behaviour (rolled back)
# ----------------------------------------------------------------------

def test_valid_rows_are_accepted(db_conn, fixture_rows):
    r = fixture_rows
    harvest = insert_id(db_conn, "INSERT INTO Harvest (crop_id, season_id, "
                        "harvest_date, quantity) VALUES (:c, :s, "
                        "'2098-02-05', 100)", c=r["crop"], s=r["season"])
    forecast = insert_id(db_conn, "INSERT INTO Forecast (crop_id, season_id,"
                         " forecast_date, estimated_quantity, method) VALUES "
                         "(:c, :s, '2098-02-10', 0, 'TEST')",
                         c=r["crop"], s=r["season"])
    assert harvest and forecast


def test_invalid_foreign_key_rejected(db_conn):
    expect_error(db_conn, "INSERT INTO Lot (farm_id, name, area) VALUES "
                 "(2147483647, 'TEST_invalid', 1.00)", {1452})


def test_cannot_delete_referenced_parent(db_conn, fixture_rows):
    expect_error(db_conn, "DELETE FROM Farm WHERE farm_id = :f", {1451},
                 f=fixture_rows["farm"])


@pytest.mark.parametrize("quantity", [0, -5])
def test_harvest_quantity_must_be_positive(db_conn, fixture_rows, quantity):
    expect_error(db_conn, "INSERT INTO Harvest (crop_id, season_id, "
                 "harvest_date, quantity) VALUES (:c, :s, '2098-02-05', :q)",
                 {3819}, c=fixture_rows["crop"], s=fixture_rows["season"],
                 q=quantity)


def test_season_end_before_start_rejected(db_conn):
    expect_error(db_conn, "INSERT INTO Season (name, start_date, end_date) "
                 "VALUES ('TEST_bad', '2098-05-10', '2098-05-01')", {3819})


def test_forecast_quantity_cannot_be_negative(db_conn, fixture_rows):
    expect_error(db_conn, "INSERT INTO Forecast (crop_id, season_id, "
                 "forecast_date, estimated_quantity, method) VALUES "
                 "(:c, :s, '2098-02-10', -1, 'TEST')", {3819},
                 c=fixture_rows["crop"], s=fixture_rows["season"])


def test_harvest_outside_season_rejected_by_trigger(db_conn, fixture_rows):
    expect_error(db_conn, "INSERT INTO Harvest (crop_id, season_id, "
                 "harvest_date, quantity) VALUES (:c, :s, '2098-03-01', 10)",
                 {1644}, c=fixture_rows["crop"], s=fixture_rows["season"])


def test_harvest_update_outside_season_rejected(db_conn, fixture_rows):
    harvest = insert_id(db_conn, "INSERT INTO Harvest (crop_id, season_id, "
                        "harvest_date, quantity) VALUES (:c, :s, "
                        "'2098-02-05', 10)", c=fixture_rows["crop"],
                        s=fixture_rows["season"])
    expect_error(db_conn, "UPDATE Harvest SET harvest_date = '2098-06-01' "
                 "WHERE harvest_id = :h", {1644}, h=harvest)


def test_forecast_outside_season_rejected_by_trigger(db_conn, fixture_rows):
    expect_error(db_conn, "INSERT INTO Forecast (crop_id, season_id, "
                 "forecast_date, estimated_quantity, method) VALUES "
                 "(:c, :s, '2098-07-01', 10, 'TEST')", {1644},
                 c=fixture_rows["crop"], s=fixture_rows["season"])


def test_forecast_update_outside_season_rejected(db_conn, fixture_rows):
    forecast = insert_id(db_conn, "INSERT INTO Forecast (crop_id, season_id,"
                         " forecast_date, estimated_quantity, method) VALUES "
                         "(:c, :s, '2098-02-10', 5, 'TEST')",
                         c=fixture_rows["crop"], s=fixture_rows["season"])
    expect_error(db_conn, "UPDATE Forecast SET forecast_date = '2098-09-01' "
                 "WHERE forecast_id = :f", {1644}, f=forecast)


def test_duplicate_forecast_for_crop_and_date_rejected(db_conn, fixture_rows):
    params = {"c": fixture_rows["crop"], "s": fixture_rows["season"]}
    db_conn.execute(text("INSERT INTO Forecast (crop_id, season_id, "
                         "forecast_date, estimated_quantity, method) VALUES "
                         "(:c, :s, '2098-02-11', 5, 'TEST')"), params)
    expect_error(db_conn, "INSERT INTO Forecast (crop_id, season_id, "
                 "forecast_date, estimated_quantity, method) VALUES "
                 "(:c, :s, '2098-02-11', 6, 'TEST')", {1062}, **params)


def test_not_null_columns_enforced(db_conn):
    expect_error(db_conn, "INSERT INTO RoseVariety (name, color) VALUES "
                 "(NULL, 'Red')", {1048})


def test_auto_increment_enabled(db_conn):
    found = {r[0] for r in rows(db_conn, """
        SELECT TABLE_NAME FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND EXTRA LIKE '%auto_increment%'""")}
    assert EXPECTED_TABLES <= found


# ----------------------------------------------------------------------
# Stored procedures found in the schema (read-only analytics)
# ----------------------------------------------------------------------

EXPECTED_PROCEDURES = {
    "sp_add_variety_production", "sp_check_variety",
    "sp_get_variety_production", "sp_production_by_variety",
    "sp_safe_variety_query", "sp_validate_variety",
}


def test_stored_procedures_exist(db_conn):
    found = {r[0] for r in rows(db_conn, """
        SELECT ROUTINE_NAME FROM information_schema.ROUTINES
        WHERE ROUTINE_SCHEMA = DATABASE() AND ROUTINE_TYPE = 'PROCEDURE'""")}
    assert EXPECTED_PROCEDURES <= found


def test_procedure_production_by_variety_matches_sql(db_conn):
    name = scalar(db_conn, """
        SELECT rv.name FROM RoseVariety rv JOIN Crop c
          ON c.variety_id = rv.variety_id JOIN Harvest h
          ON h.crop_id = c.crop_id
        GROUP BY rv.name ORDER BY SUM(h.quantity) DESC LIMIT 1""")
    if name is None:
        pytest.skip("no harvest data to aggregate")
    result = db_conn.exec_driver_sql(
        "CALL sp_production_by_variety(%s)", (name,)).mappings().first()
    expected_total = scalar(db_conn, """
        SELECT SUM(h.quantity) FROM RoseVariety rv JOIN Crop c
          ON c.variety_id = rv.variety_id JOIN Harvest h
          ON h.crop_id = c.crop_id WHERE rv.name = :n""", n=name)
    assert int(result["total_production"]) == int(expected_total)


def test_procedure_validate_variety_signals_unknown_name(db_conn):
    savepoint = db_conn.begin_nested()
    with pytest.raises(DBAPIError) as info:
        db_conn.exec_driver_sql("CALL sp_validate_variety(%s)",
                                ("TEST_no_such_variety",))
    savepoint.rollback()
    assert mysql_code(info.value) == 1644
