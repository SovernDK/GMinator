import pytest

from gminator.ai.context import ContextBuilder
from gminator.ai.factcheck import FactCheck
from gminator.core.characters import create_character
from gminator.core.game import Game
from gminator.scenario.story import opening_events
from tiny_cellar import load_tiny_cellar

SCORES = {"str": 16, "con": 15, "dex": 13, "wis": 12, "int": 9, "cha": 8}


@pytest.fixture
def scenario(tmp_path, dungeon_world):
    return load_tiny_cellar(tmp_path, dungeon_world)


@pytest.fixture
def game(dungeon_world, scenario):
    game = Game.new(0)
    for event in create_character(dungeon_world, "fighter", "hero", "Hero", SCORES):
        game.record(event)
    for event in opening_events(scenario, "hero"):
        game.record(event)
    return game


@pytest.fixture
def builder(dungeon_world, scenario):
    return ContextBuilder(scenario, scenario.ruleset(dungeon_world), "hero")


@pytest.fixture
def check(dungeon_world, scenario):
    return FactCheck(scenario, scenario.ruleset(dungeon_world))
