import pytest

from gminator.core.characters import create_character
from gminator.core.events import (
    CharacterMoved,
    ClockAdvanced,
    GameEnded,
    GmMoveMade,
    GmMoveTriggered,
    HpChanged,
    MoveMade,
    ObstacleCleared,
    SecretRevealed,
)
from gminator.core.game import Game
from gminator.packs.models import GmMoveDefinition
from gminator.play.session import Session
from support import BAND_TOTALS, ScriptedDecider, seed_for
from tiny_cellar import HOSTILE_RATS, NPCS, VALID, load_tiny_cellar

SCORES = {"str": 16, "con": 15, "dex": 13, "wis": 12, "int": 9, "cha": 8}


@pytest.fixture
def scenario(tmp_path, dungeon_world):
    return load_tiny_cellar(tmp_path, dungeon_world)


def begin(pack, scenario, seed=0, class_id="fighter") -> Session:
    hero = create_character(pack, class_id, "hero", "Hero", SCORES)
    return Session.begin(pack, scenario, seed, hero)


def run(session: Session, line: str, *picks) -> str:
    return "\n".join(session.handle(line, ScriptedDecider(*picks)))


def unchanged(session: Session, line: str) -> str:
    before = session.game.events
    output = run(session, line)
    assert session.game.events == before
    return output


def made(session: Session) -> list[MoveMade]:
    return [e for e in session.game.events if isinstance(e, MoveMade)]


# Starting and looking around


def test_session_begins_with_the_intro_at_the_start_location(dungeon_world, scenario):
    session = begin(dungeon_world, scenario)

    opening = "\n".join(session.opening())

    assert "You stand in the inn." in opening
    assert "The inn" in opening
    assert session.state.characters["hero"].location == "inn"
    assert "corwin" in session.state.characters


def test_look_shows_the_location_its_exits_and_who_is_here(dungeon_world, scenario):
    output = unchanged(begin(dungeon_world, scenario), "/look")

    assert "The inn" in output
    assert "Warm and loud." in output
    assert "The cellar (cellar)" in output
    assert "Corwin (corwin)" in output


def test_go_moves_the_pc_through_an_exit(dungeon_world, scenario):
    session = begin(dungeon_world, scenario)

    output = run(session, "/go cellar")

    assert session.state.characters["hero"].location == "cellar"
    assert "The cellar" in output


@pytest.mark.parametrize("line", ["/go attic", "/go inn", "/go"])
def test_go_refuses_places_not_reachable_from_here(dungeon_world, scenario, line):
    output = unchanged(begin(dungeon_world, scenario), line)

    assert "/go" in output or "can't" in output


# Making moves


def test_move_resolves_against_a_target_here(dungeon_world, scenario):
    session = begin(dungeon_world, scenario, seed_for("partial", 2))

    output = run(session, "/move hack_and_slash corwin")

    move = made(session)[-1]
    assert (move.move_id, move.target_id, move.band) == ("hack_and_slash", "corwin", "partial")
    assert "Hack and Slash" in output
    assert str(move.total) in output
    assert "the enemy makes an attack against you" in output
    assert "Corwin takes" in output


def test_move_passes_the_chosen_stat(dungeon_world, scenario):
    seed = seed_for("partial", 1)
    session = begin(dungeon_world, scenario, seed)

    run(session, "/move defy_danger dex")

    assert made(session)[-1].band == "partial"


def test_target_must_be_here(dungeon_world, scenario):
    session = begin(dungeon_world, scenario)
    session.game.record(CharacterMoved(character_id="corwin", location_id="cellar"))

    assert "not here" in unchanged(session, "/move hack_and_slash corwin")


@pytest.mark.parametrize(
    "line",
    [
        "/move summon_dragon",
        "/move tricks_of_the_trade",  # a thief move, and the hero is a fighter
        "/move last_breath",  # only made on reaching 0 HP
        "/move hack_and_slash",  # needs a target
        "/move defend_spend_hold corwin",  # no hold to spend
        "/move",
    ],
)
def test_moves_that_cannot_be_made_change_nothing(dungeon_world, scenario, line):
    assert unchanged(begin(dungeon_world, scenario), line)


def test_scenario_move_waits_for_its_condition(dungeon_world, scenario):
    session = begin(dungeon_world, scenario)

    assert "can't" in unchanged(session, "/move unmask corwin")
    session.game.record(SecretRevealed(secret_id="wererat"))
    run(session, "/move unmask corwin")

    assert made(session)[-1].move_id == "unmask"


def test_moves_lists_only_what_the_pc_can_make_now(dungeon_world, scenario):
    session = begin(dungeon_world, scenario)

    before = run(session, "/moves")
    session.game.record(SecretRevealed(secret_id="wererat"))
    after = run(session, "/moves")

    assert "hack_and_slash" in before
    assert "bend_bars_lift_gates" not in before  # no obstacle to bend
    assert "tricks_of_the_trade" not in before
    assert "last_breath" not in before
    assert "unmask" not in before
    assert "unmask" in after


# What happens after the move


def test_a_miss_brings_a_gm_move_told_as_what_happens_not_as_a_rule(dungeon_world, scenario):
    session = begin(dungeon_world, scenario, seed_for("miss", 1))

    output = run(session, "/move defy_danger dex")

    made = next(e for e in session.game.events if isinstance(e, GmMoveMade))
    gm_move = dungeon_world.gm_moves[made.gm_move_id]
    assert gm_move.text in output
    assert gm_move.name not in output
    assert "GM" not in output
    assert session.gm_lines == [gm_move.text]


def test_a_hostile_npc_here_answers_a_miss_with_its_own_move(dungeon_world, tmp_path):
    files = {**VALID, "npcs.yaml": NPCS + HOSTILE_RATS}
    scenario = load_tiny_cellar(tmp_path, dungeon_world, files)
    session = begin(dungeon_world, scenario, seed_for("miss", 2))
    session.game.record(CharacterMoved(character_id="hero", location_id="cellar"))

    output = run(session, "/move hack_and_slash rats")

    assert "Teeth sink into your leg." in output


def test_a_turn_that_fails_part_way_records_nothing(dungeon_world, scenario):
    spend_missing_hold = GmMoveDefinition(
        id="trip",
        name="Trip",
        severity="hard",
        effects=[{"spend_hold": {"move": "defend"}}],
    )
    pack = dungeon_world.model_copy(update={"gm_moves": {"trip": spend_missing_hold}})
    session = begin(pack, scenario, seed_for("miss", 1))

    output = unchanged(session, "/move defy_danger dex")

    assert "defend" in output


def test_reaching_zero_hp_brings_the_dying_move(dungeon_world, scenario):
    session = begin(dungeon_world, scenario, seed_for("strong", 0))
    session.game.record(HpChanged(character_id="hero", amount=-99))

    run(session, "/move spout_lore")

    assert [m.move_id for m in made(session)] == ["spout_lore", "last_breath"]


def test_ending_is_recorded_and_told_and_ends_play(dungeon_world, scenario):
    session = begin(dungeon_world, scenario)
    session.game.record(ClockAdvanced(clock_id="swarm", amount=2))

    output = run(session, "/go cellar")

    assert session.game.events[-1] == GameEnded(ending_id="overrun")
    assert session.ending.id == "overrun"
    assert "Overrun" in output
    assert "The rats win." in output
    assert "ended" in unchanged(session, "/go inn")
    assert "ended" in unchanged(session, "/move spout_lore")


# Information


def test_sheet_shows_the_pc(dungeon_world, scenario):
    output = unchanged(begin(dungeon_world, scenario), "/sheet")

    assert "Hero" in output
    assert "Fighter" in output
    assert "25/25" in output
    assert "Armor 2" in output  # chainmail and shield
    assert "Dungeon rations" in output


def test_clocks_show_each_danger_and_its_portents_so_far(dungeon_world, scenario):
    session = begin(dungeon_world, scenario)
    session.game.record(ClockAdvanced(clock_id="swarm", amount=1))

    output = unchanged(session, "/clocks")

    assert "The swarm: 1/2" in output
    assert "Rats in the pantry." in output
    assert "A child is bitten." not in output


def test_secrets_show_only_revealed_ones(dungeon_world, scenario):
    session = begin(dungeon_world, scenario)
    assert "Corwin is a wererat." not in unchanged(session, "/secrets")

    session.game.record(SecretRevealed(secret_id="wererat"))

    assert "Corwin is a wererat." in unchanged(session, "/secrets")


@pytest.mark.parametrize("line", ["/dance", "/", "I attack Corwin"])
def test_other_input_points_to_help_and_changes_nothing(dungeon_world, scenario, line):
    assert "/help" in unchanged(begin(dungeon_world, scenario), line)


def test_help_lists_the_commands(dungeon_world, scenario):
    output = unchanged(begin(dungeon_world, scenario), "/help")

    for command in ("/look", "/go", "/moves", "/move", "/sheet", "/clocks", "/secrets"):
        assert command in output


# Resuming


def test_a_resumed_session_carries_on_where_the_log_left_off(dungeon_world, scenario):
    session = begin(dungeon_world, scenario)
    run(session, "/go cellar")

    resumed = Session.resume(dungeon_world, scenario, session.game.events)

    assert resumed.pc_id == "hero"
    assert resumed.state == session.state
    assert "The inn" in run(resumed, "/go inn")


# Danger nearby: hostile rats in the cellar


DANGER_LOCATIONS = """\
- id: inn
  name: The inn
  exits: [cellar]
- id: cellar
  name: The cellar
  exits: [inn, pit]
  obstacles:
    - id: grate
      name: The grate
      description: Iron bars over the pit.
      blocks: pit
    - id: barrel
      name: A stuck barrel
- id: pit
  name: The pit
  exits: [cellar]
"""

RATS = """\
- id: rats
  name: The rats
  location: cellar
  max_hp: 7
  damage: d6
  attitude: hostile
"""

DEX, STR = 1, 2  # the hero's modifiers


@pytest.fixture
def cellar(tmp_path, dungeon_world):
    files = {**VALID, "locations.yaml": DANGER_LOCATIONS, "npcs.yaml": NPCS + RATS}
    return load_tiny_cellar(tmp_path, dungeon_world, files)


def in_the_cellar(pack, scenario, *bands: tuple[str, int], rats_alive=True) -> Session:
    """The hero in the cellar, with a seed whose first rolls plus their modifiers land in
    `bands`."""
    seed = next(
        seed
        for seed in range(5000)
        if all(
            game.roll("2d6") + modifier in BAND_TOTALS[band]
            for game in [Game.new(seed)]
            for band, modifier in bands
        )
    )
    session = begin(pack, scenario, seed)
    session.game.record(CharacterMoved(character_id="hero", location_id="cellar"))
    if not rats_alive:
        session.game.record(HpChanged(character_id="rats", amount=-99))
    return session


def test_going_on_past_a_hostile_npc_defies_danger_first(dungeon_world, cellar):
    session = in_the_cellar(dungeon_world, cellar, ("strong", DEX))

    output = run(session, "/go inn")

    assert [m.move_id for m in made(session)] == ["defy_danger"]
    assert session.state.characters["hero"].location == "inn"
    assert "Defy Danger" in output


def test_a_partial_hit_goes_on_at_a_cost(dungeon_world, cellar):
    session = in_the_cellar(dungeon_world, cellar, ("partial", DEX))

    run(session, "/go inn")

    assert session.state.characters["hero"].location == "inn"
    assert GmMoveTriggered(severity="soft") in session.game.events


def test_a_miss_stops_the_action(dungeon_world, cellar):
    session = in_the_cellar(dungeon_world, cellar, ("miss", DEX))

    run(session, "/go inn")

    assert session.state.characters["hero"].location == "cellar"
    assert GmMoveTriggered(severity="hard") in session.game.events


def test_any_other_move_near_danger_is_gated(dungeon_world, cellar):
    session = in_the_cellar(dungeon_world, cellar, ("strong", DEX))

    run(session, "/move spout_lore")

    assert [m.move_id for m in made(session)] == ["defy_danger", "spout_lore"]


@pytest.mark.parametrize("line", ["/move hack_and_slash rats", "/move defy_danger str"])
def test_fighting_or_defying_danger_yourself_is_not_gated(dungeon_world, cellar, line):
    session = in_the_cellar(dungeon_world, cellar)

    run(session, line)

    assert len(made(session)) == 1


def test_no_danger_without_a_living_hostile_npc(dungeon_world, cellar):
    at_the_inn = begin(dungeon_world, cellar)  # Corwin is here, but not hostile
    rats_dead = in_the_cellar(dungeon_world, cellar, rats_alive=False)

    run(at_the_inn, "/move spout_lore")
    run(rats_dead, "/move spout_lore")

    assert [m.move_id for m in made(at_the_inn)] == ["spout_lore"]
    assert [m.move_id for m in made(rats_dead)] == ["spout_lore"]


def test_the_danger_stat_follows_the_action(dungeon_world, cellar):
    session = in_the_cellar(dungeon_world, cellar)

    assert session.danger_stat(["travel"]) == "dex"
    assert session.danger_stat([]) == "dex"
    assert session.danger_stat(["combat"]) is None
    assert session.threats() == ["rats"]


# Obstacles


def test_look_shows_what_is_in_the_way(dungeon_world, cellar):
    output = unchanged(in_the_cellar(dungeon_world, cellar), "/look")

    assert "The grate (grate), blocking The pit" in output
    assert "A stuck barrel (barrel)" in output


def test_a_blocked_exit_cannot_be_used(dungeon_world, cellar):
    session = in_the_cellar(dungeon_world, cellar, rats_alive=False)

    assert "The grate blocks the way to The pit" in unchanged(session, "/go pit")


def test_an_obstacle_move_waits_for_an_obstacle(dungeon_world, cellar):
    session = begin(dungeon_world, cellar)

    assert "can't" in unchanged(session, "/move bend_bars_lift_gates grate")
    assert "bend_bars_lift_gates" not in run(session, "/moves")


def test_bending_the_bars_clears_the_obstacle_for_good(dungeon_world, cellar):
    session = in_the_cellar(dungeon_world, cellar, ("strong", STR), rats_alive=False)

    run(session, "/move bend_bars_lift_gates grate")

    assert ObstacleCleared(obstacle_id="grate") in session.game.events
    assert "grate" not in unchanged(session, "/look")
    assert "no grate" in unchanged(session, "/move bend_bars_lift_gates grate")
    run(session, "/go pit")
    assert session.state.characters["hero"].location == "pit"


def test_a_move_then_goes_on_unless_it_misses(dungeon_world, cellar):
    went = in_the_cellar(dungeon_world, cellar, ("partial", STR), rats_alive=False)
    stayed = in_the_cellar(dungeon_world, cellar, ("miss", STR), rats_alive=False)

    output = run(went, "/move bend_bars_lift_gates grate then pit")
    run(stayed, "/move bend_bars_lift_gates grate then pit")

    assert went.state.characters["hero"].location == "pit"
    assert "== The pit ==" in output
    assert stayed.state.characters["hero"].location == "cellar"


def test_one_danger_move_covers_a_move_and_where_it_goes_on_to(dungeon_world, cellar):
    session = in_the_cellar(dungeon_world, cellar, ("strong", DEX), ("strong", STR))

    run(session, "/move bend_bars_lift_gates grate then pit")

    assert [m.move_id for m in made(session)] == ["defy_danger", "bend_bars_lift_gates"]
    assert session.state.characters["hero"].location == "pit"


@pytest.mark.parametrize("line", ["/move spout_lore then attic", "/move spout_lore then"])
def test_then_needs_a_way_on(dungeon_world, cellar, line):
    unchanged(in_the_cellar(dungeon_world, cellar), line)


# The dead


def test_the_dead_are_remains_not_people(dungeon_world, scenario):
    session = begin(dungeon_world, scenario)
    session.game.record(HpChanged(character_id="corwin", amount=-99))

    output = unchanged(session, "/look")

    assert "Remains: the body of Corwin" in output
    assert "Here:" not in output
    assert "no corwin" in unchanged(session, "/move hack_and_slash corwin")


# The story the narrator is told


def test_the_story_tells_the_turn_without_numbers(dungeon_world, scenario):
    session = begin(dungeon_world, scenario, seed_for("partial", STR))

    lines = run(session, "/move hack_and_slash corwin")

    story = "\n".join(session.story)
    assert any(c.isdigit() for c in lines)
    assert not any(c.isdigit() for c in story)
    assert "Hero tries Hack and Slash, and it only half works." in story
    assert "Hero is hurt." in story
