from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from ..extensions import db
from ..models import User
from ..security import PASSWORD_MAX, PASSWORD_MIN, RateLimiter, valid_password, valid_username

bp = Blueprint("auth", __name__)



def _limiter(name: str, limit: int, window: float) -> RateLimiter:
    """Limiters live on the app so separate app instances (and tests) don't share counters."""
    limiters = current_app.extensions.setdefault("auth_limiters", {})
    if name not in limiters:
        limiters[name] = RateLimiter(limit=limit, window=window)
    return limiters[name]


def _client_ip() -> str:
    return request.remote_addr or "unknown"


def _error(message: str, status: int):
    return jsonify({"ok": False, "message": message}), status


def _credentials():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, None
    username, password = data.get("username"), data.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return None, None
    return username.strip(), password


@bp.get("/login")
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("main.play"))
    mode = "signup" if request.args.get("mode") == "signup" else "login"
    return render_template("auth.html", mode=mode)


@bp.post("/api/auth/login")
def login():
    username, password = _credentials()
    if username is None or len(username) > 80 or len(password) > PASSWORD_MAX:
        return _error("Enter your username and password.", 400)

    key = f"{_client_ip()}:{username.lower()}"
    login_limiter = _limiter("login", 8, 300)
    if not login_limiter.hit(key):
        return _error("Too many attempts. Wait a few minutes and try again.", 429)

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return _error("That username and password don't match.", 401)

    login_limiter.reset(key)
    login_user(user, remember=True)
    return jsonify({"ok": True, "redirect": url_for("main.play")})


@bp.post("/api/auth/signup")
def signup():
    username, password = _credentials()
    if username is None or not valid_username(username):
        return _error("Usernames are 3–20 characters: letters, numbers and underscores.", 400)
    if not valid_password(password):
        return _error(f"Passwords need {PASSWORD_MIN}–{PASSWORD_MAX} characters.", 400)
    if not _limiter("signup", current_app.config["SIGNUPS_PER_HOUR"], 3600).hit(_client_ip()):
        return _error("Too many new accounts from this network. Try again later.", 429)
    if User.query.filter(func.lower(User.username) == username.lower()).first():
        return _error("That username is taken.", 409)

    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    login_user(user, remember=True)
    return jsonify({"ok": True, "redirect": url_for("main.play")}), 201


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.index"))
