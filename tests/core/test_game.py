import pytest

from gminator.core.events import CharacterCreated, DiceRolled, GameStarted, HpChanged
from gminator.core.expr import ExpressionError
from gminator.core.game import Game
from gminator.core.state import ReplayError

FIGHTER = CharacterCreated(character_id="pc", name="Brakka", stats={"str": 2}, max_hp=18)


def test_new_game_log_starts_with_its_seed():
    game = Game.new(seed=5)

    assert game.events == (GameStarted(seed=5),)
    assert game.state.seed == 5


def test_recorded_event_is_appended_and_applied():
    game = Game.new(seed=5)

    game.record(FIGHTER)
    game.record(HpChanged(character_id="pc", amount=-2))

    assert game.events[1:] == (FIGHTER, HpChanged(character_id="pc", amount=-2))
    assert game.state.characters["pc"].hp == 16


def test_rejected_event_leaves_game_unchanged():
    game = Game.new(seed=5)
    game.record(FIGHTER)
    state_before = game.state

    with pytest.raises(ReplayError):
        game.record(HpChanged(character_id="ghost", amount=-1))

    assert game.events == (GameStarted(seed=5), FIGHTER)
    assert game.state == state_before


def test_roll_records_every_die_and_the_total():
    game = Game.new(seed=3)

    total = game.roll("2d6 + 1")

    event = game.events[-1]
    assert isinstance(event, DiceRolled)
    assert event.expression == "2d6 + 1"
    assert [die.sides for die in event.dice] == [6, 6]
    assert all(1 <= die.value <= 6 for die in event.dice)
    assert total == event.total == sum(die.value for die in event.dice) + 1
    assert game.state.rng_position == 2


def test_roll_resolves_refs():
    game = Game.new(seed=3)

    assert game.roll("stat.str + 1", refs={"stat.str": 2}) == 3


def test_invalid_roll_records_nothing():
    game = Game.new(seed=3)

    with pytest.raises(ExpressionError):
        game.roll("2d6 +")

    assert game.events == (GameStarted(seed=3),)


def test_same_seed_gives_same_rolls():
    first, second = Game.new(seed=11), Game.new(seed=11)

    assert [first.roll("2d6") for _ in range(10)] == [second.roll("2d6") for _ in range(10)]


def test_game_rebuilt_from_its_events_rolls_what_the_original_would():
    original = Game.new(seed=11)
    for _ in range(3):
        original.roll("2d6")

    rebuilt = Game(original.events)

    assert [rebuilt.roll("2d6") for _ in range(5)] == [original.roll("2d6") for _ in range(5)]
