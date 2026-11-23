"""Input validation helpers for JSON request bodies and query strings.

Each validator returns the cleaned value or raises _FieldError; ``validate``
collects all field problems and raises one ApiError(400) with ``details``.
"""

import math
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from flask import request

from errors import ApiError

MYSQL_INT_MAX = 2_147_483_647


class _FieldError(Exception):
    pass


def require_json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "A valid JSON object is required",
                       code="INVALID_JSON")
    return data


# ----------------------------------------------------------------------
# Field validators
# ----------------------------------------------------------------------

def string(max_length):
    def check(value):
        if not isinstance(value, str):
            raise _FieldError("must be a string")
        value = value.strip()
        if not value:
            raise _FieldError("cannot be empty")
        if len(value) > max_length:
            raise _FieldError(f"must be at most {max_length} characters")
        return value
    return check


def name_text(max_length):
    """A name-like text: trimmed and with internal runs of whitespace
    collapsed to one space ("  Lot   A " -> "Lot A"), so that values that
    only differ in spacing are stored identically. Case is kept as typed;
    duplicate checks compare case-insensitively (see routes/common.py)."""
    base = string(max_length)

    def check(value):
        value = base(value)
        return " ".join(value.split())
    return check


def _as_int(value):
    if isinstance(value, bool):
        raise _FieldError("must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    raise _FieldError("must be an integer")


def record_id(value):
    value = _as_int(value)
    if value < 1 or value > MYSQL_INT_MAX:
        raise _FieldError("must be a positive identifier")
    return value


def positive_int(maximum=MYSQL_INT_MAX):
    def check(value):
        value = _as_int(value)
        if value <= 0:
            raise _FieldError("must be greater than zero")
        if value > maximum:
            raise _FieldError(f"must be at most {maximum}")
        return value
    return check


def decimal(minimum=None, maximum=None, exclusive_minimum=False, places=2):
    quantum = Decimal(1).scaleb(-places)

    def check(value):
        if isinstance(value, bool) or not isinstance(
            value, (int, float, str)
        ):
            raise _FieldError("must be a number")
        if isinstance(value, float) and not math.isfinite(value):
            raise _FieldError("must be a finite number")
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            raise _FieldError("must be a number") from None
        if not number.is_finite():
            raise _FieldError("must be a finite number")
        number = number.quantize(quantum, rounding=ROUND_HALF_UP)
        if minimum is not None:
            if exclusive_minimum and number <= minimum:
                raise _FieldError(f"must be greater than {minimum}")
            if not exclusive_minimum and number < minimum:
                raise _FieldError(f"must be at least {minimum}")
        if maximum is not None and number > maximum:
            raise _FieldError(f"must be at most {maximum}")
        return number
    return check


def iso_date(value):
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or len(value.strip()) != 10:
        raise _FieldError("must be a date in YYYY-MM-DD format")
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError:
        raise _FieldError("must be a valid date in YYYY-MM-DD format") \
            from None
    if parsed.year < 1900 or parsed.year > 2200:
        raise _FieldError("must be between the years 1900 and 2200")
    return parsed


def boolean(value):
    if isinstance(value, bool):
        return value
    raise _FieldError("must be true or false")


# ----------------------------------------------------------------------
# Schema validation
# ----------------------------------------------------------------------

def validate(data, schema, partial=False):
    """Validate ``data`` against ``schema``.

    ``schema`` maps field name -> (validator, required). With
    ``partial=True`` missing fields are skipped (used for optional args).
    """
    clean, errors = {}, {}
    for field, (check, required) in schema.items():
        if field not in data or data[field] is None:
            if required and not partial:
                errors[field] = "is required"
            continue
        try:
            clean[field] = check(data[field])
        except _FieldError as exc:
            errors[field] = str(exc)
    if errors:
        raise ApiError(400, "Validation failed", details=errors,
                       code="VALIDATION_ERROR")
    return clean


def query_args(schema):
    """Validate optional query-string filters with the same validators."""
    raw = {key: request.args.get(key) for key in schema
           if request.args.get(key) not in (None, "")}
    return validate(raw, {k: (v, False) for k, v in schema.items()})
