"""UNO: Normal & No Mercy. Application factory."""
import os
import secrets
import warnings

from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError

from .config import Config
from .extensions import csrf, db, login_manager, socketio
from .security import apply_security_headers


def _local_secret_key(instance_path: str) -> str:
    """Fall back to a key stored beside the database.

    Hosting panels often can't set arbitrary environment variables, and a key
    regenerated on every boot signs everyone out on every restart. Setting
    SECRET_KEY is still the better option.
    """
    path = os.path.join(instance_path, "secret_key")
    try:
        with open(path) as handle:
            key = handle.read().strip()
        if key:
            return key
    except OSError:
        pass

    key = secrets.token_hex(32)
    try:
        with open(os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600), "w") as handle:
            handle.write(key)
    except OSError:
        warnings.warn(
            "SECRET_KEY is not set and instance/secret_key could not be written; "
            "sessions will reset on restart.",
            stacklevel=3,
        )
    return key


def create_app(config: type[Config] = Config) -> Flask:
    app = Flask(__name__, instance_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance"))
    app.config.from_object(config)
    os.makedirs(app.instance_path, exist_ok=True)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _local_secret_key(app.instance_path)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login_page"
    login_manager.session_protection = "strong"
    socketio.init_app(
        app,
        async_mode="threading",
        cors_allowed_origins=app.config["SOCKET_CORS_ORIGINS"] or None,
        max_http_buffer_size=16 * 1024,
    )

    from .models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id)) if user_id.isdigit() else None

    from .game.sockets import init_sockets
    from .routes import auth, main

    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    init_sockets(app)

    app.after_request(apply_security_headers)

    def wants_json() -> bool:
        return request.path.startswith("/api/")

    @app.errorhandler(CSRFError)
    def csrf_error(_err):
        if wants_json():
            return jsonify({"ok": False, "message": "Your session expired. Refresh the page and try again."}), 400
        return render_template("error.html", code=400, title="Session expired",
                               message="Refresh the page and try again."), 400

    @app.errorhandler(404)
    def not_found(_err):
        if wants_json():
            return jsonify({"ok": False, "message": "Not found."}), 404
        return render_template("error.html", code=404, title="This card isn't in the deck",
                               message="The page you asked for doesn't exist."), 404

    @app.errorhandler(500)
    def server_error(_err):
        if wants_json():
            return jsonify({"ok": False, "message": "Something went wrong on our side."}), 500
        return render_template("error.html", code=500, title="Misdeal",
                               message="Something went wrong on our side. Try again in a moment."), 500

    with app.app_context():
        db.create_all()

    return app
