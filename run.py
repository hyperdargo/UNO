"""Development entry point: `python run.py`.

Hosting panels usually run `app.py`; both share this host/port logic.
"""
import os

from app import create_app
from app.extensions import socketio

app = create_app()


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


if __name__ == "__main__":
    # A panel sets SERVER_PORT; binding to 0.0.0.0 keeps the port reachable.
    host = os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("SERVER_PORT") else "127.0.0.1")
    port = _int("SERVER_PORT", _int("PORT", 5000))
    socketio.run(
        app,
        host=host,
        port=port,
        debug=os.environ.get("FLASK_DEBUG") == "1",
        allow_unsafe_werkzeug=True,
    )
