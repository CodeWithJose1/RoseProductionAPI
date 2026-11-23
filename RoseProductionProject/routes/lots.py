"""Lot CRUD: /lots"""

from decimal import Decimal

from flask import Blueprint, jsonify

from errors import commit_or_raise
from models import Crop, Farm, Lot, db
from routes.common import (ensure_exists, ensure_not_referenced,
                           find_duplicate, get_or_404, lock_parent,
                           normalized, raise_duplicate, text_key)
from serializers import count_by, crop_dict, lot_dict
from validators import (decimal, name_text, query_args, record_id,
                        require_json_object, validate)

lots_bp = Blueprint("lots", __name__)

LOT_SCHEMA = {
    "farm_id": (record_id, True),
    "name": (name_text(100), True),
    # DECIMAL(10,2): at most 99,999,999.99. A cultivation area must be > 0.
    "area": (decimal(minimum=Decimal("0"), exclusive_minimum=True,
                     maximum=Decimal("99999999.99")), True),
}



def _ensure_unique_lot(clean, current=None):
    """A lot name must be unique inside its farm ("Lot A" may exist in two
    different farms). Comparison ignores case and spacing."""
    if current is not None and current.farm_id == clean["farm_id"] and (
            normalized(current.name) == normalized(clean["name"])):
        return
    lock_parent(Farm, clean["farm_id"])
    existing = find_duplicate(Lot, [
        Lot.farm_id == clean["farm_id"],
        text_key(Lot.name) == normalized(clean["name"]),
    ], exclude_id=current.lot_id if current is not None else None)
    if existing is not None:
        raise_duplicate(
            f"This lot already exists in the selected farm: "
            f"'{existing.name}' (lot #{existing.lot_id})",
            {"name": "A lot with this name already exists in the selected "
                     "farm"},
        )

# ==========================================
# GET: ALL LOTS (original endpoint; optional ?farm_id=)
# ==========================================
@lots_bp.route("/lots", methods=["GET"])
def get_lots():
    filters = query_args({"farm_id": record_id})
    query = Lot.query
    if "farm_id" in filters:
        query = query.filter(Lot.farm_id == filters["farm_id"])
    lots = query.order_by(Lot.lot_id).all()
    crops = count_by(Crop.lot_id)

    return jsonify({
        "count": len(lots),
        "lots": [lot_dict(lot, crops.get(lot.lot_id, 0)) for lot in lots]
    }), 200


# ==========================================
# GET: ONE LOT (with its crops)
# ==========================================
@lots_bp.route("/lots/<int:lot_id>", methods=["GET"])
def get_lot(lot_id):
    lot = get_or_404(Lot, lot_id, "Lot")
    crops = sorted(lot.crops, key=lambda crop: crop.crop_id)
    data = lot_dict(lot, len(crops))
    data["crops"] = [crop_dict(crop) for crop in crops]
    return jsonify({"lot": data}), 200


# ==========================================
# POST: CREATE LOT
# ==========================================
@lots_bp.route("/lots", methods=["POST"])
def create_lot():
    clean = validate(require_json_object(), LOT_SCHEMA)
    ensure_exists(Farm, clean["farm_id"], "farm_id", "Farm")
    _ensure_unique_lot(clean)
    lot = Lot(**clean)
    db.session.add(lot)
    commit_or_raise(db.session)

    return jsonify({
        "message": "Lot created successfully",
        "lot": lot_dict(lot, 0)
    }), 201


# ==========================================
# PUT: UPDATE LOT
# ==========================================
@lots_bp.route("/lots/<int:lot_id>", methods=["PUT"])
def update_lot(lot_id):
    lot = get_or_404(Lot, lot_id, "Lot")
    clean = validate(require_json_object(), LOT_SCHEMA)
    ensure_exists(Farm, clean["farm_id"], "farm_id", "Farm")
    _ensure_unique_lot(clean, current=lot)
    lot.farm_id = clean["farm_id"]
    lot.name = clean["name"]
    lot.area = clean["area"]
    commit_or_raise(db.session)
    db.session.refresh(lot)

    return jsonify({
        "message": "Lot updated successfully",
        "lot": lot_dict(lot, len(lot.crops))
    }), 200


# ==========================================
# DELETE: DELETE LOT (only when it has no crops)
# ==========================================
@lots_bp.route("/lots/<int:lot_id>", methods=["DELETE"])
def delete_lot(lot_id):
    lot = get_or_404(Lot, lot_id, "Lot")
    ensure_not_referenced(
        [(Crop.query.filter_by(lot_id=lot_id).count(), "crop(s)")],
        "lot",
    )
    db.session.delete(lot)
    commit_or_raise(db.session)

    return jsonify({
        "message": "Lot deleted successfully",
        "deleted_lot": {"lot_id": lot_id}
    }), 200
