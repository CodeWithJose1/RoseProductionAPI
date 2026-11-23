"""Forecast CRUD, generation and evaluation: /forecasts

GET  /forecasts                 list (filters: crop_id, season_id,
                                variety_id, lot_id, date_from, date_to)
GET  /forecasts/<id>            one forecast
POST /forecasts                 create (manual estimate)
PUT  /forecasts/<id>            update
DELETE /forecasts/<id>          delete
POST /forecasts/generate        moving-average estimate (preview, or save)
GET  /forecasts/status          rows of the vw_forecast_status view
GET  /forecasts/summary         rows of the vw_forecast_summary view
"""

from decimal import Decimal

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from errors import ApiError, commit_or_raise
from forecasting import (DEFAULT_WINDOW, MAX_WINDOW, MIN_WINDOW,
                         moving_average)
from models import Crop, Forecast, Season, db
from routes.common import (check_date_in_season, check_not_before_planting,
                           find_duplicate, lock_parent,
                           ensure_exists, get_or_404)
from serializers import forecast_dict, row_dict
from validators import (_FieldError, boolean, decimal, iso_date, query_args,
                        record_id, require_json_object, string, validate)

forecasts_bp = Blueprint("forecasts", __name__)

FORECAST_SCHEMA = {
    "crop_id": (record_id, True),
    "season_id": (record_id, True),
    "forecast_date": (iso_date, True),
    # DECIMAL(12,2) and CHECK (estimated_quantity >= 0)
    "estimated_quantity": (decimal(minimum=Decimal("0"),
                                   maximum=Decimal("9999999999.99")), True),
    "method": (string(100), True),
}

FORECAST_FILTERS = {
    "crop_id": record_id,
    "season_id": record_id,
    "variety_id": record_id,
    "lot_id": record_id,
    "date_from": iso_date,
    "date_to": iso_date,
}


def _window(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise _FieldError("must be an integer")
    if not MIN_WINDOW <= value <= MAX_WINDOW:
        raise _FieldError(f"must be between {MIN_WINDOW} and {MAX_WINDOW}")
    return value


GENERATE_SCHEMA = {
    "crop_id": (record_id, True),
    "season_id": (record_id, True),
    "forecast_date": (iso_date, True),
    "window": (_window, False),
    "save": (boolean, False),
}


def _view_rows(view_name):
    # The view names are constants of this module (never user input).
    rows = db.session.execute(text(f"SELECT * FROM {view_name}")).all()
    return [row_dict(row) for row in rows]


def _status_by_forecast():
    try:
        rows = _view_rows("vw_forecast_status")
    except Exception:  # view missing/changed: degrade gracefully
        current_app.logger.warning("vw_forecast_status could not be read",
                                   exc_info=True)
        db.session.rollback()
        return {}
    return {row.get("forecast_id"): row for row in rows
            if row.get("forecast_id") is not None}


def _ensure_unique(crop_id, forecast_date, current=None):
    """One forecast per crop and date (UNIQUE unique_crop_forecast_date).
    A repeated generation or creation is rejected with 409; an existing
    forecast is never overwritten silently (it can be edited with PUT)."""
    if current is not None and (current.crop_id, current.forecast_date) == (
            crop_id, forecast_date):
        return
    lock_parent(Crop, crop_id)
    existing = find_duplicate(Forecast, [
        Forecast.crop_id == crop_id,
        Forecast.forecast_date == forecast_date,
    ], exclude_id=current.forecast_id if current is not None else None)
    if existing is not None:
        raise ApiError(
            409,
            f"This forecast already exists for the selected crop and date "
            f"(forecast #{existing.forecast_id}, estimate "
            f"{existing.estimated_quantity})",
            details={"forecast_date": "This crop already has a forecast for "
                                      "this date"},
            code="DUPLICATE_RECORD",
        )


def _check_references(clean):
    ensure_exists(Crop, clean["crop_id"], "crop_id", "Crop")
    ensure_exists(Season, clean["season_id"], "season_id", "Season")
    season = db.session.get(Season, clean["season_id"])
    check_date_in_season(season, clean["forecast_date"], "forecast_date",
                         "forecast")
    crop = db.session.get(Crop, clean["crop_id"])
    check_not_before_planting(crop, clean["forecast_date"], "forecast_date",
                              "forecast")


# ==========================================
# GET: ALL FORECASTS (original endpoint, now with filters + status)
# ==========================================
@forecasts_bp.route("/forecasts", methods=["GET"])
def get_forecasts():
    filters = query_args(FORECAST_FILTERS)
    query = Forecast.query.join(Crop, Crop.crop_id == Forecast.crop_id)
    if "crop_id" in filters:
        query = query.filter(Forecast.crop_id == filters["crop_id"])
    if "season_id" in filters:
        query = query.filter(Forecast.season_id == filters["season_id"])
    if "variety_id" in filters:
        query = query.filter(Crop.variety_id == filters["variety_id"])
    if "lot_id" in filters:
        query = query.filter(Crop.lot_id == filters["lot_id"])
    if "date_from" in filters:
        query = query.filter(Forecast.forecast_date >= filters["date_from"])
    if "date_to" in filters:
        query = query.filter(Forecast.forecast_date <= filters["date_to"])
    forecasts = query.order_by(Forecast.forecast_id).all()
    status = _status_by_forecast()

    items = []
    for forecast in forecasts:
        item = forecast_dict(forecast)
        item["evaluation"] = status.get(forecast.forecast_id)
        items.append(item)

    return jsonify({"count": len(items), "forecasts": items}), 200


# ==========================================
# GET: VIEWS
# ==========================================
@forecasts_bp.route("/forecasts/status", methods=["GET"])
def get_forecast_status():
    rows = _view_rows("vw_forecast_status")
    return jsonify({"view": "vw_forecast_status", "count": len(rows),
                    "rows": rows}), 200


@forecasts_bp.route("/forecasts/summary", methods=["GET"])
def get_forecast_summary():
    rows = _view_rows("vw_forecast_summary")
    return jsonify({"view": "vw_forecast_summary", "count": len(rows),
                    "rows": rows}), 200


# ==========================================
# GET: ONE FORECAST
# ==========================================
@forecasts_bp.route("/forecasts/<int:forecast_id>", methods=["GET"])
def get_forecast(forecast_id):
    forecast = get_or_404(Forecast, forecast_id, "Forecast")
    item = forecast_dict(forecast)
    item["evaluation"] = _status_by_forecast().get(forecast_id)
    return jsonify({"forecast": item}), 200


# ==========================================
# POST: CREATE FORECAST
# ==========================================
@forecasts_bp.route("/forecasts", methods=["POST"])
def create_forecast():
    clean = validate(require_json_object(), FORECAST_SCHEMA)
    _check_references(clean)
    _ensure_unique(clean["crop_id"], clean["forecast_date"])
    forecast = Forecast(**clean)
    db.session.add(forecast)
    commit_or_raise(db.session)

    return jsonify({
        "message": "Forecast created successfully",
        "forecast": forecast_dict(forecast)
    }), 201


# ==========================================
# PUT: UPDATE FORECAST
# ==========================================
@forecasts_bp.route("/forecasts/<int:forecast_id>", methods=["PUT"])
def update_forecast(forecast_id):
    forecast = get_or_404(Forecast, forecast_id, "Forecast")
    clean = validate(require_json_object(), FORECAST_SCHEMA)
    _check_references(clean)
    _ensure_unique(clean["crop_id"], clean["forecast_date"],
                   current=forecast)
    for field, value in clean.items():
        setattr(forecast, field, value)
    commit_or_raise(db.session)
    db.session.refresh(forecast)

    return jsonify({
        "message": "Forecast updated successfully",
        "forecast": forecast_dict(forecast)
    }), 200


# ==========================================
# DELETE: DELETE FORECAST
# ==========================================
@forecasts_bp.route("/forecasts/<int:forecast_id>", methods=["DELETE"])
def delete_forecast(forecast_id):
    forecast = get_or_404(Forecast, forecast_id, "Forecast")
    db.session.delete(forecast)
    commit_or_raise(db.session)

    return jsonify({
        "message": "Forecast deleted successfully",
        "deleted_forecast": {"forecast_id": forecast_id}
    }), 200


# ==========================================
# POST: GENERATE FORECAST (moving average)
# ==========================================
@forecasts_bp.route("/forecasts/generate", methods=["POST"])
def generate_forecast():
    clean = validate(require_json_object(), GENERATE_SCHEMA)
    window = clean.get("window", DEFAULT_WINDOW)
    save = clean.get("save", False)

    _check_references(clean)
    result, estimate = moving_average(clean["crop_id"],
                                      clean["forecast_date"], window)
    crop = db.session.get(Crop, clean["crop_id"])
    season = db.session.get(Season, clean["season_id"])
    result.update({
        "crop_id": crop.crop_id,
        "crop_label": f"#{crop.crop_id} · {crop.variety.name} · "
                      f"{crop.lot.name}",
        "season_id": season.season_id,
        "season": season.name,
        "forecast_date": clean["forecast_date"].isoformat(),
        "saved": False,
    })

    if not save:
        # Tell the client before it tries to save whether this crop already
        # has a forecast for that date (saving it again would be refused).
        existing = Forecast.query.filter_by(
            crop_id=clean["crop_id"],
            forecast_date=clean["forecast_date"]).first()
        result["existing_forecast_id"] = (
            existing.forecast_id if existing is not None else None)
        return jsonify({"message": "Forecast estimate calculated",
                        "calculation": result}), 200

    _ensure_unique(clean["crop_id"], clean["forecast_date"])
    forecast = Forecast(
        crop_id=clean["crop_id"],
        season_id=clean["season_id"],
        forecast_date=clean["forecast_date"],
        estimated_quantity=estimate,
        method=result["method"],
    )
    db.session.add(forecast)
    commit_or_raise(db.session)
    result["saved"] = True

    return jsonify({
        "message": "Forecast generated and saved successfully",
        "calculation": result,
        "forecast": forecast_dict(forecast),
    }), 201
