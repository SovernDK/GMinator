"""Helpers shared by tests."""

from collections.abc import Sequence
from pathlib import Path

from gminator.core.game import Game

DUNGEON_WORLD = Path(__file__).parents[1] / "packs" / "dungeon-world"

BAND_TOTALS = {"strong": range(10, 100), "partial": range(7, 10), "miss": range(-100, 7)}


class ScriptedDecider:
    """Answers choices from a script, then falls back to the first `n` options."""

    def __init__(self, *picks: Sequence[int]) -> None:
        self._picks = list(picks)
        self.calls: list[tuple[str, list[str], int]] = []

    def choose(self, prompt: str, options: Sequence[str], n: int) -> Sequence[int]:
        self.calls.append((prompt, list(options), n))
        return self._picks.pop(0) if self._picks else list(range(n))


def seed_for(band: str, modifier: int = 0) -> int:
    """A seed whose first 2d6 roll plus `modifier` lands in `band`."""
    return next(
        seed for seed in range(1000) if Game.new(seed).roll("2d6") + modifier in BAND_TOTALS[band]
    )


def first_roll(seed: int) -> int:
    return Game.new(seed).roll("2d6")
