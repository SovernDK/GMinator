import json
from collections.abc import Iterator

import pytest

from gminator.ai.context import Context
from gminator.ai.provider import FakeProvider, ProviderError
from gminator.ai.tasks import (
    Intent,
    MoveOption,
    Options,
    Retract,
    classify,
    narrate,
    voice_npc,
)

CONTEXT = Context(
    location="The inn",
    description="Warm and loud.",
    exits=["The cellar"],
    present=["Corwin"],
    pc="Hero, Fighter; unhurt",
    secrets=[],
    recent=[],
    narration="",
)

OPTIONS = Options(
    moves={
        "defy_danger": MoveOption(
            "Defy Danger: When you act despite an imminent threat", stats=["str", "dex"]
        ),
        "hack_and_slash": MoveOption(
            "Hack and Slash: When you attack an enemy in melee", targeted=True
        ),
    },
    people={"corwin": "Corwin"},
    places={"cellar": "The cellar"},
)

WITH_A_GRATE = Options(
    moves={
        **OPTIONS.moves,
        "bend_bars": MoveOption("Bend Bars: When you destroy an obstacle", targeted="obstacle"),
    },
    people=OPTIONS.people,
    places=OPTIONS.places,
    obstacles={"grate": "The grate"},
)


def intent(kind, move_id=None, stat=None, target=None, then=None) -> str:
    answer = {"kind": kind, "move_id": move_id, "stat": stat, "target": target, "then": then}
    return json.dumps(answer)


def text_of(request) -> str:
    return "\n".join(message.content for message in request.messages)


# Classify


def test_classify_returns_the_intent_the_model_chose():
    provider = FakeProvider([intent("move", "defy_danger", "dex")])

    result = classify(provider, CONTEXT, OPTIONS, "I leap over the table")

    assert result == Intent(kind="move", move_id="defy_danger", stat="dex")


def test_classify_offers_only_what_the_engine_offers_now():
    provider = FakeProvider([intent("look")])

    classify(provider, CONTEXT, OPTIONS, "I leap over the table")

    request = provider.requests[0]
    properties = request.schema["properties"]
    assert properties["move_id"]["enum"] == ["defy_danger", "hack_and_slash", None]
    assert properties["stat"]["enum"] == ["str", "dex", None]
    assert properties["target"]["enum"] == ["corwin", "cellar", None]
    assert "I leap over the table" in text_of(request)
    assert "When you attack an enemy in melee" in text_of(request)


def test_classify_drops_fields_the_kind_does_not_use():
    provider = FakeProvider([intent("look", "defy_danger", "dex", "corwin")])

    assert classify(provider, CONTEXT, OPTIONS, "I look around") == Intent(kind="look")


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        intent("dance"),
        intent("move", "summon_dragon"),
        intent("move"),
        intent("move", "hack_and_slash"),  # needs a target
        intent("move", "hack_and_slash", target="maud"),
        intent("move", "hack_and_slash", target="cellar"),
        intent("travel", target="attic"),
        intent("travel", target="corwin"),
        intent("talk", target="cellar"),
        intent("travel", target=["cellar"]),
        "[]",
    ],
)
def test_classify_asks_again_after_an_answer_it_cannot_use(bad):
    provider = FakeProvider([bad, intent("travel", target="cellar")])

    assert classify(provider, CONTEXT, OPTIONS, "Downstairs") == Intent(
        kind="travel", target="cellar"
    )
    assert len(provider.requests) == 2


@pytest.mark.parametrize(
    ("reply", "meant"),
    [
        (intent("move", "defy_danger", "wis"), Intent(kind="move", move_id="defy_danger")),
        (
            intent("move", "hack_and_slash", "dex", "corwin"),
            Intent(kind="move", move_id="hack_and_slash", target="corwin"),
        ),
        (
            intent("move", "defy_danger", "dex", "corwin"),
            Intent(kind="move", move_id="defy_danger", stat="dex"),
        ),
    ],
)
def test_classify_drops_a_stat_or_target_the_move_does_not_take(reply, meant):
    assert classify(FakeProvider([reply]), CONTEXT, OPTIONS, "Hm") == meant


def test_the_options_say_which_moves_offer_a_stat_or_a_target():
    provider = FakeProvider([intent("look")])

    classify(provider, CONTEXT, OPTIONS, "Hm")

    request = text_of(provider.requests[0])
    assert "When you act despite an imminent threat (stat: str, dex)" in request
    assert "When you attack an enemy in melee (aimed at someone)" in request


def test_classify_aims_obstacle_moves_at_obstacles_only():
    provider = FakeProvider(
        [intent("move", "bend_bars", target="corwin"), intent("move", "bend_bars", target="grate")]
    )

    result = classify(provider, CONTEXT, WITH_A_GRATE, "I bend the bars")

    assert result == Intent(kind="move", move_id="bend_bars", target="grate")
    request = text_of(provider.requests[0])
    assert "When you destroy an obstacle (aimed at an obstacle)" in request
    assert "Obstacles here:\n- grate: The grate" in request
    assert "grate" in provider.requests[0].schema["properties"]["target"]["enum"]


def test_classify_takes_where_a_move_goes_on_to():
    provider = FakeProvider([intent("move", "bend_bars", target="grate", then="cellar")])

    said = "I bend the bars and climb down to the cellar"
    result = classify(provider, CONTEXT, WITH_A_GRATE, said)

    assert result == Intent(kind="move", move_id="bend_bars", target="grate", then="cellar")
    assert provider.requests[0].schema["properties"]["then"]["enum"] == ["cellar", None]


def test_classify_drops_a_then_the_player_never_named():
    reply = intent("move", "hack_and_slash", target="corwin", then="cellar")

    result = classify(FakeProvider([reply]), CONTEXT, OPTIONS, "I attack Corwin")

    assert result == Intent(kind="move", move_id="hack_and_slash", target="corwin")


@pytest.mark.parametrize(
    "said",
    [
        "I duck the rats and dive through the hole in the back wall",
        "I dodge them and run for the Broken Wall!",
        "I dodge, then broken_wall",
    ],
)
def test_classify_keeps_a_then_named_by_any_word_of_the_place(said):
    options = Options(moves=OPTIONS.moves, places={"broken_wall": "The broken wall"})
    reply = intent("move", "defy_danger", "dex", then="broken_wall")

    assert classify(FakeProvider([reply]), CONTEXT, options, said).then == "broken_wall"


@pytest.mark.parametrize(
    "reply",
    [intent("move", "defy_danger", "dex", then="attic"), intent("look", then="cellar")],
)
def test_classify_drops_a_then_that_is_no_way_on_or_not_after_a_move(reply):
    assert classify(FakeProvider([reply]), CONTEXT, OPTIONS, "Hm").then is None


def test_classify_gives_up_as_unclear_after_two_bad_answers():
    provider = FakeProvider(["not json", intent("move", "summon_dragon")])

    assert classify(provider, CONTEXT, OPTIONS, "Hm") == Intent(kind="unclear")


def test_classify_lets_a_provider_failure_through():
    with pytest.raises(ProviderError):
        classify(FakeProvider([ProviderError("down")]), CONTEXT, OPTIONS, "Hm")


# Narrate


def test_narration_streams_from_the_facts_and_the_context(check):
    provider = FakeProvider(["Corwin flinches as your blade bites."])

    parts = list(narrate(provider, check, CONTEXT, ["Corwin takes 4 damage."], "I stab Corwin"))

    assert len(parts) > 1
    assert "".join(parts) == "Corwin flinches as your blade bites."
    request = provider.requests[0]
    assert request.stream
    assert "Corwin takes 4 damage." in text_of(request)
    assert "I stab Corwin" in text_of(request)
    assert "Warm and loud." in text_of(request)


def test_narration_naming_what_is_not_there_is_retracted_and_told_again(check):
    provider = FakeProvider(["You raise your shield.", "You brace yourself."])

    parts = list(narrate(provider, check, CONTEXT, ["Hero makes Defend."]))

    retract = parts.index(Retract())
    assert "".join(parts[:retract]) == "You raise your shield."
    assert "".join(parts[retract + 1 :]) == "You brace yourself."
    assert "Shield" in text_of(provider.requests[1])


def test_narration_failing_twice_is_retracted_for_the_template(check):
    provider = FakeProvider(["You raise your shield.", "Your shield holds."])

    parts = list(narrate(provider, check, CONTEXT, ["Hero makes Defend."]))

    assert parts[-1] == Retract()
    assert parts.count(Retract()) == 2
    assert len(provider.requests) == 2


@pytest.mark.parametrize(
    "rules_talk",
    ["You take 4 damage.", "Your HP drops.", "You roll the dice.", "Your DEX saves you."],
)
def test_narration_talking_about_the_rules_is_retracted_and_told_again(check, rules_talk):
    provider = FakeProvider([rules_talk, "You stagger, but stay standing."])

    parts = list(narrate(provider, check, CONTEXT, ["Hero is hurt."]))

    retract = parts.index(Retract())
    assert "".join(parts[retract + 1 :]) == "You stagger, but stay standing."
    assert "Do not mention numbers" in text_of(provider.requests[1])


def test_narration_is_empty_when_the_model_is_down(check):
    assert list(narrate(FakeProvider([ProviderError("down")]), check, CONTEXT, ["x"])) == []


def test_narration_cut_off_by_a_failure_is_retracted(check):
    class Dropping(FakeProvider):
        def stream(self, messages, *, temperature=None) -> Iterator[str]:
            yield "Rain "
            raise ProviderError("connection reset")

    parts = list(narrate(Dropping([]), check, CONTEXT, ["x"]))

    assert parts == ["Rain ", Retract()]


# NPC voice


def test_npc_speaks_from_their_profile_and_the_context(check):
    provider = FakeProvider(["Only a few rats, friend."])
    profile = "Name: Corwin\nVoice: Soft, amused."

    parts = list(voice_npc(provider, check, CONTEXT, profile, "What's in the cellar?"))

    assert "".join(parts) == "Only a few rats, friend."
    request = text_of(provider.requests[0])
    assert "Soft, amused." in request
    assert "What's in the cellar?" in request
    assert "Warm and loud." in request


def test_npc_naming_what_is_not_there_is_retracted(check):
    provider = FakeProvider(["Ask the man with the shield.", "Ask no one."])

    parts = list(voice_npc(provider, check, CONTEXT, "Name: Corwin", "Who knows?"))

    assert Retract() in parts
    assert "".join(parts[parts.index(Retract()) + 1 :]) == "Ask no one."


def test_narration_stops_after_four_sentences(check):
    provider = FakeProvider(["One. Two! Three? Four. Five. Six."])

    parts = list(narrate(provider, check, CONTEXT, ["x"]))

    assert "".join(parts) == "One. Two! Three? Four."


def test_npc_stops_after_three_sentences(check):
    provider = FakeProvider(['"One." Two. Three. Four.'])

    parts = list(voice_npc(provider, check, CONTEXT, "Name: Corwin", "Hm?"))

    assert "".join(parts) == '"One." Two. Three.'
