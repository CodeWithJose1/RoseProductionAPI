
"""Rose Production Management and Forecasting System - Flask REST API.

Entry point. Run with ``python app.py`` (http://127.0.0.1:7003).

Structure
---------
app.py          application factory, security headers, public home route
auth.py         X-API-Key authentication + GUI session login
errors.py       JSON error format and MySQL error translation
validators.py   request validation
serializers.py  model -> JSON
forecasting.py  moving-average forecast
routes/         one blueprint per resource (+ /stats and the GUI at /app/)

The seven original GET list endpoints and the original POST/PUT/DELETE
/varieties endpoints were moved from this file into routes/ without
changing their URLs or response keys.
"""

from flask import Flask, jsonify, request

from auth import auth_bp, require_api_key
from config import Config
from errors import register_error_handlers
from models import db
from routes import ALL_BLUEPRINTS

API_VERSION = "1.2.0"

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


def create_app(config_object=Config):
    app = Flask(__name__, static_folder=None)
    app.config.from_object(config_object)
    app.json.sort_keys = False

    db.init_app(app)

    # ==========================================
    # API KEY AUTHENTICATION (X-API-Key or GUI session)
    # ==========================================
    app.before_request(require_api_key)

    # ==========================================
    # HOME (public)
    # ==========================================
    @app.route("/", methods=["GET"])
    def home():
        return jsonify({
            "message": "Rose Production API is running",
            "database": "RoseProductionDB",
            "gui": "/app/",
            "version": API_VERSION
        }), 200

    # ==========================================
    # RESOURCES
    # ==========================================
    app.register_blueprint(auth_bp)
    for blueprint in ALL_BLUEPRINTS:
        app.register_blueprint(blueprint)

    register_error_handlers(app, db)

    # ==========================================
    # SECURITY HEADERS
    # ==========================================
    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy",
                                    CONTENT_SECURITY_POLICY)
        if not request.path.startswith("/app"):
            # API data is private: never cache it.
            response.headers["Cache-Control"] = "no-store"
        return response

    return app


# ==========================================
# APPLICATION ENTRY POINT
# ==========================================
app = create_app()


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=7003,
        debug=False
    )
