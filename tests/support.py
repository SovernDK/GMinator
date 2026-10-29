"""Helpers shared by tests."""

from collections.abc import Sequence
from pathlib import Path
from textwrap import dedent

from gminator.core.game import Game

DUNGEON_WORLD = Path(__file__).parents[1] / "packs" / "dungeon-world"

BAND_TOTALS = {"strong": range(10, 100), "partial": range(7, 10), "miss": range(-100, 7)}


def write_files(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(text), encoding="utf-8")
    return root


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


class ScriptedConfirmer:
    """Answers confirmations from a script, then says yes."""

    def __init__(self, *answers: bool) -> None:
        self._answers = list(answers)
        self.questions: list[str] = []

    def confirm(self, question: str) -> bool:
        self.questions.append(question)
        return self._answers.pop(0) if self._answers else True
