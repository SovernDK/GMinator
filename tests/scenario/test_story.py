from gminator.core.events import (
    CharacterCreated,
    ClockAdvanced,
    HpChanged,
    TagAdded,
)
from gminator.core.game import Game
from gminator.scenario.story import opening_events, reached_ending
from tiny_cellar import load_tiny_cellar

HERO = CharacterCreated(character_id="hero", name="Hero", stats={}, max_hp=10)


def opened(scenario, *events) -> Game:
    game = Game.new(0)
    for event in (HERO, *opening_events(scenario, "hero"), *events):
        game.record(event)
    return game


def test_opening_creates_npcs_from_their_stat_blocks_where_they_start(tmp_path, dungeon_world):
    scenario = load_tiny_cellar(tmp_path, dungeon_world)

    corwin = opened(scenario).state.characters["corwin"]

    assert (corwin.name, corwin.hp, corwin.max_hp) == ("Corwin", 8, 8)
    assert (corwin.damage, corwin.armor, corwin.location) == ("d6", 0, "inn")


def test_opening_gives_each_danger_a_clock_with_one_segment_per_portent(tmp_path, dungeon_world):
    scenario = load_tiny_cellar(tmp_path, dungeon_world)

    clock = opened(scenario).state.clocks["swarm"]

    assert (clock.label, clock.segments, clock.filled) == ("The swarm", 2, 0)


def test_opening_puts_the_pc_at_the_start(tmp_path, dungeon_world):
    scenario = load_tiny_cellar(tmp_path, dungeon_world)

    assert opened(scenario).state.characters["hero"].location == "inn"


def test_no_ending_is_reached_at_the_start(tmp_path, dungeon_world):
    scenario = load_tiny_cellar(tmp_path, dungeon_world)

    assert reached_ending(scenario, opened(scenario).state, "hero") is None


def test_ending_is_reached_when_its_condition_holds(tmp_path, dungeon_world):
    scenario = load_tiny_cellar(tmp_path, dungeon_world)
    game = opened(scenario, TagAdded(character_id="corwin", tag="exposed"))

    assert reached_ending(scenario, game.state, "hero").id == "exposed"


def test_earlier_ending_wins_when_several_hold(tmp_path, dungeon_world):
    scenario = load_tiny_cellar(tmp_path, dungeon_world)
    game = opened(
        scenario,
        TagAdded(character_id="corwin", tag="exposed"),
        ClockAdvanced(clock_id="swarm", amount=2),
        HpChanged(character_id="hero", amount=-1),
    )

    assert reached_ending(scenario, game.state, "hero").id == "overrun"
