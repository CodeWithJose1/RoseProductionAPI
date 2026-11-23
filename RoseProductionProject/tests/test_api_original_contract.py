"""Regression: the original endpoints keep their URLs and JSON keys."""

import pytest

from conftest import TEST_YEAR

ORIGINAL_ITEM_KEYS = {
    "/farms": ("farms", {"farm_id", "name", "location"}),
    "/lots": ("lots", {"lot_id", "name", "area", "farm"}),
    "/varieties": ("varieties", {"variety_id", "name", "color"}),
    "/crops": ("crops", {"crop_id", "planting_date", "lot", "variety"}),
    "/seasons": ("seasons", {"season_id", "name", "start_date", "end_date"}),
    "/harvests": ("harvests", {"harvest_id", "harvest_date", "quantity",
                               "crop", "season"}),
    "/forecasts": ("forecasts", {"forecast_id", "forecast_date",
                                 "estimated_quantity", "method", "crop",
                                 "season"}),
}
NESTED = {
    "/lots": {"farm": {"farm_id", "name"}},
    "/crops": {"lot": {"lot_id", "name"},
               "variety": {"variety_id", "name", "color"}},
    "/harvests": {"crop": {"crop_id", "variety", "lot"},
                  "season": {"season_id", "name"}},
    "/forecasts": {"crop": {"crop_id", "variety", "lot"},
                   "season": {"season_id", "name"}},
}


@pytest.mark.parametrize("path", sorted(ORIGINAL_ITEM_KEYS))
def test_original_list_contract(client, h, path, factory):
    # Make sure at least one row exists for every resource.
    crop, season = factory.crop(), factory.season()
    factory.harvest(crop["crop_id"], season["season_id"],
                    f"{TEST_YEAR}-02-02", 5)
    factory.forecast(crop["crop_id"], season["season_id"],
                     f"{TEST_YEAR}-02-03")

    response = client.get(path, headers=h)
    assert response.status_code == 200
    body = response.get_json()
    list_key, keys = ORIGINAL_ITEM_KEYS[path]
    assert set(body) >= {"count", list_key}
    for item in body[list_key]:
        assert keys <= set(item)
        for nested, nested_keys in NESTED.get(path, {}).items():
            assert nested_keys <= set(item[nested])


def test_types_of_original_fields(client, h):
    for item in client.get("/lots", headers=h).get_json()["lots"]:
        assert isinstance(item["area"], float)
    for item in client.get("/forecasts", headers=h).get_json()["forecasts"]:
        assert isinstance(item["estimated_quantity"], float)
    for item in client.get("/harvests", headers=h).get_json()["harvests"]:
        assert isinstance(item["quantity"], int)
        assert len(item["harvest_date"]) == 10
