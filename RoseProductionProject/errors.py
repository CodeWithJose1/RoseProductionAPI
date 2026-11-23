"""Consistent JSON errors and translation of MySQL errors.

Every error returned by the API has the shape::

    {"error": "Human readable message",
     "code": "MACHINE_READABLE_CODE",      # optional
     "details": {"field": "problem"}}      # optional

The "error" key is kept as a plain string so that clients written for the
original API keep working.
"""

import re

from flask import jsonify
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from werkzeug.exceptions import HTTPException


class ApiError(Exception):
    """An error that should be returned to the client as JSON."""

    def __init__(self, status, message, details=None, code=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details
        self.code = code


def error_response(status, message, details=None, code=None):
    body = {"error": message}
    if code:
        body["code"] = code
    if details:
        body["details"] = details
    return jsonify(body), status


# ----------------------------------------------------------------------
# MySQL error translation
# ----------------------------------------------------------------------

_CHECK_MESSAGES = {
    "Season_chk_1": "The season end date must be on or after its start date",
    "Harvest_chk_1": "The harvest quantity must be greater than zero",
    "Forecast_chk_1": "The estimated quantity cannot be negative",
}

_UNIQUE_MESSAGES = {
    "unique_crop_forecast_date": (
        "This forecast already exists for the selected crop and date"
    ),
    # Added on 2026-11-23 (approved schema change, see
    # scripts/db/add_unique_constraints.sh).
    "unique_farm_name_location": (
        "A farm with this name already exists at this location"
    ),
    "unique_lot_farm_name": "This lot already exists in the selected farm",
    "unique_season_name_dates": (
        "A season with these identifying attributes already exists"
    ),
    "unique_harvest_crop_date": (
        "This crop already has a harvest record on this date"
    ),
}


# Form field that a UNIQUE violation is shown on in the GUI.
_UNIQUE_FIELDS = {
    "unique_crop_forecast_date": "forecast_date",
    "unique_farm_name_location": "name",
    "unique_lot_farm_name": "name",
    "unique_season_name_dates": "name",
    "unique_harvest_crop_date": "harvest_date",
}


def _mysql_code_and_message(exc):
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", None) or ()
    code = args[0] if args and isinstance(args[0], int) else None
    message = args[1] if len(args) > 1 else str(orig or exc)
    return code, str(message)


def translate_db_error(exc):
    """Convert a SQLAlchemy/PyMySQL exception into an ApiError."""

    code, message = _mysql_code_and_message(exc)

    if code == 1452:
        return ApiError(
            400,
            "A referenced record does not exist",
            code="FOREIGN_KEY_NOT_FOUND",
        )

    if code == 1451:
        return ApiError(
            409,
            "This record is referenced by other records and cannot be "
            "deleted or changed",
            code="RECORD_IN_USE",
        )

    if code == 1062:
        for key, text in _UNIQUE_MESSAGES.items():
            if key in message:
                field = _UNIQUE_FIELDS.get(key)
                return ApiError(409, text,
                                details={field: text} if field else None,
                                code="DUPLICATE_RECORD")
        return ApiError(409, "Duplicate record", code="DUPLICATE_RECORD")

    if code == 3819:
        match = re.search(r"'([^']+)'", message)
        name = match.group(1) if match else ""
        return ApiError(
            400,
            _CHECK_MESSAGES.get(
                name, "The data violates a database CHECK constraint"
            ),
            code="CHECK_CONSTRAINT_VIOLATION",
        )

    if code == 1644:
        # Raised by SIGNAL in the season-validation triggers; the trigger
        # message is written for users, so it is returned as is.
        return ApiError(400, message, code="DATABASE_RULE_VIOLATION")

    if code in (1048, 1364):
        return ApiError(400, "A required field is missing",
                        code="VALIDATION_ERROR")

    if code in (1406, 1264, 1292, 1366, 1265):
        return ApiError(400, "A field has an invalid or out-of-range value",
                        code="VALIDATION_ERROR")

    if code == 1213:
        # InnoDB deadlock: the transaction was rolled back; nothing written.
        return ApiError(409, "The record was being changed by another "
                        "request at the same time; please try again",
                        code="CONCURRENT_UPDATE")

    if code in (1045, 2002, 2003, 2006, 2013, 1040, 1205):
        return ApiError(503, "The database is not available",
                        code="DATABASE_UNAVAILABLE")

    return ApiError(500, "Database error", code="DATABASE_ERROR")


def commit_or_raise(session):
    """Commit the current transaction or roll back and raise ApiError."""
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise translate_db_error(exc) from exc


# ----------------------------------------------------------------------
# Flask handlers
# ----------------------------------------------------------------------

def register_error_handlers(app, db):

    @app.errorhandler(ApiError)
    def handle_api_error(exc):
        return error_response(exc.status, exc.message, exc.details, exc.code)

    @app.errorhandler(SQLAlchemyError)
    def handle_db_error(exc):
        db.session.rollback()
        api_error = translate_db_error(exc)
        if api_error.status >= 500 and not isinstance(exc, DBAPIError):
            app.logger.exception("Unexpected database error")
        return error_response(
            api_error.status, api_error.message, api_error.details,
            api_error.code
        )

    @app.errorhandler(HTTPException)
    def handle_http_error(exc):
        messages = {
            400: "Bad request",
            404: "Resource not found",
            405: "Method not allowed",
            413: "Request body too large",
            415: "Unsupported media type",
        }
        return error_response(
            exc.code or 500,
            messages.get(exc.code, exc.name),
            code=exc.name.upper().replace(" ", "_"),
        )

    @app.errorhandler(Exception)
    def handle_unexpected(exc):
        app.logger.exception("Unhandled error")
        try:
            db.session.rollback()
        except Exception:  # pragma: no cover - best effort
            pass
        return error_response(500, "Internal server error",
                              code="INTERNAL_ERROR")
