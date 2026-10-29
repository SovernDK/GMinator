"""A running game: the event log plus the state it replays to."""

from collections.abc import Iterable

from gminator.core.dice import Dice, SeededDice
from gminator.core.events import DiceRolled, DieRoll, Event, GameStarted
from gminator.core.expr import Refs, parse
from gminator.core.state import GameState, apply, replay


class _RecordingDice:
    def __init__(self, inner: Dice) -> None:
        self._inner = inner
        self.rolls: list[DieRoll] = []

    def roll(self, sides: int) -> int:
        value = self._inner.roll(sides)
        self.rolls.append(DieRoll(sides=sides, value=value))
        return value


class Game:
    def __init__(self, events: Iterable[Event]) -> None:
        self._events = tuple(events)
        self._state = replay(self._events)

    @classmethod
    def new(cls, seed: int) -> "Game":
        return cls([GameStarted(seed=seed)])

    @property
    def events(self) -> tuple[Event, ...]:
        return self._events

    @property
    def state(self) -> GameState:
        return self._state

    def record(self, event: Event) -> GameState:
        """Apply `event` and append it to the log. A rejected event changes nothing."""
        self._state = apply(self._state, event)
        self._events = (*self._events, event)
        return self._state

    def roll(self, expression: str, refs: Refs | None = None) -> int:
        dice = _RecordingDice(SeededDice(self._state.seed, self._state.rng_position))
        total = parse(expression).evaluate(dice, refs or {})
        self.record(DiceRolled(expression=expression, dice=dice.rolls, total=total))
        return total
