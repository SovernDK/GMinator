import json

import pytest

from gminator.ai.provider import FakeProvider, ProviderError, Providers
from gminator.ai.tasks import Retract
from gminator.core.characters import create_character
from gminator.core.events import CharacterMoved, HpChanged, MoveMade
from gminator.play.session import Session
from gminator.play.table import Reply, Table
from support import ScriptedConfirmer, ScriptedDecider, seed_for
from tiny_cellar import NPCS, VALID, load_tiny_cellar

SCORES = {"str": 16, "con": 15, "dex": 13, "wis": 12, "int": 9, "cha": 8}


@pytest.fixture
def scenario(tmp_path, dungeon_world):
    return load_tiny_cellar(tmp_path, dungeon_world)


def sit(pack, scenario, provider, seed=0) -> Table:
    hero = create_character(pack, "fighter", "hero", "Hero", SCORES)
    return Table(Session.begin(pack, scenario, seed, hero), provider)


def intent(kind, move_id=None, stat=None, target=None, then=None) -> str:
    answer = {"kind": kind, "move_id": move_id, "stat": stat, "target": target, "then": then}
    return json.dumps(answer)


def told(reply: Reply) -> str:
    """The narration as the player is left with it: whatever follows the last retraction."""
    parts = list(reply.narration)
    if Retract() in parts:
        parts = parts[len(parts) - parts[::-1].index(Retract()) :]
    return "".join(parts)


def text_of(request) -> str:
    return "\n".join(message.content for message in request.messages)


# Free text, classified and confirmed


def test_a_move_in_free_text_is_confirmed_made_and_narrated(dungeon_world, scenario):
    provider = FakeProvider([intent("move", "defy_danger", "dex"), "You vault the bar."])
    table = sit(dungeon_world, scenario, provider, seed_for("strong", 1))
    confirmer = ScriptedConfirmer()

    reply = table.handle("I vault over the bar", ScriptedDecider(), confirmer)

    assert "Defy Danger" in confirmer.questions[0]
    assert "+DEX" in confirmer.questions[0]
    moves = [e for e in table.session.game.events if isinstance(e, MoveMade)]
    assert [m.move_id for m in moves] == ["defy_danger"]
    assert "Hero makes Defy Danger" in "\n".join(reply.lines)
    assert told(reply) == "You vault the bar."
    narration = text_of(provider.requests[1])
    assert "Hero tries Defy Danger, and it goes well." in narration
    assert "I vault over the bar" in narration


def test_a_move_against_someone_names_them_in_the_confirmation(dungeon_world, scenario):
    provider = FakeProvider([intent("move", "hack_and_slash", target="corwin"), "Steel flashes."])
    table = sit(dungeon_world, scenario, provider)
    confirmer = ScriptedConfirmer()

    table.handle("I attack Corwin", ScriptedDecider(), confirmer)

    assert "Corwin" in confirmer.questions[0]
    assert [e.target_id for e in table.session.game.events if isinstance(e, MoveMade)] == ["corwin"]


def test_a_declined_move_changes_nothing_and_is_not_narrated(dungeon_world, scenario):
    provider = FakeProvider([intent("move", "defy_danger", "dex")])
    table = sit(dungeon_world, scenario, provider)
    before = table.session.game.events

    reply = table.handle("I vault over the bar", ScriptedDecider(), ScriptedConfirmer(False))

    assert table.session.game.events == before
    assert reply.lines
    assert told(reply) == ""
    assert len(provider.requests) == 1


def test_travel_is_confirmed_and_narrated(dungeon_world, scenario):
    provider = FakeProvider([intent("travel", target="cellar"), "Damp stairs creak."])
    table = sit(dungeon_world, scenario, provider)
    confirmer = ScriptedConfirmer()

    reply = table.handle("I go down to the cellar", ScriptedDecider(), confirmer)

    assert "The cellar" in confirmer.questions[0]
    assert table.session.state.characters["hero"].location == "cellar"
    assert told(reply) == "Damp stairs creak."


@pytest.mark.parametrize(
    ("kind", "shown"), [("look", "Warm and loud."), ("inventory", "Dungeon rations")]
)
def test_looking_and_checking_gear_need_no_confirmation_or_narration(
    dungeon_world, scenario, kind, shown
):
    provider = FakeProvider([intent(kind)])
    table = sit(dungeon_world, scenario, provider)
    confirmer = ScriptedConfirmer()

    reply = table.handle("what now?", ScriptedDecider(), confirmer)

    assert shown in "\n".join(reply.lines)
    assert confirmer.questions == []
    assert told(reply) == ""
    assert len(provider.requests) == 1


def test_talking_to_someone_here_gets_their_answer_and_changes_nothing(dungeon_world, scenario):
    provider = FakeProvider([intent("talk", target="corwin"), "Only a few rats, friend."])
    table = sit(dungeon_world, scenario, provider)
    before = table.session.game.events

    reply = table.handle("Corwin, what's down there?", ScriptedDecider(), ScriptedConfirmer())

    assert "Corwin" in "\n".join(reply.lines)
    assert told(reply) == "Only a few rats, friend."
    assert table.session.game.events == before
    voice = text_of(provider.requests[1])
    assert "Name: Corwin" in voice
    assert "Corwin, what's down there?" in voice


def test_each_task_can_have_its_own_model(dungeon_world, scenario):
    classifier = FakeProvider(
        [intent("move", "defy_danger", "dex"), intent("talk", target="corwin")]
    )
    narrator = FakeProvider(["You vault the bar."])
    voice = FakeProvider(["Only a few rats, friend."])
    table = sit(dungeon_world, scenario, Providers(classifier, narrator, voice))

    vaulted = table.handle("I vault over the bar", ScriptedDecider(), ScriptedConfirmer())
    answered = table.handle("Corwin, what's down there?", ScriptedDecider(), ScriptedConfirmer())

    assert told(vaulted) == "You vault the bar."
    assert told(answered) == "Only a few rats, friend."
    assert [r.schema is not None for r in classifier.requests] == [True, True]
    assert "Hero tries Defy Danger" in text_of(narrator.requests[0])
    assert "Name: Corwin" in text_of(voice.requests[0])


def test_unclear_words_point_to_help(dungeon_world, scenario):
    table = sit(dungeon_world, scenario, FakeProvider([intent("unclear")]))
    before = table.session.game.events

    reply = table.handle("hmm", ScriptedDecider(), ScriptedConfirmer())

    assert "/help" in "\n".join(reply.lines)
    assert table.session.game.events == before


def test_going_nowhere_from_here_names_the_ways_on(dungeon_world, scenario):
    table = sit(dungeon_world, scenario, FakeProvider([intent("travel")]))
    before = table.session.game.events

    reply = table.handle("I go to the broken wall", ScriptedDecider(), ScriptedConfirmer())

    assert reply.lines == ["You can't get there from here. Ways on: The cellar."]
    assert table.session.game.events == before


def test_out_of_character_words_are_answered_by_the_gm(dungeon_world, scenario):
    provider = FakeProvider([intent("ooc"), "You can make Defy Danger here."])
    table = sit(dungeon_world, scenario, provider)
    before = table.session.game.events

    reply = table.handle("what can I do here?", ScriptedDecider(), ScriptedConfirmer())

    assert reply.lines == ["GM:"]
    assert told(reply) == "You can make Defy Danger here."
    assert "The player asks: what can I do here?" in text_of(provider.requests[1])
    assert table.session.game.events == before


# Talking without being classified


def test_say_to_someone_here_gets_their_answer_without_classifying(dungeon_world, scenario):
    provider = FakeProvider(["Only a few rats, friend."])
    table = sit(dungeon_world, scenario, provider)
    before = table.session.game.events

    reply = table.handle("/say @corwin What's down there?", ScriptedDecider(), ScriptedConfirmer())

    assert "Corwin" in "\n".join(reply.lines)
    assert told(reply) == "Only a few rats, friend."
    assert table.session.game.events == before
    assert len(provider.requests) == 1
    assert "The player character says: What's down there?" in text_of(provider.requests[0])


@pytest.mark.parametrize("line", ["/say @COR hello", "/say hello"])
def test_say_takes_a_name_prefix_or_the_only_person_here(dungeon_world, scenario, line):
    provider = FakeProvider(["Evening."])
    table = sit(dungeon_world, scenario, provider)

    reply = table.handle(line, ScriptedDecider(), ScriptedConfirmer())

    assert told(reply) == "Evening."
    assert "Name: Corwin" in text_of(provider.requests[0])


def test_say_asks_whom_when_it_could_be_anyone_here(dungeon_world, cellar):
    provider = FakeProvider([])
    table = in_the_cellar(dungeon_world, cellar, provider)
    table.session.game.record(CharacterMoved(character_id="corwin", location_id="cellar"))

    reply = table.handle("/say hello", ScriptedDecider(), ScriptedConfirmer())

    assert "Corwin (corwin)" in "\n".join(reply.lines)
    assert "The rats (rats)" in "\n".join(reply.lines)
    assert provider.requests == []


@pytest.mark.parametrize("line", ["/say @maud hello", "/say @corwin", "/say"])
def test_say_to_no_one_here_or_saying_nothing_is_refused(dungeon_world, scenario, line):
    provider = FakeProvider([])
    table = sit(dungeon_world, scenario, provider)

    reply = table.handle(line, ScriptedDecider(), ScriptedConfirmer())

    assert "/say" in "\n".join(reply.lines)
    assert provider.requests == []


def test_say_with_no_one_here_says_so(dungeon_world, scenario):
    provider = FakeProvider([])
    table = sit(dungeon_world, scenario, provider)
    table.session.game.record(CharacterMoved(character_id="corwin", location_id="cellar"))

    reply = table.handle("/say hello", ScriptedDecider(), ScriptedConfirmer())

    assert "no one here" in "\n".join(reply.lines)


def test_only_quoted_speech_is_said_without_classifying(dungeon_world, scenario):
    provider = FakeProvider(["Rats, mostly."])
    table = sit(dungeon_world, scenario, provider)

    reply = table.handle('"What\'s down there?"', ScriptedDecider(), ScriptedConfirmer())

    assert told(reply) == "Rats, mostly."
    assert len(provider.requests) == 1


def test_quoted_speech_is_left_out_of_classifying_but_narrated(dungeon_world, scenario):
    provider = FakeProvider([intent("move", "defy_danger", "dex"), "You vault the bar."])
    table = sit(dungeon_world, scenario, provider, seed_for("strong", 1))
    line = 'I vault over the bar shouting "Stand back, Corwin!"'

    told(table.handle(line, ScriptedDecider(), ScriptedConfirmer()))

    classified = text_of(provider.requests[0])
    assert "Player: I vault over the bar shouting" in classified
    assert "Stand back" not in classified
    assert f"The player said: {line}" in text_of(provider.requests[1])


def test_the_gm_answers_out_of_character_and_may_talk_rules(dungeon_world, scenario):
    provider = FakeProvider(["Hack and Slash rolls +STR and deals your damage."])
    table = sit(dungeon_world, scenario, provider)
    before = table.session.game.events

    reply = table.handle("/gm how does fighting work?", ScriptedDecider(), ScriptedConfirmer())

    assert told(reply) == "Hack and Slash rolls +STR and deals your damage."
    prompt = text_of(provider.requests[0])
    assert "hack_and_slash" in prompt
    assert "The player asks: how does fighting work?" in prompt
    assert table.session.game.events == before


def test_the_gm_needs_a_question(dungeon_world, scenario):
    provider = FakeProvider([])
    table = sit(dungeon_world, scenario, provider)

    reply = table.handle("/gm", ScriptedDecider(), ScriptedConfirmer())

    assert "/gm" in "\n".join(reply.lines)
    assert provider.requests == []


def test_classify_is_offered_only_what_can_be_done_now(dungeon_world, scenario):
    provider = FakeProvider([intent("look")])
    table = sit(dungeon_world, scenario, provider)
    table.session.game.record(HpChanged(character_id="corwin", amount=-99))

    table.handle("hmm", ScriptedDecider(), ScriptedConfirmer())

    properties = provider.requests[0].schema["properties"]
    moves = properties["move_id"]["enum"]
    assert "hack_and_slash" in moves
    assert "tricks_of_the_trade" not in moves  # a thief move
    assert "last_breath" not in moves
    assert "unmask" not in moves  # until the secret is revealed
    assert properties["target"]["enum"] == ["cellar", None]  # Corwin is dead


def test_a_move_the_session_refuses_changes_nothing_and_is_not_narrated(dungeon_world, scenario):
    no_hold_to_spend = intent("move", "defend_spend_hold", target="corwin")
    provider = FakeProvider([no_hold_to_spend])
    table = sit(dungeon_world, scenario, provider)
    before = table.session.game.events

    reply = table.handle("I guard against Corwin", ScriptedDecider(), ScriptedConfirmer())

    assert table.session.game.events == before
    assert reply.lines
    assert told(reply) == ""
    assert len(provider.requests) == 1


# The narrator being unavailable


def test_free_text_without_the_narrator_points_to_commands(dungeon_world, scenario):
    table = sit(dungeon_world, scenario, None)

    reply = table.handle("I attack Corwin", ScriptedDecider(), ScriptedConfirmer())

    assert "/help" in "\n".join(reply.lines)
    assert told(reply) == ""


@pytest.mark.parametrize("line", ["/say @corwin hello", "/gm what now?"])
def test_say_and_gm_without_the_narrator_point_to_commands(dungeon_world, scenario, line):
    table = sit(dungeon_world, scenario, None)

    reply = table.handle(line, ScriptedDecider(), ScriptedConfirmer())

    assert "/help" in "\n".join(reply.lines)
    assert told(reply) == ""


def test_a_narrator_that_is_down_points_to_commands(dungeon_world, scenario):
    table = sit(dungeon_world, scenario, FakeProvider([ProviderError("connection refused")]))
    before = table.session.game.events

    reply = table.handle("I attack Corwin", ScriptedDecider(), ScriptedConfirmer())

    assert "/" in "\n".join(reply.lines)
    assert "connection refused" in "\n".join(reply.lines)
    assert table.session.game.events == before


# Slash commands


def test_slash_commands_skip_classification_but_are_narrated(dungeon_world, scenario):
    provider = FakeProvider(["You descend."])
    table = sit(dungeon_world, scenario, provider)

    reply = table.handle("/go cellar", ScriptedDecider(), ScriptedConfirmer())

    assert table.session.state.characters["hero"].location == "cellar"
    assert told(reply) == "You descend."
    assert provider.requests[0].stream
    assert "Hero goes to The cellar." in text_of(provider.requests[0])


def test_slash_commands_that_change_nothing_are_not_narrated(dungeon_world, scenario):
    provider = FakeProvider([])
    table = sit(dungeon_world, scenario, provider)

    reply = table.handle("/sheet", ScriptedDecider(), ScriptedConfirmer())

    assert "Hero" in "\n".join(reply.lines)
    assert told(reply) == ""
    assert provider.requests == []


def test_slash_commands_without_the_narrator_are_not_narrated(dungeon_world, scenario):
    table = sit(dungeon_world, scenario, None)

    reply = table.handle("/go cellar", ScriptedDecider(), ScriptedConfirmer())

    assert "The cellar" in "\n".join(reply.lines)
    assert told(reply) == ""


# Memory between turns


def test_narration_remembers_recent_facts_and_the_last_narration(dungeon_world, scenario):
    provider = FakeProvider(["Damp stairs creak underfoot.", "Warmth again."])
    table = sit(dungeon_world, scenario, provider)

    told(table.handle("/go cellar", ScriptedDecider(), ScriptedConfirmer()))
    told(table.handle("/go inn", ScriptedDecider(), ScriptedConfirmer()))

    second = text_of(provider.requests[1])
    assert "Damp stairs creak underfoot." in second
    assert "Hero goes to The cellar." in second


def test_a_retracted_narration_is_not_remembered(dungeon_world, scenario):
    provider = FakeProvider(["You draw a rapier.", "Your rapier gleams.", "Warmth again."])
    table = sit(dungeon_world, scenario, provider)

    told(table.handle("/go cellar", ScriptedDecider(), ScriptedConfirmer()))
    told(table.handle("/go inn", ScriptedDecider(), ScriptedConfirmer()))

    assert "rapier" not in text_of(provider.requests[2]).lower()


def test_what_an_npc_says_is_remembered(dungeon_world, scenario):
    provider = FakeProvider([intent("talk", target="corwin"), "Only rats.", "You descend."])
    table = sit(dungeon_world, scenario, provider)

    told(table.handle("Corwin?", ScriptedDecider(), ScriptedConfirmer()))
    told(table.handle("/go cellar", ScriptedDecider(), ScriptedConfirmer()))

    assert "Only rats." in text_of(provider.requests[2])


def test_a_stat_is_proposed_only_for_a_move_that_lets_the_player_choose(dungeon_world, scenario):
    provider = FakeProvider([intent("move", "hack_and_slash", "dex", "corwin"), "Steel."])
    table = sit(dungeon_world, scenario, provider)
    confirmer = ScriptedConfirmer()

    table.handle("I attack Corwin", ScriptedDecider(), confirmer)

    assert "+DEX" not in confirmer.questions[0]


def test_a_target_is_dropped_from_a_move_not_made_against_anyone(dungeon_world, scenario):
    provider = FakeProvider([intent("move", "defy_danger", "dex", "corwin"), "You dodge."])
    table = sit(dungeon_world, scenario, provider)
    confirmer = ScriptedConfirmer()

    table.handle("I dodge past Corwin", ScriptedDecider(), confirmer)

    assert "Corwin" not in confirmer.questions[0]
    assert [e.move_id for e in table.session.game.events if isinstance(e, MoveMade)] == [
        "defy_danger"
    ]


# Danger, obstacles and going on


LOCATIONS = """\
- id: inn
  name: The inn
  exits: [cellar]
- id: cellar
  name: The cellar
  exits: [inn, pit]
  obstacles:
    - {id: grate, name: The grate, blocks: pit}
- id: pit
  name: The pit
  exits: [cellar]
"""

RATS = "- {id: rats, name: The rats, location: cellar, max_hp: 7, attitude: hostile}\n"


@pytest.fixture
def cellar(tmp_path, dungeon_world):
    files = {**VALID, "locations.yaml": LOCATIONS, "npcs.yaml": NPCS + RATS}
    return load_tiny_cellar(tmp_path, dungeon_world, files)


def in_the_cellar(pack, scenario, provider, seed=0) -> Table:
    table = sit(pack, scenario, provider, seed)
    table.session.game.record(CharacterMoved(character_id="hero", location_id="cellar"))
    return table


def test_the_confirmation_names_the_danger_move_first(dungeon_world, cellar):
    provider = FakeProvider([intent("travel", target="inn"), "You slip past."])
    table = in_the_cellar(dungeon_world, cellar, provider)
    confirmer = ScriptedConfirmer()

    table.handle("I run for the stairs", ScriptedDecider(), confirmer)

    assert confirmer.questions[0] == "The rats: you Defy Danger +DEX first. Go to The inn?"


def test_fighting_needs_no_danger_move(dungeon_world, cellar):
    provider = FakeProvider([intent("move", "hack_and_slash", target="rats"), "Steel flashes."])
    table = in_the_cellar(dungeon_world, cellar, provider)
    confirmer = ScriptedConfirmer()

    table.handle("I hack at the rats", ScriptedDecider(), confirmer)

    assert "Defy Danger" not in confirmer.questions[0]


def test_a_move_against_an_obstacle_then_going_on_is_one_command(dungeon_world, cellar):
    reply = intent("move", "bend_bars_lift_gates", target="grate", then="pit")
    provider = FakeProvider([reply, "Iron screams."])
    table = in_the_cellar(dungeon_world, cellar, provider, seed_for("strong", 1))
    table.session.game.record(HpChanged(character_id="rats", amount=-99))
    confirmer = ScriptedConfirmer()

    assert table.options().obstacles == {"grate": "The grate"}
    table.handle("I tear the grate open and drop into the pit", ScriptedDecider(), confirmer)

    assert confirmer.questions[0] == (
        "Make Bend Bars, Lift Gates against The grate, then go to The pit?"
    )
    assert table.session.state.characters["hero"].location == "pit"


def test_the_narrator_is_told_the_story_without_numbers(dungeon_world, scenario):
    provider = FakeProvider(
        [intent("move", "hack_and_slash", target="corwin"), "Steel.", intent("look"), "x"]
    )
    table = sit(dungeon_world, scenario, provider, seed_for("partial", 2))

    reply = table.handle("I attack Corwin", ScriptedDecider(), ScriptedConfirmer())
    list(reply.narration)

    assert any(c.isdigit() for c in "".join(reply.lines))
    narration = text_of(provider.requests[1])
    facts = narration[narration.index("What just happened") :]
    assert not any(c.isdigit() for c in facts)
    assert not any(c.isdigit() for c in "".join(table.context().recent))


# GM moves are told by the narrator

SPOT = "The ground shifts under you, and suddenly you are cornered."


def at_a_miss(pack, scenario, narrator: list) -> tuple[Table, Reply]:
    """A Defy Danger that misses and brings the one hard GM move the pack has."""
    pack = pack.model_copy(update={"gm_moves": {"put_in_a_spot": pack.gm_moves["put_in_a_spot"]}})
    provider = FakeProvider([intent("move", "defy_danger", "dex"), *narrator])
    table = sit(pack, scenario, provider, seed_for("miss", 1))
    return table, table.handle("I leap the bar", ScriptedDecider(), ScriptedConfirmer())


def test_with_the_narrator_a_gm_move_is_told_not_shown(dungeon_world, scenario):
    table, reply = at_a_miss(dungeon_world, scenario, ["You land badly, boxed in."])

    assert SPOT not in reply.lines
    assert told(reply) == "You land badly, boxed in."
    assert SPOT in text_of(table.providers.narrate.requests[1])


@pytest.mark.parametrize(
    "narrator",
    [[ProviderError("down")], ["The dragon roars. You see 3 HP.", "Corwin has 2 HP."]],
)
def test_a_gm_move_the_narrator_cannot_tell_is_shown_after_all(dungeon_world, scenario, narrator):
    _, reply = at_a_miss(dungeon_world, scenario, narrator)

    assert told(reply) == SPOT


def test_without_the_narrator_a_gm_move_is_shown(dungeon_world, scenario):
    pack = dungeon_world.model_copy(
        update={"gm_moves": {"put_in_a_spot": dungeon_world.gm_moves["put_in_a_spot"]}}
    )
    table = sit(pack, scenario, None, seed_for("miss", 1))

    reply = table.handle("/move defy_danger dex", ScriptedDecider(), ScriptedConfirmer())

    assert SPOT in reply.lines
