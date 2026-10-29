import pytest

from support import DUNGEON_WORLD


@pytest.fixture(scope="session")
def dungeon_world():
    from gminator.packs.loader import load_pack

    return load_pack(DUNGEON_WORLD)
