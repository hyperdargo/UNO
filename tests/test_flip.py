import random

import pytest

from app.game.bots import take_turn
from app.game.cards import COLORS, DARK, DARK_COLORS, FLIP, LIGHT, Card, build_deck
from app.game.engine import OVER, Game, GameError


def make(players=("ann", "bob", "cat"), seed=5):
    return Game(list(players), mode=FLIP, rng=random.Random(seed))


def rig(game, player, *cards):
    """Hand of (color, value, alt_color, alt_value) tuples."""
    game.hands[player] = [
        Card(f"t{player}{i}", color, value, alt_color, alt_value)
        for i, (color, value, alt_color, alt_value) in enumerate(cards)
    ]
    return game.hands[player]


def set_top(game, color, value, alt_color="pink", alt_value="3"):
    game.discard.append(Card(f"top{len(game.discard)}", color, value, alt_color, alt_value))
    game.active_color = color


def total_cards(game):
    return len(game.draw_pile) + len(game.discard) + sum(len(h) for h in game.hands.values())


# --------------------------------------------------------------------- deck
def test_deck_is_112_double_sided_cards():
    deck = build_deck(FLIP, random.Random(0))
    assert len(deck) == 112
    assert all(card.two_sided for card in deck)
    assert all(card.color in COLORS + ("wild",) for card in deck)
    assert all(card.alt_color in DARK_COLORS + ("wild",) for card in deck)


def test_deck_composition_matches_the_rule_sheet():
    deck = build_deck(FLIP, random.Random(1))
    light = [(c.color, c.value) for c in deck]
    dark = [(c.alt_color, c.alt_value) for c in deck]

    def count(faces, value):
        return sum(1 for _, v in faces if v == value)

    assert count(light, "0") == 0 and count(dark, "0") == 0  # no zeros in UNO Flip
    for number in "123456789":
        assert count(light, number) == 8
        assert count(dark, number) == 8
    assert count(light, "draw1") == 8
    assert count(light, "skip") == 8
    assert count(light, "reverse") == 8
    assert count(light, "flip") == 8
    assert count(light, "wild") == 4
    assert count(light, "wild_draw2") == 4
    assert count(dark, "draw5") == 8
    assert count(dark, "skip_all") == 8
    assert count(dark, "reverse") == 8
    assert count(dark, "flip") == 8
    assert count(dark, "wild") == 4
    assert count(dark, "wild_draw_color") == 4


def test_game_starts_on_the_light_side():
    g = make()
    assert g.side == LIGHT
    assert g.colors == COLORS
    assert g.other_colors == DARK_COLORS
    assert g.top.color in COLORS
    assert total_cards(g) == 112


# ------------------------------------------------------------ light side
def test_draw_one_skips_the_next_player():
    g = make()
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "draw1", "pink", "4"), ("red", "1", "teal", "2"))
    before = len(g.hands["bob"])
    g.play("ann", "tann0")
    assert len(g.hands["bob"]) == before + 1
    assert g.current_player() == "cat"


def test_wild_draw_two():
    g = make()
    set_top(g, "red", "5")
    rig(g, "ann", ("wild", "wild_draw2", "wild", "wild"), ("red", "1", "teal", "2"))
    before = len(g.hands["bob"])
    g.play("ann", "tann0", color="green")
    assert g.active_color == "green"
    assert len(g.hands["bob"]) == before + 2
    assert g.current_player() == "cat"


def test_wild_needs_a_light_color_on_the_light_side():
    g = make()
    rig(g, "ann", ("wild", "wild", "wild", "wild"), ("red", "1", "teal", "2"))
    with pytest.raises(GameError):
        g.play("ann", "tann0", color="teal")
    g.play("ann", "tann0", color="blue")
    assert g.active_color == "blue"


# ------------------------------------------------------------------ flip
def test_flip_turns_every_card_over():
    g = make()
    set_top(g, "red", "5", "pink", "7")
    rig(g, "ann", ("red", "flip", "teal", "9"), ("blue", "2", "orange", "4"))
    bob_backs = [(c.alt_color, c.alt_value) for c in g.hands["bob"]]

    g.play("ann", "tann0")

    assert g.side == DARK
    assert g.colors == DARK_COLORS
    # Every hand is now showing the side opponents used to see.
    assert [(c.color, c.value) for c in g.hands["bob"]] == bob_backs
    assert g.hands["ann"][0].color == "orange" and g.hands["ann"][0].value == "4"
    assert all(c.color in DARK_COLORS + ("wild",) for c in g.draw_pile)
    assert g.current_player() == "bob"


def test_flip_brings_up_the_card_under_the_pile():
    g = make()
    g.discard = [Card("bottom", "blue", "8", "purple", "6"), Card("mid", "red", "5", "pink", "3")]
    g.active_color = "red"
    rig(g, "ann", ("red", "flip", "teal", "9"), ("blue", "2", "orange", "4"))

    # Everyone can see that underside before the flip.
    assert g.view_for("bob")["under_card"] == {"id": "bottom", "color": "purple", "value": "6"}

    g.play("ann", "tann0")
    assert g.top.id == "bottom"
    assert (g.top.color, g.top.value) == ("purple", "6")
    assert g.active_color == "purple"
    assert g.discard[0].id == "tann0"  # the flip card went to the bottom


def test_flip_onto_a_wild_asks_for_a_color():
    g = make()
    g.discard = [Card("bottom", "blue", "8", "wild", "wild_draw_color"), Card("mid", "red", "5", "pink", "3")]
    g.active_color = "red"
    rig(g, "ann", ("red", "flip", "teal", "9"), ("blue", "2", "orange", "4"))
    with pytest.raises(GameError):
        g.play("ann", "tann0")
    with pytest.raises(GameError):
        g.play("ann", "tann0", color="red")  # light color, but the dark side is coming up
    g.play("ann", "tann0", color="teal")
    assert g.side == DARK
    assert g.active_color == "teal"


def test_flipping_back_returns_to_the_light_side():
    g = make()
    set_top(g, "red", "5", "pink", "3")
    rig(g, "ann", ("red", "flip", "teal", "9"), ("blue", "2", "orange", "4"))
    g.play("ann", "tann0")
    assert g.side == DARK
    dark_top = (g.top.color, g.top.value)
    g.turn = g.players.index("bob")
    rig(g, "bob", (dark_top[0], "flip", "red", "9"), ("teal", "2", "green", "4"))
    g.play("bob", "tbob0")
    assert g.side == LIGHT
    assert g.top.color in COLORS


# ------------------------------------------------------------- dark side
def dark_game(seed=5):
    g = make(seed=seed)
    set_top(g, "red", "5", "pink", "3")
    rig(g, "ann", ("red", "flip", "teal", "9"), ("blue", "2", "orange", "4"))
    g.play("ann", "tann0")
    g.turn = g.players.index("ann")
    g.phase = "play"
    return g


def test_draw_five():
    g = dark_game()
    set_top(g, "pink", "5", "red", "2")
    rig(g, "ann", ("pink", "draw5", "red", "9"), ("teal", "2", "green", "4"))
    before = len(g.hands["bob"])
    g.play("ann", "tann0")
    assert len(g.hands["bob"]) == before + 5
    assert g.current_player() == "cat"


def test_skip_everyone_returns_the_turn():
    g = dark_game()
    set_top(g, "pink", "5", "red", "2")
    rig(g, "ann", ("pink", "skip_all", "red", "9"), ("teal", "2", "green", "4"))
    g.play("ann", "tann0")
    assert g.current_player() == "ann"


def test_wild_draw_color_draws_until_the_color_appears():
    g = dark_game()
    set_top(g, "pink", "5", "red", "2")
    rig(g, "ann", ("wild", "wild_draw_color", "wild", "wild"), ("teal", "2", "green", "4"))
    rig(g, "bob", ("teal", "1", "red", "1"))
    g.draw_pile = [
        Card("d1", "orange", "1", "red", "1"),
        Card("d2", "purple", "2", "red", "2"),
        Card("d3", "teal", "3", "red", "3"),  # drawn first
    ]
    g.play("ann", "tann0", color="purple")
    # Drew teal, then purple, and stopped.
    assert [c.id for c in g.hands["bob"]][1:] == ["d3", "d2"]
    assert g.active_color == "purple"
    assert g.current_player() == "cat"


def test_wild_draw_color_needs_a_dark_color():
    g = dark_game()
    rig(g, "ann", ("wild", "wild_draw_color", "wild", "wild"), ("teal", "2", "green", "4"))
    with pytest.raises(GameError):
        g.play("ann", "tann0", color="red")


# --------------------------------------------------------------- scoring
def test_scoring_uses_the_side_the_round_ended_on():
    g = make()
    set_top(g, "red", "5")
    rig(g, "ann", ("red", "1", "pink", "1"))
    rig(g, "bob", ("blue", "draw1", "teal", "5"), ("wild", "wild_draw2", "wild", "wild"))
    rig(g, "cat", ("green", "skip", "purple", "9"))
    g.play("ann", "tann0")
    assert g.phase == OVER
    # Draw One 10 + Wild Draw Two 50 + Skip 20
    assert g.points == 80


def test_dark_side_scoring():
    g = dark_game()
    set_top(g, "pink", "5", "red", "2")
    rig(g, "ann", ("pink", "1", "red", "1"))
    rig(g, "bob", ("teal", "skip_all", "blue", "3"), ("wild", "wild_draw_color", "wild", "wild"))
    rig(g, "cat", ("purple", "flip", "red", "4"))
    g.play("ann", "tann0")
    # Skip Everyone 30 + Wild Draw Color 60 + Flip 20
    assert g.points == 110


# ------------------------------------------------------- hidden information
def test_you_cannot_see_your_own_backs_but_opponents_can():
    g = make()
    view = g.view_for("ann")
    assert all("alt_color" not in card for card in view["hand"])
    bob_seat = next(s for s in view["seats"] if s["name"] == "bob")
    assert len(bob_seat["backs"]) == len(g.hands["bob"])
    assert {c["color"] for c in bob_seat["backs"]} <= set(DARK_COLORS) | {"wild"}
    my_seat = next(s for s in view["seats"] if s["name"] == "ann")
    assert my_seat["backs"] == []


def test_other_modes_have_no_backs_or_side():
    g = Game(["ann", "bob"], mode="normal", rng=random.Random(1))
    view = g.view_for("ann")
    assert view["side"] is None
    assert view["under_card"] is None
    assert all(seat["backs"] == [] for seat in view["seats"])


# ----------------------------------------------------------- simulations
@pytest.mark.parametrize("seed", range(25))
def test_bot_games_finish_and_conserve_cards(seed):
    rng = random.Random(seed)
    players = [f"p{i}" for i in range(2 + seed % 5)]
    g = Game(players, mode=FLIP, rng=rng)
    assert total_cards(g) == 112
    for _ in range(4000):
        if g.over:
            break
        take_turn(g, g.current_player(), rng)
        assert total_cards(g) == 112
        # The card in play always belongs to the side currently face up.
        assert g.top.color in g.colors + ("wild",)
    assert g.over and g.winner in players


def test_sides_flip_during_play():
    """Across a batch of games the deck turns over, and both sides get used."""
    flips = 0
    sides = set()
    for seed in range(12):
        rng = random.Random(seed)
        g = Game([f"p{i}" for i in range(4)], mode=FLIP, rng=rng)
        for _ in range(4000):
            if g.over:
                break
            before = g.side
            take_turn(g, g.current_player(), rng)
            flips += before != g.side
            sides.add(g.side)
    assert flips > 0
    assert sides == {LIGHT, DARK}
