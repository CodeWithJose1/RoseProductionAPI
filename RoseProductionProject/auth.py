"""API authentication.

Two ways to authenticate a request to a protected endpoint:

1. ``X-API-Key`` header (original mechanism, used by scripts and curl).
2. GUI session: the operator signs in once on the GUI login form with the
   API key; the server validates it and issues a signed, HttpOnly,
   SameSite=Strict session cookie. The key itself is never stored in the
   browser, in JavaScript bundles or in Vite environment variables.

State-changing requests authenticated by the session cookie must also send
``X-Requested-With: RoseProductionGUI`` (CSRF protection: a cross-site
page cannot add custom headers without a CORS pre-flight, which this API
does not allow).
"""

import hashlib
import hmac
import time
from collections import defaultdict, deque

from flask import Blueprint, current_app, jsonify, request, session

from errors import error_response
from validators import require_json_object

GUI_HEADER = "X-Requested-With"
GUI_HEADER_VALUE = "RoseProductionGUI"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Endpoints reachable without credentials.
PUBLIC_ENDPOINTS = {
    "home",
    "auth.login",
    "auth.logout",
    "auth.status",
    "gui.index",
    "gui.index_redirect",
    "gui.files",
}

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

_failed_logins = defaultdict(deque)


def _key_matches(provided, expected):
    # Compare bytes: hmac.compare_digest raises TypeError for non-ASCII str.
    return hmac.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    )


def _key_fingerprint(expected):
    """Binds a session to the current API key (rotating the key logs out)."""
    secret = current_app.config["SECRET_KEY"].encode("utf-8")
    return hmac.new(secret, expected.encode("utf-8"),
                    hashlib.sha256).hexdigest()[:32]


def session_is_valid():
    expected = current_app.config.get("API_KEY")
    return bool(
        expected
        and session.get("authenticated") is True
        and session.get("key_fp") == _key_fingerprint(expected)
    )


def require_api_key():
    """before_request hook protecting every non-public endpoint."""

    # The home endpoint, the GUI files and the login endpoints are public.
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None

    # Fail closed if API_KEY is not configured.
    expected_key = current_app.config.get("API_KEY")
    if not expected_key:
        return jsonify({
            "error": "API authentication is not configured"
        }), 503

    provided_key = request.headers.get("X-API-Key")
    if provided_key is not None:
        if _key_matches(provided_key, expected_key):
            return None
        return jsonify({"error": "Unauthorized"}), 401

    if session_is_valid():
        if (request.method in UNSAFE_METHODS
                and request.headers.get(GUI_HEADER) != GUI_HEADER_VALUE):
            return error_response(
                403,
                "Forbidden: request did not come from the application GUI",
                code="CSRF_CHECK_FAILED",
            )
        return None

    return jsonify({"error": "Unauthorized"}), 401


# ----------------------------------------------------------------------
# GUI login / logout
# ----------------------------------------------------------------------

def _client_id():
    return request.remote_addr or "unknown"


def _too_many_failures():
    window = current_app.config["LOGIN_WINDOW_SECONDS"]
    limit = current_app.config["LOGIN_MAX_FAILURES"]
    attempts = _failed_logins[_client_id()]
    now = time.monotonic()
    while attempts and now - attempts[0] > window:
        attempts.popleft()
    return len(attempts) >= limit


@auth_bp.route("/login", methods=["POST"])
def login():
    expected_key = current_app.config.get("API_KEY")
    if not expected_key:
        return error_response(503, "API authentication is not configured")

    if _too_many_failures():
        response, status = error_response(
            429, "Too many failed attempts. Try again in a few minutes.",
            code="TOO_MANY_ATTEMPTS",
        )
        response.headers["Retry-After"] = str(
            current_app.config["LOGIN_WINDOW_SECONDS"]
        )
        return response, status

    data = require_json_object()
    provided = data.get("api_key")
    if not isinstance(provided, str) or not provided:
        return error_response(400, "The access key is required",
                              details={"api_key": "is required"},
                              code="VALIDATION_ERROR")

    if not _key_matches(provided, expected_key):
        _failed_logins[_client_id()].append(time.monotonic())
        return error_response(401, "Invalid access key",
                              code="INVALID_CREDENTIALS")

    _failed_logins.pop(_client_id(), None)
    session.clear()
    session.permanent = True
    session["authenticated"] = True
    session["key_fp"] = _key_fingerprint(expected_key)
    hours = current_app.config["PERMANENT_SESSION_LIFETIME"]
    return jsonify({
        "authenticated": True,
        "session_hours": hours.total_seconds() / 3600,
    }), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"authenticated": False}), 200


@auth_bp.route("/status", methods=["GET"])
def status():
    return jsonify({
        "authenticated": session_is_valid(),
        "auth_configured": bool(current_app.config.get("API_KEY")),
    }), 200
