import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db, socketio
from app.game import sockets


@pytest.fixture(scope="session")
def _app():
    # Flask-SocketIO binds handlers to one server, so the suite shares a single app.
    return create_app(TestConfig)


@pytest.fixture
def app(_app):
    with _app.app_context():
        db.drop_all()
        db.create_all()
    _app.extensions.pop("auth_limiters", None)
    sockets.init_sockets(_app)
    sockets._event_limiter.__init__(sockets._event_limiter.limit, sockets._event_limiter.window)
    sockets._chat_limiter.__init__(sockets._chat_limiter.limit, sockets._chat_limiter.window)
    yield _app
    with _app.app_context():
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


def signup(client, username="alice", password="correct-horse"):
    return client.post("/api/auth/signup", json={"username": username, "password": password})


@pytest.fixture
def make_player(app):
    """Return a logged-in (http_client, socket_client) pair for a new user."""

    def factory(username):
        http = app.test_client()
        assert signup(http, username).status_code == 201
        sock = socketio.test_client(app, flask_test_client=http)
        assert sock.is_connected()
        return http, sock

    return factory
