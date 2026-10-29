import pytest
from pydantic import TypeAdapter, ValidationError

from gminator.core.conditions import holds
from gminator.core.events import (
    CharacterCreated,
    CharacterMoved,
    ClockAdvanced,
    ClockCreated,
    GameStarted,
    HpChanged,
    SecretRevealed,
    TagAdded,
)
from gminator.core.state import replay
from gminator.packs.models import Condition

HERO = CharacterCreated(character_id="hero", name="Hero", stats={}, max_hp=10)
CORWIN = CharacterCreated(character_id="corwin", name="Corwin", stats={}, max_hp=8)

condition_adapter: TypeAdapter[Condition] = TypeAdapter(Condition)


def state_after(*events):
    return replay(
        [
            GameStarted(seed=0),
            HERO,
            CORWIN,
            ClockCreated(clock_id="swarm", label="Swarm", segments=2),
            CharacterMoved(character_id="hero", location_id="cellar"),
            CharacterMoved(character_id="corwin", location_id="cellar"),
            *events,
        ]
    )


def check(condition: dict, *events) -> bool:
    return holds(condition_adapter.validate_python(condition), state_after(*events), "hero")


def test_secret_revealed():
    assert not check({"secret_revealed": "wererat"})
    assert check({"secret_revealed": "wererat"}, SecretRevealed(secret_id="wererat"))


def test_clock_full():
    assert not check({"clock_full": "swarm"}, ClockAdvanced(clock_id="swarm", amount=1))
    assert check({"clock_full": "swarm"}, ClockAdvanced(clock_id="swarm", amount=2))


def test_pc_at():
    assert check({"pc_at": "cellar"})
    assert not check({"pc_at": "tunnel"})


def test_pc_has_tag():
    assert not check({"pc_has_tag": "dead"})
    assert check({"pc_has_tag": "dead"}, TagAdded(character_id="hero", tag="dead"))


def test_npc_has_tag():
    condition = {"npc_has_tag": {"npc": "corwin", "tag": "exposed"}}

    assert not check(condition, TagAdded(character_id="hero", tag="exposed"))
    assert check(condition, TagAdded(character_id="corwin", tag="exposed"))


@pytest.mark.parametrize(
    "event",
    [HpChanged(character_id="corwin", amount=-8), TagAdded(character_id="corwin", tag="dead")],
    ids=["no-hp", "dead-tag"],
)
def test_npc_dead(event):
    assert not check({"npc_dead": "corwin"}, HpChanged(character_id="corwin", amount=-7))
    assert check({"npc_dead": "corwin"}, event)


def test_npc_with_pc_needs_the_same_location():
    moved_away = CharacterMoved(character_id="corwin", location_id="cache")

    assert check({"npc_with_pc": "corwin"})
    assert not check({"npc_with_pc": "corwin"}, moved_away)


def test_npc_with_pc_needs_the_npc_alive():
    assert not check({"npc_with_pc": "corwin"}, HpChanged(character_id="corwin", amount=-8))


def test_all_any_and_not_combine_conditions():
    revealed = SecretRevealed(secret_id="wererat")
    both = {"all": [{"pc_at": "cellar"}, {"secret_revealed": "wererat"}]}
    either = {"any": [{"pc_at": "tunnel"}, {"secret_revealed": "wererat"}]}

    assert not check(both)
    assert check(both, revealed)
    assert not check(either)
    assert check(either, revealed)
    assert check({"not": {"pc_at": "tunnel"}})
    assert not check({"not": {"pc_at": "cellar"}})


def test_unknown_condition_is_rejected_naming_the_known_ones():
    with pytest.raises(ValidationError, match="secret_revealed"):
        condition_adapter.validate_python({"moon_is_full": True})


def test_condition_with_two_keys_is_rejected():
    with pytest.raises(ValidationError, match="exactly one key"):
        condition_adapter.validate_python({"pc_at": "cellar", "secret_revealed": "wererat"})
