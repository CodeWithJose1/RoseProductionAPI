"""Crop CRUD: /crops"""

from flask import Blueprint, jsonify

from errors import ApiError, commit_or_raise
from models import Crop, Forecast, Harvest, Lot, RoseVariety, db
from routes.common import (ensure_exists, ensure_not_referenced,
                           find_duplicate, get_or_404, lock_parent,
                           raise_duplicate)
from serializers import count_by, crop_dict
from validators import (iso_date, query_args, record_id, require_json_object,
                        validate)

crops_bp = Blueprint("crops", __name__)

CROP_SCHEMA = {
    "lot_id": (record_id, True),
    "variety_id": (record_id, True),
    "planting_date": (iso_date, True),
}


# ==========================================
# GET: ALL CROPS (original endpoint; optional ?lot_id=&variety_id=)
# ==========================================
@crops_bp.route("/crops", methods=["GET"])
def get_crops():
    filters = query_args({"lot_id": record_id, "variety_id": record_id})
    query = Crop.query
    if "lot_id" in filters:
        query = query.filter(Crop.lot_id == filters["lot_id"])
    if "variety_id" in filters:
        query = query.filter(Crop.variety_id == filters["variety_id"])
    crops = query.order_by(Crop.crop_id).all()
    harvests = count_by(Harvest.crop_id)
    forecasts = count_by(Forecast.crop_id)

    return jsonify({
        "count": len(crops),
        "crops": [
            crop_dict(crop, harvests.get(crop.crop_id, 0),
                      forecasts.get(crop.crop_id, 0))
            for crop in crops
        ]
    }), 200


# ==========================================
# GET: ONE CROP
# ==========================================
@crops_bp.route("/crops/<int:crop_id>", methods=["GET"])
def get_crop(crop_id):
    crop = get_or_404(Crop, crop_id, "Crop")
    data = crop_dict(crop, len(crop.harvests), len(crop.forecasts))
    data["total_harvested"] = sum(h.quantity for h in crop.harvests)
    return jsonify({"crop": data}), 200


def _validated_crop_payload():
    clean = validate(require_json_object(), CROP_SCHEMA)
    ensure_exists(Lot, clean["lot_id"], "lot_id", "Lot")
    ensure_exists(RoseVariety, clean["variety_id"], "variety_id",
                  "Rose variety")
    return clean



def _ensure_unique_crop(clean, current=None):
    """A crop is one planting of a variety in a lot. The same variety may be
    planted again in the same lot on another date (a new crop cycle), but
    the same lot + variety + planting date is the same crop."""
    key = (clean["lot_id"], clean["variety_id"], clean["planting_date"])
    if current is not None and key == (
            current.lot_id, current.variety_id, current.planting_date):
        return
    lock_parent(Lot, clean["lot_id"])
    existing = find_duplicate(Crop, [
        Crop.lot_id == clean["lot_id"],
        Crop.variety_id == clean["variety_id"],
        Crop.planting_date == clean["planting_date"],
    ], exclude_id=current.crop_id if current is not None else None)
    if existing is not None:
        raise_duplicate(
            f"This crop already exists: variety '{existing.variety.name}' "
            f"was planted in '{existing.lot.name}' on "
            f"{existing.planting_date.isoformat()} (crop "
            f"#{existing.crop_id})",
            {"planting_date": "This variety is already planted in this lot "
                              "on this date"},
        )

# ==========================================
# POST: CREATE CROP
# ==========================================
@crops_bp.route("/crops", methods=["POST"])
def create_crop():
    clean = _validated_crop_payload()
    _ensure_unique_crop(clean)
    crop = Crop(**clean)
    db.session.add(crop)
    commit_or_raise(db.session)

    return jsonify({
        "message": "Crop created successfully",
        "crop": crop_dict(crop, 0, 0)
    }), 201


# ==========================================
# PUT: UPDATE CROP
# ==========================================
@crops_bp.route("/crops/<int:crop_id>", methods=["PUT"])
def update_crop(crop_id):
    crop = get_or_404(Crop, crop_id, "Crop")
    clean = _validated_crop_payload()
    _ensure_unique_crop(clean, current=crop)

    # Moving the planting date later must not leave harvests or forecasts
    # of this crop dated before the planting (unchanged dates are allowed
    # so that existing records can still be edited).
    if clean["planting_date"] > crop.planting_date:
        earlier = [
            (Harvest.query.filter(
                Harvest.crop_id == crop_id,
                Harvest.harvest_date < clean["planting_date"]).count(),
             "harvest record(s)"),
            (Forecast.query.filter(
                Forecast.crop_id == crop_id,
                Forecast.forecast_date < clean["planting_date"]).count(),
             "forecast(s)"),
        ]
        blocking = [f"{n} {name}" for n, name in earlier if n]
        if blocking:
            raise ApiError(
                409,
                "The new planting date would leave " + " and ".join(blocking)
                + " of this crop dated before the planting",
                details={"planting_date": "conflicts with existing records"},
                code="PLANTING_DATE_CONFLICT",
            )

    crop.lot_id = clean["lot_id"]
    crop.variety_id = clean["variety_id"]
    crop.planting_date = clean["planting_date"]
    commit_or_raise(db.session)
    db.session.refresh(crop)

    return jsonify({
        "message": "Crop updated successfully",
        "crop": crop_dict(crop, len(crop.harvests), len(crop.forecasts))
    }), 200


# ==========================================
# DELETE: DELETE CROP (only without harvests/forecasts)
# ==========================================
@crops_bp.route("/crops/<int:crop_id>", methods=["DELETE"])
def delete_crop(crop_id):
    crop = get_or_404(Crop, crop_id, "Crop")
    ensure_not_referenced(
        [
            (Harvest.query.filter_by(crop_id=crop_id).count(),
             "harvest record(s)"),
            (Forecast.query.filter_by(crop_id=crop_id).count(),
             "forecast(s)"),
        ],
        "crop",
    )
    db.session.delete(crop)
    commit_or_raise(db.session)

    return jsonify({
        "message": "Crop deleted successfully",
        "deleted_crop": {"crop_id": crop_id}
    }), 200
