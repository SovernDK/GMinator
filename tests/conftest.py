import pytest

from support import DUNGEON_WORLD


@pytest.fixture(scope="session")
def dungeon_world():
    from gminator.packs.loader import load_pack

    return load_pack(DUNGEON_WORLD)


@pytest.fixture(autouse=True)
def _no_user_config(monkeypatch, tmp_path_factory):
    """Tests run on the default settings, never on the player's own file."""
    monkeypatch.setattr("gminator.config.USER_CONFIG", tmp_path_factory.mktemp("home") / "none")


@pytest.fixture(autouse=True)
def _no_line_delay(monkeypatch):
    """Tests don't wait between the lines of a turn."""
    monkeypatch.setattr("gminator.cli.LINE_DELAY", 0)
    monkeypatch.setattr("gminator.tui.app.LINE_DELAY", 0)


@pytest.fixture
def unused_url():
    """The URL of a local port nothing listens on."""
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"
