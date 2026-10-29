"""M1 exit criterion: a recorded event log replays to an identical state."""

from pathlib import Path

from gminator.core.events import CharacterCreated, ClockAdvanced, ClockCreated, HpChanged, XpMarked
from gminator.core.game import Game
from gminator.core.state import replay
from gminator.persistence.saves import load_game, save_game

RECORDED_SESSION = Path(__file__).parent / "fixtures" / "recorded_session.json"


def play_a_little(game: Game) -> None:
    game.record(CharacterCreated(character_id="pc", name="Brakka", stats={"str": 2}, max_hp=18))
    game.record(ClockCreated(clock_id="swarm", label="The swarm grows", segments=4))
    game.roll("2d6 + stat.str", refs={"stat.str": 2})
    game.record(XpMarked(character_id="pc", amount=1))
    game.record(ClockAdvanced(clock_id="swarm", amount=1))
    damage = game.roll("d6")
    game.record(HpChanged(character_id="pc", amount=-damage))


def test_saved_session_loads_to_identical_state_and_continues_identically(tmp_path):
    game = Game.new(seed=2026)
    play_a_little(game)
    path = tmp_path / "save.json"

    save_game(path, game.events)
    loaded = Game(load_game(path))

    assert loaded.events == game.events
    assert loaded.state == game.state
    assert [loaded.roll("2d6") for _ in range(5)] == [game.roll("2d6") for _ in range(5)]


def test_recorded_log_replays_to_known_state():
    state = replay(load_game(RECORDED_SESSION))

    pc = state.characters["pc"]
    assert (pc.hp, pc.max_hp, pc.xp) == (14, 18, 1)
    assert state.clocks["swarm"].filled == 3
    assert state.seed == 2026
    assert state.rng_position == 5
