"""Shared pytest fixtures.

The tests run against the database configured in the project's .env
(RoseProductionDB). They never modify pre-existing rows:

* every record a test needs is created by the test itself (names start with
  ``TEST_``) and is deleted again by ID when the test finishes;
* database-level constraint tests run inside a transaction that is always
  rolled back;
* the whole session takes a snapshot of every pre-existing row first and
  ``test_zz_production_data_guard.py`` checks at the end that all of them
  are unchanged and that no test row was left behind.

Side effect to be aware of: AUTO_INCREMENT counters advance (MySQL does not
reuse ids), exactly as with any insert/delete.
"""

import os
import sys
import uuid
from collections import defaultdict
from datetime import date

import pytest
from sqlalchemy import text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app  # noqa: E402
from models import db  # noqa: E402

TABLES = {
    # table: primary key
    "Farm": "farm_id",
    "Lot": "lot_id",
    "RoseVariety": "variety_id",
    "Crop": "crop_id",
    "Season": "season_id",
    "Harvest": "harvest_id",
    "Forecast": "forecast_id",
}
# Children first, so foreign keys never block the clean-up.
DELETE_ORDER = ["Forecast", "Harvest", "Crop", "Season", "Lot",
                "RoseVariety", "Farm"]

# Test seasons live in a past year that does not overlap the real data
# (harvests cannot be dated in the future, so test harvests need a past
# season). Tests that need a future season pass explicit dates.
TEST_YEAR = 2001


def unique(prefix="TEST"):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@pytest.fixture(scope="session")
def app():
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture(scope="session")
def api_key(app):
    key = app.config.get("API_KEY")
    assert key, "API_KEY must be defined in .env to run the API tests"
    return key


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def h(api_key):
    """Headers authenticating with the original X-API-Key mechanism."""
    return {"X-API-Key": api_key}


def take_snapshot(app):
    snapshot = {}
    with app.app_context():
        with db.engine.connect() as conn:
            for table, pk in TABLES.items():
                rows = conn.execute(text(f"SELECT * FROM `{table}`")).all()
                snapshot[table] = {
                    row._mapping[pk]: tuple(row) for row in rows
                }
    return snapshot


@pytest.fixture(scope="session")
def baseline(app):
    """Every row that existed before the test session started."""
    return take_snapshot(app)


@pytest.fixture(scope="session", autouse=True)
def _snapshot_first(baseline):
    # autouse + session scope: the snapshot is taken before any test runs.
    return baseline


class Tracker:
    """Remembers ids created by a test and deletes exactly those ids."""

    def __init__(self, app, baseline):
        self.app = app
        self.baseline = baseline
        self.ids = defaultdict(set)

    def add(self, table, record_id):
        assert record_id not in self.baseline[table], (
            f"refusing to track pre-existing {table} id {record_id}"
        )
        self.ids[table].add(record_id)

    def forget(self, table, record_id):
        self.ids[table].discard(record_id)

    def cleanup(self):
        with self.app.app_context():
            with db.engine.begin() as conn:
                for table in DELETE_ORDER:
                    ids = sorted(self.ids[table] -
                                 set(self.baseline[table].keys()))
                    if not ids:
                        continue
                    pk = TABLES[table]
                    params = {f"id{i}": v for i, v in enumerate(ids)}
                    placeholders = ", ".join(f":id{i}" for i in range(len(ids)))
                    conn.execute(
                        text(f"DELETE FROM `{table}` WHERE `{pk}` IN "
                             f"({placeholders})"),
                        params,
                    )
        self.ids.clear()


@pytest.fixture
def tracker(app, baseline):
    t = Tracker(app, baseline)
    yield t
    t.cleanup()


class Factory:
    """Creates isolated TEST_ records through the API (and tracks them)."""

    def __init__(self, client, headers, tracker):
        self.client = client
        self.h = headers
        self.tracker = tracker

    def _post(self, path, body, key, table, pk):
        response = self.client.post(path, json=body, headers=self.h)
        assert response.status_code == 201, response.get_json()
        record = response.get_json()[key]
        self.tracker.add(table, record[pk])
        return record

    def farm(self, **kw):
        body = {"name": unique("TEST_Farm"), "location": "TEST location"}
        body.update(kw)
        return self._post("/farms", body, "farm", "Farm", "farm_id")

    def lot(self, farm_id=None, **kw):
        farm_id = farm_id or self.farm()["farm_id"]
        body = {"farm_id": farm_id, "name": unique("TEST_Lot"), "area": 1.25}
        body.update(kw)
        return self._post("/lots", body, "lot", "Lot", "lot_id")

    def variety(self, **kw):
        body = {"name": unique("TEST_Variety"), "color": "Red"}
        body.update(kw)
        return self._post("/varieties", body, "variety", "RoseVariety",
                          "variety_id")

    def crop(self, lot_id=None, variety_id=None, **kw):
        body = {
            "lot_id": lot_id or self.lot()["lot_id"],
            "variety_id": variety_id or self.variety()["variety_id"],
            "planting_date": f"{TEST_YEAR - 1}-06-01",
        }
        body.update(kw)
        return self._post("/crops", body, "crop", "Crop", "crop_id")

    def season(self, start=None, end=None, **kw):
        body = {
            "name": unique("TEST_Season"),
            "start_date": (start or date(TEST_YEAR, 2, 1)).isoformat(),
            "end_date": (end or date(TEST_YEAR, 2, 28)).isoformat(),
        }
        body.update(kw)
        return self._post("/seasons", body, "season", "Season", "season_id")

    def harvest(self, crop_id, season_id, harvest_date, quantity):
        body = {"crop_id": crop_id, "season_id": season_id,
                "harvest_date": harvest_date, "quantity": quantity}
        return self._post("/harvests", body, "harvest", "Harvest",
                          "harvest_id")

    def forecast(self, crop_id, season_id, forecast_date, estimated=100.0,
                 method="TEST manual"):
        body = {"crop_id": crop_id, "season_id": season_id,
                "forecast_date": forecast_date,
                "estimated_quantity": estimated, "method": method}
        return self._post("/forecasts", body, "forecast", "Forecast",
                          "forecast_id")


@pytest.fixture
def factory(client, h, tracker):
    return Factory(client, h, tracker)


@pytest.fixture
def db_conn(app):
    """Raw connection inside a transaction that is ALWAYS rolled back."""
    with app.app_context():
        connection = db.engine.connect()
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()
            connection.close()
