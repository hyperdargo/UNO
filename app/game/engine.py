"""Authoritative game engine.

The engine is pure Python with no web framework imports so every rule can be
unit tested. All player actions validate input and raise ``GameError`` when a
move is not allowed; callers never mutate game state directly.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .cards import COLORS, KNOCKOUT_POINTS, NO_MERCY, NORMAL, Card, build_deck

HAND_SIZE = 7
MERCY_LIMIT = 25
UNO_PENALTY = 2
LOG_LIMIT = 40
EVENT_LIMIT = 40

PLAY = "play"
ROULETTE = "roulette"  # current player must name a color to flip for
OVER = "over"


class GameError(Exception):
    """Raised when a player attempts an illegal action."""


@dataclass
class Result:
    name: str
    outcome: str  # "winner" | "finished" | "knocked_out" | "left"
    cards_left: int = 0


@dataclass
class Game:
    players: list[str]
    mode: str = NORMAL
    rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        if self.mode not in (NORMAL, NO_MERCY):
            raise ValueError(f"unknown mode {self.mode!r}")
        if not 2 <= len(self.players) <= 10:
            raise ValueError("a game needs between 2 and 10 players")
        if len(set(self.players)) != len(self.players):
            raise ValueError("player names must be unique")

        self.players = list(self.players)
        self.seating = list(self.players)  # original order, never shrinks
        self.hands: dict[str, list[Card]] = {p: [] for p in self.players}
        self.draw_pile: list[Card] = build_deck(self.mode, self.rng)
        self.discard: list[Card] = []
        self.direction = 1
        self.turn = 0
        self.turn_counter = 0
        self.active_color: str | None = None
        self.pending_draw = 0
        self.pending_min = 0
        self.phase = PLAY
        self.drawn_card_id: str | None = None
        self.uno_safe: set[str] = set()
        self.uno_vulnerable: set[str] = set()
        self.out: list[Result] = []  # knocked out / left, in order
        self.winner: str | None = None
        self.points = 0
        self.results: list[Result] = []
        self.seq = 0
        self.log: list[dict] = []
        self.events: list[dict] = []

        for _ in range(HAND_SIZE):
            for p in self.players:
                self.hands[p].append(self._take_card())
        self._flip_start_card()
        self._emit(
            "deal",
            f"Dealt {HAND_SIZE} cards each. {describe(self.top)} starts the discard pile.",
            mode=self.mode,
        )

    # ------------------------------------------------------------------ helpers
    @property
    def is_no_mercy(self) -> bool:
        return self.mode == NO_MERCY

    @property
    def top(self) -> Card:
        return self.discard[-1]

    @property
    def over(self) -> bool:
        return self.phase == OVER

    def current_player(self) -> str:
        return self.players[self.turn]

    def next_player(self, steps: int = 1) -> str:
        return self.players[(self.turn + self.direction * steps) % len(self.players)]

    def _emit(self, kind: str, text: str | None = None, **data) -> None:
        self.seq += 1
        event = {"seq": self.seq, "type": kind, **data}
        self.events.append(event)
        del self.events[:-EVENT_LIMIT]
        if text:
            self.log.append({"seq": self.seq, "text": text})
            del self.log[:-LOG_LIMIT]

    def _take_card(self) -> Card | None:
        if not self.draw_pile and len(self.discard) > 1:
            top = self.discard.pop()
            self.draw_pile = self.discard
            self.discard = [top]
            self.rng.shuffle(self.draw_pile)
            self._emit("reshuffle", "The discard pile was shuffled into a new draw pile.")
        return self.draw_pile.pop() if self.draw_pile else None

    def _flip_start_card(self) -> None:
        # Both modes start on a number card; anything else goes to the bottom.
        while True:
            card = self.draw_pile.pop()
            if card.is_number:
                self.discard.append(card)
                self.active_color = card.color
                return
            self.draw_pile.insert(0, card)

    def _give(self, player: str, count: int) -> int:
        given = 0
        for _ in range(count):
            card = self._take_card()
            if card is None:
                break
            self.hands[player].append(card)
            given += 1
        if len(self.hands[player]) > 1:
            self.uno_safe.discard(player)
            self.uno_vulnerable.discard(player)
        return given

    def _require_turn(self, player: str) -> None:
        if self.over:
            raise GameError("The game is over.")
        if player not in self.hands:
            raise GameError("You are not playing in this game.")
        if self.current_player() != player:
            raise GameError("It's not your turn.")

    def _advance(self, steps: int = 1) -> None:
        self.turn = (self.turn + self.direction * steps) % len(self.players)
        self.drawn_card_id = None
        self.phase = PLAY
        self.turn_counter += 1

    def _find(self, player: str, card_id: str) -> Card:
        for card in self.hands[player]:
            if card.id == card_id:
                return card
        raise GameError("That card is not in your hand.")

    # ---------------------------------------------------------------- queries
    def matches(self, card: Card) -> bool:
        if card.is_wild:
            return True
        if card.color == self.active_color:
            return True
        return not self.top.is_wild and card.value == self.top.value

    def playable_ids(self, player: str) -> list[str]:
        if self.over or self.phase != PLAY or player not in self.hands or self.current_player() != player:
            return []
        hand = self.hands[player]
        if self.pending_draw:
            return [c.id for c in hand if c.draw_value >= self.pending_min]
        if self.drawn_card_id:
            return [c.id for c in hand if c.id == self.drawn_card_id and self.matches(c)]
        return [c.id for c in hand if self.matches(c)]

    def can_pass(self, player: str) -> bool:
        # Classic lets you keep a playable drawn card; No Mercy forces you to play it.
        return (
            not self.is_no_mercy
            and not self.over
            and self.phase == PLAY
            and self.current_player() == player
            and self.drawn_card_id is not None
        )

    def can_call_uno(self, player: str) -> bool:
        if self.over or player not in self.hands:
            return False
        if player in self.uno_vulnerable:
            return True
        return (
            len(self.hands[player]) == 2
            and player not in self.uno_safe
            and self.current_player() == player
            and bool(self.playable_ids(player))
        )

    # ---------------------------------------------------------------- actions
    def play(self, player: str, card_id: str, color: str | None = None, target: str | None = None) -> None:
        self._require_turn(player)
        if self.phase != PLAY:
            raise GameError("Choose a color for Color Roulette first.")
        card = self._find(player, card_id)
        if card.id not in self.playable_ids(player):
            if self.pending_draw:
                raise GameError(f"Stack a draw card worth +{self.pending_min} or more, or draw {self.pending_draw}.")
            if self.drawn_card_id:
                raise GameError("You can only play the card you just drew.")
            raise GameError("That card doesn't match the color or symbol in play.")
        if card.is_wild and color not in COLORS:
            raise GameError("Pick a color for your wild card.")

        swap_with = None
        if self.is_no_mercy and card.value == "7":
            others = [p for p in self.players if p != player]
            if len(others) == 1:
                swap_with = others[0]
            elif target in others:
                swap_with = target
            else:
                raise GameError("Choose a player to swap hands with.")

        hand = self.hands[player]
        hand.remove(card)
        self.discard.append(card)
        self.active_color = color if card.is_wild else card.color
        self.drawn_card_id = None
        self.uno_vulnerable.clear()

        label = describe(card) + (f" and chose {color}" if card.is_wild else "")
        self._emit("play", f"{player} played {label}.", player=player, card=card.to_dict(), color=self.active_color)

        if card.value == "discard_all":
            extra = [c for c in hand if c.color == card.color]
            for c in extra:
                hand.remove(c)
            # Tuck the extra cards under the top card so it stays in play.
            self.discard[-1:-1] = extra
            if extra:
                self._emit("discard_all", f"{player} discarded {len(extra)} more {card.color} card(s).",
                           player=player, count=len(extra))

        if not hand:
            self._finish(player)
            return

        if len(hand) == 1:
            if player in self.uno_safe:
                self._emit("uno", f"{player} has UNO!", player=player)
            else:
                self.uno_vulnerable.add(player)
        self.uno_safe.discard(player)

        if self.is_no_mercy:
            self._apply_no_mercy(player, card, swap_with)
        else:
            self._apply_normal(card)

    def _apply_normal(self, card: Card) -> None:
        two_players = len(self.players) == 2
        if card.value == "skip":
            self._emit("skip", f"{self.next_player()} was skipped.", player=self.next_player())
            self._advance(2)
        elif card.value == "reverse":
            self.direction *= -1
            self._emit("reverse", "Direction reversed.", direction=self.direction)
            self._advance(2 if two_players else 1)
        elif card.draw_value:
            victim = self.next_player()
            got = self._give(victim, card.draw_value)
            self._emit("draw", f"{victim} drew {got} and was skipped.", player=victim, count=got)
            self._advance(2)
        else:
            self._advance(1)

    def _apply_no_mercy(self, player: str, card: Card, swap_with: str | None) -> None:
        two_players = len(self.players) == 2
        value = card.value

        if card.draw_value:
            if value == "wild_reverse_draw4":
                self.direction *= -1
                self._emit("reverse", "Direction reversed.", direction=self.direction)
            self.pending_draw += card.draw_value
            self.pending_min = card.draw_value
            self._emit("stack", None, total=self.pending_draw)
            self._advance(1)
        elif value == "7" and swap_with:
            self.hands[player], self.hands[swap_with] = self.hands[swap_with], self.hands[player]
            self._reset_uno_after_swap()
            self._emit("swap", f"{player} swapped hands with {swap_with}.", player=player, target=swap_with)
            self._advance(1)
        elif value == "0":
            old = {p: self.hands[p] for p in self.players}
            n = len(self.players)
            for i, p in enumerate(self.players):
                self.hands[self.players[(i + self.direction) % n]] = old[p]
            self._reset_uno_after_swap()
            self._emit("rotate", "Everyone passed their hand to the next player.", direction=self.direction)
            self._advance(1)
        elif value == "skip":
            self._emit("skip", f"{self.next_player()} was skipped.", player=self.next_player())
            self._advance(2)
        elif value == "skip_all":
            self._emit("skip_all", f"{player} skipped everyone and goes again.", player=player)
            self._advance(0)
        elif value == "reverse":
            self.direction *= -1
            self._emit("reverse", "Direction reversed.", direction=self.direction)
            self._advance(2 if two_players else 1)
        elif value == "wild_roulette":
            self._advance(1)
            self.phase = ROULETTE
            self._emit("roulette", f"{self.current_player()} must spin Color Roulette.", player=self.current_player())
        else:
            self._advance(1)

    def _reset_uno_after_swap(self) -> None:
        self.uno_safe.clear()
        self.uno_vulnerable.clear()

    def draw(self, player: str) -> None:
        self._require_turn(player)
        if self.phase != PLAY:
            raise GameError("Choose a color for Color Roulette first.")
        # The catch window closes as soon as the next player acts.
        self.uno_vulnerable.clear()

        if self.pending_draw:
            total = self.pending_draw
            self.pending_draw = self.pending_min = 0
            got = self._give(player, total)
            self._emit("draw", f"{player} took the stack: {got} cards.", player=player, count=got)
            if not self._mercy_check(player):
                self._advance(1)
            return

        if self.drawn_card_id:
            raise GameError("You already drew this turn.")

        if not self.is_no_mercy:
            got = self._give(player, 1)
            drawn = self.hands[player][-1] if got else None
            self._emit("draw", f"{player} drew a card.", player=player, count=got)
            if drawn and self.matches(drawn):
                self.drawn_card_id = drawn.id
            else:
                self._advance(1)
            return

        # No Mercy: keep drawing until something playable turns up.
        got = 0
        drawn = None
        while True:
            if self._give(player, 1) == 0:
                drawn = None
                break
            got += 1
            drawn = self.hands[player][-1]
            if len(self.hands[player]) >= MERCY_LIMIT or self.matches(drawn):
                break
        self._emit("draw", f"{player} drew {got} card(s).", player=player, count=got)
        if self._mercy_check(player):
            return
        if drawn and self.matches(drawn):
            self.drawn_card_id = drawn.id
        else:
            self._advance(1)

    def pass_turn(self, player: str) -> None:
        self._require_turn(player)
        if not self.can_pass(player):
            if self.is_no_mercy and self.drawn_card_id:
                raise GameError("In No Mercy you must play the card you drew.")
            raise GameError("Draw a card before passing.")
        self._emit("pass", f"{player} passed.", player=player)
        self._advance(1)

    def spin_roulette(self, player: str, color: str) -> None:
        self._require_turn(player)
        if self.phase != ROULETTE:
            raise GameError("There is no Color Roulette to spin.")
        if color not in COLORS:
            raise GameError("Pick a valid color.")
        self.uno_vulnerable.clear()
        got = 0
        while True:
            if self._give(player, 1) == 0:
                break
            got += 1
            card = self.hands[player][-1]
            if card.color == color or len(self.hands[player]) >= MERCY_LIMIT:
                break
        self._emit("draw", f"{player} spun for {color} and flipped {got} card(s).", player=player, count=got)
        if not self._mercy_check(player):
            self._advance(1)

    def call_uno(self, player: str) -> None:
        if not self.can_call_uno(player):
            raise GameError("You can call UNO when you're about to play down to one card.")
        self.uno_vulnerable.discard(player)
        self.uno_safe.add(player)
        self._emit("uno", f"{player} called UNO!", player=player)

    def catch_uno(self, catcher: str, target: str) -> None:
        if self.over:
            raise GameError("The game is over.")
        if catcher not in self.hands or catcher == target:
            raise GameError("You can't catch that player.")
        if target not in self.uno_vulnerable:
            raise GameError(f"{target} is safe.")
        self.uno_vulnerable.discard(target)
        got = self._give(target, UNO_PENALTY)
        self._emit(
            "caught",
            f"{catcher} caught {target} without UNO: +{got}.",
            player=target,
            catcher=catcher,
            count=got,
        )
        self._mercy_check(target)

    def remove_player(self, player: str, outcome: str = "left") -> None:
        """Remove a player who left, was kicked, or was knocked out."""
        if player not in self.hands or self.over:
            return
        idx = self.players.index(player)
        was_current = idx == self.turn

        # Their cards go to the bottom of the draw pile.
        cards = self.hands.pop(player)
        self.draw_pile[0:0] = cards
        self.players.pop(idx)
        self.uno_safe.discard(player)
        self.uno_vulnerable.discard(player)
        self.out.append(Result(player, outcome, len(cards)))

        if len(self.players) == 1:
            self._finish(self.players[0])
            return

        if idx < self.turn:
            self.turn -= 1
        if was_current:
            start = idx if self.direction == 1 else idx - 1
            self.turn = start % len(self.players)
            self.drawn_card_id = None
            self.phase = PLAY
            self.turn_counter += 1
        else:
            self.turn %= len(self.players)

    def _mercy_check(self, player: str) -> bool:
        if not self.is_no_mercy or player not in self.hands or len(self.hands[player]) < MERCY_LIMIT:
            return False
        count = len(self.hands[player])
        self._emit("knockout", f"{player} hit {count} cards and is knocked out by the Mercy Rule.", player=player)
        self.remove_player(player, "knocked_out")
        return True

    def _finish(self, winner: str) -> None:
        self.phase = OVER
        self.winner = winner
        self.pending_draw = self.pending_min = 0
        remaining = sorted((p for p in self.players if p != winner), key=lambda p: len(self.hands[p]))
        points = sum(c.points for p in remaining for c in self.hands[p])
        if self.is_no_mercy:
            points += KNOCKOUT_POINTS * sum(1 for r in self.out if r.outcome == "knocked_out")
        self.points = points
        self.results = (
            [Result(winner, "winner", len(self.hands[winner]))]
            + [Result(p, "finished", len(self.hands[p])) for p in remaining]
            + list(reversed(self.out))
        )
        self._emit("win", f"{winner} wins and scores {points} points!", player=winner, points=points)

    # ------------------------------------------------------------ serialisation
    def view_for(self, viewer: str) -> dict:
        """State visible to one participant. Other players' cards stay hidden."""
        in_game = viewer in self.hands
        current = None if self.over else self.current_player()
        out_names = {r.name: r.outcome for r in self.out}
        return {
            "mode": self.mode,
            "phase": self.phase,
            "turn_counter": self.turn_counter,
            "current": current,
            "direction": self.direction,
            "active_color": self.active_color,
            "top_card": self.top.to_dict(),
            "discard_count": len(self.discard),
            "draw_count": len(self.draw_pile),
            "pending_draw": self.pending_draw,
            "pending_min": self.pending_min,
            "seats": [
                {
                    "name": p,
                    "cards": len(self.hands[p]) if p in self.hands else 0,
                    "status": "playing" if p in self.hands else out_names.get(p, "left"),
                    "uno_vulnerable": p in self.uno_vulnerable,
                    "uno_safe": p in self.uno_safe,
                }
                for p in self.seating
            ],
            "hand": [c.to_dict() for c in self.hands[viewer]] if in_game else [],
            "playable": self.playable_ids(viewer),
            "drawn_card_id": self.drawn_card_id if current == viewer else None,
            "can_draw": in_game and current == viewer and self.phase == PLAY and not self.drawn_card_id,
            "can_pass": self.can_pass(viewer),
            "can_call_uno": self.can_call_uno(viewer),
            "spectating": not in_game,
            "winner": self.winner,
            "points": self.points,
            "results": [r.__dict__ for r in self.results],
            "log": list(self.log),
            "events": list(self.events),
        }


LABELS = {
    "skip": "Skip",
    "reverse": "Reverse",
    "draw2": "Draw 2",
    "draw4": "Draw 4",
    "skip_all": "Skip Everyone",
    "discard_all": "Discard All",
    "wild": "Wild",
    "wild_draw4": "Wild Draw 4",
    "wild_reverse_draw4": "Wild Reverse Draw 4",
    "wild_draw6": "Wild Draw 6",
    "wild_draw10": "Wild Draw 10",
    "wild_roulette": "Wild Color Roulette",
}


def describe(card: Card) -> str:
    name = LABELS.get(card.value, card.value)
    return name if card.is_wild else f"{card.color} {name}"
