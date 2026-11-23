"""Production statistics (FR-05, FR-06) and dashboard data.

GET /stats/dashboard
GET /stats/production?group_by=variety|lot|season|crop|month|date
                     [&crop_id&season_id&variety_id&lot_id&date_from&date_to]
"""

from datetime import date

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from errors import ApiError
from models import (Crop, Farm, Forecast, Harvest, Lot, RoseVariety, Season,
                    db)
from routes.forecasts import _status_by_forecast
from routes.harvests import filtered_harvest_query, parse_harvest_filters
from serializers import iso, to_number

stats_bp = Blueprint("stats", __name__, url_prefix="/stats")


def _aggregates():
    return (
        func.coalesce(func.sum(Harvest.quantity), 0).label("total"),
        func.avg(Harvest.quantity).label("average"),
        func.min(Harvest.quantity).label("minimum"),
        func.max(Harvest.quantity).label("maximum"),
        func.count(Harvest.harvest_id).label("records"),
    )


def _agg_dict(row):
    average = row.average
    return {
        "total": int(row.total or 0),
        "average": round(float(average), 2) if average is not None else None,
        "minimum": row.minimum,
        "maximum": row.maximum,
        "records": row.records,
    }


GROUPS = {
    "variety": (RoseVariety.variety_id, RoseVariety.name),
    "lot": (Lot.lot_id, Lot.name),
    "season": (Season.season_id, Season.name),
    "crop": (Crop.crop_id, None),
    "month": (func.date_format(Harvest.harvest_date, "%Y-%m"), None),
    "date": (Harvest.harvest_date, None),
}


def production_groups(group_by, filters):
    key_col, label_col = GROUPS[group_by]
    columns = [key_col.label("key")]
    if label_col is not None:
        columns.append(label_col.label("label"))
    query = (
        filtered_harvest_query(filters)
        .join(RoseVariety, RoseVariety.variety_id == Crop.variety_id)
        .join(Lot, Lot.lot_id == Crop.lot_id)
        .join(Season, Season.season_id == Harvest.season_id)
        .with_entities(*columns, *_aggregates())
        .group_by(*([key_col] + ([label_col] if label_col is not None
                                 else [])))
        .order_by(key_col)
    )
    groups = []
    for row in query.all():
        key = row.key
        label = getattr(row, "label", None)
        if group_by == "crop":
            label = f"Crop #{key}"
        if label is None:
            label = iso(key) if hasattr(key, "isoformat") else str(key)
        item = {"key": iso(key) if hasattr(key, "isoformat") else key,
                "label": label}
        item.update(_agg_dict(row))
        groups.append(item)
    return groups


@stats_bp.route("/production", methods=["GET"])
def production_statistics():
    group_by = request.args.get("group_by", "variety")
    if group_by not in GROUPS:
        raise ApiError(
            400, "Invalid group_by value",
            details={"group_by": "must be one of " + ", ".join(GROUPS)},
            code="VALIDATION_ERROR",
        )
    filters = parse_harvest_filters()
    overall = filtered_harvest_query(filters).with_entities(
        *_aggregates()
    ).one()

    return jsonify({
        "group_by": group_by,
        "filters": {k: iso(v) if hasattr(v, "isoformat") else v
                    for k, v in filters.items()},
        "overall": _agg_dict(overall),
        "groups": production_groups(group_by, filters),
    }), 200


@stats_bp.route("/dashboard", methods=["GET"])
def dashboard():
    today = date.today()

    counts = {
        "farms": Farm.query.count(),
        "lots": Lot.query.count(),
        "varieties": RoseVariety.query.count(),
        "crops": Crop.query.count(),
        "seasons": Season.query.count(),
        "harvests": Harvest.query.count(),
        "forecasts": Forecast.query.count(),
    }
    total_area = db.session.query(
        func.coalesce(func.sum(Lot.area), 0)
    ).scalar()

    production = _agg_dict(
        db.session.query(*_aggregates()).select_from(Harvest).one()
    )

    by_variety = production_groups("variety", {})
    colors = {v.variety_id: v.color for v in RoseVariety.query.all()}
    for item in by_variety:
        item["color"] = colors.get(item["key"])

    by_season = production_groups("season", {})
    seasons = {s.season_id: s for s in Season.query.all()}
    for item in by_season:
        season = seasons.get(item["key"])
        item["start_date"] = iso(season.start_date) if season else None
        item["end_date"] = iso(season.end_date) if season else None

    over_time = [
        {"date": g["key"], "total": g["total"], "records": g["records"]}
        for g in production_groups("date", {})
    ]

    upcoming = []
    for season in sorted(seasons.values(), key=lambda s: s.start_date):
        if season.end_date < today:
            continue
        status = "active" if season.start_date <= today else "upcoming"
        upcoming.append({
            "season_id": season.season_id,
            "name": season.name,
            "start_date": iso(season.start_date),
            "end_date": iso(season.end_date),
            "status": status,
            "days_until_start": max((season.start_date - today).days, 0),
        })

    status_rows = _status_by_forecast()
    forecast_status = {}
    for row in status_rows.values():
        label = str(row.get("status") or row.get("forecast_status")
                    or "Unknown")
        forecast_status[label] = forecast_status.get(label, 0) + 1

    forecast_vs_actual = []
    for forecast in Forecast.query.order_by(Forecast.forecast_date).all():
        row = status_rows.get(forecast.forecast_id) or {}
        actual = row.get("actual_quantity")
        forecast_vs_actual.append({
            "forecast_id": forecast.forecast_id,
            "label": f"#{forecast.forecast_id} "
                     f"{forecast.crop.variety.name} "
                     f"{iso(forecast.forecast_date)}",
            "forecast_date": iso(forecast.forecast_date),
            "estimated": float(forecast.estimated_quantity),
            "actual": to_number(actual) if actual is not None else None,
            "status": row.get("status") or row.get("forecast_status"),
        })

    return jsonify({
        "today": today.isoformat(),
        "counts": counts,
        "total_area": float(total_area or 0),
        "production": production,
        "by_variety": by_variety,
        "by_season": by_season,
        "over_time": over_time,
        "upcoming_seasons": upcoming,
        "forecast_status": forecast_status,
        "forecast_vs_actual": forecast_vs_actual,
    }), 200
