"""Season CRUD: /seasons"""

from flask import Blueprint, jsonify

from errors import ApiError, commit_or_raise
from models import Forecast, Harvest, Season, db
from routes.common import (ensure_not_referenced, find_duplicate, get_or_404,
                           lock_table, normalized, raise_duplicate,
                           text_key)
from serializers import count_by, season_dict
from validators import iso_date, name_text, require_json_object, validate

seasons_bp = Blueprint("seasons", __name__)

SEASON_SCHEMA = {
    "name": (name_text(100), True),
    "start_date": (iso_date, True),
    "end_date": (iso_date, True),
}


def _validated_season_payload():
    clean = validate(require_json_object(), SEASON_SCHEMA)
    if clean["end_date"] < clean["start_date"]:
        raise ApiError(
            400, "The season end date must be on or after its start date",
            details={"end_date": "must be on or after start_date"},
            code="VALIDATION_ERROR",
        )
    return clean


def _ensure_unique_season(clean, current=None):
    """A season is identified by its name and its period. The same name may
    be used again for another period (e.g. a yearly "Valentines Day"), but
    two seasons with the same name and overlapping dates are the same
    season registered twice. Comparison of names ignores case and spacing."""
    if current is not None and (
            normalized(current.name) == normalized(clean["name"])
            and current.start_date == clean["start_date"]
            and current.end_date == clean["end_date"]):
        return
    lock_table(Season)
    existing = find_duplicate(Season, [
        text_key(Season.name) == normalized(clean["name"]),
        Season.start_date <= clean["end_date"],
        Season.end_date >= clean["start_date"],
    ], exclude_id=current.season_id if current is not None else None)
    if existing is not None:
        raise_duplicate(
            f"A season with these identifying attributes already exists: "
            f"'{existing.name}' from {existing.start_date.isoformat()} to "
            f"{existing.end_date.isoformat()} (season #{existing.season_id})",
            {"name": "A season with this name already exists for an "
                     "overlapping period"},
        )


# ==========================================
# GET: ALL SEASONS (original endpoint)
# ==========================================
@seasons_bp.route("/seasons", methods=["GET"])
def get_seasons():
    seasons = Season.query.order_by(Season.season_id).all()
    harvests = count_by(Harvest.season_id)
    forecasts = count_by(Forecast.season_id)

    return jsonify({
        "count": len(seasons),
        "seasons": [
            season_dict(season, harvests.get(season.season_id, 0),
                        forecasts.get(season.season_id, 0))
            for season in seasons
        ]
    }), 200


# ==========================================
# GET: ONE SEASON
# ==========================================
@seasons_bp.route("/seasons/<int:season_id>", methods=["GET"])
def get_season(season_id):
    season = get_or_404(Season, season_id, "Season")
    data = season_dict(season, len(season.harvests), len(season.forecasts))
    data["total_harvested"] = sum(h.quantity for h in season.harvests)
    return jsonify({"season": data}), 200


# ==========================================
# POST: CREATE SEASON
# ==========================================
@seasons_bp.route("/seasons", methods=["POST"])
def create_season():
    clean = _validated_season_payload()
    _ensure_unique_season(clean)
    season = Season(**clean)
    db.session.add(season)
    commit_or_raise(db.session)

    return jsonify({
        "message": "Season created successfully",
        "season": season_dict(season, 0, 0)
    }), 201


# ==========================================
# PUT: UPDATE SEASON
# ==========================================
@seasons_bp.route("/seasons/<int:season_id>", methods=["PUT"])
def update_season(season_id):
    season = get_or_404(Season, season_id, "Season")
    clean = _validated_season_payload()
    _ensure_unique_season(clean, current=season)

    # Shrinking a season must not leave harvests/forecasts outside it
    # (the triggers only validate rows when they are written).
    outside = [
        (Harvest.query.filter(
            Harvest.season_id == season_id,
            (Harvest.harvest_date < clean["start_date"])
            | (Harvest.harvest_date > clean["end_date"])).count(),
         "harvest record(s)"),
        (Forecast.query.filter(
            Forecast.season_id == season_id,
            (Forecast.forecast_date < clean["start_date"])
            | (Forecast.forecast_date > clean["end_date"])).count(),
         "forecast(s)"),
    ]
    blocking = [f"{count} {name}" for count, name in outside if count]
    if blocking:
        raise ApiError(
            409,
            "The new date range would leave " + " and ".join(blocking)
            + " of this season outside the season dates",
            details={"start_date": "conflicts with existing records",
                     "end_date": "conflicts with existing records"},
            code="SEASON_RANGE_CONFLICT",
        )

    season.name = clean["name"]
    season.start_date = clean["start_date"]
    season.end_date = clean["end_date"]
    commit_or_raise(db.session)

    return jsonify({
        "message": "Season updated successfully",
        "season": season_dict(season, len(season.harvests),
                              len(season.forecasts))
    }), 200


# ==========================================
# DELETE: DELETE SEASON (only without harvests/forecasts)
# ==========================================
@seasons_bp.route("/seasons/<int:season_id>", methods=["DELETE"])
def delete_season(season_id):
    season = get_or_404(Season, season_id, "Season")
    ensure_not_referenced(
        [
            (Harvest.query.filter_by(season_id=season_id).count(),
             "harvest record(s)"),
            (Forecast.query.filter_by(season_id=season_id).count(),
             "forecast(s)"),
        ],
        "season",
    )
    db.session.delete(season)
    commit_or_raise(db.session)

    return jsonify({
        "message": "Season deleted successfully",
        "deleted_season": {"season_id": season_id}
    }), 200
