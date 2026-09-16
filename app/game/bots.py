"""Computer opponents.

Bots only ever see what a human in their seat could see (their own hand plus
public counts) and act through the same engine methods humans use.
"""
from __future__ import annotations

import random
from collections import Counter

from .cards import COLORS, Card
from .engine import PLAY, ROULETTE, Game

BOT_NAMES = ["Ada", "Blaise", "Grace", "Alan", "Hedy", "Linus", "Margaret", "Edsger", "Barbara"]
BOT_PREFIX = "Bot "


def is_bot(name: str) -> bool:
    return name.startswith(BOT_PREFIX)


def best_color(hand: list[Card], rng: random.Random) -> str:
    counts = Counter(c.color for c in hand if not c.is_wild)
    if not counts:
        return rng.choice(COLORS)
    top = max(counts.values())
    return rng.choice([c for c in COLORS if counts[c] == top])


def _score(game: Game, me: str, card: Card) -> float:
    hand = game.hands[me]
    nxt = game.next_player()
    danger = len(game.hands[nxt]) <= 2
    score = 0.0

    if card.draw_value:
        score += 6 + card.draw_value if danger else 1 + card.draw_value * 0.2
    if card.value in ("skip", "skip_all", "reverse"):
        score += 7 if danger else 2
    if card.value == "discard_all":
        score += 3 * sum(1 for c in hand if c.color == card.color)
    if card.is_wild:
        # Keep wilds as escape hatches unless the hand is nearly empty.
        score += -4 if len(hand) > 3 else 2
    if card.is_number:
        score += int(card.value) * 0.1
    if game.is_no_mercy and card.value == "7":
        smallest = min(len(game.hands[p]) for p in game.players if p != me)
        score += (len(hand) - 1 - smallest) * 1.5
    if game.is_no_mercy and card.value == "0":
        prev = game.players[(game.players.index(me) - game.direction) % len(game.players)]
        score += (len(hand) - 1 - len(game.hands[prev])) * 1.2
    # Prefer shedding the color we hold most of.
    score += sum(1 for c in hand if c.color == card.color) * 0.3
    return score


def take_turn(game: Game, me: str, rng: random.Random) -> None:
    """Perform exactly one engine action for the bot whose turn it is."""
    hand = game.hands[me]

    if game.phase == ROULETTE:
        game.spin_roulette(me, best_color(hand, rng))
        return

    if game.phase != PLAY:
        return

    playable = [c for c in hand if c.id in game.playable_ids(me)]
    if not playable:
        if game.can_pass(me):
            game.pass_turn(me)
        else:
            game.draw(me)
        return

    if len(hand) == 2 and game.can_call_uno(me) and rng.random() < 0.8:
        game.call_uno(me)

    if game.pending_draw:
        card = min(playable, key=lambda c: (c.draw_value, c.is_wild))
    else:
        card = max(playable, key=lambda c: _score(game, me, c) + rng.random() * 0.5)

    remaining = [c for c in hand if c.id != card.id]
    color = best_color(remaining, rng) if card.is_wild else None
    target = None
    if game.is_no_mercy and card.value == "7":
        others = [p for p in game.players if p != me]
        target = min(others, key=lambda p: len(game.hands[p]))
    game.play(me, card.id, color=color, target=target)


def pick_names(count: int, taken: set[str], rng: random.Random) -> list[str]:
    pool = [BOT_PREFIX + n for n in BOT_NAMES if BOT_PREFIX + n not in taken]
    rng.shuffle(pool)
    return pool[:count]
