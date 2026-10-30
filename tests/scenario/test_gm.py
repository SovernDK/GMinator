import pytest

from gminator.core.events import (
    CharacterCreated,
    CharacterMoved,
    ClockAdvanced,
    DiceRolled,
    GmMoveMade,
    HpChanged,
)
from gminator.core.game import Game
from gminator.scenario.gm import gm_move_candidates, make_scenario_gm_move
from gminator.scenario.story import opening_events
from support import ScriptedDecider
from tiny_cellar import HOSTILE_RATS, NPCS, VALID, load_tiny_cellar

HERO = CharacterCreated(character_id="hero", name="Hero", stats={}, max_hp=10)
TO_CELLAR = CharacterMoved(character_id="hero", location_id="cellar")


def opened(scenario, *events, seed=0) -> Game:
    game = Game.new(seed)
    for event in (HERO, *opening_events(scenario, "hero"), *events):
        game.record(event)
    return game


def candidate_ids(scenario, pack, game, severity) -> list[str]:
    return [c.gm_move.id for c in gm_move_candidates(scenario, pack, game.state, "hero", severity)]


def test_candidates_are_the_pack_moves_of_that_severity_when_no_danger_applies(
    tmp_path, dungeon_world
):
    scenario = load_tiny_cellar(tmp_path, dungeon_world)
    game = opened(scenario)

    assert candidate_ids(scenario, dungeon_world, game, "hard") == ["deal_damage", "put_in_a_spot"]
    assert "show_signs" in candidate_ids(scenario, dungeon_world, game, "soft")


def test_danger_moves_join_the_candidates_while_their_condition_holds(tmp_path, dungeon_world):
    scenario = load_tiny_cellar(tmp_path, dungeon_world)
    game = opened(scenario, TO_CELLAR)

    candidates = gm_move_candidates(scenario, dungeon_world, game.state, "hero", "hard")

    assert [c.gm_move.id for c in candidates] == ["rats_bite", "deal_damage", "put_in_a_spot"]
    assert [c.source_id for c in candidates] == ["corwin", None, None]


@pytest.mark.parametrize("seed", range(6))
def test_the_gm_move_is_picked_by_a_recorded_die(tmp_path, dungeon_world, seed):
    scenario = load_tiny_cellar(tmp_path, dungeon_world)
    game = opened(scenario, TO_CELLAR, seed=seed)
    before = len(game.events)

    make_scenario_gm_move(game, dungeon_world, scenario, "hero", "hard", ScriptedDecider())

    die, made = game.events[before : before + 2]
    assert isinstance(die, DiceRolled)
    assert die.expression == "d3"
    expected = ["rats_bite", "deal_damage", "put_in_a_spot"][die.total - 1]
    assert made == GmMoveMade(gm_move_id=expected)


def test_a_lone_candidate_needs_no_die_and_comes_from_its_danger_npc(tmp_path, dungeon_world):
    scenario = load_tiny_cellar(tmp_path, dungeon_world)
    pack = dungeon_world.model_copy(update={"gm_moves": {}})
    game = opened(scenario, TO_CELLAR)
    before = len(game.events)

    resolution = make_scenario_gm_move(game, pack, scenario, "hero", "hard", ScriptedDecider())

    assert game.events[before] == GmMoveMade(gm_move_id="rats_bite")
    damage = next(e for e in resolution.events if isinstance(e, DiceRolled))
    assert damage.expression == "target.damage"
    assert game.state.characters["hero"].hp == 10 - damage.total
    assert ClockAdvanced(clock_id="swarm", amount=1) in resolution.events


def test_without_candidates_the_gm_makes_no_move(tmp_path, dungeon_world):
    scenario = load_tiny_cellar(tmp_path, dungeon_world)
    pack = dungeon_world.model_copy(update={"gm_moves": {}})
    game = opened(scenario)
    before = game.events

    assert make_scenario_gm_move(game, pack, scenario, "hero", "hard", ScriptedDecider()) is None
    assert game.events == before


@pytest.fixture
def ratty(tmp_path, dungeon_world):
    return load_tiny_cellar(tmp_path, dungeon_world, {**VALID, "npcs.yaml": NPCS + HOSTILE_RATS})


def test_a_hostile_npc_here_makes_the_gm_move_when_it_has_one(ratty, dungeon_world):
    game = opened(ratty, TO_CELLAR)

    candidates = gm_move_candidates(ratty, dungeon_world, game.state, "hero", "hard")

    assert [(c.gm_move.id, c.source_id) for c in candidates] == [("rats_gnaw", "rats")]


def test_without_a_move_from_a_hostile_npc_here_any_candidate_will_do(ratty, dungeon_world):
    game = opened(ratty, TO_CELLAR)

    assert "show_signs" in candidate_ids(ratty, dungeon_world, game, "soft")


def test_an_npc_makes_its_moves_only_while_alive_and_with_the_pc(ratty, dungeon_world):
    away = opened(ratty)
    dead = opened(ratty, TO_CELLAR, HpChanged(character_id="rats", amount=-99))

    assert "rats_gnaw" not in candidate_ids(ratty, dungeon_world, away, "hard")
    assert candidate_ids(ratty, dungeon_world, dead, "hard") == [
        "rats_bite",
        "deal_damage",
        "put_in_a_spot",
    ]


def test_an_npc_move_comes_from_the_npc(ratty, dungeon_world):
    game = opened(ratty, TO_CELLAR)

    resolution = make_scenario_gm_move(
        game, dungeon_world, ratty, "hero", "hard", ScriptedDecider()
    )

    damage = next(e for e in resolution.events if isinstance(e, DiceRolled))
    assert damage.expression == "target.damage"
    assert game.state.characters["hero"].hp == 10 - damage.total
