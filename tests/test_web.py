from app.extensions import socketio
from app.models import User

from .conftest import signup


def last(received, name):
    events = [e for e in received if e["name"] == name]
    return events[-1]["args"][0] if events else None


# ------------------------------------------------------------------- pages
def test_landing_and_security_headers(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"No Mercy" in res.data
    csp = res.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp.split("style-src")[0]
    assert res.headers["X-Frame-Options"] == "DENY"


def test_play_requires_login(client):
    res = client.get("/play")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_404_page(client):
    assert client.get("/nope").status_code == 404
    assert client.get("/api/nope").get_json()["ok"] is False


def test_robots_and_sitemap(client):
    assert b"Disallow: /play" in client.get("/robots.txt").data
    assert b"<urlset" in client.get("/sitemap.xml").data


# -------------------------------------------------------------------- auth
def test_signup_login_logout(client):
    assert signup(client).status_code == 201
    assert client.get("/play").status_code == 200
    assert client.post("/logout").status_code == 302
    assert client.get("/play").status_code == 302
    res = client.post("/api/auth/login", json={"username": "alice", "password": "correct-horse"})
    assert res.get_json()["ok"] is True


def test_logout_is_not_a_get(client):
    signup(client)
    assert client.get("/logout").status_code == 405


def test_signup_validation(client):
    assert signup(client, "a", "correct-horse").status_code == 400
    assert signup(client, "<script>", "correct-horse").status_code == 400
    assert signup(client, "alice", "short").status_code == 400
    assert client.post("/api/auth/signup", data="nope").status_code == 400
    assert signup(client).status_code == 201
    assert signup(client.application.test_client(), "ALICE").status_code == 409


def test_passwords_are_hashed(app, client):
    signup(client)
    with app.app_context():
        user = User.query.filter_by(username="alice").one()
        assert "correct-horse" not in user.password_hash


def test_wrong_password_and_rate_limit(client):
    signup(client, "bob")
    fresh = client.application.test_client()
    codes = [
        fresh.post("/api/auth/login", json={"username": "bob", "password": "wrong-password"}).status_code
        for _ in range(9)
    ]
    assert codes[:8] == [401] * 8
    assert codes[8] == 429


def test_csrf_enforced_when_enabled(app):
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        res = app.test_client().post("/api/auth/signup", json={"username": "eve", "password": "correct-horse"})
        assert res.status_code == 400
        assert "session expired" in res.get_json()["message"]
    finally:
        app.config["WTF_CSRF_ENABLED"] = False


# ------------------------------------------------------------------ sockets
def test_socket_rejects_anonymous(app):
    sock = socketio.test_client(app)
    assert not sock.is_connected()


def test_two_humans_play_over_sockets(make_player):
    _, ann = make_player("ann")
    _, bob = make_player("bob")

    ann.emit("room:create", {"name": "<b>Friday</b> night", "mode": "no_mercy", "turn_seconds": 15})
    room = last(ann.get_received(), "room")
    assert room["name"] == "bFridayb night"  # markup characters stripped server side
    assert room["mode"] == "no_mercy"

    lobby = last(bob.get_received(), "lobby")
    assert lobby[0]["id"] == room["id"]

    bob.emit("room:join", {"id": room["id"]})
    ann.emit("room:start")
    ann_state = last(ann.get_received(), "room")
    bob_state = last(bob.get_received(), "room")
    assert ann_state["status"] == "playing"
    assert len(ann_state["game"]["hand"]) == 7
    assert {c["id"] for c in ann_state["game"]["hand"]}.isdisjoint({c["id"] for c in bob_state["game"]["hand"]})

    current = ann_state["game"]["current"]
    waiting = bob if current == "ann" else ann
    waiting.emit("game:action", {"action": "draw"})
    assert last(waiting.get_received(), "toast")["kind"] == "error"

    mover = ann if current == "ann" else bob
    mover.emit("game:action", {"action": "draw"})
    state = last(mover.get_received(), "room")
    assert len(state["game"]["hand"]) > 7


def test_socket_payload_validation(make_player):
    _, ann = make_player("ann")
    ann.emit("room:join", {"id": "../../etc"})
    assert "isn't valid" in last(ann.get_received(), "toast")["message"]
    ann.emit("room:create", "not a dict")
    assert last(ann.get_received(), "toast")["message"] == "Malformed request."
    ann.emit("chat", {"phrase": "<img src=x onerror=alert(1)>"})
    assert last(ann.get_received(), "toast")["kind"] == "error"


def test_quick_play_and_chat(make_player):
    _, ann = make_player("ann")
    ann.emit("room:quick", {"mode": "normal", "bots": 2})
    room = last(ann.get_received(), "room")
    assert room["private"] and room["status"] == "playing"
    assert sum(1 for s in room["seats"] if s["bot"]) == 2
    ann.emit("chat", {"phrase": "gg"})
    assert last(ann.get_received(), "chat")["text"] == "Good game!"


def test_results_recorded(app, make_player):
    from app.game import sockets

    _, ann = make_player("ann")
    _, bob = make_player("bob")
    ann.emit("room:create", {"name": "Ranked"})
    room_id = last(ann.get_received(), "room")["id"]
    bob.emit("room:join", {"id": room_id})
    ann.emit("room:start")
    room = sockets.manager.rooms[room_id]
    room.game.remove_player("bob")
    with app.app_context():
        sockets.record_results(room)
        ann_user = User.query.filter_by(username="ann").one()
        bob_user = User.query.filter_by(username="bob").one()
        assert ann_user.stats.wins == 1 and ann_user.stats.games == 1
        assert bob_user.stats.wins == 0 and bob_user.stats.games == 1


def test_leaderboard(make_player):
    http, _ = make_player("ann")
    assert http.get("/api/leaderboard").status_code == 200
    assert http.get("/api/me").get_json()["username"] == "ann"
