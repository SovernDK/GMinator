"""Seeded, resumable dice."""

import random
from typing import Protocol


class Dice(Protocol):
    def roll(self, sides: int) -> int: ...


class SeededDice:
    """Each die is drawn from (seed, position), so a game can resume at any position
    without replaying earlier rolls."""

    def __init__(self, seed: int, position: int = 0) -> None:
        self.seed = seed
        self.position = position

    def roll(self, sides: int) -> int:
        if sides < 1:
            raise ValueError(f"a die needs at least one side, got {sides}")
        result = random.Random(f"{self.seed}:{self.position}").randint(1, sides)
        self.position += 1
        return result
