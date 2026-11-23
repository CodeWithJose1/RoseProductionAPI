"""Model -> JSON dictionaries.

The keys returned by the original GET endpoints are preserved exactly;
extra keys (ids of related records, usage counters) are only added, so
existing clients are not affected.
"""

from decimal import Decimal

from sqlalchemy import func

from models import db


def to_number(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def iso(value):
    return value.isoformat() if value is not None else None


def count_by(column):
    """Return {foreign_key_value: row_count} for a FK column."""
    rows = db.session.query(column, func.count()).group_by(column).all()
    return {key: total for key, total in rows}


# ----------------------------------------------------------------------

def farm_dict(farm, lot_count=None):
    data = {
        "farm_id": farm.farm_id,
        "name": farm.name,
        "location": farm.location,
    }
    if lot_count is not None:
        data["lot_count"] = lot_count
    return data


def lot_dict(lot, crop_count=None):
    data = {
        "lot_id": lot.lot_id,
        "name": lot.name,
        "area": float(lot.area),
        "farm": {
            "farm_id": lot.farm.farm_id,
            "name": lot.farm.name,
        },
        "farm_id": lot.farm_id,
    }
    if crop_count is not None:
        data["crop_count"] = crop_count
    return data


def variety_dict(variety, crop_count=None):
    data = {
        "variety_id": variety.variety_id,
        "name": variety.name,
        "color": variety.color,
    }
    if crop_count is not None:
        data["crop_count"] = crop_count
    return data


def crop_dict(crop, harvest_count=None, forecast_count=None):
    data = {
        "crop_id": crop.crop_id,
        "planting_date": iso(crop.planting_date),
        "lot": {
            "lot_id": crop.lot.lot_id,
            "name": crop.lot.name,
            "farm_id": crop.lot.farm_id,
        },
        "variety": {
            "variety_id": crop.variety.variety_id,
            "name": crop.variety.name,
            "color": crop.variety.color,
        },
        "lot_id": crop.lot_id,
        "variety_id": crop.variety_id,
        "label": f"#{crop.crop_id} · {crop.variety.name} · {crop.lot.name}",
    }
    if harvest_count is not None:
        data["harvest_count"] = harvest_count
    if forecast_count is not None:
        data["forecast_count"] = forecast_count
    return data


def season_dict(season, harvest_count=None, forecast_count=None):
    data = {
        "season_id": season.season_id,
        "name": season.name,
        "start_date": iso(season.start_date),
        "end_date": iso(season.end_date),
        "duration_days": (season.end_date - season.start_date).days + 1,
    }
    if harvest_count is not None:
        data["harvest_count"] = harvest_count
    if forecast_count is not None:
        data["forecast_count"] = forecast_count
    return data


def _crop_ref(crop):
    return {
        "crop_id": crop.crop_id,
        "variety": crop.variety.name,
        "lot": crop.lot.name,
        "variety_id": crop.variety_id,
        "lot_id": crop.lot_id,
        "color": crop.variety.color,
    }


def harvest_dict(harvest):
    return {
        "harvest_id": harvest.harvest_id,
        "harvest_date": iso(harvest.harvest_date),
        "quantity": harvest.quantity,
        "crop": _crop_ref(harvest.crop),
        "season": {
            "season_id": harvest.season.season_id,
            "name": harvest.season.name,
        },
        "crop_id": harvest.crop_id,
        "season_id": harvest.season_id,
    }


def forecast_dict(forecast):
    return {
        "forecast_id": forecast.forecast_id,
        "forecast_date": iso(forecast.forecast_date),
        "estimated_quantity": float(forecast.estimated_quantity),
        "method": forecast.method,
        "crop": _crop_ref(forecast.crop),
        "season": {
            "season_id": forecast.season.season_id,
            "name": forecast.season.name,
        },
        "crop_id": forecast.crop_id,
        "season_id": forecast.season_id,
    }


def row_dict(row):
    """Generic serializer for rows returned by raw SQL (views)."""
    out = {}
    for key, value in row._mapping.items():
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        elif isinstance(value, Decimal) and value.as_tuple().exponent >= 0:
            value = int(value)  # e.g. SUM(...) of integers -> DECIMAL(23,0)
        out[key] = to_number(value)
    return out

