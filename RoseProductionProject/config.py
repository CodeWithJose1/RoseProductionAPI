
import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _env_flag(name, default="false"):
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


class Config:
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://"
        f"{os.getenv('DB_USER')}:"
        f"{os.getenv('DB_PASSWORD')}@"
        f"{os.getenv('DB_HOST')}:"
        f"{os.getenv('DB_PORT')}/"
        f"{os.getenv('DB_NAME')}"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    API_KEY = os.getenv("API_KEY")

    # ------------------------------------------------------------------
    # Additions for the GUI integration (all optional; none of them need
    # to be present in .env for the API to keep working as before).
    # ------------------------------------------------------------------

    # Reconnect transparently if MySQL closed an idle connection.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # Signs the GUI session cookie. If SECRET_KEY is not defined, a random
    # key is generated at start-up (GUI sessions then end on restart).
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)

    SESSION_COOKIE_NAME = "rose_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Strict"
    SESSION_COOKIE_SECURE = _env_flag("SESSION_COOKIE_SECURE")
    PERMANENT_SESSION_LIFETIME = timedelta(
        hours=int(os.getenv("SESSION_HOURS", "8"))
    )

    # Production build of the React GUI served by Flask at /app/.
    GUI_DIST_DIR = os.getenv("GUI_DIST_DIR") or os.path.join(
        BASE_DIR, "frontend", "dist"
    )

    # Reject request bodies larger than 1 MiB (JSON 413 response).
    MAX_CONTENT_LENGTH = 1024 * 1024

    # Brute-force protection for the GUI login form.
    LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
    LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_WINDOW_SECONDS", "300"))
