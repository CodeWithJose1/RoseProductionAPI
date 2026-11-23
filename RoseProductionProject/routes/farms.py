"""Farm CRUD: /farms"""

from flask import Blueprint, jsonify

from errors import commit_or_raise
from models import Farm, Lot, db
from routes.common import (ensure_not_referenced, find_duplicate, get_or_404,
                           lock_table, normalized, raise_duplicate,
                           text_key)
from serializers import count_by, farm_dict, lot_dict
from validators import name_text, require_json_object, validate

farms_bp = Blueprint("farms", __name__)

FARM_SCHEMA = {
    "name": (name_text(100), True),
    "location": (name_text(150), True),
}


def _ensure_unique_farm(clean, current=None):
    """A farm is identified by its name and location (same name in another
    location is a different farm). Comparison ignores case and spacing."""
    if current is not None and (
            normalized(current.name) == normalized(clean["name"])
            and normalized(current.location) == normalized(clean["location"])):
        return  # keeping its own identifying values is always allowed
    lock_table(Farm)
    existing = find_duplicate(Farm, [
        text_key(Farm.name) == normalized(clean["name"]),
        text_key(Farm.location) == normalized(clean["location"]),
    ], exclude_id=current.farm_id if current is not None else None)
    if existing is not None:
        raise_duplicate(
            f"A farm named '{existing.name}' already exists in "
            f"'{existing.location}' (farm #{existing.farm_id})",
            {"name": "A farm with this name already exists at this location"},
        )


# ==========================================
# GET: ALL FARMS (original endpoint)
# ==========================================
@farms_bp.route("/farms", methods=["GET"])
def get_farms():
    farms = Farm.query.order_by(Farm.farm_id).all()
    lots = count_by(Lot.farm_id)

    return jsonify({
        "count": len(farms),
        "farms": [farm_dict(farm, lots.get(farm.farm_id, 0))
                  for farm in farms]
    }), 200


# ==========================================
# GET: ONE FARM (with its lots)
# ==========================================
@farms_bp.route("/farms/<int:farm_id>", methods=["GET"])
def get_farm(farm_id):
    farm = get_or_404(Farm, farm_id, "Farm")
    lots = sorted(farm.lots, key=lambda lot: lot.lot_id)
    data = farm_dict(farm, len(lots))
    data["lots"] = [lot_dict(lot) for lot in lots]
    data["total_area"] = round(sum(float(lot.area) for lot in lots), 2)
    return jsonify({"farm": data}), 200


# ==========================================
# POST: CREATE FARM
# ==========================================
@farms_bp.route("/farms", methods=["POST"])
def create_farm():
    clean = validate(require_json_object(), FARM_SCHEMA)
    _ensure_unique_farm(clean)
    farm = Farm(**clean)
    db.session.add(farm)
    commit_or_raise(db.session)

    return jsonify({
        "message": "Farm created successfully",
        "farm": farm_dict(farm, 0)
    }), 201


# ==========================================
# PUT: UPDATE FARM
# ==========================================
@farms_bp.route("/farms/<int:farm_id>", methods=["PUT"])
def update_farm(farm_id):
    farm = get_or_404(Farm, farm_id, "Farm")
    clean = validate(require_json_object(), FARM_SCHEMA)
    _ensure_unique_farm(clean, current=farm)
    farm.name = clean["name"]
    farm.location = clean["location"]
    commit_or_raise(db.session)

    return jsonify({
        "message": "Farm updated successfully",
        "farm": farm_dict(farm, len(farm.lots))
    }), 200


# ==========================================
# DELETE: DELETE FARM (only when it has no lots)
# ==========================================
@farms_bp.route("/farms/<int:farm_id>", methods=["DELETE"])
def delete_farm(farm_id):
    farm = get_or_404(Farm, farm_id, "Farm")
    ensure_not_referenced(
        [(Lot.query.filter_by(farm_id=farm_id).count(), "lot(s)")],
        "farm",
    )
    db.session.delete(farm)
    commit_or_raise(db.session)

    return jsonify({
        "message": "Farm deleted successfully",
        "deleted_farm": {"farm_id": farm_id}
    }), 200
