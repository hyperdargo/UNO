import random

import pytest

from app.game.bots import take_turn
from app.game.cards import NO_MERCY, NORMAL, Card, build_deck
from app.game.engine import MERCY_LIMIT, OVER, ROULETTE, Game, GameError


def make(mode=NORMAL, players=("ann", "bob", "cat"), seed=1):
    return Game(list(players), mode=mode, rng=random.Random(seed))


def rig(game, player, *cards):
    """Replace a player's hand with specific cards."""
    game.hands[player] = [Card(f"t{player}{i}", color, value) for i, (color, value) in enumerate(cards)]
    return game.hands[player]


def set_top(game, color, value):
    game.discard.append(Card(f"top{len(game.discard)}", color, value))
    game.active_color = color if color != "wild" else game.active_color


def total_cards(game):
    return len(game.draw_pile) + len(game.discard) + sum(len(h) for h in game.hands.values())


# ------------------------------------------------------------------ decks
def test_deck_sizes():
    assert len(build_deck(NORMAL, random.Random(0))) == 108
    assert len(build_deck(NO_MERCY, random.Random(0))) == 168


def test_no_mercy_deck_composition():
    deck = build_deck(NO_MERCY, random.Random(0))
    def count(value):
        return sum(1 for c in deck if c.value == value)

    assert count("wild_draw10") == 4
    assert count("wild_draw6") == 4
    assert count("wild_reverse_draw4") == 8
    assert count("wild_roulette") == 8
    assert count("skip_all") == 8
    assert count("discard_all") == 12


def test_deal_and_start_card():
    g = make()
    assert all(len(h) == 7 for h in g.hands.values())
    assert g.top.is_number
    assert g.active_color == g.top.color
    assert total_cards(g) == 108


def test_invalid_setup():
    with pytest.raises(ValueError):
        Game(["solo"])
    with pytest.raises(ValueError):
        Game(["a", "a"])
    with pytest.raises(ValueError):
        Game(["a", "b"], mode="chaos")


# ------------------------------------------------------------------ normal
def test_must_match_color_or_value():
    g = make()
    set_top(g, "red", "5")
    rig(g, "ann", ("blue", "7"), ("blue", "5"), ("red", "1"))
    with pytest.raises(GameError):
        g.play("ann", "tann0")
    g.play("ann", "tann1")  # value match
    assert g.active_color == "blue"
    assert g.current_player() == "bob"


def test_not_your_turn():
    g = make()
    with pytest.raises(GameError):
        g.draw("bob")


def test_wild_requires_color():
    g = make()
    rig(g, "ann", ("wild", "wild"), ("red", "1"))
    with pytest.raises(GameError):
        g.play("ann", "tann0")
    g.play("ann", "tann0", color="green")
    assert g.active_color == "green"


def test_skip_and_reverse():
    g = make()
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "skip"), ("red", "1"))
    g.play("ann", "tann0")
    assert g.current_player() == "cat"

    set_top(g, "red", "5")
    rig(g, "cat", ("red", "reverse"), ("red", "1"))
    g.play("cat", "tcat0")
    assert g.direction == -1
    assert g.current_player() == "bob"


def test_reverse_is_skip_with_two_players():
    g = make(players=("ann", "bob"))
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "reverse"), ("red", "1"))
    g.play("ann", "tann0")
    assert g.current_player() == "ann"


def test_draw_two_hits_next_player_and_skips():
    g = make()
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "draw2"), ("red", "1"))
    before = len(g.hands["bob"])
    g.play("ann", "tann0")
    assert len(g.hands["bob"]) == before + 2
    assert g.current_player() == "cat"


def test_normal_draw_playable_can_pass_but_not_play_other():
    g = make()
    set_top(g, "red", "5")
    rig(g, "ann", ("blue", "1"))
    g.draw_pile.append(Card("drawn", "red", "9"))
    g.draw("ann")
    assert g.drawn_card_id == "drawn"
    assert g.playable_ids("ann") == ["drawn"]
    assert g.can_pass("ann")
    g.pass_turn("ann")
    assert g.current_player() == "bob"


def test_normal_draw_unplayable_auto_passes():
    g = make()
    set_top(g, "red", "5")
    rig(g, "ann", ("blue", "1"))
    g.draw_pile.append(Card("drawn", "green", "9"))
    g.draw("ann")
    assert g.current_player() == "bob"


def test_pass_requires_draw():
    g = make()
    with pytest.raises(GameError):
        g.pass_turn("ann")


def test_uno_catch_penalty_and_call():
    g = make()
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "1"), ("red", "2"))
    g.play("ann", "tann0")  # forgot UNO
    assert "ann" in g.uno_vulnerable
    g.catch_uno("bob", "ann")
    assert len(g.hands["ann"]) == 3
    with pytest.raises(GameError):
        g.catch_uno("bob", "ann")


def test_calling_uno_protects():
    g = make()
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "1"), ("red", "2"))
    g.call_uno("ann")
    g.play("ann", "tann0")
    assert "ann" not in g.uno_vulnerable
    with pytest.raises(GameError):
        g.catch_uno("bob", "ann")


def test_late_uno_call_before_catch():
    g = make()
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "1"), ("red", "2"))
    g.play("ann", "tann0")
    g.call_uno("ann")
    with pytest.raises(GameError):
        g.catch_uno("bob", "ann")


def test_win_and_points():
    g = make()
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "1"))
    rig(g, "bob", ("blue", "9"), ("wild", "wild"))
    rig(g, "cat", ("green", "skip"))
    g.play("ann", "tann0")
    assert g.phase == OVER
    assert g.winner == "ann"
    assert g.points == 9 + 50 + 20
    assert [r.name for r in g.results] == ["ann", "cat", "bob"]
    with pytest.raises(GameError):
        g.draw("bob")


def test_hidden_information():
    g = make()
    view = g.view_for("bob")
    assert {c["id"] for c in view["hand"]} == {c.id for c in g.hands["bob"]}
    assert "hands" not in view
    assert view["playable"] == []  # not bob's turn


def test_player_leaving_on_their_turn():
    g = make(players=("ann", "bob", "cat", "dan"))
    g.remove_player("ann")
    assert g.current_player() == "bob"
    g.direction = -1
    g.turn = g.players.index("cat")
    g.remove_player("cat")
    assert g.current_player() == "bob"


def test_last_player_standing_wins():
    g = make(players=("ann", "bob"))
    g.remove_player("bob")
    assert g.winner == "ann"


def test_reshuffle_when_draw_pile_empty():
    g = make()
    set_top(g, "red", "5")
    g.discard = [Card("x1", "blue", "3"), Card("x2", "red", "5")]
    g.draw_pile = []
    rig(g, "ann", ("green", "1"))
    g.draw("ann")
    assert g.top.id == "x2"
    assert len(g.hands["ann"]) == 2


# ---------------------------------------------------------------- no mercy
def nm(players=("ann", "bob", "cat"), seed=3):
    return make(NO_MERCY, players, seed)


def test_stacking_equal_or_higher_regardless_of_color():
    g = nm()
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "draw2"), ("red", "1"))
    rig(g, "bob", ("blue", "draw2"), ("green", "draw4"), ("blue", "1"))
    rig(g, "cat", ("yellow", "draw2"), ("wild", "wild_draw10"), ("red", "3"))
    g.play("ann", "tann0")
    assert g.pending_draw == 2
    assert set(g.playable_ids("bob")) == {"tbob0", "tbob1"}
    g.play("bob", "tbob1")
    assert g.pending_draw == 6
    assert g.playable_ids("cat") == ["tcat1"]  # +2 is lower than +4
    with pytest.raises(GameError):
        g.play("cat", "tcat0")
    g.play("cat", "tcat1", color="blue")
    assert g.pending_draw == 16
    before = len(g.hands["ann"])
    g.draw("ann")
    assert len(g.hands["ann"]) == before + 16
    assert g.pending_draw == 0
    assert g.current_player() == "bob"


def test_reverse_draw4_flips_direction_and_stacks():
    g = nm()
    set_top(g, "red", "5")
    rig(g, "ann", ("wild", "wild_reverse_draw4"), ("red", "1"))
    g.play("ann", "tann0", color="red")
    assert g.direction == -1
    assert g.current_player() == "cat"
    assert g.pending_draw == 4


def test_draw_until_playable_and_must_play():
    g = nm()
    set_top(g, "red", "5")
    rig(g, "ann", ("blue", "1"))
    g.draw_pile += [Card("hit", "red", "8"), Card("m2", "green", "2"), Card("m1", "yellow", "3")]
    g.draw("ann")
    assert len(g.hands["ann"]) == 4
    assert g.drawn_card_id == "hit"
    assert not g.can_pass("ann")
    with pytest.raises(GameError):
        g.pass_turn("ann")
    g.play("ann", "hit")
    assert g.current_player() == "bob"


def test_mercy_rule_knocks_out():
    g = nm()
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "draw2"), ("red", "1"))
    rig(g, "bob", *[("blue", "1")] * 23)
    g.play("ann", "tann0")
    g.draw("bob")
    assert "bob" not in g.players
    assert g.out[-1].outcome == "knocked_out"
    assert g.current_player() == "cat"


def test_mercy_during_draw_until_playable():
    g = nm(players=("ann", "bob"))
    set_top(g, "red", "5")
    rig(g, "ann", *[("blue", "1")] * 24)
    g.draw_pile += [Card(f"g{i}", "green", "2") for i in range(5)]
    g.draw("ann")
    assert g.winner == "bob"
    assert g.points >= 250


def test_seven_swaps_with_target():
    g = nm()
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "7"), ("red", "1"), ("red", "2"))
    rig(g, "cat", ("blue", "9"))
    with pytest.raises(GameError):
        g.play("ann", "tann0")  # needs a target with 3 players
    g.play("ann", "tann0", target="cat")
    assert [c.id for c in g.hands["ann"]] == ["tcat0"]
    assert len(g.hands["cat"]) == 2


def test_zero_rotates_hands_in_direction():
    g = nm()
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "0"), ("red", "1"))
    rig(g, "bob", ("blue", "2"))
    rig(g, "cat", ("green", "3"))
    g.play("ann", "tann0")
    assert [c.id for c in g.hands["bob"]] == ["tann1"]
    assert [c.id for c in g.hands["cat"]] == ["tbob0"]
    assert [c.id for c in g.hands["ann"]] == ["tcat0"]


def test_skip_everyone_plays_again():
    g = nm()
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "skip_all"), ("red", "1"))
    g.play("ann", "tann0")
    assert g.current_player() == "ann"


def test_discard_all_sheds_matching_color():
    g = nm()
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "discard_all"), ("red", "1"), ("red", "9"), ("blue", "2"))
    g.play("ann", "tann0")
    assert [c.value for c in g.hands["ann"]] == ["2"]
    assert g.top.value == "discard_all"


def test_color_roulette():
    g = nm()
    set_top(g, "red", "5")
    rig(g, "ann", ("wild", "wild_roulette"), ("red", "1"))
    rig(g, "bob", ("red", "4"))
    g.play("ann", "tann0", color="yellow")
    assert g.phase == ROULETTE and g.current_player() == "bob"
    with pytest.raises(GameError):
        g.draw("bob")
    g.draw_pile += [Card("y", "yellow", "1"), Card("w", "wild", "wild_draw6"), Card("b", "blue", "1")]
    g.spin_roulette("bob", "yellow")
    assert [c.id for c in g.hands["bob"]][1:] == ["b", "w", "y"]
    assert g.current_player() == "cat"


def test_knockout_scoring_order():
    g = nm(players=("ann", "bob", "cat"))
    g.remove_player("bob", "knocked_out")
    rig(g, "cat", ("blue", "1"))
    set_top(g, "red", "5")
    g.turn = g.players.index("ann")
    rig(g, "ann", ("red", "1"))
    g.play("ann", "tann0")
    assert g.points == 1 + 250
    assert [r.outcome for r in g.results] == ["winner", "finished", "knocked_out"]


# ------------------------------------------------------------ simulations
@pytest.mark.parametrize("mode", [NORMAL, NO_MERCY])
@pytest.mark.parametrize("seed", range(40))
def test_bot_games_terminate_and_conserve_cards(mode, seed):
    rng = random.Random(seed)
    players = [f"p{i}" for i in range(2 + seed % 5)]
    g = Game(players, mode=mode, rng=rng)
    deck_size = total_cards(g)
    for _ in range(5000):
        if g.over:
            break
        take_turn(g, g.current_player(), rng)
        assert total_cards(g) == deck_size
        if mode == NO_MERCY:
            assert all(len(h) < MERCY_LIMIT for h in g.hands.values())
    assert g.over, "game did not finish"
    assert g.winner in players
    assert len(g.results) == len(players)
