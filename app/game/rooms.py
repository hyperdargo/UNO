"""Room lifecycle, turn timers and bot scheduling.

``RoomManager`` owns every live room. It knows nothing about Socket.IO; it
reports changes through a ``hooks`` object so it can be tested in isolation.
All public methods take the manager lock, so socket handlers and the
background ticker never interleave mid-action.
"""
from __future__ import annotations

import random
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Protocol

from . import bots
from .cards import MODES, NORMAL
from .engine import PLAY, ROULETTE, Game, GameError

MAX_SEATS = 10
MAX_ROOMS = 500
TURN_CHOICES = (15, 30, 60)
WAITING_GRACE = 30  # seconds a disconnected player keeps their seat in a lobby
ABANDON_AFTER = 120  # seconds before a game with nobody connected is closed
HOST_PAUSE_GRACE = 60  # seconds a paused table waits for an absent host before resuming
FINISHED_TTL = 600


class RoomError(Exception):
    """A request that can't be honoured, with a message safe to show the user."""


class Hooks(Protocol):
    def room_changed(self, room: Room) -> None: ...
    def lobby_changed(self) -> None: ...
    def room_closed(self, room: Room, users: list[str]) -> None: ...
    def game_finished(self, room: Room) -> None: ...
    def notice(self, user: str, message: str) -> None: ...


@dataclass
class Seat:
    name: str
    bot: bool = False


@dataclass
class Room:
    id: str
    name: str
    mode: str
    host: str
    private: bool
    turn_seconds: int
    seats: list[Seat] = field(default_factory=list)
    status: str = "waiting"  # waiting | playing | finished
    game: Game | None = None
    paused: bool = False
    rng: random.Random = field(default_factory=random.Random)
    turn_deadline: float = 0.0
    paused_remaining: float = 0.0
    bot_due: float = 0.0
    seen_counter: int = -1
    catch_due: dict[str, float] = field(default_factory=dict)
    finished_at: float = 0.0
    has_bots_at_start: bool = False
    humans_at_start: int = 0
    game_no: int = 0

    @property
    def humans(self) -> list[str]:
        return [s.name for s in self.seats if not s.bot]

    def seat(self, name: str) -> Seat | None:
        return next((s for s in self.seats if s.name == name), None)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "host": self.host,
            "players": len(self.seats),
            "max": MAX_SEATS,
            "bots": sum(1 for s in self.seats if s.bot),
            "turn_seconds": self.turn_seconds,
        }

    def payload_for(self, user: str, now: float, online: dict[str, int]) -> dict:
        if self.paused:
            remaining = self.paused_remaining
        else:
            remaining = max(0.0, self.turn_deadline - now) if self.status == "playing" else 0.0
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "host": self.host,
            "private": self.private,
            "status": self.status,
            "paused": self.paused,
            "turn_seconds": self.turn_seconds,
            "turn_remaining": round(remaining, 2),
            "game_no": self.game_no,
            "you": user,
            "seats": [
                {"name": s.name, "bot": s.bot, "connected": s.bot or online.get(s.name, 0) > 0}
                for s in self.seats
            ],
            "game": self.game.view_for(user) if self.game else None,
        }


class RoomManager:
    def __init__(self, hooks: Hooks, rng: random.Random | None = None, clock=time.monotonic):
        self.hooks = hooks
        self.rng = rng or random.Random()
        self.clock = clock
        self.lock = threading.RLock()
        self.rooms: dict[str, Room] = {}
        self.user_room: dict[str, str] = {}
        self.online: dict[str, int] = {}
        self.offline_since: dict[str, float] = {}

    # ------------------------------------------------------------ lookups
    def room_of(self, user: str) -> Room | None:
        room_id = self.user_room.get(user)
        return self.rooms.get(room_id) if room_id else None

    def lobby(self) -> list[dict]:
        with self.lock:
            return [r.summary() for r in self.rooms.values() if r.status == "waiting" and not r.private]

    def payload_for(self, user: str) -> dict | None:
        with self.lock:
            room = self.room_of(user)
            return room.payload_for(user, self.clock(), self.online) if room else None

    def _require_room(self, user: str) -> Room:
        room = self.room_of(user)
        if not room:
            raise RoomError("You're not at a table.")
        return room

    def _require_host(self, user: str) -> Room:
        room = self._require_room(user)
        if room.host != user:
            raise RoomError("Only the host can do that.")
        return room

    # ------------------------------------------------------------ lifecycle
    def create(self, host: str, name: str, mode: str = NORMAL, private: bool = False, turn_seconds: int = 30) -> Room:
        if mode not in MODES:
            raise RoomError("Unknown game mode.")
        if turn_seconds not in TURN_CHOICES:
            turn_seconds = 30
        with self.lock:
            if len(self.rooms) >= MAX_ROOMS:
                raise RoomError("The server is full right now. Try again shortly.")
            self._leave(host)
            room_id = secrets.token_urlsafe(6)
            while room_id in self.rooms:
                room_id = secrets.token_urlsafe(6)
            room = Room(
                id=room_id,
                name=name,
                mode=mode,
                host=host,
                private=private,
                turn_seconds=turn_seconds,
                rng=random.Random(self.rng.random()),
            )
            room.seats.append(Seat(host))
            self.rooms[room_id] = room
            self.user_room[host] = room_id
            self.hooks.room_changed(room)
            if not private:
                self.hooks.lobby_changed()
            return room

    def quick_play(self, user: str, mode: str, bot_count: int) -> Room:
        bot_count = max(1, min(int(bot_count), 5))
        with self.lock:
            room = self.create(user, f"{user}'s table", mode=mode, private=True)
            for name in bots.pick_names(bot_count, set(), room.rng):
                room.seats.append(Seat(name, bot=True))
            self._start(room)
            return room

    def join(self, user: str, room_id: str) -> Room:
        with self.lock:
            room = self.rooms.get(room_id)
            if not room:
                raise RoomError("That table doesn't exist anymore.")
            if room.seat(user) and self.user_room.get(user) == room_id:
                return room
            if room.status != "waiting":
                raise RoomError("That game has already started.")
            if len(room.seats) >= MAX_SEATS:
                raise RoomError("That table is full.")
            self._leave(user)
            room.seats.append(Seat(user))
            self.user_room[user] = room_id
            self.hooks.room_changed(room)
            if not room.private:
                self.hooks.lobby_changed()
            return room

    def leave(self, user: str) -> None:
        with self.lock:
            self._leave(user)

    def _leave(self, user: str) -> None:
        room = self.room_of(user)
        if not room:
            return
        self.user_room.pop(user, None)

        if room.status == "playing" and room.game:
            room.game.remove_player(user, "left")
        room.seats = [s for s in room.seats if s.name != user]

        if not room.humans:
            self._close(room)
            return
        if room.host == user:
            room.host = room.humans[0]
        self._after_change(room)
        if room.status == "waiting" and not room.private:
            self.hooks.lobby_changed()

    def _close(self, room: Room) -> None:
        self.rooms.pop(room.id, None)
        users = [u for u, rid in self.user_room.items() if rid == room.id]
        for u in users:
            self.user_room.pop(u, None)
        self.hooks.room_closed(room, users)
        self.hooks.lobby_changed()

    def add_bot(self, host: str) -> None:
        with self.lock:
            room = self._require_host(host)
            if room.status != "waiting":
                raise RoomError("Bots can only join before the game starts.")
            if len(room.seats) >= MAX_SEATS:
                raise RoomError("The table is full.")
            names = bots.pick_names(1, {s.name for s in room.seats}, room.rng)
            if not names:
                raise RoomError("No more bots available.")
            room.seats.append(Seat(names[0], bot=True))
            self._after_change(room, lobby=True)

    def kick(self, host: str, target: str) -> None:
        with self.lock:
            room = self._require_host(host)
            seat = room.seat(target) if isinstance(target, str) else None
            if not seat or target == host:
                raise RoomError("You can't remove that player.")
            if seat.bot:
                if room.status == "playing" and room.game:
                    room.game.remove_player(target, "left")
                room.seats.remove(seat)
                self._after_change(room, lobby=True)
                return
            self.hooks.notice(target, "The host removed you from the table.")
            self._leave(target)
            self.hooks.room_closed(room, [target])

    def start(self, host: str) -> None:
        with self.lock:
            room = self._require_host(host)
            if room.status != "waiting":
                raise RoomError("The game is already running.")
            if len(room.seats) < 2:
                raise RoomError("You need at least two players. Add a bot to play solo.")
            self._start(room)

    def _start(self, room: Room) -> None:
        room.game = Game([s.name for s in room.seats], mode=room.mode, rng=room.rng)
        room.game_no += 1
        room.status = "playing"
        room.paused = False
        room.seen_counter = -1
        room.catch_due.clear()
        room.has_bots_at_start = any(s.bot for s in room.seats)
        room.humans_at_start = len(room.humans)
        self._schedule(room, self.clock())
        self.hooks.room_changed(room)
        self.hooks.lobby_changed()

    def rematch(self, host: str) -> None:
        with self.lock:
            room = self._require_host(host)
            if room.status != "finished":
                raise RoomError("Finish this game first.")
            room.status = "waiting"
            room.game = None
            if len(room.seats) >= 2 and all(self.online.get(h, 0) for h in room.humans):
                self._start(room)
            else:
                self._after_change(room, lobby=True)

    def toggle_pause(self, host: str) -> None:
        with self.lock:
            room = self._require_host(host)
            if room.status != "playing":
                raise RoomError("Nothing to pause.")
            now = self.clock()
            if room.paused:
                self._resume(room, now)
            else:
                room.paused = True
                room.paused_remaining = max(0.0, room.turn_deadline - now)
            self.hooks.room_changed(room)

    def _resume(self, room: Room, now: float) -> None:
        room.paused = False
        room.turn_deadline = now + room.paused_remaining
        room.bot_due = now + 1.0

    # ------------------------------------------------------------ gameplay
    def act(self, user: str, action: str, data: dict) -> None:
        with self.lock:
            room = self._require_room(user)
            game = room.game
            if room.status != "playing" or not game:
                raise RoomError("The game isn't running.")
            if room.paused and action != "call_uno":
                raise RoomError("The game is paused.")
            try:
                if action == "play":
                    game.play(user, data.get("card_id"), color=data.get("color"), target=data.get("target"))
                elif action == "draw":
                    game.draw(user)
                elif action == "pass":
                    game.pass_turn(user)
                elif action == "roulette":
                    game.spin_roulette(user, data.get("color"))
                elif action == "call_uno":
                    game.call_uno(user)
                elif action == "catch_uno":
                    game.catch_uno(user, data.get("target"))
                else:
                    raise RoomError("Unknown action.")
            except GameError as exc:
                raise RoomError(str(exc)) from exc
            self._after_change(room)

    def _after_change(self, room: Room, lobby: bool = False) -> None:
        if room.status == "playing" and room.game:
            if room.game.over:
                self._finish(room)
            else:
                self._schedule(room, self.clock())
        self.hooks.room_changed(room)
        if lobby and not room.private:
            self.hooks.lobby_changed()

    def _schedule(self, room: Room, now: float) -> None:
        game = room.game
        if game.turn_counter != room.seen_counter:
            room.seen_counter = game.turn_counter
            room.turn_deadline = now + room.turn_seconds
            room.bot_due = now + room.rng.uniform(1.1, 2.0)
        for name in list(room.catch_due):
            if name not in game.uno_vulnerable:
                room.catch_due.pop(name)
        for name in game.uno_vulnerable:
            if name not in room.catch_due and not bots.is_bot(name):
                # Bots notice a missed UNO some of the time, after a human-ish delay.
                hunters = [p for p in game.players if bots.is_bot(p) and p != name]
                if hunters and room.rng.random() < 0.6:
                    room.catch_due[name] = now + room.rng.uniform(1.4, 2.6)
                else:
                    room.catch_due[name] = float("inf")

    def _finish(self, room: Room) -> None:
        if room.status == "finished":
            return
        room.status = "finished"
        room.finished_at = self.clock()
        room.catch_due.clear()
        self.hooks.game_finished(room)

    def _auto_turn(self, room: Room, player: str) -> None:
        """Act for a bot, or for a human whose turn timer ran out."""
        game = room.game
        if bots.is_bot(player):
            bots.take_turn(game, player, room.rng)
            return
        hand = game.hands[player]
        if game.phase == ROULETTE:
            game.spin_roulette(player, bots.best_color(hand, room.rng, game.colors))
            return
        if game.phase != PLAY:
            return
        if not game.drawn_card_id or game.pending_draw:
            game.draw(player)
        if game.over or game.current_player() != player or not game.drawn_card_id:
            return
        if game.can_pass(player):
            game.pass_turn(player)
        else:
            card = next(c for c in hand if c.id == game.drawn_card_id)
            color = bots.best_color(hand, room.rng, game.colors) if card.is_wild else None
            if game.is_flip and card.value == "flip":
                color = room.rng.choice(game.other_colors)
            others = [p for p in game.players if p != player]
            target = room.rng.choice(others) if card.value == "7" else None
            game.play(player, card.id, color=color, target=target)

    # ------------------------------------------------------------ presence
    def connect(self, user: str) -> Room | None:
        with self.lock:
            self.online[user] = self.online.get(user, 0) + 1
            self.offline_since.pop(user, None)
            room = self.room_of(user)
            if room:
                self.hooks.room_changed(room)
            return room

    def disconnect(self, user: str) -> None:
        with self.lock:
            self.online[user] = max(0, self.online.get(user, 0) - 1)
            if self.online[user]:
                return
            del self.online[user]
            self.offline_since[user] = self.clock()
            room = self.room_of(user)
            if room:
                self.hooks.room_changed(room)

    def _away(self, room: Room, now: float) -> dict[str, float]:
        """Seconds each disconnected human in the room has been gone."""
        return {u: now - self.offline_since.get(u, now) for u in room.humans if not self.online.get(u)}

    # ------------------------------------------------------------ ticker
    def tick(self) -> None:
        with self.lock:
            now = self.clock()
            for room in list(self.rooms.values()):
                try:
                    self._tick_room(room, now)
                except GameError:
                    # A timed action raced a human move; the next tick retries.
                    continue
            for user, since in list(self.offline_since.items()):
                if user not in self.user_room and now - since > ABANDON_AFTER:
                    del self.offline_since[user]

    def _tick_room(self, room: Room, now: float) -> None:
        away = self._away(room, now)
        everyone_away = bool(room.humans) and len(away) == len(room.humans)

        if room.status == "waiting":
            for user, gone in away.items():
                if gone > WAITING_GRACE:
                    self._leave(user)
            return

        if room.status == "finished":
            if now - room.finished_at > FINISHED_TTL or (everyone_away and min(away.values()) > WAITING_GRACE):
                self._close(room)
            return

        game = room.game
        if everyone_away and min(away.values()) > ABANDON_AFTER:
            self._close(room)
            return
        if room.paused:
            # Only the host can resume, so an absent host must not freeze the table.
            if away.get(room.host, 0) > HOST_PAUSE_GRACE:
                self._resume(room, now)
                for name in room.humans:
                    self.hooks.notice(name, "The host is away, so the game resumed.")
                self.hooks.room_changed(room)
            return
        if game.over:
            return

        changed = False
        for name, due in list(room.catch_due.items()):
            if now >= due and name in game.uno_vulnerable:
                hunters = [p for p in game.players if bots.is_bot(p) and p != name]
                if hunters:
                    game.catch_uno(room.rng.choice(hunters), name)
                    changed = True
                room.catch_due[name] = float("inf")

        if not game.over:
            current = game.current_player()
            if bots.is_bot(current):
                if now >= room.bot_due:
                    self._auto_turn(room, current)
                    changed = True
            elif now >= room.turn_deadline:
                self._auto_turn(room, current)
                self.hooks.notice(current, "Time's up, so a move was made for you.")
                changed = True

        if changed:
            self._after_change(room)
