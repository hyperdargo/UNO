"""Card definitions and deck builders for both game modes."""
from __future__ import annotations

import random
from dataclasses import dataclass

COLORS = ("red", "yellow", "green", "blue")
WILD = "wild"

NORMAL = "normal"
NO_MERCY = "no_mercy"
MODES = (NORMAL, NO_MERCY)

NUMBERS = tuple(str(n) for n in range(10))

# How many cards a draw card forces onto the next player.
DRAW_VALUES = {
    "draw2": 2,
    "draw4": 4,
    "wild_draw4": 4,
    "wild_reverse_draw4": 4,
    "wild_draw6": 6,
    "wild_draw10": 10,
}

# Classic scoring values: numbers are face value, colored actions 20, wilds 50.
ACTION_POINTS = 20
WILD_POINTS = 50
KNOCKOUT_POINTS = 250


@dataclass(frozen=True)
class Card:
    id: str
    color: str
    value: str

    @property
    def is_wild(self) -> bool:
        return self.color == WILD

    @property
    def is_number(self) -> bool:
        return self.value in NUMBERS

    @property
    def draw_value(self) -> int:
        return DRAW_VALUES.get(self.value, 0)

    @property
    def points(self) -> int:
        if self.is_number:
            return int(self.value)
        return WILD_POINTS if self.is_wild else ACTION_POINTS

    def to_dict(self) -> dict:
        return {"id": self.id, "color": self.color, "value": self.value}


# (value, copies per color) for colored cards; (value, total copies) for wilds.
NORMAL_COLORED = [("0", 1)] + [(n, 2) for n in NUMBERS[1:]] + [("skip", 2), ("reverse", 2), ("draw2", 2)]
NORMAL_WILDS = [("wild", 4), ("wild_draw4", 4)]

NO_MERCY_COLORED = [(n, 2) for n in NUMBERS] + [
    ("draw2", 3),
    ("draw4", 2),
    ("skip", 3),
    ("skip_all", 2),
    ("reverse", 3),
    ("discard_all", 3),
]
NO_MERCY_WILDS = [
    ("wild_reverse_draw4", 8),
    ("wild_draw6", 4),
    ("wild_draw10", 4),
    ("wild_roulette", 8),
]

DECK_SPECS = {
    NORMAL: (NORMAL_COLORED, NORMAL_WILDS),
    NO_MERCY: (NO_MERCY_COLORED, NO_MERCY_WILDS),
}


def build_deck(mode: str, rng: random.Random) -> list[Card]:
    """Return a freshly shuffled deck: 108 cards for normal, 168 for No Mercy."""
    colored, wilds = DECK_SPECS[mode]
    cards: list[Card] = []

    def add(color: str, value: str) -> None:
        cards.append(Card(id=f"c{len(cards)}", color=color, value=value))

    for color in COLORS:
        for value, copies in colored:
            for _ in range(copies):
                add(color, value)
    for value, copies in wilds:
        for _ in range(copies):
            add(WILD, value)

    rng.shuffle(cards)
    return cards
