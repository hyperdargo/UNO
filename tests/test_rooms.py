import random

import pytest

from app.game.engine import OVER
from app.game.rooms import ABANDON_AFTER, WAITING_GRACE, RoomError, RoomManager


class FakeHooks:
    def __init__(self):
        self.changed = 0
        self.closed = []
        self.finished = []
        self.notices = []

    def room_changed(self, room):
        self.changed += 1

    def lobby_changed(self):
        pass

    def room_closed(self, room, users):
        self.closed.append((room.id, users))

    def game_finished(self, room):
        self.finished.append(room.id)

    def notice(self, user, message):
        self.notices.append((user, message))


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def env():
    hooks, clock = FakeHooks(), Clock()
    mgr = RoomManager(hooks, rng=random.Random(7), clock=clock)
    return mgr, hooks, clock


def test_create_join_start(env):
    mgr, hooks, _ = env
    room = mgr.create("ann", "Table", mode="no_mercy")
    assert mgr.lobby()[0]["id"] == room.id
    mgr.join("bob", room.id)
    with pytest.raises(RoomError):
        mgr.start("bob")  # not host
    mgr.start("ann")
    assert room.status == "playing"
    assert room.game.mode == "no_mercy"
    assert mgr.lobby() == []
    with pytest.raises(RoomError):
        mgr.join("cat", room.id)


def test_private_rooms_hidden_but_joinable(env):
    mgr, _, _ = env
    room = mgr.create("ann", "Secret", private=True)
    assert mgr.lobby() == []
    mgr.join("bob", room.id)
    assert [s.name for s in room.seats] == ["ann", "bob"]


def test_start_needs_two(env):
    mgr, _, _ = env
    mgr.create("ann", "Solo")
    with pytest.raises(RoomError):
        mgr.start("ann")
    mgr.add_bot("ann")
    mgr.start("ann")


def test_host_leaving_transfers_host(env):
    mgr, _, _ = env
    room = mgr.create("ann", "T")
    mgr.join("bob", room.id)
    mgr.leave("ann")
    assert room.host == "bob"


def test_last_human_leaving_closes_room(env):
    mgr, hooks, _ = env
    room = mgr.create("ann", "T")
    mgr.add_bot("ann")
    mgr.leave("ann")
    assert room.id not in mgr.rooms
    assert "ann" not in mgr.user_room


def test_creating_second_room_leaves_first(env):
    mgr, _, _ = env
    first = mgr.create("ann", "A")
    mgr.create("ann", "B")
    assert first.id not in mgr.rooms
    assert len(mgr.rooms) == 1


def test_actions_validate_turn(env):
    mgr, _, _ = env
    room = mgr.create("ann", "T")
    mgr.join("bob", room.id)
    mgr.start("ann")
    other = [p for p in room.game.players if p != room.game.current_player()][0]
    with pytest.raises(RoomError):
        mgr.act(other, "draw", {})
    with pytest.raises(RoomError):
        mgr.act("stranger", "draw", {})
    with pytest.raises(RoomError):
        mgr.act(room.game.current_player(), "explode", {})


def test_bots_play_full_quick_game(env):
    mgr, hooks, clock = env
    mgr.connect("ann")
    room = mgr.quick_play("ann", "no_mercy", 3)
    assert room.private and room.status == "playing"
    for _ in range(20000):
        if room.status == "finished":
            break
        clock.t += 31  # every tick expires human timers too
        mgr.tick()
    assert room.status == "finished"
    assert room.game.phase == OVER
    assert hooks.finished == [room.id]


def test_timeout_moves_for_human(env):
    mgr, hooks, clock = env
    room = mgr.create("ann", "T", turn_seconds=15)
    mgr.join("bob", room.id)
    mgr.connect("ann")
    mgr.connect("bob")
    mgr.start("ann")
    player = room.game.current_player()
    counter = room.game.turn_counter
    clock.t += 16
    mgr.tick()
    assert room.game.turn_counter != counter or room.game.drawn_card_id is None
    assert any(user == player for user, _ in hooks.notices)


def test_pause_freezes_timer(env):
    mgr, _, clock = env
    room = mgr.create("ann", "T", turn_seconds=15)
    mgr.add_bot("ann")
    mgr.start("ann")
    mgr.toggle_pause("ann")
    counter = room.game.turn_counter
    clock.t += 500
    mgr.tick()
    assert room.game.turn_counter == counter
    with pytest.raises(RoomError):
        mgr.act(room.game.current_player(), "draw", {})
    mgr.toggle_pause("ann")
    assert room.turn_deadline > clock.t


def test_disconnected_waiting_player_loses_seat(env):
    mgr, _, clock = env
    room = mgr.create("ann", "T")
    mgr.join("bob", room.id)
    mgr.connect("ann")
    mgr.connect("bob")
    mgr.disconnect("bob")
    clock.t += WAITING_GRACE + 1
    mgr.tick()
    assert [s.name for s in room.seats] == ["ann"]


def test_reconnect_within_grace_keeps_seat(env):
    mgr, _, clock = env
    room = mgr.create("ann", "T")
    mgr.join("bob", room.id)
    mgr.connect("bob")
    mgr.disconnect("bob")
    clock.t += WAITING_GRACE - 5
    mgr.connect("bob")
    clock.t += 60
    mgr.tick()
    assert room.seat("bob")


def test_abandoned_game_closes(env):
    mgr, hooks, clock = env
    mgr.connect("ann")
    room = mgr.quick_play("ann", "normal", 1)
    mgr.toggle_pause("ann")
    mgr.disconnect("ann")
    clock.t += ABANDON_AFTER + 1
    mgr.tick()
    assert room.id not in mgr.rooms


def test_kick_human_and_bot(env):
    mgr, hooks, _ = env
    room = mgr.create("ann", "T")
    mgr.join("bob", room.id)
    mgr.add_bot("ann")
    bot = room.seats[-1].name
    mgr.kick("ann", bot)
    mgr.kick("ann", "bob")
    assert [s.name for s in room.seats] == ["ann"]
    assert "bob" not in mgr.user_room
    with pytest.raises(RoomError):
        mgr.kick("ann", "ann")


def test_rematch(env):
    mgr, _, clock = env
    mgr.connect("ann")
    room = mgr.quick_play("ann", "normal", 1)
    room.game.remove_player(room.seats[1].name)
    mgr.tick()
    mgr._after_change(room)
    assert room.status == "finished"
    old_game = room.game
    mgr.rematch("ann")
    # Every human is online and the bot still holds its seat, so a fresh game deals at once.
    assert room.status == "playing"
    assert room.game is not old_game and not room.game.over


def test_player_payload_hides_other_hands(env):
    mgr, _, _ = env
    room = mgr.create("ann", "T")
    mgr.join("bob", room.id)
    mgr.start("ann")
    payload = mgr.payload_for("bob")
    bob_ids = {c.id for c in room.game.hands["bob"]}
    assert {c["id"] for c in payload["game"]["hand"]} == bob_ids
    assert "ann" not in str(payload["game"]["hand"])


def test_paused_table_resumes_when_the_host_vanishes(env):
    mgr, hooks, clock = env
    room = mgr.create("ann", "T", turn_seconds=15)
    mgr.join("bob", room.id)
    mgr.connect("ann")
    mgr.connect("bob")
    mgr.start("ann")
    mgr.toggle_pause("ann")
    assert room.paused

    mgr.disconnect("ann")
    clock.t += 30
    mgr.tick()
    assert room.paused, "a short absence should not resume the game"

    clock.t += 40
    mgr.tick()
    assert not room.paused
    assert room.turn_deadline > clock.t
    assert any("host is away" in message for _, message in hooks.notices)
