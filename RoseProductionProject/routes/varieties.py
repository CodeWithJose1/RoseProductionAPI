"""RoseVariety CRUD: /varieties

POST, PUT and DELETE existed in the original app.py and were verified in
TC-15. They keep the same URLs, request fields, status codes, success
messages and response keys. Changes: validation errors now use the shared
format (400 + "details" per field), deleting a variety that still has
crops answers 409 instead of a generic 500, and GET /varieties/<id> is new.
"""

from flask import Blueprint, jsonify

from errors import commit_or_raise
from models import Crop, RoseVariety, db
from routes.common import (ensure_not_referenced, find_duplicate, get_or_404,
                           lock_table, normalized, raise_duplicate,
                           text_key)
from serializers import count_by, crop_dict, variety_dict
from validators import name_text, require_json_object, validate

varieties_bp = Blueprint("varieties", __name__)

VARIETY_SCHEMA = {
    "name": (name_text(100), True),
    "color": (name_text(50), True),
}


def _ensure_unique_variety(clean, current=None):
    """A rose variety is identified by its name (business rule confirmed by
    the project owner on 2026-11-23): two varieties may not share a name,
    whatever their colour. Comparison ignores case and spacing. There is no
    UNIQUE constraint in the database for this rule (existing varieties 6
    and 7 share a name), so the table lock below is what makes it safe
    against concurrent requests."""
    if current is not None and (
            normalized(current.name) == normalized(clean["name"])):
        return  # unchanged name: allowed even for pre-existing duplicates
    lock_table(RoseVariety)
    existing = find_duplicate(RoseVariety, [
        text_key(RoseVariety.name) == normalized(clean["name"]),
    ], exclude_id=current.variety_id if current is not None else None)
    if existing is not None:
        raise_duplicate(
            f"A rose variety with this name already exists: "
            f"'{existing.name}' ({existing.color}, variety "
            f"#{existing.variety_id})",
            {"name": "A rose variety with this name already exists"},
        )


# ==========================================
# GET: ALL ROSE VARIETIES (original endpoint)
# ==========================================
@varieties_bp.route("/varieties", methods=["GET"])
def get_varieties():
    varieties = RoseVariety.query.order_by(RoseVariety.variety_id).all()
    crops = count_by(Crop.variety_id)

    return jsonify({
        "count": len(varieties),
        "varieties": [
            variety_dict(variety, crops.get(variety.variety_id, 0))
            for variety in varieties
        ]
    }), 200


# ==========================================
# GET: ONE ROSE VARIETY
# ==========================================
@varieties_bp.route("/varieties/<int:variety_id>", methods=["GET"])
def get_variety(variety_id):
    variety = get_or_404(RoseVariety, variety_id, "Rose variety")
    crops = sorted(variety.crops, key=lambda crop: crop.crop_id)
    data = variety_dict(variety, len(crops))
    data["crops"] = [crop_dict(crop) for crop in crops]
    return jsonify({"variety": data}), 200


# ==========================================
# POST: CREATE ROSE VARIETY (original endpoint)
# ==========================================
@varieties_bp.route("/varieties", methods=["POST"])
def create_variety():
    clean = validate(require_json_object(), VARIETY_SCHEMA)
    _ensure_unique_variety(clean)
    variety = RoseVariety(name=clean["name"], color=clean["color"])
    db.session.add(variety)
    commit_or_raise(db.session)

    return jsonify({
        "message": "Rose variety created successfully",
        "variety": variety_dict(variety)
    }), 201


# ==========================================
# PUT: UPDATE ROSE VARIETY (original endpoint)
# ==========================================
@varieties_bp.route("/varieties/<int:variety_id>", methods=["PUT"])
def update_variety(variety_id):
    variety = get_or_404(RoseVariety, variety_id, "Rose variety")
    clean = validate(require_json_object(), VARIETY_SCHEMA)
    _ensure_unique_variety(clean, current=variety)
    variety.name = clean["name"]
    variety.color = clean["color"]
    commit_or_raise(db.session)

    return jsonify({
        "message": "Rose variety updated successfully",
        "variety": variety_dict(variety)
    }), 200


# ==========================================
# DELETE: DELETE ROSE VARIETY (original endpoint)
# ==========================================
@varieties_bp.route("/varieties/<int:variety_id>", methods=["DELETE"])
def delete_variety(variety_id):
    variety = get_or_404(RoseVariety, variety_id, "Rose variety")
    ensure_not_referenced(
        [(Crop.query.filter_by(variety_id=variety_id).count(), "crop(s)")],
        "rose variety",
    )
    db.session.delete(variety)
    commit_or_raise(db.session)

    return jsonify({
        "message": "Rose variety deleted successfully",
        "deleted_variety": {
            "variety_id": variety_id
        }
    }), 200
