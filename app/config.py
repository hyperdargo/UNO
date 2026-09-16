import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")  # create_app falls back to a random key with a warning
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'uno.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SECURE_COOKIES")
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    # Static URLs carry a ?v= stamp, so they can be cached hard.
    SEND_FILE_MAX_AGE_DEFAULT = 60 * 60 * 24 * 30

    WTF_CSRF_TIME_LIMIT = None  # token lives as long as the session
    MAX_CONTENT_LENGTH = 16 * 1024

    # Comma separated extra origins allowed to open a socket. Same origin is always allowed.
    SOCKET_CORS_ORIGINS = [o.strip() for o in os.environ.get("SOCKET_CORS_ORIGINS", "").split(",") if o.strip()]
    PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
    RUN_TICKER = True
    SIGNUPS_PER_HOUR = int(os.environ.get("SIGNUPS_PER_HOUR", "5"))


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    RUN_TICKER = False
    SIGNUPS_PER_HOUR = 1000
