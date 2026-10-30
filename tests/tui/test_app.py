"""The Textual interface, driven the way a player drives it: keys and clicks."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from textual.pilot import Pilot
from textual.widgets import Input, Select, Static

from gminator.ai.provider import FakeProvider
from gminator.core.characters import create_character
from gminator.core.events import ChoiceMade, MoveMade
from gminator.persistence.saves import load_game, save_game
from gminator.play.session import Session
from gminator.scenario.loader import load_scenario
from gminator.tui.app import ChoiceModal, ConfirmStrip, CreationScreen, GameApp, GameScreen
from support import ScriptedDecider, seed_for
from tiny_cellar import load_tiny_cellar

RATS = Path(__file__).parents[2] / "scenarios" / "rats-under-the-inn"
SIZE = (120, 60)


@pytest.fixture
def scenario(tmp_path, dungeon_world):
    return load_tiny_cellar(tmp_path / "scenario", dungeon_world)


@pytest.fixture
def save(tmp_path) -> Path:
    return tmp_path / "save.json"


def intent(kind, move_id=None, stat=None, target=None) -> str:
    return json.dumps({"kind": kind, "move_id": move_id, "stat": stat, "target": target})


async def until(pilot: Pilot, ready: Callable[[], bool]) -> None:
    for _ in range(500):
        if ready():
            return
        await pilot.pause(0.01)
    pytest.fail("the interface never got there")


def story(app: GameApp) -> str:
    return "\n".join(str(w.content) for w in app.screen.query("#log Static"))


def panel(app: GameApp, panel_id: str) -> str:
    return str(app.screen.query_one(f"#{panel_id}", Static).content)


async def create(pilot: Pilot, name: str = "Hero", class_id: str = "fighter") -> None:
    await pilot.click("#new")
    await until(pilot, lambda: isinstance(pilot.app.screen, CreationScreen))
    await pilot.click("#name")
    await pilot.press(*name)
    await pilot.click(f"#class-{class_id}")
    await pilot.pause()


async def begin(pilot: Pilot) -> None:
    await pilot.click("#begin")
    await until(pilot, lambda: isinstance(pilot.app.screen, GameScreen))


async def say(pilot: Pilot, line: str) -> None:
    """Types a line and waits until the turn it starts is over."""
    screen = pilot.app.screen
    assert isinstance(screen, GameScreen)
    turns = screen.turns
    await pilot.click("#command")
    await pilot.press(*line, "enter")
    await until(pilot, lambda: screen.turns > turns)


async def start_saying(pilot: Pilot, line: str) -> None:
    """Types a line without waiting for the turn: it may stop to ask the player something."""
    await pilot.click("#command")
    await pilot.press(*line, "enter")


# Title screen


async def test_the_title_screen_names_the_scenario(dungeon_world, scenario, save):
    app = GameApp(dungeon_world, scenario, save_path=save)
    async with app.run_test(size=SIZE):
        assert "Tiny Cellar" in panel(app, "title")


async def test_there_is_nothing_to_continue_without_a_save(dungeon_world, scenario, save):
    app = GameApp(dungeon_world, scenario, save_path=save)
    async with app.run_test(size=SIZE):
        assert app.screen.query_one("#continue").disabled


# Character creation


async def test_a_new_character_starts_the_scenario(dungeon_world, scenario, save):
    app = GameApp(dungeon_world, scenario, save_path=save)
    async with app.run_test(size=SIZE) as pilot:
        await create(pilot, "Vex", "thief")
        await begin(pilot)

        assert "You stand in the inn." in story(app)
        assert "Vex, Thief" in panel(app, "sheet")
        assert "The swarm: 0/2" in panel(app, "clocks")


async def test_scores_go_where_the_player_puts_them(dungeon_world, scenario, save):
    app = GameApp(dungeon_world, scenario, save_path=save)
    async with app.run_test(size=SIZE) as pilot:
        await create(pilot)
        screen = app.screen
        screen.query_one("#score-str", Select).value = 8
        screen.query_one("#score-cha", Select).value = 16
        await begin(pilot)

        assert "str -1" in panel(app, "sheet")
        assert "cha +2" in panel(app, "sheet")


async def test_a_score_used_twice_is_refused(dungeon_world, scenario, save):
    app = GameApp(dungeon_world, scenario, save_path=save)
    async with app.run_test(size=SIZE) as pilot:
        await create(pilot)
        app.screen.query_one("#score-dex", Select).value = 16
        await pilot.click("#begin")
        await pilot.pause()

        assert isinstance(app.screen, CreationScreen)
        assert "each used once" in panel(app, "error")


async def test_a_character_needs_a_name(dungeon_world, scenario, save):
    app = GameApp(dungeon_world, scenario, save_path=save)
    async with app.run_test(size=SIZE) as pilot:
        await create(pilot, name="")
        await pilot.click("#begin")
        await pilot.pause()

        assert isinstance(app.screen, CreationScreen)
        assert panel(app, "error")


async def test_gear_choices_follow_the_chosen_class(dungeon_world, scenario, save):
    app = GameApp(dungeon_world, scenario, save_path=save)
    async with app.run_test(size=SIZE) as pilot:
        await create(pilot, class_id="thief")
        await pilot.click("#gear-0-1")
        await begin(pilot)

        assert "Rapier" in panel(app, "sheet")
        assert "Dagger" not in panel(app, "sheet")


# Playing


async def test_a_command_plays_a_turn_and_refreshes_the_panels(dungeon_world, scenario, save):
    app = GameApp(dungeon_world, scenario, save_path=save)
    async with app.run_test(size=SIZE) as pilot:
        await create(pilot)
        await begin(pilot)
        await say(pilot, "/go cellar")

        assert "Hero goes to The cellar." in story(app)
        assert "== The cellar ==" in story(app)
        assert "/go cellar" in story(app)


async def test_every_turn_is_saved(dungeon_world, scenario, save):
    app = GameApp(dungeon_world, scenario, save_path=save)
    async with app.run_test(size=SIZE) as pilot:
        await create(pilot)
        await begin(pilot)
        await say(pilot, "/go cellar")

        screen = app.screen
        assert isinstance(screen, GameScreen)
        assert load_game(save) == list(screen.table.session.game.events)


async def test_a_choice_in_a_move_is_asked_in_a_modal(dungeon_world, scenario, save):
    app = GameApp(dungeon_world, scenario, save_path=save, seed=seed_for("strong", 2))
    async with app.run_test(size=SIZE) as pilot:
        await create(pilot)
        await begin(pilot)
        screen = app.screen
        assert isinstance(screen, GameScreen)
        await start_saying(pilot, "/move hack_and_slash corwin")
        await until(pilot, lambda: isinstance(app.screen, ChoiceModal))
        await pilot.press("down", "enter")
        await until(pilot, lambda: screen.turns == 1)

        chosen = [e for e in screen.table.session.game.events if isinstance(e, ChoiceMade)]
        assert chosen[0].chosen == ["Deal +1d6 damage, but expose yourself to their attack"]
        assert "Chosen: Deal +1d6 damage, but expose yourself to their attack." in story(app)


async def test_free_text_is_confirmed_in_the_strip_then_narrated(dungeon_world, scenario, save):
    provider = FakeProvider([intent("move", "defy_danger", "dex"), "You vault the bar."])
    app = GameApp(dungeon_world, scenario, provider, save_path=save)
    async with app.run_test(size=SIZE) as pilot:
        await create(pilot)
        await begin(pilot)
        screen = app.screen
        assert isinstance(screen, GameScreen)
        strip = screen.query_one(ConfirmStrip)
        await start_saying(pilot, "I vault over the bar")
        await until(pilot, lambda: strip.display)

        assert "Defy Danger +DEX?" in str(strip.content)
        await pilot.press("enter")
        await until(pilot, lambda: screen.turns == 1)

        assert not strip.display
        moves = [e for e in screen.table.session.game.events if isinstance(e, MoveMade)]
        assert [m.move_id for m in moves] == ["defy_danger"]
        assert "You vault the bar." in story(app)


async def test_escape_in_the_strip_cancels_the_move(dungeon_world, scenario, save):
    provider = FakeProvider([intent("move", "defy_danger", "dex")])
    app = GameApp(dungeon_world, scenario, provider, save_path=save)
    async with app.run_test(size=SIZE) as pilot:
        await create(pilot)
        await begin(pilot)
        screen = app.screen
        assert isinstance(screen, GameScreen)
        before = screen.table.session.game.events
        strip = screen.query_one(ConfirmStrip)
        await start_saying(pilot, "I vault over the bar")
        await until(pilot, lambda: strip.display)
        await pilot.press("escape")
        await until(pilot, lambda: screen.turns == 1)

        assert screen.table.session.game.events == before
        assert "Nothing happens." in story(app)


async def test_narration_taken_back_is_replaced_in_the_story(dungeon_world, scenario, save):
    provider = FakeProvider(["You draw a rapier.", "Mist curls on the stairs."])
    app = GameApp(dungeon_world, scenario, provider, save_path=save)
    async with app.run_test(size=SIZE) as pilot:
        await create(pilot)
        await begin(pilot)
        await say(pilot, "/go cellar")

        assert "Mist curls on the stairs." in story(app)
        assert "rapier" not in story(app)
        assert "(The narrator takes that back.)" in story(app)


async def test_quit_leaves_the_game(dungeon_world, scenario, save):
    app = GameApp(dungeon_world, scenario, save_path=save)
    async with app.run_test(size=SIZE) as pilot:
        await create(pilot)
        await begin(pilot)
        await start_saying(pilot, "/quit")
        await until(pilot, lambda: app.return_code is not None)


# Saved games


async def test_a_broken_save_is_reported_and_not_continued(dungeon_world, scenario, save):
    save.write_text("not json", encoding="utf-8")
    app = GameApp(dungeon_world, scenario, save_path=save)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.click("#continue")
        await pilot.pause()

        assert "not valid JSON" in panel(app, "error")
        assert not isinstance(app.screen, GameScreen)


async def test_continue_resumes_the_saved_game(dungeon_world, scenario, save):
    hero = create_character(
        dungeon_world,
        "fighter",
        "pc",
        "Brakka",
        {"str": 16, "con": 15, "dex": 13, "wis": 12, "int": 9, "cha": 8},
    )
    session = Session.begin(dungeon_world, scenario, 0, hero)
    session.handle("/go cellar", ScriptedDecider())
    save_game(save, session.game.events)

    app = GameApp(dungeon_world, scenario, save_path=save)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.click("#continue")
        await until(pilot, lambda: isinstance(app.screen, GameScreen))

        assert "== The cellar ==" in story(app)
        assert "Brakka, Fighter" in panel(app, "sheet")
        await say(pilot, "/go inn")
        assert "Brakka goes to The inn." in story(app)


# The M6 exit criterion: the scenario plays end to end in the TUI


async def test_rats_under_the_inn_plays_to_an_ending(dungeon_world, save):
    rats = load_scenario(RATS, dungeon_world)
    app = GameApp(dungeon_world, rats, save_path=save)
    async with app.run_test(size=SIZE) as pilot:
        await create(pilot, "Vex", "thief")
        await begin(pilot)
        for place in ("cellar", "broken_wall", "gallery", "river_exit"):
            await say(pilot, f"/go {place}")

        assert "THE END" in story(app)
        assert app.screen.query_one("#command", Input).disabled
        assert not save.exists()
