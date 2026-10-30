import pytest

from gminator.evals.cases import (
    Cases,
    ClassifyCase,
    Expected,
    NarrateCase,
    Scene,
    VoiceCase,
    load_cases,
)
from gminator.packs.loader import PackError
from support import write_files


def test_cases_load_from_one_file_per_task(tmp_path):
    write_files(
        tmp_path,
        {
            "classify.yaml": """\
                - id: stab_rat
                  scene: {class_id: thief, seed: 3, commands: [/go cellar]}
                  said: I stab the nearest rat
                  expect: {kind: move, move_id: hack_and_slash, target: giant_rats}
                - id: look_around
                  said: What's here?
                  expect:
                    - {kind: look}
                    - {kind: move, move_id: discern_realities}
                """,
            "narrate.yaml": """\
                - id: down_the_trapdoor
                  command: /go cellar
                  said: I climb down
                  mentions: [rat]
                  forbidden: [wererat]
                """,
            "voice.yaml": """\
                - id: ask_maud
                  npc: maud
                  said: What's in your cellar?
                """,
        },
    )

    cases = load_cases(tmp_path)

    assert cases.classify == [
        ClassifyCase(
            id="stab_rat",
            scene=Scene(class_id="thief", seed=3, commands=["/go cellar"]),
            said="I stab the nearest rat",
            expect=[Expected(kind="move", move_id="hack_and_slash", target="giant_rats")],
        ),
        ClassifyCase(
            id="look_around",
            said="What's here?",
            expect=[Expected(kind="look"), Expected(kind="move", move_id="discern_realities")],
        ),
    ]
    assert cases.narrate == [
        NarrateCase(
            id="down_the_trapdoor",
            command="/go cellar",
            said="I climb down",
            mentions=["rat"],
            forbidden=["wererat"],
        )
    ]
    assert cases.voice == [VoiceCase(id="ask_maud", npc="maud", said="What's in your cellar?")]


def test_a_scene_starts_a_fighter_at_the_beginning_by_default():
    assert Scene() == Scene(class_id="fighter", seed=0, commands=[])


def test_a_missing_file_has_no_cases(tmp_path):
    assert load_cases(tmp_path) == Cases()


def test_bad_cases_are_reported_with_file_and_line(tmp_path):
    write_files(
        tmp_path,
        {
            "classify.yaml": """\
                - id: a
                  said: hm
                  expect: {kind: dance}
                """,
            "voice.yaml": """\
                - id: b
                  npc: maud
                """,
        },
    )

    with pytest.raises(PackError) as error:
        load_cases(tmp_path)

    problems = [(p.path.name, p.line) for p in error.value.problems]
    assert ("classify.yaml", 3) in problems
    assert ("voice.yaml", 1) in problems  # no said


def test_case_ids_are_unique_within_a_task(tmp_path):
    write_files(
        tmp_path,
        {
            "voice.yaml": """\
                - {id: b, npc: maud, said: hi}
                - {id: b, npc: pip, said: hi}
                """,
        },
    )

    with pytest.raises(PackError, match="duplicate voice case id 'b'"):
        load_cases(tmp_path)
