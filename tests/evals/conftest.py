from pathlib import Path

import pytest

from gminator.scenario.loader import load_scenario

RATS = Path(__file__).parents[2] / "scenarios" / "rats-under-the-inn"


@pytest.fixture(scope="session")
def rats(dungeon_world):
    return load_scenario(RATS, dungeon_world)
