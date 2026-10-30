from pathlib import Path

import pytest

from gminator.packs.loader import PackError
from gminator.scenario.loader import load_scenario
from support import write_files
from tiny_cellar import HOSTILE_RATS, SECRETS, VALID


def problems(root: Path, files: dict[str, str], pack) -> list:
    with pytest.raises(PackError) as error:
        load_scenario(write_files(root, files), pack)
    return error.value.problems


def only_problem(root: Path, files: dict[str, str], pack):
    found = problems(root, files, pack)
    assert len(found) == 1, found
    return found[0]


def changed(name: str, old: str, new: str) -> dict[str, str]:
    assert old in VALID[name]
    return {**VALID, name: VALID[name].replace(old, new)}


def test_loads_every_part_of_a_scenario(tmp_path, dungeon_world):
    scenario = load_scenario(write_files(tmp_path, VALID), dungeon_world)

    assert scenario.manifest.name == "Tiny Cellar"
    assert scenario.locations["inn"].exits == ["cellar"]
    assert scenario.npcs["corwin"].knows == ["wererat"]
    assert set(scenario.secrets) == {"wererat"}
    assert set(scenario.tags) == {"exposed"}
    assert [danger.id for danger in scenario.dangers()] == ["swarm"]
    assert [ending.id for ending in scenario.endings] == ["overrun", "exposed"]
    assert set(scenario.moves) == {"unmask"}


def test_only_the_manifest_locations_and_endings_are_required(tmp_path, dungeon_world):
    files = {name: VALID[name] for name in ("scenario.yaml", "locations.yaml")}
    files["endings.yaml"] = "- {id: fled, title: Fled, text: Gone., when: {pc_at: cellar}}\n"

    scenario = load_scenario(write_files(tmp_path, files), dungeon_world)

    assert scenario.npcs == scenario.secrets == scenario.fronts == scenario.moves == {}


@pytest.mark.parametrize("name", ["scenario.yaml", "locations.yaml", "endings.yaml"])
def test_required_files_are_reported_missing(tmp_path, dungeon_world, name):
    files = {key: text for key, text in VALID.items() if key != name}

    problem = only_problem(tmp_path, files, dungeon_world)

    assert problem.path.name == name
    assert "missing" in problem.message


def test_validation_error_reports_file_and_line(tmp_path, dungeon_world):
    problem = only_problem(tmp_path, changed("npcs.yaml", "max_hp: 8", "max_hp: -1"), dungeon_world)

    assert (problem.path.name, problem.line) == ("npcs.yaml", 4)


def test_scenario_must_be_for_the_loaded_pack(tmp_path, dungeon_world):
    files = changed("scenario.yaml", "system: dungeon-world", "system: apocalypse-world")

    problem = only_problem(tmp_path, files, dungeon_world)

    assert (problem.path.name, problem.line) == ("scenario.yaml", 6)
    assert "apocalypse-world" in problem.message


@pytest.mark.parametrize(
    ("name", "old", "new", "line"),
    [
        ("scenario.yaml", "start: inn", "start: attic", 7),
        ("locations.yaml", "exits: [cellar]", "exits: [attic]", 4),
        ("npcs.yaml", "location: inn", "location: attic", 3),
        ("moves/unmask.yaml", "location: cellar", "location: attic", 17),
    ],
    ids=["start", "exit", "npc", "move_to"],
)
def test_locations_must_exist(tmp_path, dungeon_world, name, old, new, line):
    problem = only_problem(tmp_path, changed(name, old, new), dungeon_world)

    assert (problem.path.name, problem.line) == (Path(name).name, line)
    assert "attic" in problem.message


@pytest.mark.parametrize(
    ("name", "old", "new"),
    [
        ("npcs.yaml", "knows: [wererat]", "knows: [ledger]"),
        ("moves/unmask.yaml", "reveal_secret: wererat", "reveal_secret: ledger"),
        ("moves/unmask.yaml", "{secret_revealed: wererat}", "{secret_revealed: ledger}"),
    ],
    ids=["knows", "reveal", "condition"],
)
def test_secrets_must_exist(tmp_path, dungeon_world, name, old, new):
    problem = only_problem(tmp_path, changed(name, old, new), dungeon_world)

    assert problem.path.name == Path(name).name
    assert "ledger" in problem.message


@pytest.mark.parametrize(
    ("name", "old", "new"),
    [
        ("fronts.yaml", "npc: corwin", "npc: maud"),
        ("endings.yaml", "{npc: corwin, tag", "{npc: maud, tag"),
    ],
    ids=["danger", "condition"],
)
def test_npcs_must_exist(tmp_path, dungeon_world, name, old, new):
    problem = only_problem(tmp_path, changed(name, old, new), dungeon_world)

    assert problem.path.name == name
    assert "maud" in problem.message


@pytest.mark.parametrize(
    ("name", "old", "new"),
    [
        ("fronts.yaml", "advance_clock: {clock: swarm}", "advance_clock: {clock: doom}"),
        ("endings.yaml", "{clock_full: swarm}", "{clock_full: doom}"),
    ],
    ids=["effect", "condition"],
)
def test_clocks_must_belong_to_a_danger(tmp_path, dungeon_world, name, old, new):
    problem = only_problem(tmp_path, changed(name, old, new), dungeon_world)

    assert problem.path.name == name
    assert "doom" in problem.message


def test_tags_may_come_from_the_pack_or_the_scenario(tmp_path, dungeon_world):
    files = changed("moves/unmask.yaml", "reveal_secret: wererat", "add_tag: {tag: dead}")
    load_scenario(write_files(tmp_path / "ok", files), dungeon_world)

    problem = only_problem(
        tmp_path / "bad", changed("endings.yaml", "tag: exposed", "tag: shamed"), dungeon_world
    )
    assert "shamed" in problem.message


def test_danger_moves_may_refer_to_the_danger_npc_only_when_it_has_one(tmp_path, dungeon_world):
    problem = only_problem(
        tmp_path, changed("fronts.yaml", "      npc: corwin\n", ""), dungeon_world
    )

    assert (problem.path.name, problem.line) == ("fronts.yaml", 16)
    assert "target.damage" in problem.message


def test_npcs_may_have_gm_moves_of_their_own_that_refer_to_them(tmp_path, dungeon_world):
    files = {**VALID, "npcs.yaml": VALID["npcs.yaml"] + HOSTILE_RATS}

    scenario = load_scenario(write_files(tmp_path, files), dungeon_world)

    assert [m.id for m in scenario.npcs["rats"].moves] == ["rats_gnaw"]


def test_npc_gm_moves_are_checked(tmp_path, dungeon_world):
    npcs = VALID["npcs.yaml"] + HOSTILE_RATS.replace("target.damage", "target.claws")

    problem = only_problem(tmp_path, {**VALID, "npcs.yaml": npcs}, dungeon_world)

    assert problem.path.name == "npcs.yaml"
    assert "target.claws" in problem.message


@pytest.mark.parametrize("taken", ["rats_bite", "deal_damage"])
def test_gm_move_ids_are_unique_across_the_pack_dangers_and_npcs(tmp_path, dungeon_world, taken):
    npcs = VALID["npcs.yaml"] + HOSTILE_RATS.replace("rats_gnaw", taken)

    problem = only_problem(tmp_path, {**VALID, "npcs.yaml": npcs}, dungeon_world)

    assert problem.path.name == "npcs.yaml"
    assert taken in problem.message


def test_scenario_moves_cannot_replace_pack_moves(tmp_path, dungeon_world):
    files = changed("moves/unmask.yaml", "id: unmask", "id: parley")

    problem = only_problem(tmp_path, files, dungeon_world)

    assert (problem.path.name, problem.line) == ("unmask.yaml", 1)
    assert "parley" in problem.message


def test_ids_are_unique_across_the_scenario(tmp_path, dungeon_world):
    files = {**VALID, "secrets.yaml": SECRETS + "- {id: cellar, text: The cellar is haunted.}\n"}

    problem = only_problem(tmp_path, files, dungeon_world)

    assert problem.path.name == "secrets.yaml"
    assert "cellar" in problem.message


def test_ruleset_adds_scenario_moves_and_tags_to_the_pack(tmp_path, dungeon_world):
    scenario = load_scenario(write_files(tmp_path, VALID), dungeon_world)

    rules = scenario.ruleset(dungeon_world)

    assert rules.moves["unmask"] is scenario.moves["unmask"]
    assert "hack_and_slash" in rules.moves
    assert {"exposed", "dead"} <= set(rules.tags)


def test_npc_damage_cannot_refer_to_anything(tmp_path, dungeon_world):
    files = changed("npcs.yaml", "damage: d6", "damage: d6 + self.level")

    problem = only_problem(tmp_path, files, dungeon_world)

    assert (problem.path.name, problem.line) == ("npcs.yaml", 5)
    assert "self.level" in problem.message


GRATE = "  obstacles:\n    - {id: grate, name: The grate, blocks: cellar}\n"


def test_locations_may_have_obstacles_blocking_their_exits(tmp_path, dungeon_world):
    files = changed("locations.yaml", "  exits: [cellar]\n", "  exits: [cellar]\n" + GRATE)

    scenario = load_scenario(write_files(tmp_path, files), dungeon_world)

    assert [o.blocks for o in scenario.locations["inn"].obstacles] == ["cellar"]
    assert [o.id for o in scenario.obstacles()] == ["grate"]


def test_an_obstacle_blocks_only_an_exit_of_its_location(tmp_path, dungeon_world):
    grate = GRATE.replace("blocks: cellar", "blocks: attic")
    files = changed("locations.yaml", "  exits: [cellar]\n", "  exits: [cellar]\n" + grate)

    problem = only_problem(tmp_path, files, dungeon_world)

    assert problem.path.name == "locations.yaml"
    assert "attic" in problem.message


def test_obstacle_ids_are_unique_across_the_scenario(tmp_path, dungeon_world):
    grate = GRATE.replace("id: grate", "id: corwin")
    files = changed("locations.yaml", "  exits: [cellar]\n", "  exits: [cellar]\n" + grate)

    problem = only_problem(tmp_path, files, dungeon_world)

    assert "corwin" in problem.message
