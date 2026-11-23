"""Duplicate prevention (2026-11-23).

Uniqueness rules (confirmed with the project owner):

    Farm        name + location                (DB: unique_farm_name_location)
    Lot         name inside its farm           (DB: unique_lot_farm_name)
    RoseVariety name                           (API only: varieties 6/7 share a name)
    Crop        lot + variety + planting date  (API only: crops 7/8 are identical)
    Season      name + overlapping period      (DB: unique_season_name_dates, exact dates)
    Harvest     crop + day                     (DB: unique_harvest_crop_date)
    Forecast    crop + date                    (DB: unique_crop_forecast_date, pre-existing)

Text comparisons ignore case and surrounding/internal extra spaces. Every test
counts the rows with SQL before and after, creates only TEST_ rows and
deletes them by id (``tracker``); the production data guard runs at the end.
"""

import threading
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from conftest import TEST_YEAR, unique
from models import db

D = lambda m, d: date(TEST_YEAR, m, d).isoformat()  # noqa: E731


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def count(app, sql, **params):
    """Committed row count read on a separate connection (real MySQL)."""
    with app.app_context():
        with db.engine.connect() as conn:
            return conn.execute(text(sql), params).scalar()


def post(client, h, path, body):
    response = client.post(path, json=body, headers=h)
    return response.status_code, response.get_json()


def put(client, h, path, body):
    response = client.put(path, json=body, headers=h)
    return response.status_code, response.get_json()


def assert_duplicate(status, body, field):
    assert status == 409, body
    assert body["code"] == "DUPLICATE_RECORD"
    assert field in body.get("details", {}), body


@pytest.fixture
def season(factory):
    return factory.season(start=date(TEST_YEAR, 2, 1),
                          end=date(TEST_YEAR, 2, 28))


@pytest.fixture
def crop(factory):
    return factory.crop(planting_date=f"{TEST_YEAR - 1}-06-01")


# ----------------------------------------------------------------------
# Farm: name + location
# ----------------------------------------------------------------------

def test_farm_duplicates(app, client, h, factory, tracker):
    name = unique("TEST_Farm")
    farm = factory.farm(name=name, location="TEST Cayambe")
    where = "SELECT COUNT(*) FROM Farm WHERE name = :n"
    assert count(app, where, n=name) == 1

    for variant in ({"name": name, "location": "TEST Cayambe"},
                    {"name": f"  {name}  ", "location": " TEST   Cayambe "},
                    {"name": name.lower(), "location": "test cayambe"}):
        status, body = post(client, h, "/farms", variant)
        assert_duplicate(status, body, "name")
    assert count(app, where, n=name) == 1

    # same name in another location is a different farm
    other = factory.farm(name=name, location="TEST Tabacundo")
    assert count(app, where, n=name) == 2

    # update keeping its own values is allowed
    status, _ = put(client, h, f"/farms/{farm['farm_id']}",
                    {"name": name, "location": "TEST Cayambe"})
    assert status == 200
    # update to the values of another farm is refused and changes nothing
    status, body = put(client, h, f"/farms/{other['farm_id']}",
                       {"name": name, "location": "TEST cayambe"})
    assert_duplicate(status, body, "name")
    assert count(app, "SELECT location FROM Farm WHERE farm_id = :i",
                 i=other["farm_id"]) == "TEST Tabacundo"


def test_text_is_stored_normalized(app, client, h, tracker):
    name = unique("TEST_Farm")
    status, body = post(client, h, "/farms",
                        {"name": f"  {name}   North ", "location": " A   B "})
    assert status == 201
    tracker.add("Farm", body["farm"]["farm_id"])
    assert body["farm"]["name"] == f"{name} North"
    assert count(app, "SELECT location FROM Farm WHERE farm_id = :i",
                 i=body["farm"]["farm_id"]) == "A B"


# ----------------------------------------------------------------------
# Lot: name unique inside its farm
# ----------------------------------------------------------------------

def test_lot_duplicates(app, client, h, factory):
    farm_a, farm_b = factory.farm(), factory.farm()
    lot = factory.lot(farm_id=farm_a["farm_id"], name="TEST Lot A")
    where = "SELECT COUNT(*) FROM Lot WHERE farm_id IN (:a, :b)"
    before = count(app, where, a=farm_a["farm_id"], b=farm_b["farm_id"])

    for name in ("TEST Lot A", "  test   lot a ", "TEST LOT A"):
        status, body = post(client, h, "/lots", {
            "farm_id": farm_a["farm_id"], "name": name, "area": 2})
        assert_duplicate(status, body, "name")
    assert count(app, where, a=farm_a["farm_id"],
                 b=farm_b["farm_id"]) == before

    # the same lot name in another farm is legitimate
    moved = factory.lot(farm_id=farm_b["farm_id"], name="TEST Lot A")
    # editing a lot without changing farm/name is allowed
    status, _ = put(client, h, f"/lots/{lot['lot_id']}", {
        "farm_id": farm_a["farm_id"], "name": "TEST Lot A", "area": 3})
    assert status == 200
    # moving the second lot into the first farm would duplicate the name
    status, body = put(client, h, f"/lots/{moved['lot_id']}", {
        "farm_id": farm_a["farm_id"], "name": "TEST Lot A", "area": 1})
    assert_duplicate(status, body, "name")
    assert count(app, "SELECT farm_id FROM Lot WHERE lot_id = :i",
                 i=moved["lot_id"]) == farm_b["farm_id"]


# ----------------------------------------------------------------------
# RoseVariety: name (any colour)
# ----------------------------------------------------------------------

def test_variety_duplicates(app, client, h, factory):
    name = unique("TEST_Variety")
    variety = factory.variety(name=name, color="Red")
    where = "SELECT COUNT(*) FROM RoseVariety WHERE LOWER(name) = LOWER(:n)"

    for body_in in ({"name": name, "color": "Red"},
                    {"name": name, "color": "White"},      # name-only rule
                    {"name": f"  {name.upper()} ", "color": "Red"}):
        status, body = post(client, h, "/varieties", body_in)
        assert_duplicate(status, body, "name")
    assert count(app, where, n=name) == 1

    # editing colour while keeping the name is allowed
    status, body = put(client, h, f"/varieties/{variety['variety_id']}",
                       {"name": name, "color": "Pink"})
    assert status == 200 and body["variety"]["color"] == "Pink"
    # renaming another variety to this name is refused
    other = factory.variety()
    status, body = put(client, h, f"/varieties/{other['variety_id']}",
                       {"name": name.lower(), "color": "Red"})
    assert_duplicate(status, body, "name")
    assert count(app, "SELECT name FROM RoseVariety WHERE variety_id = :i",
                 i=other["variety_id"]) == other["name"]


def test_preexisting_duplicates_stay_editable(app, client, h, tracker):
    """Rows that were duplicated before the rule existed (like varieties 6
    and 7) can still be edited as long as their identifying value is kept;
    they are never merged or modified automatically."""
    name = unique("TEST_Legacy")
    ids = []
    with app.app_context():
        with db.engine.begin() as conn:
            for _ in range(2):  # simulate legacy rows written directly by SQL
                conn.execute(text("INSERT INTO RoseVariety (name, color) "
                                  "VALUES (:n, 'Peach')"), {"n": name})
                ids.append(conn.execute(
                    text("SELECT LAST_INSERT_ID()")).scalar())
    for i in ids:
        tracker.add("RoseVariety", i)
    status, body = put(client, h, f"/varieties/{ids[1]}",
                       {"name": name, "color": "Light peach"})
    assert status == 200, body
    assert count(app, "SELECT COUNT(*) FROM RoseVariety WHERE name = :n",
                 n=name) == 2


# ----------------------------------------------------------------------
# Crop: lot + variety + planting date
# ----------------------------------------------------------------------

def test_crop_duplicates(app, client, h, factory):
    lot, variety = factory.lot(), factory.variety()
    first = factory.crop(lot_id=lot["lot_id"], variety_id=variety["variety_id"],
                         planting_date=f"{TEST_YEAR - 1}-06-01")
    where = "SELECT COUNT(*) FROM Crop WHERE lot_id = :l"
    status, body = post(client, h, "/crops", {
        "lot_id": lot["lot_id"], "variety_id": variety["variety_id"],
        "planting_date": f"{TEST_YEAR - 1}-06-01"})
    assert_duplicate(status, body, "planting_date")
    assert count(app, where, l=lot["lot_id"]) == 1

    # a new crop cycle of the same variety in the same lot is legitimate
    second = factory.crop(lot_id=lot["lot_id"],
                          variety_id=variety["variety_id"],
                          planting_date=f"{TEST_YEAR}-06-01")
    assert count(app, where, l=lot["lot_id"]) == 2
    status, _ = put(client, h, f"/crops/{first['crop_id']}", {
        "lot_id": lot["lot_id"], "variety_id": variety["variety_id"],
        "planting_date": f"{TEST_YEAR - 1}-06-01"})
    assert status == 200
    status, body = put(client, h, f"/crops/{second['crop_id']}", {
        "lot_id": lot["lot_id"], "variety_id": variety["variety_id"],
        "planting_date": f"{TEST_YEAR - 1}-06-01"})
    assert_duplicate(status, body, "planting_date")


# ----------------------------------------------------------------------
# Season: name + overlapping period
# ----------------------------------------------------------------------

def test_season_duplicates(app, client, h, factory):
    name = unique("TEST_Valentine")
    first = factory.season(name=name, start=date(TEST_YEAR, 2, 1),
                           end=date(TEST_YEAR, 2, 14))
    where = "SELECT COUNT(*) FROM Season WHERE LOWER(name) = LOWER(:n)"
    for body_in in (
            {"name": name, "start_date": D(2, 1), "end_date": D(2, 14)},
            {"name": f" {name.upper()} ", "start_date": D(2, 1),
             "end_date": D(2, 14)},
            {"name": name, "start_date": D(2, 10), "end_date": D(2, 20)}):
        status, body = post(client, h, "/seasons", body_in)
        assert_duplicate(status, body, "name")
    assert count(app, where, n=name) == 1

    # the same name the next year, and another name on the same dates
    next_year = factory.season(name=name, start=date(TEST_YEAR + 1, 2, 1),
                               end=date(TEST_YEAR + 1, 2, 14))
    factory.season(start=date(TEST_YEAR, 2, 1), end=date(TEST_YEAR, 2, 14))
    assert count(app, where, n=name) == 2
    status, _ = put(client, h, f"/seasons/{first['season_id']}", {
        "name": name, "start_date": D(2, 1), "end_date": D(2, 14)})
    assert status == 200
    status, body = put(client, h, f"/seasons/{next_year['season_id']}", {
        "name": name, "start_date": D(2, 5), "end_date": D(2, 9)})
    assert_duplicate(status, body, "name")


# ----------------------------------------------------------------------
# Harvest: one record per crop and day; legitimate repeats preserved
# ----------------------------------------------------------------------

def test_harvest_duplicates_and_legitimate_repeats(app, client, h, factory,
                                                   crop, season):
    other_crop = factory.crop()
    sid = season["season_id"]
    first = factory.harvest(crop["crop_id"], sid, D(2, 5), 1000)
    where = "SELECT COUNT(*) FROM Harvest WHERE crop_id IN (:a, :b)"

    status, body = post(client, h, "/harvests", {
        "crop_id": crop["crop_id"], "season_id": sid,
        "harvest_date": D(2, 5), "quantity": 1000})
    assert_duplicate(status, body, "harvest_date")
    status, body = post(client, h, "/harvests", {
        "crop_id": crop["crop_id"], "season_id": sid,
        "harvest_date": D(2, 5), "quantity": 350})   # same day, other amount
    assert_duplicate(status, body, "harvest_date")
    assert count(app, where, a=crop["crop_id"], b=other_crop["crop_id"]) == 1

    # legitimate: same quantity the next day, and same day/quantity on
    # another crop (different lot/variety) are distinct production records
    factory.harvest(crop["crop_id"], sid, D(2, 6), 1000)
    factory.harvest(other_crop["crop_id"], sid, D(2, 5), 1000)
    assert count(app, where, a=crop["crop_id"], b=other_crop["crop_id"]) == 3

    status, _ = put(client, h, f"/harvests/{first['harvest_id']}", {
        "crop_id": crop["crop_id"], "season_id": sid,
        "harvest_date": D(2, 5), "quantity": 1100})
    assert status == 200
    status, body = put(client, h, f"/harvests/{first['harvest_id']}", {
        "crop_id": crop["crop_id"], "season_id": sid,
        "harvest_date": D(2, 6), "quantity": 1100})
    assert_duplicate(status, body, "harvest_date")
    assert count(app, "SELECT harvest_date FROM Harvest WHERE harvest_id = :i",
                 i=first["harvest_id"]).isoformat() == D(2, 5)


# ----------------------------------------------------------------------
# Forecast: one per crop and date, never overwritten
# ----------------------------------------------------------------------

def test_forecast_duplicates_are_rejected_not_overwritten(app, client, h,
                                                         factory, crop,
                                                         season):
    sid = season["season_id"]
    for day in (2, 3, 4):
        factory.harvest(crop["crop_id"], sid, D(2, day), 1000 + day)
    manual = factory.forecast(crop["crop_id"], sid, D(2, 10), estimated=42)
    where = "SELECT COUNT(*) FROM Forecast WHERE crop_id = :c"

    status, body = post(client, h, "/forecasts", {
        "crop_id": crop["crop_id"], "season_id": sid,
        "forecast_date": D(2, 10), "estimated_quantity": 50,
        "method": "TEST again"})
    assert_duplicate(status, body, "forecast_date")
    # preview tells the client that a forecast already exists
    status, body = post(client, h, "/forecasts/generate", {
        "crop_id": crop["crop_id"], "season_id": sid,
        "forecast_date": D(2, 10), "save": False})
    assert status == 200
    assert body["calculation"]["existing_forecast_id"] == manual["forecast_id"]
    # saving a generated forecast for the same date is refused, the stored
    # forecast is not overwritten
    status, body = post(client, h, "/forecasts/generate", {
        "crop_id": crop["crop_id"], "season_id": sid,
        "forecast_date": D(2, 10), "save": True})
    assert_duplicate(status, body, "forecast_date")
    assert count(app, where, c=crop["crop_id"]) == 1
    assert float(count(app, "SELECT estimated_quantity FROM Forecast WHERE "
                       "forecast_id = :i", i=manual["forecast_id"])) == 42.0

    status, body = post(client, h, "/forecasts/generate", {
        "crop_id": crop["crop_id"], "season_id": sid,
        "forecast_date": D(2, 11), "save": False})
    assert body["calculation"]["existing_forecast_id"] is None


# ----------------------------------------------------------------------
# Rapid and concurrent identical requests
# ----------------------------------------------------------------------

def _concurrent_posts(app, h, path, body, n=8):
    barrier = threading.Barrier(n)
    results = []
    lock = threading.Lock()

    def worker():
        client = app.test_client()
        barrier.wait()
        response = client.post(path, json=body, headers=h)
        with lock:
            results.append((response.status_code, response.get_json()))

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    return results


CONCURRENT_CASES = ["farm", "lot", "variety", "crop", "season", "harvest",
                    "forecast"]


@pytest.mark.parametrize("entity", CONCURRENT_CASES)
def test_concurrent_identical_posts_create_one_record(app, h, factory,
                                                      tracker, entity):
    if entity == "farm":
        path, key, table, pk = "/farms", "farm", "Farm", "farm_id"
        body = {"name": unique("TEST_Farm"), "location": "TEST race"}
        where, params = "SELECT COUNT(*) FROM Farm WHERE name = :n", {
            "n": body["name"]}
    elif entity == "lot":
        farm = factory.farm()
        path, key, table, pk = "/lots", "lot", "Lot", "lot_id"
        body = {"farm_id": farm["farm_id"], "name": "TEST race", "area": 1}
        where, params = "SELECT COUNT(*) FROM Lot WHERE farm_id = :f", {
            "f": farm["farm_id"]}
    elif entity == "variety":
        path, key, table, pk = ("/varieties", "variety", "RoseVariety",
                                "variety_id")
        body = {"name": unique("TEST_Variety"), "color": "Red"}
        where, params = "SELECT COUNT(*) FROM RoseVariety WHERE name = :n", {
            "n": body["name"]}
    elif entity == "crop":
        lot, variety = factory.lot(), factory.variety()
        path, key, table, pk = "/crops", "crop", "Crop", "crop_id"
        body = {"lot_id": lot["lot_id"], "variety_id": variety["variety_id"],
                "planting_date": f"{TEST_YEAR - 1}-06-01"}
        where, params = "SELECT COUNT(*) FROM Crop WHERE lot_id = :l", {
            "l": lot["lot_id"]}
    elif entity == "season":
        path, key, table, pk = "/seasons", "season", "Season", "season_id"
        body = {"name": unique("TEST_Season"), "start_date": D(3, 1),
                "end_date": D(3, 10)}
        where, params = "SELECT COUNT(*) FROM Season WHERE name = :n", {
            "n": body["name"]}
    else:
        crop = factory.crop()
        season = factory.season(start=date(TEST_YEAR, 2, 1),
                                end=date(TEST_YEAR, 2, 28))
        if entity == "harvest":
            path, key, table, pk = "/harvests", "harvest", "Harvest", \
                "harvest_id"
            body = {"crop_id": crop["crop_id"],
                    "season_id": season["season_id"],
                    "harvest_date": D(2, 7), "quantity": 500}
            where = "SELECT COUNT(*) FROM Harvest WHERE crop_id = :c"
        else:
            path, key, table, pk = "/forecasts", "forecast", "Forecast", \
                "forecast_id"
            body = {"crop_id": crop["crop_id"],
                    "season_id": season["season_id"],
                    "forecast_date": D(2, 20), "estimated_quantity": 5,
                    "method": "TEST race"}
            where = "SELECT COUNT(*) FROM Forecast WHERE crop_id = :c"
        params = {"c": crop["crop_id"]}

    before = count(app, where, **params)
    results = _concurrent_posts(app, h, path, body)
    created = [b for s, b in results if s == 201]
    for b in created:
        tracker.add(table, b[key][pk])
    statuses = sorted(s for s, _ in results)
    assert statuses == [201] + [409] * 7, statuses
    assert all(b["code"] == "DUPLICATE_RECORD"
               for s, b in results if s == 409)
    assert count(app, where, **params) == before + 1


def test_rapid_identical_requests(app, client, h, tracker):
    body = {"name": unique("TEST_Variety"), "color": "Red"}
    statuses = []
    for _ in range(5):
        response = client.post("/varieties", json=body, headers=h)
        statuses.append(response.status_code)
        if response.status_code == 201:
            tracker.add("RoseVariety", response.get_json()["variety"]
                        ["variety_id"])
    assert statuses == [201, 409, 409, 409, 409]
    assert count(app, "SELECT COUNT(*) FROM RoseVariety WHERE name = :n",
                 n=body["name"]) == 1


# ----------------------------------------------------------------------
# Database level (inside a transaction that is always rolled back)
# ----------------------------------------------------------------------

NEW_CONSTRAINTS = {
    ("Farm", "unique_farm_name_location"): ["name", "location"],
    ("Lot", "unique_lot_farm_name"): ["farm_id", "name"],
    ("Season", "unique_season_name_dates"): ["name", "start_date",
                                             "end_date"],
    ("Harvest", "unique_harvest_crop_date"): ["crop_id", "harvest_date"],
    ("Forecast", "unique_crop_forecast_date"): ["crop_id", "forecast_date"],
}


@pytest.mark.parametrize("table_index", sorted(NEW_CONSTRAINTS))
def test_unique_constraints_exist(db_conn, table_index):
    table, index = table_index
    columns = [r[0] for r in db_conn.execute(text("""
        SELECT COLUMN_NAME FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t
          AND INDEX_NAME = :i AND NON_UNIQUE = 0
        ORDER BY SEQ_IN_INDEX"""), {"t": table, "i": index})]
    assert columns == NEW_CONSTRAINTS[table_index]


def _expect_1062(conn, sql, **params):
    savepoint = conn.begin_nested()
    with pytest.raises(DBAPIError) as info:
        conn.execute(text(sql), params)
    savepoint.rollback()
    assert info.value.orig.args[0] == 1062, info.value


def _insert(conn, sql, **params):
    conn.execute(text(sql), params)
    return conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()


def test_database_rejects_duplicates_directly(db_conn):
    c = db_conn
    farm = _insert(c, "INSERT INTO Farm (name, location) "
                      "VALUES ('TEST_DB_DupFarm', 'Here')")
    _expect_1062(c, "INSERT INTO Farm (name, location) "
                    "VALUES ('test_db_dupfarm', 'HERE')")      # collation
    _insert(c, "INSERT INTO Farm (name, location) "
               "VALUES ('TEST_DB_DupFarm', 'Elsewhere')")      # legitimate
    _insert(c, "INSERT INTO Lot (farm_id, name, area) "
               "VALUES (:f, 'TEST_DB_Lot', 1)", f=farm)
    _expect_1062(c, "INSERT INTO Lot (farm_id, name, area) "
                    "VALUES (:f, 'TEST_DB_LOT', 2)", f=farm)
    variety = _insert(c, "INSERT INTO RoseVariety (name, color) "
                         "VALUES ('TEST_DB_V', 'Red')")
    lot = c.execute(text("SELECT lot_id FROM Lot WHERE farm_id = :f"),
                    {"f": farm}).scalar()
    crop = _insert(c, "INSERT INTO Crop (lot_id, variety_id, planting_date) "
                      "VALUES (:l, :v, '2097-06-01')", l=lot, v=variety)
    season = _insert(c, "INSERT INTO Season (name, start_date, end_date) "
                        "VALUES ('TEST_DB_S', '2098-02-01', '2098-02-14')")
    _expect_1062(c, "INSERT INTO Season (name, start_date, end_date) "
                    "VALUES ('test_db_s', '2098-02-01', '2098-02-14')")
    _insert(c, "INSERT INTO Season (name, start_date, end_date) "
               "VALUES ('TEST_DB_S', '2099-02-01', '2099-02-14')")
    _insert(c, "INSERT INTO Harvest (crop_id, season_id, harvest_date, "
               "quantity) VALUES (:c, :s, '2098-02-05', 10)", c=crop, s=season)
    _expect_1062(c, "INSERT INTO Harvest (crop_id, season_id, harvest_date, "
                    "quantity) VALUES (:c, :s, '2098-02-05', 99)",
                 c=crop, s=season)
    _insert(c, "INSERT INTO Harvest (crop_id, season_id, harvest_date, "
               "quantity) VALUES (:c, :s, '2098-02-06', 10)", c=crop, s=season)
