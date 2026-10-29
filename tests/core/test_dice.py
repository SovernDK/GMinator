import pytest

from gminator.core.dice import SeededDice


def roll_many(dice: SeededDice, count: int, sides: int = 6) -> list[int]:
    return [dice.roll(sides) for _ in range(count)]


def test_same_seed_produces_same_sequence():
    assert roll_many(SeededDice(seed=42), 20) == roll_many(SeededDice(seed=42), 20)


def test_different_seeds_produce_different_sequences():
    assert roll_many(SeededDice(seed=1), 20) != roll_many(SeededDice(seed=2), 20)


def test_rolls_cover_every_face_and_nothing_else():
    results = set(roll_many(SeededDice(seed=7), 400, sides=4))

    assert results == {1, 2, 3, 4}


def test_position_counts_dice_rolled():
    dice = SeededDice(seed=1)
    roll_many(dice, 3)

    assert dice.position == 3


def test_dice_resumed_at_a_position_continue_the_original_sequence():
    original = SeededDice(seed=99)
    roll_many(original, 5)
    continuation = roll_many(original, 5)

    resumed = SeededDice(seed=99, position=5)

    assert roll_many(resumed, 5) == continuation


def test_die_needs_at_least_one_side():
    with pytest.raises(ValueError, match="side"):
        SeededDice(seed=1).roll(0)
