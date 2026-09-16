"""Entry point for hosting panels that run `python app.py` (Pterodactyl and friends).

Reads the panel's SERVER_IP / SERVER_PORT variables when they are present, and
falls back to HOST / PORT, then to 0.0.0.0:25604.

For a normal server, `run.py` (development) or gunicorn (production) is the
better entry point — see the README.
"""
import os

from app import create_app
from app.extensions import socketio

application = create_app()
app = application  # gunicorn app:app also works


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


if __name__ == "__main__":
    # Panels hand the container a private address; binding to 0.0.0.0 keeps the
    # port reachable through the panel's port mapping.
    host = os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("SERVER_PORT") else "127.0.0.1")
    port = _int("SERVER_PORT", _int("PORT", 25604))
    print(f"UNO is starting on http://{host}:{port}", flush=True)
    socketio.run(
        application,
        host=host,
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True,
    )
