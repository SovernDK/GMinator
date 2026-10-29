import pytest
from pydantic import ValidationError

from gminator.core.events import (
    CharacterCreated,
    ChoiceMade,
    ClockAdvanced,
    ClockCreated,
    DiceRolled,
    DieRoll,
    ForwardChanged,
    GameStarted,
    GmMoveTriggered,
    HoldChanged,
    HpChanged,
    ItemGained,
    ItemUsed,
    MoveMade,
    QuestionsAsked,
    TagAdded,
    TagRemoved,
    XpMarked,
    event_adapter,
)

ONE_OF_EACH = [
    GameStarted(seed=12),
    CharacterCreated(character_id="pc", name="Brakka", stats={"str": 2}, max_hp=18),
    DiceRolled(
        expression="2d6", dice=[DieRoll(sides=6, value=4), DieRoll(sides=6, value=1)], total=5
    ),
    HpChanged(character_id="pc", amount=-3),
    XpMarked(character_id="pc", amount=1),
    ClockCreated(clock_id="swarm", label="The swarm grows", segments=4),
    ClockAdvanced(clock_id="swarm", amount=1),
    TagAdded(character_id="pc", tag="dead"),
    TagRemoved(character_id="pc", tag="dead"),
    HoldChanged(character_id="pc", move_id="defend", amount=3),
    ForwardChanged(character_id="pc", amount=1),
    ItemGained(character_id="pc", item_id="dungeon_rations", uses=5),
    ItemUsed(character_id="pc", item_id="dungeon_rations"),
    MoveMade(character_id="pc", move_id="hack_and_slash", target_id="rat", total=9, band="partial"),
    ChoiceMade(character_id="pc", move_id="volley", chosen=["Take several shots"]),
    QuestionsAsked(character_id="pc", questions=["What is about to happen?"]),
    GmMoveTriggered(severity="hard"),
]


@pytest.mark.parametrize("event", ONE_OF_EACH, ids=lambda event: event.type)
def test_event_round_trips_through_json(event):
    assert event_adapter.validate_json(event_adapter.dump_json(event)) == event


def test_unknown_event_type_is_rejected():
    with pytest.raises(ValidationError):
        event_adapter.validate_python({"type": "dragon_summoned"})


def test_events_are_immutable():
    event = HpChanged(character_id="pc", amount=-3)

    with pytest.raises(ValidationError):
        event.amount = 100


def test_character_created_defaults_suit_a_monster_without_a_class():
    event = CharacterCreated(character_id="rat", name="Rat", stats={}, max_hp=3)

    assert (event.class_id, event.damage, event.armor, event.level) == (None, None, 0, 1)
