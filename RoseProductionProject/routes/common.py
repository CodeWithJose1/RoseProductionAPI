"""Helpers shared by the resource blueprints."""

from errors import ApiError
from models import db


def get_or_404(model, record_id, label):
    record = db.session.get(model, record_id)
    if record is None:
        raise ApiError(404, f"{label} not found", code="NOT_FOUND")
    return record


def ensure_exists(model, record_id, field, label):
    """Validate a foreign key before writing (clear 400 instead of 1452)."""
    if db.session.get(model, record_id) is None:
        raise ApiError(
            400,
            f"{label} {record_id} does not exist",
            details={field: f"{label.lower()} {record_id} does not exist"},
            code="FOREIGN_KEY_NOT_FOUND",
        )


def ensure_not_referenced(references, label):
    """Refuse a delete when dependent rows exist (409 Conflict).

    ``references`` is a list of (count, dependent_label) tuples.
    """
    blocking = [f"{count} {name}" for count, name in references if count]
    if blocking:
        raise ApiError(
            409,
            f"Cannot delete this {label}: it is still referenced by "
            + ", ".join(blocking)
            + ". Delete or reassign those records first.",
            code="RECORD_IN_USE",
        )


def check_date_in_season(season, value, field, label):
    """Mirror of the database triggers, to give a clear field error."""
    if not (season.start_date <= value <= season.end_date):
        raise ApiError(
            400,
            f"The {label} date {value.isoformat()} is outside the season "
            f"'{season.name}' ({season.start_date.isoformat()} to "
            f"{season.end_date.isoformat()})",
            details={field: (
                f"must be between {season.start_date.isoformat()} and "
                f"{season.end_date.isoformat()}"
            )},
            code="DATE_OUTSIDE_SEASON",
        )


def check_not_before_planting(crop, value, field, label):
    """A crop cannot be harvested (or forecast) before it was planted."""
    if value < crop.planting_date:
        raise ApiError(
            400,
            f"The {label} date {value.isoformat()} is before the planting "
            f"date of crop #{crop.crop_id} "
            f"({crop.planting_date.isoformat()})",
            details={field: (
                f"must be on or after the planting date "
                f"{crop.planting_date.isoformat()}"
            )},
            code="DATE_BEFORE_PLANTING",
        )


# ----------------------------------------------------------------------
# Duplicate prevention (concurrency-safe)
# ----------------------------------------------------------------------
#
# Each write that must be unique follows the same three steps inside the
# request's transaction:
#
#   1. lock_parent()/lock_table()  - take an exclusive row lock that every
#      writer of the same group must also take (the parent row, e.g. the
#      farm of a lot, or the first row of the table for top-level
#      entities). Concurrent requests for the same group therefore run one
#      after the other; the lock is released by COMMIT/ROLLBACK.
#   2. find_duplicate()            - a locking read (FOR SHARE), which
#      always sees the latest committed rows, so the second request sees
#      the row inserted by the first one.
#   3. INSERT/UPDATE + commit; UNIQUE constraints in the database (where
#      they exist) are the final guarantee and are translated to 409.

from sqlalchemy import func, select  # noqa: E402


def normalized(value):
    """Identity key of a text value: collapsed spaces, case-insensitive."""
    return " ".join(str(value).split()).lower()


def text_key(column):
    """SQL expression equivalent to normalized() for a text column.

    The comparison also uses the column collation (utf8mb4_unicode_ci), so
    it is case-insensitive like the database UNIQUE indexes.
    """
    return func.lower(func.trim(
        func.regexp_replace(column, "[[:space:]]+", " ")))


def lock_parent(model, record_id):
    """Exclusive lock on one existing row (serializes writers of a group)."""
    pk = model.__mapper__.primary_key[0]
    db.session.execute(
        select(pk).where(pk == record_id).with_for_update()
    ).first()


def lock_table(model):
    """Exclusive lock on the first row of a table (serializes writers of a
    top-level entity that has no parent row). On an empty table there is
    nothing to lock; the database UNIQUE constraint, where present, still
    protects the first insert."""
    pk = model.__mapper__.primary_key[0]
    db.session.execute(
        select(pk).order_by(pk).limit(1).with_for_update()
    ).first()


def find_duplicate(model, criteria, exclude_id=None):
    """Return an existing row matching ``criteria`` (latest committed data)
    other than ``exclude_id``, or None."""
    pk = model.__mapper__.primary_key[0]
    stmt = select(model).where(*criteria)
    if exclude_id is not None:
        stmt = stmt.where(pk != exclude_id)
    stmt = stmt.order_by(pk).limit(1).with_for_update(read=True)
    return db.session.execute(stmt).scalars().first()


def raise_duplicate(message, details):
    raise ApiError(409, message, details=details, code="DUPLICATE_RECORD")
