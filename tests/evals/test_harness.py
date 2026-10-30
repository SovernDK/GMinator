import json

import pytest

from gminator.ai.provider import FakeProvider, ProviderError, Request
from gminator.evals.cases import Cases, ClassifyCase, Expected, NarrateCase, Scene, VoiceCase
from gminator.evals.harness import Harness

IN_THE_CELLAR = Scene(commands=["/go cellar"])
STAB = ClassifyCase(
    id="stab",
    scene=IN_THE_CELLAR,
    said="I stab the nearest rat",
    expect=[Expected(kind="move", move_id="hack_and_slash", target="giant_rats")],
)
SWING = NarrateCase(
    id="swing",
    scene=IN_THE_CELLAR,
    command="/move hack_and_slash giant_rats",
    said="I hack at the rats",
    mentions=["rat"],
)
ASK_MAUD = VoiceCase(id="ask_maud", npc="maud", said="What's in your cellar?")


def intent(kind, move_id=None, stat=None, target=None) -> str:
    return json.dumps({"kind": kind, "move_id": move_id, "stat": stat, "target": target})


def text_of(request: Request) -> str:
    return "\n".join(message.content for message in request.messages)


@pytest.fixture
def harness(dungeon_world, rats):
    return Harness(dungeon_world, rats)


# Classify


def test_a_classify_case_passes_when_the_model_meets_the_expectation(harness):
    provider = FakeProvider([intent("move", "hack_and_slash", target="giant_rats")])

    [result] = harness.run("classify", [STAB], provider)

    assert (result.task, result.case_id, result.passed) == ("classify", "stab", True)
    assert [check.name for check in result.checks] == ["answered", "intent"]
    assert json.loads(result.output) == {
        "kind": "move",
        "move_id": "hack_and_slash",
        "target": "giant_rats",
    }


def test_the_model_is_asked_in_the_scene_the_case_sets_up(harness):
    provider = FakeProvider([intent("look")])

    harness.run("classify", [STAB], provider)

    request = text_of(provider.requests[0])
    assert "Location: The cellar" in request
    assert "Player: I stab the nearest rat" in request
    assert "giant_rats" in provider.requests[0].schema["properties"]["target"]["enum"]


def test_a_classify_case_fails_when_the_model_means_something_else(harness):
    provider = FakeProvider([intent("travel", target="common_room")])

    [result] = harness.run("classify", [STAB], provider)

    assert not result.passed
    assert [check.name for check in result.checks if not check.passed] == ["intent"]


def test_a_model_that_is_down_fails_the_case_and_says_why(harness):
    provider = FakeProvider([ProviderError("connection refused")])

    [result] = harness.run("classify", [STAB], provider)

    assert [check.passed for check in result.checks] == [False, False]
    assert "connection refused" in result.output


# Narrate


def test_a_narrate_case_narrates_the_command_in_its_scene(harness):
    provider = FakeProvider(["You swing at the rats. They scatter, squealing."])

    [result] = harness.run("narrate", [SWING], provider)

    assert result.passed
    assert result.output == "You swing at the rats. They scatter, squealing."
    [request] = provider.requests  # the scene's own commands are never narrated
    assert "Hack and Slash" in text_of(request)
    assert "I hack at the rats" in text_of(request)


def test_narration_that_was_retracted_fails_the_fact_check_but_keeps_what_was_told(harness):
    provider = FakeProvider(
        ["Pip screams as you swing. The rats scatter.", "You swing. The rats scatter."]
    )

    [result] = harness.run("narrate", [SWING], provider)

    assert [check.name for check in result.checks if not check.passed] == ["fact_check"]
    assert result.output == "You swing. The rats scatter."


# NPC voice


def test_a_voice_case_has_the_npc_answer_in_its_scene(harness):
    provider = FakeProvider(["My cellar? Rats, love, nothing but rats."])

    [result] = harness.run("voice", [ASK_MAUD], provider)

    assert result.passed
    assert result.output == "My cellar? Rats, love, nothing but rats."
    assert "Name: Maud" in text_of(provider.requests[0])
    assert "What's in your cellar?" in text_of(provider.requests[0])


# Timing


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def slow(clock: Clock, seconds: float, reply: str):
    def model(request: Request) -> str:
        clock.now += seconds
        return reply

    return model


def test_each_case_is_timed(dungeon_world, rats):
    clock = Clock()
    harness = Harness(dungeon_world, rats, clock=clock)
    provider = FakeProvider(slow(clock, 1.5, intent("look")))

    [result] = harness.run("classify", [STAB], provider)

    assert result.seconds == 1.5
    assert result.first_text is None


def test_prose_is_timed_to_its_first_text(dungeon_world, rats):
    clock = Clock()
    harness = Harness(dungeon_world, rats, clock=clock)
    provider = FakeProvider(slow(clock, 0.5, "You swing. The rats scatter."))

    [result] = harness.run("narrate", [SWING], provider)

    assert result.first_text == 0.5
    assert result.seconds == 0.5


# Checking the cases themselves


def test_good_cases_have_no_problems(harness):
    assert harness.validate(Cases(classify=[STAB], narrate=[SWING], voice=[ASK_MAUD])) == []


@pytest.mark.parametrize(
    ("cases", "problem"),
    [
        (
            Cases(classify=[STAB.model_copy(update={"scene": Scene(commands=["/go nest"])})]),
            "classify case stab: /go nest changes nothing",
        ),
        (
            Cases(
                classify=[
                    STAB.model_copy(
                        update={"expect": [Expected(kind="move", move_id="search_the_cache")]}
                    )
                ]
            ),
            "classify case stab: search_the_cache is not a move here",
        ),
        (
            Cases(
                classify=[
                    STAB.model_copy(update={"expect": [Expected(kind="talk", target="maud")]})
                ]
            ),
            "classify case stab: maud is not here",
        ),
        (
            Cases(
                classify=[
                    STAB.model_copy(
                        update={
                            "expect": [Expected(kind="move", move_id="defy_danger", stat="luck")]
                        }
                    )
                ]
            ),
            "classify case stab: defy_danger does not take luck",
        ),
        (
            Cases(narrate=[SWING.model_copy(update={"command": "/look"})]),
            "narrate case swing: /look changes nothing",
        ),
        (
            Cases(voice=[ASK_MAUD.model_copy(update={"npc": "swarm"})]),
            "voice case ask_maud: swarm is not here",
        ),
    ],
)
def test_bad_cases_are_reported(harness, cases, problem):
    assert harness.validate(cases) == [problem]
