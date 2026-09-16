"""Socket.IO transport: authenticates sockets and forwards requests to the RoomManager."""
from __future__ import annotations

import functools
import logging

from flask import current_app
from flask_login import current_user
from flask_socketio import emit, join_room

from ..extensions import db, socketio
from ..models import User, stats_for
from ..security import RateLimiter, clean_room_name, short_str, valid_room_id
from . import bots
from .cards import MODES
from .rooms import TURN_CHOICES, Room, RoomError, RoomManager

log = logging.getLogger(__name__)

QUICK_CHAT = {
    "hello": "Hello!",
    "gg": "Good game!",
    "nice": "Nice one.",
    "oops": "Oops!",
    "haha": "Ha ha!",
    "hurry": "Your move!",
    "revenge": "I'll remember that.",
    "mercy": "No mercy!",
}
GAME_ACTIONS = {"play", "draw", "pass", "roulette", "call_uno", "catch_uno"}

manager: RoomManager | None = None
_event_limiter = RateLimiter(limit=40, window=10)
_chat_limiter = RateLimiter(limit=4, window=8)
_ticker_started = False


def user_channel(name: str) -> str:
    return f"u:{name}"


class SocketHooks:
    def __init__(self, app):
        self.app = app

    def room_changed(self, room: Room) -> None:
        now = manager.clock()
        for name in room.humans:
            if manager.user_room.get(name) == room.id:
                socketio.emit("room", room.payload_for(name, now, manager.online), to=user_channel(name))

    def lobby_changed(self) -> None:
        socketio.emit("lobby", manager.lobby(), to="lobby")

    def room_closed(self, room: Room, users: list[str]) -> None:
        for name in users:
            socketio.emit("room_closed", {"name": room.name}, to=user_channel(name))

    def notice(self, user: str, message: str) -> None:
        socketio.emit("toast", {"kind": "info", "message": message}, to=user_channel(user))

    def game_finished(self, room: Room) -> None:
        try:
            with self.app.app_context():
                record_results(room)
                for name in room.humans:
                    user = User.query.filter_by(username=name).first()
                    if user and user.stats:
                        socketio.emit("stats", user.stats.to_dict(), to=user_channel(name))
        except Exception:  # stats must never break a running table
            log.exception("failed to record results for room %s", room.id)


def record_results(room: Room) -> None:
    game = room.game
    humans = [n for n in game.seating if not bots.is_bot(n)]
    ranked = room.humans_at_start >= 2 and not room.has_bots_at_start
    for name in humans:
        user = User.query.filter_by(username=name).first()
        if not user:
            continue
        stats = stats_for(user)
        won = game.winner == name
        if ranked:
            stats.games += 1
            if won:
                stats.wins += 1
                stats.points += game.points
                if game.is_no_mercy:
                    stats.wins_no_mercy += 1
                else:
                    stats.wins_normal += 1
        else:
            stats.bot_games += 1
            stats.bot_wins += int(won)
    db.session.commit()


def _fail(message: str) -> None:
    emit("toast", {"kind": "error", "message": message})


def socket_handler(fn):
    """Require a logged-in user, rate limit, validate payload shape, surface RoomErrors."""

    @functools.wraps(fn)
    def wrapper(data=None):
        if not current_user.is_authenticated:
            return _fail("Please sign in again.")
        name = current_user.username
        if not _event_limiter.hit(name):
            return _fail("Slow down a little.")
        if data is not None and not isinstance(data, dict):
            return _fail("Malformed request.")
        try:
            return fn(name, data or {})
        except RoomError as exc:
            return _fail(str(exc))

    return wrapper


@socketio.on("connect")
def on_connect(auth=None):
    if not current_user.is_authenticated:
        raise ConnectionRefusedError("authentication required")
    name = current_user.username
    join_room(user_channel(name))
    join_room("lobby")
    emit("lobby", manager.lobby())
    emit("stats", (current_user.stats.to_dict() if current_user.stats else None))
    if manager.connect(name) is None:
        emit("room", None)
    _ensure_ticker()


@socketio.on("disconnect")
def on_disconnect(*_args):
    if current_user.is_authenticated:
        manager.disconnect(current_user.username)


@socketio.on("room:create")
@socket_handler
def on_create(name, data):
    if bots.is_bot(name):
        raise RoomError("This legacy username can't host tables. Please create a new account.")
    mode = data.get("mode") if data.get("mode") in MODES else "normal"
    turn = data.get("turn_seconds") if data.get("turn_seconds") in TURN_CHOICES else 30
    room_name = clean_room_name(data.get("name"), f"{name}'s table")
    manager.create(name, room_name, mode=mode, private=bool(data.get("private")), turn_seconds=turn)


@socketio.on("room:quick")
@socket_handler
def on_quick(name, data):
    if bots.is_bot(name):
        raise RoomError("This legacy username can't play. Please create a new account.")
    mode = data.get("mode") if data.get("mode") in MODES else "normal"
    count = data.get("bots") if isinstance(data.get("bots"), int) else 3
    manager.quick_play(name, mode, count)


@socketio.on("room:join")
@socket_handler
def on_join(name, data):
    if bots.is_bot(name):
        raise RoomError("This legacy username can't play. Please create a new account.")
    room_id = data.get("id")
    if not valid_room_id(room_id):
        raise RoomError("That table code isn't valid.")
    manager.join(name, room_id)


@socketio.on("room:leave")
@socket_handler
def on_leave(name, data):
    manager.leave(name)
    emit("room", None)
    emit("lobby", manager.lobby())


@socketio.on("room:add_bot")
@socket_handler
def on_add_bot(name, data):
    manager.add_bot(name)


@socketio.on("room:kick")
@socket_handler
def on_kick(name, data):
    target = short_str(data.get("target"), 80)
    if not target:
        raise RoomError("Choose a player.")
    manager.kick(name, target)


@socketio.on("room:start")
@socket_handler
def on_start(name, data):
    manager.start(name)


@socketio.on("room:rematch")
@socket_handler
def on_rematch(name, data):
    manager.rematch(name)


@socketio.on("room:pause")
@socket_handler
def on_pause(name, data):
    manager.toggle_pause(name)


@socketio.on("game:action")
@socket_handler
def on_action(name, data):
    action = data.get("action")
    if action not in GAME_ACTIONS:
        raise RoomError("Unknown action.")
    payload = {
        "card_id": short_str(data.get("card_id"), 16),
        "color": short_str(data.get("color"), 8),
        "target": short_str(data.get("target"), 80),
    }
    manager.act(name, action, payload)


@socketio.on("chat")
@socket_handler
def on_chat(name, data):
    phrase = data.get("phrase")
    if phrase not in QUICK_CHAT:
        raise RoomError("Pick one of the quick chat phrases.")
    room = manager.room_of(name)
    if not room:
        raise RoomError("You're not at a table.")
    if not _chat_limiter.hit(name):
        raise RoomError("Give the table a moment.")
    for member in room.humans:
        socketio.emit("chat", {"player": name, "phrase": phrase, "text": QUICK_CHAT[phrase]}, to=user_channel(member))


def _ensure_ticker() -> None:
    global _ticker_started
    if _ticker_started or not current_app.config.get("RUN_TICKER", True):
        return
    _ticker_started = True
    socketio.start_background_task(_tick_forever)


def _tick_forever() -> None:
    while True:
        socketio.sleep(0.25)
        try:
            manager.tick()
        except Exception:
            log.exception("room ticker failed")


def init_sockets(app) -> RoomManager:
    global manager
    manager = RoomManager(SocketHooks(app))
    app.extensions["rooms"] = manager
    return manager
