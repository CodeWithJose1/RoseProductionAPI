"""Statistics (FR-05, FR-06) and dashboard endpoints."""

from datetime import date

import pytest
from sqlalchemy import text

from conftest import TEST_YEAR
from models import db

Y = TEST_YEAR


def sql_scalar(app, sql, **params):
    with app.app_context():
        return db.session.execute(text(sql), params).scalar()


def test_dashboard_counts_match_database(client, h, app):
    body = client.get("/stats/dashboard", headers=h).get_json()
    for key, table in (("farms", "Farm"), ("lots", "Lot"),
                       ("varieties", "RoseVariety"), ("crops", "Crop"),
                       ("seasons", "Season"), ("harvests", "Harvest"),
                       ("forecasts", "Forecast")):
        assert body["counts"][key] == sql_scalar(
            app, f"SELECT COUNT(*) FROM {table}"), key
    total = sql_scalar(app, "SELECT COALESCE(SUM(quantity), 0) FROM Harvest")
    assert body["production"]["total"] == int(total)
    assert sum(v["total"] for v in body["by_variety"]) == int(total)
    assert sum(s["total"] for s in body["by_season"]) == int(total)
    assert sum(d["total"] for d in body["over_time"]) == int(total)


def test_dashboard_forecast_vs_actual_only_reports_real_actuals(client, h):
    body = client.get("/stats/dashboard", headers=h).get_json()
    status = client.get("/forecasts/status", headers=h).get_json()["rows"]
    actual_by_id = {r["forecast_id"]: r.get("actual_quantity")
                    for r in status}
    for item in body["forecast_vs_actual"]:
        assert item["actual"] == actual_by_id.get(item["forecast_id"])


@pytest.mark.parametrize("group_by",
                         ["variety", "lot", "season", "crop", "month", "date"])
def test_production_groups_sum_to_overall(client, h, group_by):
    body = client.get(f"/stats/production?group_by={group_by}",
                      headers=h).get_json()
    assert body["group_by"] == group_by
    assert sum(g["total"] for g in body["groups"]) == body["overall"]["total"]
    assert sum(g["records"] for g in body["groups"]) == \
        body["overall"]["records"]


def test_statistics_for_filtered_variety(client, h, factory):
    crop, season = factory.crop(), factory.season()
    for day, quantity in ((3, 1000), (5, 1600), (7, 1300)):
        factory.harvest(crop["crop_id"], season["season_id"],
                        f"{Y}-02-{day:02d}", quantity)
    body = client.get(f"/stats/production?group_by=variety&variety_id="
                      f"{crop['variety_id']}", headers=h).get_json()
    assert body["overall"] == {"total": 3900, "average": 1300.0,
                               "minimum": 1000, "maximum": 1600,
                               "records": 3}
    assert len(body["groups"]) == 1
    assert body["groups"][0]["label"] == crop["variety"]["name"]

    by_date = client.get(f"/stats/production?group_by=date&crop_id="
                         f"{crop['crop_id']}&date_from={Y}-02-04&date_to="
                         f"{Y}-02-06", headers=h).get_json()
    assert by_date["overall"]["total"] == 1600


def test_invalid_group_by_is_400(client, h):
    response = client.get("/stats/production?group_by=planet", headers=h)
    assert response.status_code == 400


def test_upcoming_seasons_include_future_test_season(client, h, factory):
    season = factory.season(start=date(2097, 2, 1), end=date(2097, 2, 14))
    body = client.get("/stats/dashboard", headers=h).get_json()
    upcoming = {s["season_id"]: s for s in body["upcoming_seasons"]}
    assert upcoming[season["season_id"]]["status"] == "upcoming"
