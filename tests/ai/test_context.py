from gminator.ai.context import ContextBuilder
from gminator.core.events import CharacterMoved, HpChanged, SecretRevealed, TagAdded
from tiny_cellar import VALID, load_tiny_cellar


def test_context_tells_where_the_pc_is_and_the_ways_on(builder, game):
    text = builder.build(game.state).render()

    assert "The inn" in text
    assert "Warm and loud." in text
    assert "The cellar" in text


def test_context_tells_who_is_here_and_no_one_else(builder, game):
    here = builder.build(game.state).render()
    game.record(CharacterMoved(character_id="corwin", location_id="cellar"))
    gone = builder.build(game.state).render()

    assert "Corwin" in here
    assert "Corwin" not in gone


def test_context_marks_the_dead(builder, game):
    game.record(HpChanged(character_id="corwin", amount=-99))

    assert "Corwin (dead)" in builder.build(game.state).render()


def test_context_tells_the_pc_condition(builder, game):
    game.record(HpChanged(character_id="hero", amount=-5))
    game.record(TagAdded(character_id="hero", tag="exposed"))

    text = builder.build(game.state).render()

    assert "Hero" in text
    assert "Fighter" in text
    assert "20/25 HP" in text
    assert "exposed" in text
    assert "Dungeon rations" in text


def test_unrevealed_secrets_never_reach_the_context(builder, game):
    # Corwin, who knows the secret, is right here.
    assert "wererat" not in builder.build(game.state).render()

    game.record(SecretRevealed(secret_id="wererat"))

    assert "Corwin is a wererat." in builder.build(game.state).render()


def test_context_keeps_only_the_last_five_facts(builder, game):
    facts = [f"Fact {n}." for n in range(1, 8)]

    text = builder.build(game.state, recent=facts).render()

    assert "Fact 2." not in text
    assert all(f"Fact {n}." in text for n in range(3, 8))


def test_context_keeps_the_last_two_sentences_of_narration(builder, game):
    narration = "Rain falls. The fire spits. A dog barks! Someone laughs?"

    text = builder.build(game.state, narration=narration).render()

    assert "Rain falls." not in text
    assert "The fire spits." not in text
    assert "A dog barks! Someone laughs?" in text


def test_npc_profile_gives_the_role_play_data(dungeon_world, game, tmp_path):
    npcs = VALID["npcs.yaml"] + "  drive: Get rich.\n  voice: Soft.\n  attitude: ambiguous\n"
    scenario = load_tiny_cellar(tmp_path, dungeon_world, {**VALID, "npcs.yaml": npcs})
    builder = ContextBuilder(scenario, scenario.ruleset(dungeon_world), "hero")

    profile = builder.profile(game.state, "corwin")

    assert "Corwin" in profile
    assert "Get rich." in profile
    assert "Soft." in profile
    assert "ambiguous" in profile


def test_npc_profile_keeps_what_the_npc_knows_secret_until_revealed(builder, game):
    assert "wererat" not in builder.profile(game.state, "corwin")

    game.record(SecretRevealed(secret_id="wererat"))

    assert "Corwin is a wererat." in builder.profile(game.state, "corwin")
