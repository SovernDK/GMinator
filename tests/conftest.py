import pytest

from support import DUNGEON_WORLD


@pytest.fixture(scope="session")
def dungeon_world():
    from gminator.packs.loader import load_pack

    return load_pack(DUNGEON_WORLD)


@pytest.fixture
def unused_url():
    """The URL of a local port nothing listens on."""
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"
