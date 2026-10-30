import pytest

from gminator.core.characters import CharacterError, create_character, quick_start
from gminator.core.events import CharacterCreated, ItemGained
from gminator.core.game import Game

SCORES = {"str": 16, "con": 15, "dex": 13, "wis": 12, "int": 9, "cha": 8}


def gained(events) -> list[tuple[str, int | None]]:
    return [(e.item_id, e.uses) for e in events if isinstance(e, ItemGained)]


@pytest.mark.parametrize(
    ("score", "modifier"),
    [
        (3, -3),
        (4, -2),
        (5, -2),
        (6, -1),
        (8, -1),
        (9, 0),
        (12, 0),
        (13, 1),
        (15, 1),
        (16, 2),
        (17, 2),
        (18, 3),
    ],
)
def test_dungeon_world_score_modifiers(dungeon_world, score, modifier):
    assert dungeon_world.manifest.modifier(score) == modifier


def test_fighter_is_created_from_scores(dungeon_world):
    events = create_character(dungeon_world, "fighter", "pc", "Brakka", SCORES)

    assert events[0] == CharacterCreated(
        character_id="pc",
        name="Brakka",
        stats={"str": 2, "con": 1, "dex": 1, "wis": 0, "int": 0, "cha": -1},
        max_hp=25,
        class_id="fighter",
        damage="d10",
    )


def test_a_quick_start_gives_the_scores_to_the_stats_in_the_pack_order(dungeon_world):
    events = quick_start(dungeon_world, "thief", "pc", "Vex")

    assert events == create_character(
        dungeon_world,
        "thief",
        "pc",
        "Vex",
        {"str": 16, "dex": 15, "con": 13, "int": 12, "wis": 9, "cha": 8},
    )


def test_thief_hp_and_damage_come_from_the_class(dungeon_world):
    created = create_character(dungeon_world, "thief", "pc", "Vex", SCORES)[0]

    assert (created.max_hp, created.damage) == (21, "d8")


def test_fighter_gets_starting_gear_and_first_choices_by_default(dungeon_world):
    events = create_character(dungeon_world, "fighter", "pc", "Brakka", SCORES)

    assert gained(events) == [
        ("dungeon_rations", 5),
        ("short_sword", None),
        ("chainmail", None),
        ("adventuring_gear", 5),
        ("healing_potion", 1),
        ("healing_potion", 1),
        ("shield", None),
    ]


def test_gear_choices_pick_options(dungeon_world):
    events = create_character(
        dungeon_world, "thief", "pc", "Vex", SCORES, gear_choices=[[1], [1], [1]]
    )

    assert gained(events) == [
        ("dungeon_rations", 5),
        ("leather_armor", None),
        ("poison", 3),
        ("rapier", None),
        ("ragged_bow", None),
        ("bundle_of_arrows", 3),
        ("healing_potion", 1),
    ]


def test_created_character_replays_into_state(dungeon_world):
    game = Game.new(seed=1)
    for event in create_character(dungeon_world, "fighter", "pc", "Brakka", SCORES):
        game.record(event)

    pc = game.state.characters["pc"]
    assert (pc.hp, pc.max_hp, pc.stats["str"]) == (25, 25, 2)
    assert len(pc.inventory) == 7


def test_unknown_class_is_rejected(dungeon_world):
    with pytest.raises(CharacterError, match="wizard"):
        create_character(dungeon_world, "wizard", "pc", "Tim", SCORES)


def test_every_stat_needs_a_score(dungeon_world):
    scores = {key: value for key, value in SCORES.items() if key != "cha"}

    with pytest.raises(CharacterError, match="cha"):
        create_character(dungeon_world, "fighter", "pc", "Brakka", scores)


def test_scores_must_be_the_pack_score_array(dungeon_world):
    with pytest.raises(CharacterError, match="16, 15, 13, 12, 9, 8"):
        create_character(dungeon_world, "fighter", "pc", "Brakka", {**SCORES, "cha": 18})


@pytest.mark.parametrize(
    "choices",
    [[[0]], [[0], [0], [0], [0]], [[5], [0], [0, 1]], [[0], [0], [0]], [[0], [0], [1, 1]]],
    ids=["too-few-choices", "too-many-choices", "out-of-range", "pick-too-few", "repeat"],
)
def test_invalid_gear_choices_are_rejected(dungeon_world, choices):
    with pytest.raises(CharacterError, match="gear"):
        create_character(dungeon_world, "fighter", "pc", "Brakka", SCORES, gear_choices=choices)
