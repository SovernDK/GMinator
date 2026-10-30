import pytest

from gminator.ai.tasks import Intent
from gminator.evals.cases import Expected
from gminator.evals.scoring import Check, intent_check, prose_checks

STAB = Expected(kind="move", move_id="hack_and_slash", target="giant_rats")


def failed(checks: list[Check]) -> list[str]:
    return [check.name for check in checks if not check.passed]


# Classify


def test_an_intent_that_matches_what_was_expected_passes():
    got = Intent(kind="move", move_id="hack_and_slash", target="giant_rats")

    assert intent_check(got, [STAB]) == Check("intent", True)


@pytest.mark.parametrize(
    "got",
    [
        Intent(kind="move", move_id="volley", target="giant_rats"),
        Intent(kind="move", move_id="hack_and_slash", target="corwin"),
        Intent(kind="talk", target="giant_rats"),
        Intent(kind="unclear"),
    ],
)
def test_an_intent_that_differs_in_kind_move_or_target_fails(got):
    assert intent_check(got, [STAB]) == Check("intent", False)


def test_a_stat_counts_only_when_one_is_expected():
    leap = Expected(kind="move", move_id="defy_danger", stat="dex")
    any_stat = Expected(kind="move", move_id="defy_danger")

    with_str = Intent(kind="move", move_id="defy_danger", stat="str")

    assert intent_check(with_str, [leap]).passed is False
    assert intent_check(with_str, [any_stat]).passed


def test_where_a_move_goes_on_to_must_match():
    on = Expected(kind="move", move_id="defy_danger", then="broken_wall")
    stay = Expected(kind="move", move_id="defy_danger")

    going = Intent(kind="move", move_id="defy_danger", then="broken_wall")
    staying = Intent(kind="move", move_id="defy_danger")

    assert intent_check(going, [on]).passed
    assert intent_check(staying, [on]).passed is False
    assert intent_check(going, [stay]).passed is False


def test_any_of_several_expected_intents_passes():
    look = Expected(kind="look")
    study = Expected(kind="move", move_id="discern_realities")

    assert intent_check(Intent(kind="look"), [study, look]).passed
    assert intent_check(Intent(kind="move", move_id="discern_realities"), [study, look]).passed


# Narration and NPC voice


GOOD_NARRATION = "You swing hard. The rat squeals and scrambles back into the dark."


def test_good_narration_passes_every_check():
    checks = prose_checks(GOOD_NARRATION, retracted=False, speaker="narrator", mentions=["rat"])

    assert failed(checks) == []
    assert [c.name for c in checks] == [
        "answered",
        "fact_check",
        "no_rules_talk",
        "length",
        "speaker",
        "mentions",
        "forbidden",
    ]


def test_nothing_told_fails_answered():
    assert "answered" in failed(prose_checks("", retracted=True, speaker="narrator"))


def test_a_retraction_fails_the_fact_check():
    assert failed(prose_checks(GOOD_NARRATION, retracted=True, speaker="narrator")) == [
        "fact_check"
    ]


@pytest.mark.parametrize(
    "text",
    [
        "You deal 6 damage. The rat squeals.",
        "The rat loses HP. It squeals at you.",
        "You roll the dice. The rat squeals.",
        "You gain XP. The rat squeals.",
        "A strong hit! The rat squeals at you.",
    ],
)
def test_numbers_and_rules_talk_fail(text):
    assert failed(prose_checks(text, retracted=False, speaker="narrator")) == ["no_rules_talk"]


def test_narration_needs_two_to_four_sentences():
    too_short = prose_checks("You swing.", retracted=False, speaker="narrator")
    too_long = prose_checks("You swing. " * 5, retracted=False, speaker="narrator")

    assert failed(too_short) == ["length"]
    assert failed(too_long) == ["length"]


def test_an_npc_may_answer_in_one_to_three_sentences():
    one = prose_checks("I saw nothing, I swear.", retracted=False, speaker="npc")
    four = prose_checks("I saw nothing. Nothing! Go away. Please.", retracted=False, speaker="npc")

    assert failed(one) == []
    assert failed(four) == ["length"]


def test_the_narrator_speaks_to_the_player_in_the_second_person():
    checks = prose_checks("The rat squeals. It flees.", retracted=False, speaker="narrator")

    assert failed(checks) == ["speaker"]


def test_an_npc_may_speak_in_any_person():
    checks = prose_checks("Oh? And just why is that, hmm?", retracted=False, speaker="npc")

    assert failed(checks) == []
    assert "speaker" not in [check.name for check in checks]


def test_at_least_one_expected_word_must_be_mentioned():
    checks = prose_checks(GOOD_NARRATION, retracted=False, speaker="narrator", mentions=["swarm"])

    assert failed(checks) == ["mentions"]


def test_mentions_match_whole_words_and_their_endings():
    text = "You see rats. They flee."

    checks = prose_checks(text, retracted=False, speaker="narrator", mentions=["Rat"])

    assert failed(checks) == []


def test_a_forbidden_word_fails():
    text = "You see Corwin's teeth. He is a wererat!"

    checks = prose_checks(text, retracted=False, speaker="narrator", forbidden=["wererat"])

    assert failed(checks) == ["forbidden"]
