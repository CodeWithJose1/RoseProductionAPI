"""CRUD tests for the seven resources (isolated TEST_ records only)."""

import pytest

from conftest import TEST_YEAR, unique

MISSING_ID = 999_999_999

RESOURCES = {
    # path: (item key, id key)
    "/farms": ("farm", "farm_id"),
    "/lots": ("lot", "lot_id"),
    "/varieties": ("variety", "variety_id"),
    "/crops": ("crop", "crop_id"),
    "/seasons": ("season", "season_id"),
    "/harvests": ("harvest", "harvest_id"),
    "/forecasts": ("forecast", "forecast_id"),
}


def ids_in(client, h, path, id_key):
    data = client.get(path, headers=h).get_json()
    key = path.strip("/")
    return {item[id_key] for item in data[key]}


# ---------------------------------------------------------------- generic

@pytest.mark.parametrize("path", sorted(RESOURCES))
def test_get_missing_record_is_404(client, h, path):
    response = client.get(f"{path}/{MISSING_ID}", headers=h)
    assert response.status_code == 404
    assert response.get_json()["code"] == "NOT_FOUND"


@pytest.mark.parametrize("path", sorted(RESOURCES))
def test_update_missing_record_is_404(client, h, path):
    response = client.put(f"{path}/{MISSING_ID}", json={}, headers=h)
    assert response.status_code == 404


@pytest.mark.parametrize("path", sorted(RESOURCES))
def test_delete_missing_record_is_404(client, h, path):
    response = client.delete(f"{path}/{MISSING_ID}", headers=h)
    assert response.status_code == 404


@pytest.mark.parametrize("path", sorted(RESOURCES))
def test_create_with_invalid_json_is_400(client, h, path):
    response = client.post(path, data="{not json",
                           headers={**h, "Content-Type": "application/json"})
    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_JSON"


@pytest.mark.parametrize("path", sorted(RESOURCES))
def test_create_with_json_array_is_400(client, h, path):
    assert client.post(path, json=[1, 2], headers=h).status_code == 400


@pytest.mark.parametrize("path", sorted(RESOURCES))
def test_create_with_missing_fields_is_400(client, h, path):
    response = client.post(path, json={}, headers=h)
    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]  # one message per missing field


@pytest.mark.parametrize("path", sorted(RESOURCES))
def test_list_returns_count_and_items(client, h, path):
    body = client.get(path, headers=h).get_json()
    key = path.strip("/")
    assert body["count"] == len(body[key])


# ---------------------------------------------------------------- Farm

def test_farm_crud(client, h, tracker):
    name = unique("TEST_Farm")
    created = client.post("/farms", headers=h,
                          json={"name": f"  {name}  ", "location": "Cayambe"})
    assert created.status_code == 201
    farm = created.get_json()["farm"]
    tracker.add("Farm", farm["farm_id"])
    assert farm["name"] == name  # trimmed

    assert farm["farm_id"] in ids_in(client, h, "/farms", "farm_id")
    detail = client.get(f"/farms/{farm['farm_id']}", headers=h).get_json()
    assert detail["farm"]["lots"] == [] and detail["farm"]["lot_count"] == 0

    updated = client.put(f"/farms/{farm['farm_id']}", headers=h,
                         json={"name": name + "_upd", "location": "Tabacundo"})
    assert updated.status_code == 200
    assert updated.get_json()["farm"]["location"] == "Tabacundo"

    deleted = client.delete(f"/farms/{farm['farm_id']}", headers=h)
    assert deleted.status_code == 200
    assert deleted.get_json()["deleted_farm"] == {"farm_id": farm["farm_id"]}
    tracker.forget("Farm", farm["farm_id"])
    assert client.get(f"/farms/{farm['farm_id']}",
                      headers=h).status_code == 404


@pytest.mark.parametrize("body,field", [
    ({"name": "", "location": "x"}, "name"),
    ({"name": "x" * 101, "location": "x"}, "name"),
    ({"name": 12, "location": "x"}, "name"),
    ({"name": "x", "location": "y" * 151}, "location"),
])
def test_farm_invalid_values(client, h, body, field):
    response = client.post("/farms", json=body, headers=h)
    assert response.status_code == 400
    assert field in response.get_json()["details"]


def test_farm_with_lots_cannot_be_deleted(client, h, factory):
    lot = factory.lot()
    response = client.delete(f"/farms/{lot['farm']['farm_id']}", headers=h)
    assert response.status_code == 409
    assert response.get_json()["code"] == "RECORD_IN_USE"


# ---------------------------------------------------------------- Lot

def test_lot_crud(client, h, factory, tracker):
    farm = factory.farm()
    created = client.post("/lots", headers=h, json={
        "farm_id": farm["farm_id"], "name": unique("TEST_Lot"),
        "area": "2.345"})
    assert created.status_code == 201
    lot = created.get_json()["lot"]
    tracker.add("Lot", lot["lot_id"])
    assert lot["area"] == 2.35  # DECIMAL(10,2), rounded half-up
    assert lot["farm"] == {"farm_id": farm["farm_id"], "name": farm["name"]}

    filtered = client.get(f"/lots?farm_id={farm['farm_id']}",
                          headers=h).get_json()
    assert [l["lot_id"] for l in filtered["lots"]] == [lot["lot_id"]]
    assert client.get(f"/lots/{lot['lot_id']}", headers=h).status_code == 200

    other = factory.farm()
    updated = client.put(f"/lots/{lot['lot_id']}", headers=h, json={
        "farm_id": other["farm_id"], "name": "TEST_moved", "area": 3})
    assert updated.status_code == 200
    assert updated.get_json()["lot"]["farm"]["farm_id"] == other["farm_id"]

    assert client.delete(f"/lots/{lot['lot_id']}", headers=h).status_code \
        == 200
    tracker.forget("Lot", lot["lot_id"])
    assert client.get(f"/lots/{lot['lot_id']}", headers=h).status_code == 404


def test_lot_invalid_farm_is_400(client, h):
    response = client.post("/lots", headers=h, json={
        "farm_id": MISSING_ID, "name": "TEST_x", "area": 1})
    assert response.status_code == 400
    assert response.get_json()["code"] == "FOREIGN_KEY_NOT_FOUND"


@pytest.mark.parametrize("area", [0, -1, "abc", 100000000, True])
def test_lot_invalid_area(client, h, factory, area):
    farm = factory.farm()
    response = client.post("/lots", headers=h, json={
        "farm_id": farm["farm_id"], "name": "TEST_x", "area": area})
    assert response.status_code == 400
    assert "area" in response.get_json()["details"]


def test_lot_with_crops_cannot_be_deleted(client, h, factory):
    crop = factory.crop()
    response = client.delete(f"/lots/{crop['lot']['lot_id']}", headers=h)
    assert response.status_code == 409


# ---------------------------------------------------------------- Variety

def test_variety_crud(client, h, tracker):
    created = client.post("/varieties", headers=h,
                          json={"name": "API_TEST_Variety", "color": "Purple"})
    assert created.status_code == 201
    body = created.get_json()
    assert body["message"] == "Rose variety created successfully"
    variety = body["variety"]
    tracker.add("RoseVariety", variety["variety_id"])

    vid = variety["variety_id"]
    assert vid in ids_in(client, h, "/varieties", "variety_id")
    assert client.get(f"/varieties/{vid}", headers=h).get_json()[
        "variety"]["name"] == "API_TEST_Variety"

    updated = client.put(f"/varieties/{vid}", headers=h,
                         json={"name": "API_TEST_Variety_Updated",
                               "color": "Red"})
    assert updated.status_code == 200
    assert updated.get_json()["message"] == "Rose variety updated successfully"
    assert updated.get_json()["variety"]["color"] == "Red"

    deleted = client.delete(f"/varieties/{vid}", headers=h)
    assert deleted.status_code == 200
    assert deleted.get_json() == {
        "message": "Rose variety deleted successfully",
        "deleted_variety": {"variety_id": vid},
    }
    tracker.forget("RoseVariety", vid)
    assert vid not in ids_in(client, h, "/varieties", "variety_id")


@pytest.mark.parametrize("body", [
    {"name": "x"}, {"color": "x"}, {"name": "  ", "color": "Red"},
    {"name": "x", "color": "c" * 51}, {"name": ["x"], "color": "Red"},
])
def test_variety_invalid_values(client, h, body):
    assert client.post("/varieties", json=body, headers=h).status_code == 400


def test_variety_duplicate_names_rejected(client, h, factory):
    # Business rule confirmed on 2026-11-23: a variety is identified by its
    # name (until then duplicates were accepted; see
    # docs/final-audit/DUPLICATE_DATA_PREVENTION_REPORT.md).
    first = factory.variety(name=unique("TEST_Duplicate"))
    response = client.post("/varieties", headers=h,
                           json={"name": first["name"], "color": "White"})
    assert response.status_code == 409
    assert response.get_json()["code"] == "DUPLICATE_RECORD"


def test_variety_with_crops_cannot_be_deleted(client, h, factory):
    crop = factory.crop()
    response = client.delete(f"/varieties/{crop['variety']['variety_id']}",
                             headers=h)
    assert response.status_code == 409


# ---------------------------------------------------------------- Crop

def test_crop_crud(client, h, factory, tracker):
    lot, variety = factory.lot(), factory.variety()
    created = client.post("/crops", headers=h, json={
        "lot_id": lot["lot_id"], "variety_id": variety["variety_id"],
        "planting_date": "2097-03-15"})
    assert created.status_code == 201
    crop = created.get_json()["crop"]
    tracker.add("Crop", crop["crop_id"])
    assert crop["variety"]["name"] == variety["name"]
    assert crop["planting_date"] == "2097-03-15"

    listed = client.get(f"/crops?variety_id={variety['variety_id']}",
                        headers=h).get_json()
    assert [c["crop_id"] for c in listed["crops"]] == [crop["crop_id"]]

    other_variety = factory.variety()
    updated = client.put(f"/crops/{crop['crop_id']}", headers=h, json={
        "lot_id": lot["lot_id"], "variety_id": other_variety["variety_id"],
        "planting_date": "2097-04-01"})
    assert updated.status_code == 200
    assert updated.get_json()["crop"]["variety"]["variety_id"] == \
        other_variety["variety_id"]

    assert client.delete(f"/crops/{crop['crop_id']}",
                         headers=h).status_code == 200
    tracker.forget("Crop", crop["crop_id"])
    assert client.get(f"/crops/{crop['crop_id']}", headers=h).status_code \
        == 404


@pytest.mark.parametrize("field", ["lot_id", "variety_id"])
def test_crop_invalid_foreign_keys(client, h, factory, field):
    body = {"lot_id": factory.lot()["lot_id"],
            "variety_id": factory.variety()["variety_id"],
            "planting_date": "2097-01-01"}
    body[field] = MISSING_ID
    response = client.post("/crops", json=body, headers=h)
    assert response.status_code == 400
    assert field in response.get_json()["details"]


@pytest.mark.parametrize("value", ["2097-02-30", "01/02/2097", "", 20970101])
def test_crop_invalid_dates(client, h, factory, value):
    response = client.post("/crops", headers=h, json={
        "lot_id": factory.lot()["lot_id"],
        "variety_id": factory.variety()["variety_id"],
        "planting_date": value})
    assert response.status_code == 400


def test_crop_with_harvests_cannot_be_deleted(client, h, factory):
    crop, season = factory.crop(), factory.season()
    factory.harvest(crop["crop_id"], season["season_id"],
                    f"{TEST_YEAR}-02-03", 10)
    response = client.delete(f"/crops/{crop['crop_id']}", headers=h)
    assert response.status_code == 409


# ---------------------------------------------------------------- Season

def test_season_crud(client, h, tracker):
    created = client.post("/seasons", headers=h, json={
        "name": unique("TEST_Season"), "start_date": f"{TEST_YEAR}-05-01",
        "end_date": f"{TEST_YEAR}-05-10"})
    assert created.status_code == 201
    season = created.get_json()["season"]
    tracker.add("Season", season["season_id"])
    assert season["duration_days"] == 10

    sid = season["season_id"]
    assert sid in ids_in(client, h, "/seasons", "season_id")
    updated = client.put(f"/seasons/{sid}", headers=h, json={
        "name": "TEST_Mothers_Day", "start_date": f"{TEST_YEAR}-05-02",
        "end_date": f"{TEST_YEAR}-05-12"})
    assert updated.status_code == 200
    assert updated.get_json()["season"]["end_date"] == f"{TEST_YEAR}-05-12"

    assert client.delete(f"/seasons/{sid}", headers=h).status_code == 200
    tracker.forget("Season", sid)
    assert client.get(f"/seasons/{sid}", headers=h).status_code == 404


def test_season_end_before_start_is_400(client, h):
    response = client.post("/seasons", headers=h, json={
        "name": "TEST_bad", "start_date": f"{TEST_YEAR}-05-10",
        "end_date": f"{TEST_YEAR}-05-01"})
    assert response.status_code == 400
    assert "end_date" in response.get_json()["details"]


def test_season_cannot_shrink_around_existing_harvests(client, h, factory):
    crop, season = factory.crop(), factory.season()
    factory.harvest(crop["crop_id"], season["season_id"],
                    f"{TEST_YEAR}-02-20", 10)
    response = client.put(f"/seasons/{season['season_id']}", headers=h,
                          json={"name": season["name"],
                                "start_date": f"{TEST_YEAR}-02-01",
                                "end_date": f"{TEST_YEAR}-02-10"})
    assert response.status_code == 409
    assert response.get_json()["code"] == "SEASON_RANGE_CONFLICT"


def test_season_with_harvests_cannot_be_deleted(client, h, factory):
    crop, season = factory.crop(), factory.season()
    factory.harvest(crop["crop_id"], season["season_id"],
                    f"{TEST_YEAR}-02-04", 10)
    response = client.delete(f"/seasons/{season['season_id']}", headers=h)
    assert response.status_code == 409


# ---------------------------------------------------------------- Harvest

def test_harvest_crud_and_filters(client, h, factory, tracker):
    crop, season = factory.crop(), factory.season()
    created = client.post("/harvests", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": season["season_id"],
        "harvest_date": f"{TEST_YEAR}-02-05", "quantity": 1250})
    assert created.status_code == 201
    harvest = created.get_json()["harvest"]
    tracker.add("Harvest", harvest["harvest_id"])
    hid = harvest["harvest_id"]

    for query in (f"crop_id={crop['crop_id']}",
                  f"season_id={season['season_id']}",
                  f"variety_id={crop['variety_id']}",
                  f"lot_id={crop['lot_id']}",
                  f"date_from={TEST_YEAR}-02-05&date_to={TEST_YEAR}-02-05"):
        listed = client.get(f"/harvests?{query}", headers=h).get_json()
        assert hid in [x["harvest_id"] for x in listed["harvests"]], query

    empty = client.get(f"/harvests?crop_id={crop['crop_id']}"
                       f"&date_from={TEST_YEAR}-02-06", headers=h).get_json()
    assert empty["count"] == 0

    updated = client.put(f"/harvests/{hid}", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": season["season_id"],
        "harvest_date": f"{TEST_YEAR}-02-06", "quantity": 1300})
    assert updated.status_code == 200
    assert updated.get_json()["harvest"]["quantity"] == 1300

    assert client.delete(f"/harvests/{hid}", headers=h).status_code == 200
    tracker.forget("Harvest", hid)
    assert client.get(f"/harvests/{hid}", headers=h).status_code == 404


@pytest.mark.parametrize("quantity", [0, -10, 1.5, "many", 2147483648])
def test_harvest_invalid_quantity(client, h, factory, quantity):
    crop, season = factory.crop(), factory.season()
    response = client.post("/harvests", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": season["season_id"],
        "harvest_date": f"{TEST_YEAR}-02-05", "quantity": quantity})
    assert response.status_code == 400
    assert "quantity" in response.get_json()["details"]


def test_harvest_outside_season_is_400(client, h, factory):
    crop, season = factory.crop(), factory.season()
    response = client.post("/harvests", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": season["season_id"],
        "harvest_date": f"{TEST_YEAR}-03-15", "quantity": 10})
    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "DATE_OUTSIDE_SEASON"
    assert "harvest_date" in body["details"]


@pytest.mark.parametrize("field", ["crop_id", "season_id"])
def test_harvest_invalid_foreign_keys(client, h, factory, field):
    body = {"crop_id": factory.crop()["crop_id"],
            "season_id": factory.season()["season_id"],
            "harvest_date": f"{TEST_YEAR}-02-05", "quantity": 10}
    body[field] = MISSING_ID
    response = client.post("/harvests", json=body, headers=h)
    assert response.status_code == 400
    assert response.get_json()["code"] == "FOREIGN_KEY_NOT_FOUND"


def test_harvest_filter_validation(client, h):
    assert client.get("/harvests?crop_id=abc", headers=h).status_code == 400
    assert client.get("/harvests?date_from=2026-13-01",
                      headers=h).status_code == 400
    assert client.get("/harvests?date_from=2026-02-10&date_to=2026-02-01",
                      headers=h).status_code == 400


# ---------------------------------------------------------------- Forecast

def test_forecast_crud(client, h, factory, tracker):
    crop, season = factory.crop(), factory.season()
    created = client.post("/forecasts", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": season["season_id"],
        "forecast_date": f"{TEST_YEAR}-02-14", "estimated_quantity": 1550,
        "method": "TEST manual"})
    assert created.status_code == 201
    forecast = created.get_json()["forecast"]
    tracker.add("Forecast", forecast["forecast_id"])
    fid = forecast["forecast_id"]

    listed = client.get(f"/forecasts?crop_id={crop['crop_id']}",
                        headers=h).get_json()
    assert [f["forecast_id"] for f in listed["forecasts"]] == [fid]
    detail = client.get(f"/forecasts/{fid}", headers=h).get_json()["forecast"]
    assert detail["estimated_quantity"] == 1550.0

    updated = client.put(f"/forecasts/{fid}", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": season["season_id"],
        "forecast_date": f"{TEST_YEAR}-02-13", "estimated_quantity": 0,
        "method": "TEST manual v2"})
    assert updated.status_code == 200
    assert updated.get_json()["forecast"]["estimated_quantity"] == 0.0

    assert client.delete(f"/forecasts/{fid}", headers=h).status_code == 200
    tracker.forget("Forecast", fid)
    assert client.get(f"/forecasts/{fid}", headers=h).status_code == 404


def test_forecast_negative_quantity_is_400(client, h, factory):
    crop, season = factory.crop(), factory.season()
    response = client.post("/forecasts", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": season["season_id"],
        "forecast_date": f"{TEST_YEAR}-02-10", "estimated_quantity": -1,
        "method": "TEST"})
    assert response.status_code == 400
    assert "estimated_quantity" in response.get_json()["details"]


def test_forecast_duplicate_crop_date_is_409(client, h, factory):
    crop, season = factory.crop(), factory.season()
    factory.forecast(crop["crop_id"], season["season_id"],
                     f"{TEST_YEAR}-02-10")
    response = client.post("/forecasts", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": season["season_id"],
        "forecast_date": f"{TEST_YEAR}-02-10", "estimated_quantity": 5,
        "method": "TEST"})
    assert response.status_code == 409
    assert response.get_json()["code"] == "DUPLICATE_RECORD"


def test_forecast_outside_season_is_400(client, h, factory):
    crop, season = factory.crop(), factory.season()
    response = client.post("/forecasts", headers=h, json={
        "crop_id": crop["crop_id"], "season_id": season["season_id"],
        "forecast_date": f"{TEST_YEAR}-08-10", "estimated_quantity": 5,
        "method": "TEST"})
    assert response.status_code == 400
    assert response.get_json()["code"] == "DATE_OUTSIDE_SEASON"


def test_forecast_invalid_foreign_key(client, h, factory):
    season = factory.season()
    response = client.post("/forecasts", headers=h, json={
        "crop_id": MISSING_ID, "season_id": season["season_id"],
        "forecast_date": f"{TEST_YEAR}-02-10", "estimated_quantity": 5,
        "method": "TEST"})
    assert response.status_code == 400
    assert "crop_id" in response.get_json()["details"]
