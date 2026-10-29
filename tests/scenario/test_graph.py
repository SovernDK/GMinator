from gminator.core.events import CharacterCreated, CharacterMoved, SecretRevealed
from gminator.core.game import Game
from gminator.scenario.graph import Entity, build_graph
from gminator.scenario.story import opening_events
from tiny_cellar import load_tiny_cellar

HERO = CharacterCreated(character_id="hero", name="Hero", stats={}, max_hp=10)


def graph_after(scenario, *events):
    game = Game.new(0)
    for event in (HERO, *opening_events(scenario, "hero"), *events):
        game.record(event)
    return build_graph(scenario, game.state, "hero")


def ids(entities) -> set[str]:
    return {entity.id for entity in entities}


def test_locations_connect_through_their_exits(tmp_path, dungeon_world):
    graph = graph_after(load_tiny_cellar(tmp_path, dungeon_world))

    assert graph.entity("inn") == Entity(id="inn", kind="location", name="The inn")
    assert ids(graph.objects("inn", "connects")) == {"cellar"}


def test_characters_are_where_the_state_puts_them(tmp_path, dungeon_world):
    scenario = load_tiny_cellar(tmp_path, dungeon_world)
    graph = graph_after(scenario, CharacterMoved(character_id="corwin", location_id="cellar"))

    assert graph.entity("hero").kind == "pc"
    assert graph.entity("corwin").kind == "npc"
    assert ids(graph.subjects("at", "inn")) == {"hero"}
    assert ids(graph.subjects("at", "cellar")) == {"corwin"}


def test_unrevealed_secrets_are_not_in_the_graph(tmp_path, dungeon_world):
    graph = graph_after(load_tiny_cellar(tmp_path, dungeon_world))

    assert graph.entity("wererat") is None
    assert graph.objects("corwin", "knows") == []


def test_revealed_secrets_are_known_by_the_npcs_who_know_them(tmp_path, dungeon_world):
    scenario = load_tiny_cellar(tmp_path, dungeon_world)
    graph = graph_after(scenario, SecretRevealed(secret_id="wererat"))

    assert graph.entity("wererat") == Entity(
        id="wererat", kind="secret", name="Corwin is a wererat."
    )
    assert ids(graph.objects("corwin", "knows")) == {"wererat"}


def test_dangers_belong_to_fronts_and_are_driven_by_their_npc(tmp_path, dungeon_world):
    graph = graph_after(load_tiny_cellar(tmp_path, dungeon_world))

    assert ids(graph.objects("swarm", "part_of")) == {"undercellar"}
    assert ids(graph.objects("corwin", "drives")) == {"swarm"}


def test_entities_of_a_kind(tmp_path, dungeon_world):
    graph = graph_after(load_tiny_cellar(tmp_path, dungeon_world))

    assert ids(graph.entities("location")) == {"inn", "cellar"}
    assert ids(graph.entities("npc")) == {"corwin"}
    assert graph.entities("secret") == []
