"""Card definitions and deck builders for every game mode."""
from __future__ import annotations

import random
from dataclasses import dataclass

COLORS = ("red", "yellow", "green", "blue")
DARK_COLORS = ("pink", "teal", "orange", "purple")
WILD = "wild"

NORMAL = "normal"
NO_MERCY = "no_mercy"
FLIP = "flip"
MODES = (NORMAL, NO_MERCY, FLIP)

LIGHT = "light"
DARK = "dark"

NUMBERS = tuple(str(n) for n in range(10))

# How many cards a draw card forces onto the next player.
DRAW_VALUES = {
    "draw1": 1,
    "draw2": 2,
    "draw4": 4,
    "draw5": 5,
    "wild_draw2": 2,
    "wild_draw4": 4,
    "wild_reverse_draw4": 4,
    "wild_draw6": 6,
    "wild_draw10": 10,
}

# Classic scoring: numbers are face value, colored actions 20, wilds 50.
ACTION_POINTS = 20
WILD_POINTS = 50
KNOCKOUT_POINTS = 250

# UNO Flip uses its own table, printed on the rule sheet.
FLIP_POINTS = {
    "draw1": 10,
    "draw5": 20,
    "reverse": 20,
    "skip": 20,
    "skip_all": 30,
    "flip": 20,
    "wild": 40,
    "wild_draw2": 50,
    "wild_draw_color": 60,
}


@dataclass
class Card:
    id: str
    color: str
    value: str
    # UNO Flip cards are double sided: this is the face nobody in play can see
    # except the players sitting opposite it.
    alt_color: str | None = None
    alt_value: str | None = None

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
    def two_sided(self) -> bool:
        return self.alt_value is not None

    def turn_over(self) -> None:
        """Swap the visible face with the hidden one."""
        self.color, self.alt_color = self.alt_color, self.color
        self.value, self.alt_value = self.alt_value, self.value

    def points(self, mode: str = NORMAL) -> int:
        if self.is_number:
            return int(self.value)
        if mode == FLIP:
            return FLIP_POINTS.get(self.value, ACTION_POINTS)
        return WILD_POINTS if self.is_wild else ACTION_POINTS

    def to_dict(self) -> dict:
        return {"id": self.id, "color": self.color, "value": self.value}

    def alt_dict(self) -> dict:
        return {"id": self.id, "color": self.alt_color, "value": self.alt_value}


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

# UNO Flip: 112 cards a side, numbers 1-9 only, no zeros.
FLIP_LIGHT_COLORED = [(n, 2) for n in NUMBERS[1:]] + [("draw1", 2), ("reverse", 2), ("skip", 2), ("flip", 2)]
FLIP_LIGHT_WILDS = [("wild", 4), ("wild_draw2", 4)]
FLIP_DARK_COLORED = [(n, 2) for n in NUMBERS[1:]] + [("draw5", 2), ("reverse", 2), ("skip_all", 2), ("flip", 2)]
FLIP_DARK_WILDS = [("wild", 4), ("wild_draw_color", 4)]

DECK_SPECS = {
    NORMAL: (NORMAL_COLORED, NORMAL_WILDS),
    NO_MERCY: (NO_MERCY_COLORED, NO_MERCY_WILDS),
}


def _faces(colors: tuple[str, ...], colored: list, wilds: list) -> list[tuple[str, str]]:
    faces = [(color, value) for color in colors for value, copies in colored for _ in range(copies)]
    faces += [(WILD, value) for value, copies in wilds for _ in range(copies)]
    return faces


def build_deck(mode: str, rng: random.Random) -> list[Card]:
    """A freshly shuffled deck: 108 cards for Normal, 168 for No Mercy, 112 for Flip."""
    if mode == FLIP:
        return _build_flip_deck(rng)

    colored, wilds = DECK_SPECS[mode]
    faces = _faces(COLORS, colored, wilds)
    cards = [Card(id=f"c{i}", color=color, value=value) for i, (color, value) in enumerate(faces)]
    rng.shuffle(cards)
    return cards


def _build_flip_deck(rng: random.Random) -> list[Card]:
    """Pair every light face with a dark face to make the double-sided deck.

    Mattel doesn't publish which dark face is printed behind which light face,
    so the pairing is shuffled fresh for each game.
    """
    light = _faces(COLORS, FLIP_LIGHT_COLORED, FLIP_LIGHT_WILDS)
    dark = _faces(DARK_COLORS, FLIP_DARK_COLORED, FLIP_DARK_WILDS)
    rng.shuffle(light)
    rng.shuffle(dark)
    cards = [
        Card(id=f"c{i}", color=lc, value=lv, alt_color=dc, alt_value=dv)
        for i, ((lc, lv), (dc, dv)) in enumerate(zip(light, dark, strict=True))
    ]
    rng.shuffle(cards)
    return cards
