"""Harvest CRUD: /harvests

Filters on GET /harvests (all optional, combinable):
    crop_id, season_id, variety_id, lot_id, date_from, date_to
"""

from datetime import date

from flask import Blueprint, jsonify

from errors import ApiError, commit_or_raise
from models import Crop, Harvest, Season, db
from routes.common import (check_date_in_season, check_not_before_planting,
                           ensure_exists, find_duplicate, get_or_404,
                           lock_parent)
from serializers import harvest_dict
from validators import (iso_date, positive_int, query_args, record_id,
                        require_json_object, validate)

harvests_bp = Blueprint("harvests", __name__)

HARVEST_SCHEMA = {
    "crop_id": (record_id, True),
    "season_id": (record_id, True),
    "harvest_date": (iso_date, True),
    "quantity": (positive_int(), True),
}

HARVEST_FILTERS = {
    "crop_id": record_id,
    "season_id": record_id,
    "variety_id": record_id,
    "lot_id": record_id,
    "date_from": iso_date,
    "date_to": iso_date,
}


def filtered_harvest_query(filters):
    """Harvest query honoring the standard filters (shared with /stats)."""
    query = Harvest.query.join(Crop, Crop.crop_id == Harvest.crop_id)
    if "crop_id" in filters:
        query = query.filter(Harvest.crop_id == filters["crop_id"])
    if "season_id" in filters:
        query = query.filter(Harvest.season_id == filters["season_id"])
    if "variety_id" in filters:
        query = query.filter(Crop.variety_id == filters["variety_id"])
    if "lot_id" in filters:
        query = query.filter(Crop.lot_id == filters["lot_id"])
    if "date_from" in filters:
        query = query.filter(Harvest.harvest_date >= filters["date_from"])
    if "date_to" in filters:
        query = query.filter(Harvest.harvest_date <= filters["date_to"])
    return query


def parse_harvest_filters():
    filters = query_args(HARVEST_FILTERS)
    if ("date_from" in filters and "date_to" in filters
            and filters["date_from"] > filters["date_to"]):
        raise ApiError(400, "date_from must be on or before date_to",
                       details={"date_to": "must be on or after date_from"},
                       code="VALIDATION_ERROR")
    return filters


# ==========================================
# GET: ALL HARVESTS (original endpoint, now with optional filters)
# ==========================================
@harvests_bp.route("/harvests", methods=["GET"])
def get_harvests():
    filters = parse_harvest_filters()
    harvests = filtered_harvest_query(filters).order_by(
        Harvest.harvest_id
    ).all()

    return jsonify({
        "count": len(harvests),
        "total_quantity": sum(h.quantity for h in harvests),
        "harvests": [harvest_dict(harvest) for harvest in harvests]
    }), 200


# ==========================================
# GET: ONE HARVEST
# ==========================================
@harvests_bp.route("/harvests/<int:harvest_id>", methods=["GET"])
def get_harvest(harvest_id):
    harvest = get_or_404(Harvest, harvest_id, "Harvest")
    return jsonify({"harvest": harvest_dict(harvest)}), 200


def _validated_harvest_payload(harvest_id=None):
    """Validate a harvest body.

    Besides the database rules (FKs, quantity > 0, date inside the season)
    the API rejects records that would be inconsistent production data:
    a harvest before its crop was planted, a harvest dated in the future,
    and a second harvest for the same crop on the same day (one daily
    record per crop; duplicates would also be double-counted by the
    vw_forecast_status / vw_forecast_summary views).
    """
    clean = validate(require_json_object(), HARVEST_SCHEMA)
    ensure_exists(Crop, clean["crop_id"], "crop_id", "Crop")
    ensure_exists(Season, clean["season_id"], "season_id", "Season")
    crop = db.session.get(Crop, clean["crop_id"])
    season = db.session.get(Season, clean["season_id"])
    harvest_date = clean["harvest_date"]
    check_date_in_season(season, harvest_date, "harvest_date", "harvest")
    check_not_before_planting(crop, harvest_date, "harvest_date", "harvest")

    today = date.today()
    if harvest_date > today:
        raise ApiError(
            400,
            f"A harvest cannot be registered for a future date "
            f"({harvest_date.isoformat()}; today is {today.isoformat()})",
            details={"harvest_date": "cannot be later than today"},
            code="FUTURE_HARVEST_DATE",
        )

    current = db.session.get(Harvest, harvest_id) if harvest_id else None
    if current is None or (current.crop_id, current.harvest_date) != (
            clean["crop_id"], harvest_date):
        # One daily record per crop (business rule confirmed on
        # 2026-11-23; enforced in the database by unique_harvest_crop_date
        # once approved and applied). The crop row lock serializes
        # concurrent registrations for the same crop.
        lock_parent(Crop, clean["crop_id"])
        existing = find_duplicate(Harvest, [
            Harvest.crop_id == clean["crop_id"],
            Harvest.harvest_date == harvest_date,
        ], exclude_id=harvest_id)
        if existing is not None:
            raise ApiError(
                409,
                f"Crop #{clean['crop_id']} already has a harvest record on "
                f"{harvest_date.isoformat()} (harvest "
                f"#{existing.harvest_id}); edit that record instead",
                details={"harvest_date":
                         "This crop already has a harvest on this date"},
                code="DUPLICATE_RECORD",
            )
    return clean


# ==========================================
# POST: CREATE HARVEST
# ==========================================
@harvests_bp.route("/harvests", methods=["POST"])
def create_harvest():
    harvest = Harvest(**_validated_harvest_payload())
    db.session.add(harvest)
    commit_or_raise(db.session)

    return jsonify({
        "message": "Harvest created successfully",
        "harvest": harvest_dict(harvest)
    }), 201


# ==========================================
# PUT: UPDATE HARVEST
# ==========================================
@harvests_bp.route("/harvests/<int:harvest_id>", methods=["PUT"])
def update_harvest(harvest_id):
    harvest = get_or_404(Harvest, harvest_id, "Harvest")
    clean = _validated_harvest_payload(harvest_id)
    for field, value in clean.items():
        setattr(harvest, field, value)
    commit_or_raise(db.session)
    db.session.refresh(harvest)

    return jsonify({
        "message": "Harvest updated successfully",
        "harvest": harvest_dict(harvest)
    }), 200


# ==========================================
# DELETE: DELETE HARVEST
# ==========================================
@harvests_bp.route("/harvests/<int:harvest_id>", methods=["DELETE"])
def delete_harvest(harvest_id):
    harvest = get_or_404(Harvest, harvest_id, "Harvest")
    db.session.delete(harvest)
    commit_or_raise(db.session)

    return jsonify({
        "message": "Harvest deleted successfully",
        "deleted_harvest": {"harvest_id": harvest_id}
    }), 200
