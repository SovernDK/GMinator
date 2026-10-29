import json

import pytest

from gminator.ai.provider import FakeProvider, ProviderError
from gminator.ai.tasks import Retract
from gminator.core.characters import create_character
from gminator.core.events import HpChanged, MoveMade
from gminator.play.session import Session
from gminator.play.table import Reply, Table
from support import ScriptedConfirmer, ScriptedDecider, seed_for
from tiny_cellar import load_tiny_cellar

SCORES = {"str": 16, "con": 15, "dex": 13, "wis": 12, "int": 9, "cha": 8}


@pytest.fixture
def scenario(tmp_path, dungeon_world):
    return load_tiny_cellar(tmp_path, dungeon_world)


def sit(pack, scenario, provider, seed=0) -> Table:
    hero = create_character(pack, "fighter", "hero", "Hero", SCORES)
    return Table(Session.begin(pack, scenario, seed, hero), provider)


def intent(kind, move_id=None, stat=None, target=None) -> str:
    return json.dumps({"kind": kind, "move_id": move_id, "stat": stat, "target": target})


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
    assert "Hero makes Defy Danger" in narration
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


@pytest.mark.parametrize("kind", ["ooc", "unclear"])
def test_out_of_character_or_unclear_words_point_to_help(dungeon_world, scenario, kind):
    table = sit(dungeon_world, scenario, FakeProvider([intent(kind)]))
    before = table.session.game.events

    reply = table.handle("hmm", ScriptedDecider(), ScriptedConfirmer())

    assert "/help" in "\n".join(reply.lines)
    assert table.session.game.events == before


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
