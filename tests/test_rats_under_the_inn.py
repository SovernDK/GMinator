"""M3 exit criterion: the scenario plays to every ending with no AI."""

from collections.abc import Callable
from pathlib import Path

import pytest

from gminator.core.characters import create_character
from gminator.play.session import Session
from gminator.scenario.loader import load_scenario
from support import ScriptedDecider

RATS = Path(__file__).parents[1] / "scenarios" / "rats-under-the-inn"
SCORES = {
    "fighter": {"str": 16, "con": 15, "dex": 13, "wis": 12, "int": 9, "cha": 8},
    "thief": {"dex": 16, "int": 15, "cha": 13, "wis": 12, "str": 9, "con": 8},
}

Until = Callable[[Session], bool] | None


def revealed(secret_id: str) -> Until:
    return lambda session: secret_id in session.state.revealed


def at(location_id: str) -> Until:
    return lambda session: session.state.characters["pc"].location == location_id


TO_THE_CACHE = [("/go cellar", None), ("/go broken_wall", None), ("/go cache", None)]
BACK_TO_THE_INN = [("/go broken_wall", None), ("/go cellar", None), ("/go common_room", None)]
TO_THE_NEST = [("/go cellar", None), ("/go broken_wall", None), ("/go gallery", None)]

# For each ending: the class to play and the steps. A step repeats its command until its
# condition holds (or once, without one), and every step stops when the story ends.
PLAYS: dict[str, tuple[str, list[tuple[str, Until]]]] = {
    "fled": ("thief", [*TO_THE_NEST, ("/go river_exit", None)]),
    "corwin_killed": ("fighter", [("/move hack_and_slash corwin", None)] * 30),
    "exposed": (
        "thief",
        [
            *TO_THE_CACHE,
            ("/move search_the_cache", revealed("corwin_is_wererat")),
            *BACK_TO_THE_INN,
            *[("/move denounce_corwin maud", None)] * 30,
        ],
    ),
    "deal": (
        "thief",
        [
            *TO_THE_CACHE,
            ("/move search_the_cache", revealed("corwin_is_wererat")),
            *BACK_TO_THE_INN,
            *[("/move strike_a_deal corwin", None)] * 30,
        ],
    ),
    "swarm_won": ("fighter", [("/move defy_danger dex", None)] * 60),
    "died": (
        "thief",
        [*TO_THE_NEST, ("/go nest", None), *[("/move hack_and_slash swarm", None)] * 60],
    ),
}


@pytest.fixture(scope="module")
def rats(dungeon_world):
    return load_scenario(RATS, dungeon_world)


def play(pack, scenario, seed: int, class_id: str, steps) -> str | None:
    character = create_character(pack, class_id, "pc", "Hero", SCORES[class_id])
    session = Session.begin(pack, scenario, seed, character)
    session.opening()
    for command, until in steps:
        for _ in range(30):
            session.handle(command, ScriptedDecider())
            if session.ending or until is None or until(session):
                break
        if session.ending:
            return session.ending.id
    return None


def test_every_ending_has_a_play(rats):
    assert {ending.id for ending in rats.endings} == set(PLAYS)


@pytest.mark.parametrize("ending_id", list(PLAYS))
def test_scenario_plays_to_the_ending(dungeon_world, rats, ending_id):
    class_id, steps = PLAYS[ending_id]

    reached = (play(dungeon_world, rats, seed, class_id, steps) for seed in range(200))

    assert ending_id in reached


def test_every_location_can_be_reached_from_the_start(rats):
    reachable, frontier = set(), [rats.manifest.start]
    while frontier:
        location_id = frontier.pop()
        if location_id not in reachable:
            reachable.add(location_id)
            frontier += rats.locations[location_id].exits

    assert reachable == set(rats.locations)


def test_scenario_is_for_dungeon_world_and_carries_a_licence(rats):
    assert rats.manifest.system == "dungeon-world"
    assert rats.manifest.license
    assert (RATS / "LICENSE.md").exists()
