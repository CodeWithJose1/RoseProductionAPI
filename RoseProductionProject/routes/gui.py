"""Serves the production build of the React GUI at /app/.

The GUI is static (HTML/JS/CSS built by Vite into frontend/dist). It holds
no credentials: after the operator signs in, the browser only keeps the
HttpOnly session cookie issued by /auth/login.
"""

import os

from flask import Blueprint, current_app, redirect, send_from_directory

from errors import error_response

gui_bp = Blueprint("gui", __name__)


def _dist_dir():
    return current_app.config["GUI_DIST_DIR"]


def _index():
    dist = _dist_dir()
    if not os.path.isfile(os.path.join(dist, "index.html")):
        return error_response(
            503,
            "The GUI has not been built. Run 'npm install && npm run build'"
            " inside the frontend/ directory.",
            code="GUI_NOT_BUILT",
        )
    response = send_from_directory(dist, "index.html")
    response.headers["Cache-Control"] = "no-cache"
    return response


@gui_bp.route("/app", methods=["GET"])
def index_redirect():
    return redirect("/app/", code=302)


@gui_bp.route("/app/", methods=["GET"])
def index():
    return _index()


@gui_bp.route("/app/<path:filename>", methods=["GET"])
def files(filename):
    dist = _dist_dir()
    full_path = os.path.realpath(os.path.join(dist, filename))
    inside = full_path.startswith(os.path.realpath(dist) + os.sep)
    if inside and os.path.isfile(full_path):
        response = send_from_directory(dist, filename)
        if filename.startswith("assets/"):
            # Vite file names contain a content hash.
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable"
            )
        return response
    # Client-side routes (/app/farms, /app/harvests, ...) -> SPA entry.
    return _index()
