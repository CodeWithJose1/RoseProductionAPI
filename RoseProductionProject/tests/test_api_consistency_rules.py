"""Consistency rules added during the final audit (2026-11-22).

They close gaps found in the audit: the database (and the first API
version) accepted harvests dated before the crop was planted, harvests dated
in the future and two harvests for the same crop on the same day - the last
case also corrupts the forecast evaluation views, which join Harvest on
(crop_id, harvest_date).
"""

from datetime import date, timedelta

from conftest import TEST_YEAR

Y = TEST_YEAR


def post_harvest(client, h, crop, season, day, quantity=100):
    return client.post("/harvests", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": season["season_id"],
        "harvest_date": day, "quantity": quantity})


def test_harvest_before_planting_is_rejected(client, h, factory):
    crop = factory.crop(planting_date=f"{Y}-02-10")
    season = factory.season()
    response = post_harvest(client, h, crop, season, f"{Y}-02-05")
    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "DATE_BEFORE_PLANTING"
    assert "harvest_date" in body["details"]
    # On or after the planting date is accepted.
    ok = post_harvest(client, h, crop, season, f"{Y}-02-10")
    assert ok.status_code == 201
    factory.tracker.add("Harvest", ok.get_json()["harvest"]["harvest_id"])


def test_future_harvest_is_rejected_and_today_accepted(client, h, factory):
    today = date.today()
    crop = factory.crop(planting_date=(today - timedelta(days=60)).isoformat())
    season = factory.season(start=today - timedelta(days=5),
                            end=today + timedelta(days=30))
    future = post_harvest(client, h, crop, season,
                          (today + timedelta(days=1)).isoformat())
    assert future.status_code == 400
    assert future.get_json()["code"] == "FUTURE_HARVEST_DATE"
    current = post_harvest(client, h, crop, season, today.isoformat())
    assert current.status_code == 201
    factory.tracker.add("Harvest",
                        current.get_json()["harvest"]["harvest_id"])


def test_one_harvest_per_crop_and_day(client, h, factory):
    crop, season = factory.crop(), factory.season()
    first = factory.harvest(crop["crop_id"], season["season_id"],
                            f"{Y}-02-03", 1000)
    second = factory.harvest(crop["crop_id"], season["season_id"],
                             f"{Y}-02-04", 900)

    duplicate = post_harvest(client, h, crop, season, f"{Y}-02-03", 50)
    assert duplicate.status_code == 409
    assert duplicate.get_json()["code"] == "DUPLICATE_RECORD"

    # Moving another record onto an occupied date is refused too ...
    moved = client.put(f"/harvests/{second['harvest_id']}", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": season["season_id"],
        "harvest_date": f"{Y}-02-03", "quantity": 900})
    assert moved.status_code == 409
    # ... but a record can be saved again on its own date.
    same = client.put(f"/harvests/{first['harvest_id']}", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": season["season_id"],
        "harvest_date": f"{Y}-02-03", "quantity": 1100})
    assert same.status_code == 200
    # Another crop may use the same date.
    other = factory.crop()
    factory.harvest(other["crop_id"], season["season_id"], f"{Y}-02-03", 70)


def test_forecast_before_planting_is_rejected(client, h, factory):
    crop = factory.crop(planting_date=f"{Y}-02-10")
    season = factory.season()
    body = {"crop_id": crop["crop_id"], "season_id": season["season_id"],
            "forecast_date": f"{Y}-02-05", "estimated_quantity": 10,
            "method": "TEST"}
    response = client.post("/forecasts", headers=h, json=body)
    assert response.status_code == 400
    assert response.get_json()["code"] == "DATE_BEFORE_PLANTING"
    generated = client.post("/forecasts/generate", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": season["season_id"],
        "forecast_date": f"{Y}-02-05"})
    assert generated.status_code == 400
    assert generated.get_json()["code"] == "DATE_BEFORE_PLANTING"


def test_planting_date_cannot_move_after_existing_harvests(client, h,
                                                           factory):
    crop, season = factory.crop(), factory.season()
    factory.harvest(crop["crop_id"], season["season_id"], f"{Y}-02-03", 10)
    body = {"lot_id": crop["lot_id"], "variety_id": crop["variety_id"]}
    later = client.put(f"/crops/{crop['crop_id']}", headers=h,
                       json={**body, "planting_date": f"{Y}-02-20"})
    assert later.status_code == 409
    assert later.get_json()["code"] == "PLANTING_DATE_CONFLICT"
    unchanged = client.put(f"/crops/{crop['crop_id']}", headers=h,
                           json={**body,
                                 "planting_date": crop["planting_date"]})
    assert unchanged.status_code == 200
    earlier = client.put(f"/crops/{crop['crop_id']}", headers=h,
                         json={**body, "planting_date": f"{Y - 1}-01-01"})
    assert earlier.status_code == 200
