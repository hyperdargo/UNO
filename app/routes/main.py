from flask import Blueprint, current_app, jsonify, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required

from ..models import PlayerStats, User

bp = Blueprint("main", __name__)


def _public_url() -> str:
    return current_app.config.get("PUBLIC_URL") or request.url_root.rstrip("/")


@bp.get("/")
def index():
    return render_template("landing.html", public_url=_public_url())


@bp.get("/play")
@login_required
def play():
    return render_template("play.html")


@bp.get("/api/leaderboard")
@login_required
def leaderboard():
    rows = (
        PlayerStats.query.join(User)
        .filter(PlayerStats.games > 0)
        .order_by(PlayerStats.wins.desc(), PlayerStats.points.desc())
        .limit(20)
        .all()
    )
    return jsonify(
        [
            {"username": r.user.username, "wins": r.wins, "games": r.games, "points": r.points,
             "wins_normal": r.wins_normal, "wins_no_mercy": r.wins_no_mercy}
            for r in rows
        ]
    )


@bp.get("/api/me")
@login_required
def me():
    stats = current_user.stats.to_dict() if current_user.stats else None
    return jsonify({"username": current_user.username, "stats": stats})


@bp.get("/sw.js")
def service_worker():
    response = send_from_directory(current_app.static_folder, "sw.js", mimetype="application/javascript")
    response.headers["Cache-Control"] = "no-cache"
    return response


@bp.get("/robots.txt")
def robots():
    body = f"User-agent: *\nAllow: /\nDisallow: /play\nDisallow: /api/\nSitemap: {_public_url()}/sitemap.xml\n"
    return current_app.response_class(body, mimetype="text/plain")


@bp.get("/sitemap.xml")
def sitemap():
    base = _public_url()
    urls = [base + url_for("main.index"), base + url_for("auth.login_page")]
    items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    body = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'
    return current_app.response_class(body, mimetype="application/xml")


@bp.get("/healthz")
def health():
    return jsonify({"ok": True})
