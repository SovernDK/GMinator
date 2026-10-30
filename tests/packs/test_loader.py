from pathlib import Path

import pytest

from gminator.packs.loader import PackError, load_pack
from support import write_files

MANIFEST = """\
id: tiny
name: Tiny
version: 0.1.0
license: CC0
attribution: Written for tests
stats: [str, dex]
modifiers:
  - {up_to: 9, modifier: 0}
  - {up_to: 18, modifier: 1}
"""

TAGS = """\
- {id: ration, description: Food for one meal}
- {id: close, description: Arm's length}
"""

GEAR = """\
- {id: bread, name: Bread, uses: 2, tags: [ration]}
- {id: club, name: Club, tags: [close]}
"""

REST = """\
id: rest
name: Rest
category: special
trigger: When you rest
effects:
  - use_item: {tag: ration}
"""

SMASH = """\
id: smash
name: Smash
category: basic
trigger: When you smash something
target: true
roll: stat.str
outcomes:
  strong:
    effects:
      - deal_damage: {amount: self.damage + 1}
  partial:
    effects:
      - deal_damage: {amount: self.damage}
  miss:
    text: It holds.
"""

BRUTE = """\
id: brute
name: Brute
damage: d8
max_hp: 8 + score.str
moves: [smash]
starting_gear: [bread]
gear_choices:
  - label: Weapon
    options: [[club]]
"""

GM_MOVES = """\
- id: show_signs
  name: Show signs of an approaching threat
  severity: soft
- id: deal_damage
  name: Deal damage
  severity: hard
  effects:
    - take_damage: {amount: d6}
"""

VALID = {
    "pack.yaml": MANIFEST,
    "gm_moves.yaml": GM_MOVES,
    "tags.yaml": TAGS,
    "gear.yaml": GEAR,
    "moves/rest.yaml": REST,
    "moves/smash.yaml": SMASH,
    "classes/brute.yaml": BRUTE,
}


def pack_problems(root: Path, files: dict[str, str]) -> list:
    with pytest.raises(PackError) as error:
        load_pack(write_files(root, files))
    return error.value.problems


def only_problem(root: Path, files: dict[str, str]):
    problems = pack_problems(root, files)
    assert len(problems) == 1, problems
    return problems[0]


def test_loads_every_part_of_a_pack(tmp_path):
    pack = load_pack(write_files(tmp_path, VALID))

    assert pack.manifest.name == "Tiny"
    assert set(pack.moves) == {"rest", "smash"}
    assert set(pack.classes) == {"brute"}
    assert set(pack.items) == {"bread", "club"}
    assert set(pack.tags) == {"ration", "close"}
    assert set(pack.gm_moves) == {"show_signs", "deal_damage"}


def test_only_the_manifest_and_moves_are_required(tmp_path):
    pack = load_pack(write_files(tmp_path, {"pack.yaml": MANIFEST, "moves/smash.yaml": SMASH}))

    assert set(pack.moves) == {"smash"}
    assert pack.classes == pack.items == pack.tags == pack.gm_moves == {}


def test_missing_manifest_is_reported(tmp_path):
    problem = only_problem(tmp_path, {"moves/smash.yaml": SMASH})

    assert problem.path.name == "pack.yaml"
    assert "missing" in problem.message


def test_yaml_syntax_error_reports_file_and_line(tmp_path):
    broken = REST.replace("effects:\n", "effects: [\n")

    problem = only_problem(tmp_path, {**VALID, "moves/rest.yaml": broken})

    assert problem.path.name == "rest.yaml"
    assert problem.line is not None


def test_validation_error_reports_file_and_line_of_the_bad_value(tmp_path):
    broken = SMASH.replace("self.damage + 1", "self.damage +")

    problem = only_problem(tmp_path, {**VALID, "moves/smash.yaml": broken})

    assert problem.path.name == "smash.yaml"
    assert problem.line == 10
    assert "invalid expression" in problem.message


def test_missing_field_reports_the_line_of_its_parent(tmp_path):
    broken = BRUTE.replace("damage: d8\n", "")

    problem = only_problem(tmp_path, {**VALID, "classes/brute.yaml": broken})

    assert problem.path.name == "brute.yaml"
    assert problem.line == 1
    assert "damage" in problem.message


def test_problem_renders_as_file_line_message(tmp_path):
    broken = SMASH.replace("self.damage + 1", "self.damage +")

    problem = only_problem(tmp_path, {**VALID, "moves/smash.yaml": broken})

    assert str(problem).startswith(f"{problem.path}:10: ")


def test_problems_in_several_files_are_all_reported(tmp_path):
    problems = pack_problems(
        tmp_path,
        {
            **VALID,
            "moves/rest.yaml": REST.replace("category: special", "category: odd"),
            "moves/smash.yaml": SMASH.replace("self.damage + 1", "self.damage +"),
        },
    )

    assert sorted(problem.path.name for problem in problems) == ["rest.yaml", "smash.yaml"]


def test_duplicate_move_ids_are_rejected(tmp_path):
    problem = only_problem(tmp_path, {**VALID, "moves/smash_again.yaml": SMASH})

    assert problem.path.name in {"smash.yaml", "smash_again.yaml"}
    assert problem.line == 1
    assert "smash" in problem.message


def test_duplicate_item_ids_are_rejected(tmp_path):
    bread_again = "- {id: bread, name: Stale bread, uses: 1}\n"

    problem = only_problem(tmp_path, {**VALID, "gear.yaml": GEAR + bread_again})

    assert problem.path.name == "gear.yaml"
    assert problem.line == 3
    assert "bread" in problem.message


def test_class_move_must_exist(tmp_path):
    problem = only_problem(
        tmp_path, {**VALID, "classes/brute.yaml": BRUTE.replace("[smash]", "[smash, roar]")}
    )

    assert (problem.path.name, problem.line) == ("brute.yaml", 5)
    assert "roar" in problem.message


@pytest.mark.parametrize(
    ("old", "new", "line"),
    [("starting_gear: [bread]", "starting_gear: [cake]", 6), ("[[club]]", "[[cake]]", 9)],
    ids=["starting", "choice"],
)
def test_class_gear_must_exist(tmp_path, old, new, line):
    problem = only_problem(tmp_path, {**VALID, "classes/brute.yaml": BRUTE.replace(old, new)})

    assert (problem.path.name, problem.line) == ("brute.yaml", line)
    assert "cake" in problem.message


def test_item_tag_must_be_defined(tmp_path):
    problem = only_problem(tmp_path, {**VALID, "gear.yaml": GEAR.replace("[close]", "[heavy]")})

    assert (problem.path.name, problem.line) == ("gear.yaml", 2)
    assert "heavy" in problem.message


@pytest.mark.parametrize(
    "effect",
    ["use_item: {tag: snack}", "add_tag: {tag: snack}", "remove_tag: {tag: snack}"],
)
def test_effect_tags_must_be_defined(tmp_path, effect):
    problem = only_problem(
        tmp_path, {**VALID, "moves/rest.yaml": REST.replace("use_item: {tag: ration}", effect)}
    )

    assert (problem.path.name, problem.line) == ("rest.yaml", 6)
    assert "snack" in problem.message


def test_spent_hold_must_belong_to_a_known_move(tmp_path):
    rest = REST.replace("use_item: {tag: ration}", "spend_hold: {move: defend}")

    problem = only_problem(tmp_path, {**VALID, "moves/rest.yaml": rest})

    assert (problem.path.name, problem.line) == ("rest.yaml", 6)
    assert "defend" in problem.message


def test_roll_cannot_reference_an_unknown_stat(tmp_path):
    problem = only_problem(
        tmp_path, {**VALID, "moves/smash.yaml": SMASH.replace("stat.str", "stat.wis")}
    )

    assert (problem.path.name, problem.line) == ("smash.yaml", 6)
    assert "stat.wis" in problem.message


def test_effect_cannot_reference_an_unknown_attribute(tmp_path):
    broken = SMASH.replace("self.damage + 1", "self.charm + 1")

    problem = only_problem(tmp_path, {**VALID, "moves/smash.yaml": broken})

    assert (problem.path.name, problem.line) == ("smash.yaml", 10)
    assert "self.charm" in problem.message


def test_move_without_target_cannot_refer_to_one(tmp_path):
    broken = SMASH.replace("target: true\n", "")

    problems = pack_problems(tmp_path, {**VALID, "moves/smash.yaml": broken})

    assert {problem.line for problem in problems} == {9, 12}
    assert all("target" in problem.message for problem in problems)


def test_chosen_stat_needs_stat_options(tmp_path):
    broken = SMASH.replace("roll: stat.str", "roll: stat.chosen")

    problem = only_problem(tmp_path, {**VALID, "moves/smash.yaml": broken})

    assert "stat.chosen" in problem.message


def test_chosen_stat_rolls_with_stat_options(tmp_path):
    chosen = SMASH.replace("roll: stat.str", "roll: stat.chosen\nstat_options: [str, dex]")

    pack = load_pack(write_files(tmp_path, {**VALID, "moves/smash.yaml": chosen}))

    assert pack.moves["smash"].stat_options == ["str", "dex"]


def test_stat_options_must_be_pack_stats(tmp_path):
    broken = SMASH.replace("roll: stat.str", "roll: stat.chosen\nstat_options: [str, luck]")

    problem = only_problem(tmp_path, {**VALID, "moves/smash.yaml": broken})

    assert "luck" in problem.message


def test_class_hp_may_use_scores_but_not_other_refs(tmp_path):
    broken = BRUTE.replace("8 + score.str", "8 + score.luck")

    problem = only_problem(tmp_path, {**VALID, "classes/brute.yaml": broken})

    assert (problem.path.name, problem.line) == ("brute.yaml", 4)
    assert "score.luck" in problem.message


def test_score_array_must_cover_every_stat(tmp_path):
    manifest = MANIFEST + "score_array: [12]\n"

    problem = only_problem(tmp_path, {**VALID, "pack.yaml": manifest})

    assert problem.path.name == "pack.yaml"
    assert "score_array" in problem.message


def test_gm_move_effects_are_checked(tmp_path):
    broken = GM_MOVES.replace("{amount: d6}", "{amount: target.damage}")

    problem = only_problem(tmp_path, {**VALID, "gm_moves.yaml": broken})

    assert (problem.path.name, problem.line) == ("gm_moves.yaml", 8)
    assert "target.damage" in problem.message


def test_duplicate_gm_move_ids_are_rejected(tmp_path):
    again = "- {id: show_signs, name: Show signs again, severity: soft}\n"

    problem = only_problem(tmp_path, {**VALID, "gm_moves.yaml": GM_MOVES + again})

    assert (problem.path.name, problem.line) == ("gm_moves.yaml", 9)


def test_dying_move_must_exist(tmp_path):
    problem = only_problem(tmp_path, {**VALID, "pack.yaml": MANIFEST + "dying_move: last_gasp\n"})

    assert problem.path.name == "pack.yaml"
    assert "last_gasp" in problem.message


DODGE = """\
id: dodge
name: Dodge
category: basic
trigger: When you act despite danger
roll: stat.chosen
stat_options: [dex]
outcomes:
  strong: {}
  partial: {}
  miss: {}
"""


def test_danger_gate_loads(tmp_path):
    gate = "danger: {move: dodge, default_stat: dex, exempt: [combat]}\n"
    files = {**VALID, "pack.yaml": MANIFEST + gate, "moves/dodge.yaml": DODGE}

    danger = load_pack(write_files(tmp_path, files)).manifest.danger

    assert danger is not None
    assert (danger.move, danger.default_stat, danger.exempt) == ("dodge", "dex", ["combat"])


@pytest.mark.parametrize(
    ("gate", "wrong"),
    [
        ("{move: leap, default_stat: dex}", "leap"),
        ("{move: smash, default_stat: str}", "stat_options"),
        ("{move: dodge, default_stat: str}", "'str'"),
        ("{move: dodge, default_stat: dex, stat_by_flag: {travel: str}}", "'str'"),
    ],
)
def test_danger_gate_must_be_a_move_that_rolls_its_stats(tmp_path, gate, wrong):
    files = {**VALID, "pack.yaml": MANIFEST + f"danger: {gate}\n", "moves/dodge.yaml": DODGE}

    problem = only_problem(tmp_path, files)

    assert problem.path.name == "pack.yaml"
    assert wrong in problem.message


def test_only_a_move_against_an_obstacle_can_clear_one(tmp_path):
    clears = "      - clear_obstacle: target\n"
    smash = SMASH.replace("      - deal_damage: {amount: self.damage}\n", clears)
    pry = smash.replace("target: true", "target: obstacle").replace("id: smash", "id: pry")
    pry = pry.replace("      - deal_damage: {amount: self.damage + 1}\n", clears)

    problem = only_problem(tmp_path, {**VALID, "moves/smash.yaml": smash, "moves/pry.yaml": pry})

    assert (problem.path.name, problem.line) == ("smash.yaml", 13)
    assert "obstacle" in problem.message


def test_move_against_an_obstacle_cannot_refer_to_a_character_target(tmp_path):
    smash = SMASH.replace("target: true", "target: obstacle")

    problems = pack_problems(tmp_path, {**VALID, "moves/smash.yaml": smash})

    assert all("target" in problem.message for problem in problems)
