"""M4 exit criterion: a full playthrough in free text, with the fake provider as the AI."""

import json
from pathlib import Path

import pytest

from gminator.ai.provider import FakeProvider, Request
from gminator.core.characters import create_character
from gminator.play.session import Session
from gminator.play.table import Table
from gminator.scenario.loader import load_scenario
from support import ScriptedConfirmer, ScriptedDecider

RATS = Path(__file__).parents[1] / "scenarios" / "rats-under-the-inn"
SCORES = {
    "fighter": {"str": 16, "con": 15, "dex": 13, "wis": 12, "int": 9, "cha": 8},
    "thief": {"dex": 16, "int": 15, "cha": 13, "wis": 12, "str": 9, "con": 8},
}
PROSE = "Rain drums on the roof, and somewhere below a rat squeals."

# What the fake model takes each thing the player types to mean.
MEANINGS = {
    "I take the trapdoor down to the cellar": {"kind": "travel", "target": "cellar"},
    "I squeeze through the broken wall": {"kind": "travel", "target": "broken_wall"},
    "I wade into the flooded gallery": {"kind": "travel", "target": "gallery"},
    "I follow the draught to the river": {"kind": "travel", "target": "river_exit"},
    "What do I see?": {"kind": "look"},
    "I cut Corwin down": {"kind": "move", "move_id": "hack_and_slash", "target": "corwin"},
}


def fake_model(request: Request) -> str:
    if request.schema is None:
        return PROSE
    said = request.messages[-1].content.rsplit("Player: ", 1)[1]
    return json.dumps({"move_id": None, "stat": None, "target": None, **MEANINGS[said]})


@pytest.fixture(scope="module")
def rats(dungeon_world):
    return load_scenario(RATS, dungeon_world)


def play(pack, scenario, seed: int, class_id: str, said: list[str]) -> tuple[Table, list[str]]:
    character = create_character(pack, class_id, "pc", "Hero", SCORES[class_id])
    table = Table(Session.begin(pack, scenario, seed, character), FakeProvider(fake_model))
    narrations = []
    for words in said:
        reply = table.handle(words, ScriptedDecider(), ScriptedConfirmer())
        narrations.append("".join(part for part in reply.narration if isinstance(part, str)))
        if table.ending:
            break
    return table, narrations


def prompts(table: Table) -> str:
    assert isinstance(table.provider, FakeProvider)
    return "\n".join(m.content for r in table.provider.requests for m in r.messages)


def assert_no_unrevealed_secret_was_told(table: Table, scenario) -> None:
    told = prompts(table)
    for secret_id, secret in scenario.secrets.items():
        if secret_id not in table.session.state.revealed:
            assert secret.text not in told


def test_free_text_plays_down_the_river(dungeon_world, rats):
    said = [
        "What do I see?",
        "I take the trapdoor down to the cellar",
        "I squeeze through the broken wall",
        "I wade into the flooded gallery",
        "I follow the draught to the river",
    ]

    table, narrations = play(dungeon_world, rats, 0, "thief", said)

    assert table.ending is not None
    assert table.ending.id == "fled"
    assert narrations == ["", PROSE, PROSE, PROSE, PROSE]
    assert_no_unrevealed_secret_was_told(table, rats)


def test_free_text_fights_corwin_to_the_death(dungeon_world, rats):
    said = ["I cut Corwin down"] * 30

    for seed in range(200):
        table, narrations = play(dungeon_world, rats, seed, "fighter", said)
        if table.ending and table.ending.id == "corwin_killed":
            break
    else:
        pytest.fail("no seed killed Corwin")

    assert set(narrations) == {PROSE}
    assert_no_unrevealed_secret_was_told(table, rats)
