from gminator.ai.factcheck import FactCheck
from tiny_cellar import VALID, load_tiny_cellar

PROMPT = """\
Location: The inn
Also here: Corwin
Player character: Hero, Fighter; carrying: Dungeon rations, Chainmail"""


def test_names_from_the_prompt_pass(check):
    text = "Corwin's grin widens as you tug your chainmail straight and eye the cellar door."

    assert check.unknown_names(text, PROMPT + "\nWays on: The cellar") == []


def test_an_npc_who_is_not_in_the_prompt_is_flagged(tmp_path, dungeon_world):
    npcs = VALID["npcs.yaml"] + "- {id: maud, name: Maud, location: cellar, max_hp: 6}\n"
    scenario = load_tiny_cellar(tmp_path, dungeon_world, {**VALID, "npcs.yaml": npcs})
    check = FactCheck(scenario, scenario.ruleset(dungeon_world))

    assert check.unknown_names("Maud waves from the bar.", PROMPT) == ["Maud"]


def test_an_item_the_pc_does_not_carry_is_flagged(check):
    assert check.unknown_names("You raise your shield.", PROMPT) == ["Shield"]


def test_a_place_that_is_not_in_the_prompt_is_flagged(check):
    assert check.unknown_names("You hurry down to the cellar.", PROMPT) == ["The cellar"]


def test_names_match_whole_words_only(check):
    assert check.unknown_names("Shields of rain batter the windows.", PROMPT) == []


def test_words_that_name_nothing_in_the_scenario_are_not_flagged(check):
    assert check.unknown_names("A dragon called Smaug watches.", PROMPT) == []
