"""Moving-average forecast generation (FR-07) and evaluation (FR-08)."""

from datetime import date

import pytest

from conftest import TEST_YEAR

Y = TEST_YEAR


@pytest.fixture
def history(factory):
    """A test crop with 4 harvests in a test season (Feb 1-28)."""
    crop, season = factory.crop(), factory.season()
    for day, quantity in ((2, 1000), (4, 1200), (6, 1500), (8, 1600)):
        factory.harvest(crop["crop_id"], season["season_id"],
                        f"{Y}-02-{day:02d}", quantity)
    return crop, season


def generate(client, h, crop, season, date, **extra):
    body = {"crop_id": crop["crop_id"], "season_id": season["season_id"],
            "forecast_date": date, **extra}
    return client.post("/forecasts/generate", json=body, headers=h)


def test_preview_uses_three_most_recent_previous_harvests(client, h, history):
    crop, season = history
    response = generate(client, h, crop, season, f"{Y}-02-10")
    assert response.status_code == 200
    calc = response.get_json()["calculation"]
    # (1200 + 1500 + 1600) / 3 = 1433.33 (independent calculation)
    assert calc["estimated_quantity"] == round((1200 + 1500 + 1600) / 3, 2)
    assert [x["quantity"] for x in calc["history"]] == [1600, 1500, 1200]
    assert calc["window"] == 3
    assert calc["saved"] is False
    assert calc["method"] == "Moving Average (3 records)"


def test_preview_does_not_write(client, h, history):
    crop, season = history
    generate(client, h, crop, season, f"{Y}-02-10")
    listed = client.get(f"/forecasts?crop_id={crop['crop_id']}",
                        headers=h).get_json()
    assert listed["count"] == 0


def test_only_harvests_before_the_forecast_date_are_used(client, h, history):
    crop, season = history
    calc = generate(client, h, crop, season,
                    f"{Y}-02-07").get_json()["calculation"]
    # Feb 2, 4, 6 -> (1000 + 1200 + 1500) / 3
    assert calc["estimated_quantity"] == round(3700 / 3, 2)


def test_custom_window(client, h, history):
    crop, season = history
    calc = generate(client, h, crop, season, f"{Y}-02-20",
                    window=2).get_json()["calculation"]
    assert calc["estimated_quantity"] == 1550.0


def test_insufficient_history_is_refused(client, h, history):
    crop, season = history
    response = generate(client, h, crop, season, f"{Y}-02-05")
    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "INSUFFICIENT_HISTORY"
    assert body["details"]["available_harvests"] == 2


@pytest.mark.parametrize("window", [0, 13, "3", 2.5])
def test_invalid_window(client, h, history, window):
    crop, season = history
    response = generate(client, h, crop, season, f"{Y}-02-10", window=window)
    assert response.status_code == 400


def test_date_outside_season_is_refused(client, h, history):
    crop, season = history
    response = generate(client, h, crop, season, f"{Y}-04-01")
    assert response.status_code == 400
    assert response.get_json()["code"] == "DATE_OUTSIDE_SEASON"


def test_save_persists_and_evaluates_against_actual(client, h, history,
                                                    tracker, factory):
    crop, season = history
    response = generate(client, h, crop, season, f"{Y}-02-10", save=True)
    assert response.status_code == 201
    body = response.get_json()
    forecast = body["forecast"]
    tracker.add("Forecast", forecast["forecast_id"])
    assert forecast["estimated_quantity"] == 1433.33
    assert forecast["method"] == "Moving Average (3 records)"

    stored = client.get(f"/forecasts/{forecast['forecast_id']}",
                        headers=h).get_json()["forecast"]
    assert stored["estimated_quantity"] == 1433.33

    # Saving the same crop/date again violates unique_crop_forecast_date.
    again = generate(client, h, crop, season, f"{Y}-02-10", save=True)
    assert again.status_code == 409

    # No actual harvest yet -> the view must not report an actual value.
    status_rows = client.get("/forecasts/status", headers=h).get_json()["rows"]
    row = next(r for r in status_rows
               if r["forecast_id"] == forecast["forecast_id"])
    assert row.get("actual_quantity") is None

    # A real harvest for the same crop and date makes it evaluable.
    factory.harvest(crop["crop_id"], season["season_id"], f"{Y}-02-10", 1500)
    status_rows = client.get("/forecasts/status", headers=h).get_json()["rows"]
    row = next(r for r in status_rows
               if r["forecast_id"] == forecast["forecast_id"])
    assert row.get("actual_quantity") == 1500


def test_views_endpoints(client, h):
    for path, view in (("/forecasts/status", "vw_forecast_status"),
                       ("/forecasts/summary", "vw_forecast_summary")):
        body = client.get(path, headers=h).get_json()
        assert body["view"] == view
        assert body["count"] == len(body["rows"])


def test_reproduces_existing_moving_average_forecasts(app, client, h):
    """TC-07: the implemented method gives the same estimates as the
    forecasts already stored with method 'Moving Average (3 records)'.

    The algorithm (forecasting.moving_average) is checked for every stored
    forecast. Through the endpoint, a stored forecast may be refused only by
    the consistency rule added in the final audit (forecast dated before
    the crop's planting date, code DATE_BEFORE_PLANTING); that refusal is
    asserted explicitly, never skipped.
    """
    from forecasting import moving_average

    stored = [f for f in client.get("/forecasts", headers=h).get_json()[
        "forecasts"] if f["method"].startswith("Moving Average (3")]
    assert stored
    with app.app_context():
        for forecast in stored:
            _, estimate = moving_average(
                forecast["crop_id"],
                date.fromisoformat(forecast["forecast_date"]), 3)
            assert float(estimate) == forecast["estimated_quantity"], forecast

    for forecast in stored:
        response = client.post("/forecasts/generate", headers=h, json={
            "crop_id": forecast["crop_id"],
            "season_id": forecast["season_id"],
            "forecast_date": forecast["forecast_date"], "window": 3})
        if response.status_code == 200:
            calc = response.get_json()["calculation"]
            assert calc["estimated_quantity"] == \
                forecast["estimated_quantity"], forecast
        else:
            assert response.status_code == 400, forecast
            assert response.get_json()["code"] == "DATE_BEFORE_PLANTING"


def test_summary_view_matches_status_view(client, h):
    """TC-08: MAE/MAPE of vw_forecast_summary agree with vw_forecast_status."""
    status = client.get("/forecasts/status", headers=h).get_json()["rows"]
    summary = client.get("/forecasts/summary", headers=h).get_json()["rows"]
    assert len(summary) == 1
    row = summary[0]
    evaluated = [r for r in status if r["forecast_status"] == "Evaluated"]
    assert row["total_forecasts"] == len(status)
    assert row["evaluated_forecasts"] == len(evaluated)
    assert row["pending_forecasts"] == len(status) - len(evaluated)
    if evaluated:
        mae = sum(r["absolute_error"] for r in evaluated) / len(evaluated)
        mape = sum(abs(r["actual_quantity"] - r["estimated_quantity"])
                   / r["actual_quantity"] * 100 for r in evaluated) \
            / len(evaluated)
        assert row["MAE"] == pytest.approx(round(mae, 2), abs=0.01)
        assert row["MAPE"] == pytest.approx(round(mape, 2), abs=0.01)
    for r in status:
        if r["forecast_status"] == "Pending":
            assert r["actual_quantity"] is None
            assert r["absolute_error"] is None


def test_forecast_for_a_future_date_uses_past_history(client, h, history,
                                                      factory, tracker):
    """FR-07: estimate a FUTURE date (a season in 2097) from real earlier
    harvests of the crop (Feb of the past test year)."""
    crop, _ = history
    future = factory.season(start=date(2097, 2, 1), end=date(2097, 2, 14))
    assert date(2097, 2, 10) > date.today()
    preview = client.post("/forecasts/generate", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": future["season_id"],
        "forecast_date": "2097-02-10"})
    assert preview.status_code == 200
    calc = preview.get_json()["calculation"]
    assert calc["estimated_quantity"] == round((1200 + 1500 + 1600) / 3, 2)
    saved = client.post("/forecasts/generate", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": future["season_id"],
        "forecast_date": "2097-02-10", "save": True})
    assert saved.status_code == 201
    forecast = saved.get_json()["forecast"]
    tracker.add("Forecast", forecast["forecast_id"])
    assert forecast["forecast_date"] == "2097-02-10"
