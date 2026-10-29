import json

import pytest

from gminator.core.events import CharacterCreated, DiceRolled, DieRoll, GameStarted, HpChanged
from gminator.persistence.saves import SaveError, load_game, save_game

EVENTS = [
    GameStarted(seed=12),
    CharacterCreated(character_id="pc", name="Brakka", stats={"str": 2}, max_hp=18),
    DiceRolled(expression="d10", dice=[DieRoll(sides=10, value=4)], total=4),
    HpChanged(character_id="pc", amount=-4),
]


def test_saved_events_load_back_identical(tmp_path):
    path = tmp_path / "game.json"

    save_game(path, EVENTS)

    assert load_game(path) == EVENTS


def test_saving_again_replaces_the_previous_save(tmp_path):
    path = tmp_path / "game.json"
    save_game(path, EVENTS)

    save_game(path, EVENTS[:2])

    assert load_game(path) == EVENTS[:2]


@pytest.mark.parametrize(
    "contents",
    [
        "not json",
        json.dumps([]),
        json.dumps({"format": "something-else", "version": 1, "events": []}),
        json.dumps({"format": "gminator-save", "version": 999, "events": []}),
        json.dumps({"format": "gminator-save", "version": 1, "events": [{"type": "dragon"}]}),
    ],
    ids=["not-json", "not-an-object", "wrong-format", "future-version", "unknown-event"],
)
def test_unreadable_save_raises_save_error(tmp_path, contents):
    path = tmp_path / "game.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(SaveError):
        load_game(path)
