"""The Textual interface: a title screen, character creation, and the game itself.

The engine asks its questions (a choice inside a move, whether free text meant what the AI
took it to mean) synchronously, so each turn runs in a worker thread. The thread waits on a
modal or the confirmation strip while the interface stays live, and hands everything it shows
back to the interface's own thread.
"""

import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future
from pathlib import Path
from typing import ClassVar, TypeVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.screen import ModalScreen, Screen
from textual.widget import Widget
from textual.widgets import (
    Button,
    Input,
    Label,
    OptionList,
    RadioButton,
    RadioSet,
    Select,
    SelectionList,
    Static,
)

from gminator.ai.provider import LLMProvider, Providers
from gminator.ai.tasks import Retract
from gminator.core.characters import CharacterError, create_character
from gminator.core.events import Event
from gminator.packs.models import GearChoice, Pack
from gminator.persistence.saves import SaveError, load_game, save_game
from gminator.play.session import Session
from gminator.play.table import Table
from gminator.play.text import t
from gminator.scenario.models import Scenario

T = TypeVar("T")


LINE_DELAY = 0.4
"""Seconds between one line of a turn's result and the next, so they don't land all at once."""


class GameApp(App[None]):
    CSS = """
    TitleScreen, CreationScreen { align: center middle; }
    #title { width: auto; text-align: center; text-style: bold; margin-bottom: 1; }
    #menu { width: 40; height: auto; }
    #menu Button { width: 100%; }
    #form { width: 90; max-height: 100%; }
    #scores { height: auto; }
    #scores Vertical { width: 1fr; height: auto; }
    #gear { height: auto; }
    #error { color: $error; }
    #log { width: 1fr; padding: 0 1; }
    #log .said { color: $text-muted; margin-top: 1; }
    #log .narration { text-style: italic; color: $accent; }
    #log .retracted { color: $text-muted; }
    #side { width: 40; padding: 0 1; border-left: solid $primary; }
    #sheet { margin-bottom: 1; }
    ConfirmStrip { height: 1; padding: 0 1; background: $warning-muted; }
    ChoiceModal { align: center middle; }
    #choice { width: 70; height: auto; border: thick $primary; background: $surface; }
    """

    def __init__(
        self,
        pack: Pack,
        scenario: Scenario,
        providers: LLMProvider | Providers | None = None,
        *,
        save_path: Path,
        seed: int = 0,
    ) -> None:
        super().__init__()
        self.pack = pack
        self.scenario = scenario
        self.providers = providers
        self.save_path = save_path
        self.seed = seed
        self.title = scenario.manifest.name

    def on_mount(self) -> None:
        title = t("tui.title", scenario=self.scenario.manifest.name, system=self.pack.manifest.name)
        self.push_screen(TitleScreen(title, self.save_path, self.create, self.resume))

    def create(self) -> None:
        self.switch_screen(CreationScreen(self.pack, self.begin))

    def begin(self, character: Sequence[Event]) -> None:
        session = Session.begin(self.pack, self.scenario, self.seed, character)
        self._play(session, session.opening())

    def resume(self, events: Sequence[Event]) -> None:
        session = Session.resume(self.pack, self.scenario, events)
        self._play(session, session.look())

    def _play(self, session: Session, opening: list[str]) -> None:
        table = Table(session, self.providers)
        self.switch_screen(GameScreen(table, [t("tui.welcome"), *opening], self.save_path))


class TitleScreen(Screen[None]):
    def __init__(
        self,
        title: str,
        save_path: Path,
        on_new: Callable[[], None],
        on_continue: Callable[[list[Event]], None],
    ) -> None:
        super().__init__()
        self._title = title
        self._save_path = save_path
        self._on_new = on_new
        self._on_continue = on_continue

    def compose(self) -> ComposeResult:
        with Vertical(id="menu"):
            yield Static(self._title, id="title", markup=False)
            yield Button(t("tui.new"), id="new", variant="primary")
            yield Button(t("tui.continue"), id="continue", disabled=not self._save_path.exists())
            yield Button(t("tui.quit"), id="quit")
            yield Static(id="error", markup=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "new":
                self._on_new()
            case "continue":
                try:
                    events = load_game(self._save_path)
                except SaveError as error:
                    self.query_one("#error", Static).update(str(error))
                    return
                self._on_continue(events)
            case "quit":
                self.app.exit()


class CreationScreen(Screen[None]):
    """Name, class, scores and gear, for a character made from one of the pack's classes."""

    def __init__(self, pack: Pack, on_created: Callable[[list[Event]], None]) -> None:
        super().__init__()
        self._pack = pack
        self._on_created = on_created
        self._class_id = next(iter(pack.classes))
        self._gear_shown: str | None = None

    def compose(self) -> ComposeResult:
        manifest = self._pack.manifest
        scores = manifest.score_array or list(range(3, 19))
        choices = [(str(score), score) for score in sorted(set(scores), reverse=True)]
        with VerticalScroll(id="form"):
            yield Label(t("tui.name"))
            yield Input(id="name")
            yield Label(t("tui.class"))
            with RadioSet(id="class"):
                for cls in self._pack.classes.values():
                    label = f"{cls.name}: {cls.description}" if cls.description else cls.name
                    yield RadioButton(
                        Content(label), id=f"class-{cls.id}", value=cls.id == self._class_id
                    )
            yield Label(t("tui.scores"))
            with Horizontal(id="scores"):
                for stat, score in zip(manifest.stats, scores, strict=False):
                    with Vertical():
                        yield Label(stat.upper())
                        yield Select(choices, value=score, allow_blank=False, id=f"score-{stat}")
            yield Vertical(id="gear")
            yield Static(id="error", markup=False)
            yield Button(t("tui.begin"), id="begin", variant="primary")

    async def on_mount(self) -> None:
        await self._show_gear()

    async def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id == "class" and event.pressed.id is not None:
            self._class_id = event.pressed.id.removeprefix("class-")
            await self._show_gear()

    async def _show_gear(self) -> None:
        if self._gear_shown == self._class_id:
            return
        self._gear_shown = self._class_id
        gear = self.query_one("#gear")
        await gear.remove_children()
        widgets: list[Widget] = []
        for i, choice in enumerate(self._pack.classes[self._class_id].gear_choices):
            widgets += [Label(Content(choice.label)), self._gear_picker(i, choice)]
        await gear.mount_all(widgets)

    def _gear_picker(self, i: int, choice: GearChoice) -> Widget:
        labels = [
            Content(", ".join(self._pack.items[item_id].name for item_id in option))
            for option in choice.options
        ]
        if choice.n == 1:
            buttons = [
                RadioButton(label, id=f"gear-{i}-{j}", value=j == 0)
                for j, label in enumerate(labels)
            ]
            return RadioSet(*buttons, id=f"gear-{i}")
        return SelectionList[int](
            *((label, j, j < choice.n) for j, label in enumerate(labels)), id=f"gear-{i}"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "begin":
            return
        name = self.query_one("#name", Input).value.strip()
        if not name:
            self._error(t("tui.no_name"))
            return
        scores = {
            stat: self.query_one(f"#score-{stat}", Select).selection
            for stat in self._pack.manifest.stats
        }
        try:
            character = create_character(
                self._pack, self._class_id, "pc", name, scores, self._gear_picks()
            )
        except CharacterError as error:
            self._error(str(error))
            return
        self._on_created(character)

    def _gear_picks(self) -> list[list[int]]:
        picks: list[list[int]] = []
        for i in range(len(self._pack.classes[self._class_id].gear_choices)):
            picker = self.query_one(f"#gear-{i}")
            if isinstance(picker, RadioSet):
                picks.append([picker.pressed_index])
            else:
                assert isinstance(picker, SelectionList)
                picks.append(sorted(picker.selected))
        return picks

    def _error(self, text: str) -> None:
        self.query_one("#error", Static).update(text)


class GameScreen(Screen[None]):
    """The story log, the sheet and clocks beside it, and the line the player types on.

    It is also the turn's `Decider` and `Confirmer`: the turn's thread asks it, and it asks
    the player.
    """

    def __init__(self, table: Table, opening: list[str], save_path: Path) -> None:
        super().__init__()
        self.table = table
        self.busy = False
        self.turns = 0
        self._opening = opening
        self._save_path = save_path
        self._narration: Static | None = None
        self._told = ""

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield VerticalScroll(id="log")
            with Vertical(id="side"):
                yield Static(id="sheet", markup=False)
                yield Static(id="clocks", markup=False)
        yield ConfirmStrip()
        yield Input(placeholder=t("tui.prompt"), id="command")

    def on_mount(self) -> None:
        self._write(self._opening)
        self._settle()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        line = event.value.strip()
        event.input.clear()
        if not line:
            return
        if line == "/quit":
            self.app.exit()
            return
        self._write([t("tui.said", line=line)], "said")
        self.busy = True
        event.input.disabled = True
        self._play(line)

    @work(thread=True)
    def _play(self, line: str) -> None:
        reply = self.table.handle(line, self, self)
        for i, text in enumerate(reply.lines):
            if i:
                time.sleep(LINE_DELAY)
            self.app.call_from_thread(self._write, [text])
        if reply.lines and LINE_DELAY:
            time.sleep(LINE_DELAY)
        for part in reply.narration:
            if isinstance(part, Retract):
                self.app.call_from_thread(self._retract)
            else:
                self.app.call_from_thread(self._stream, part)
        self.app.call_from_thread(self._turn_over)

    # Asked from the turn's thread

    def choose(self, prompt: str, options: Sequence[str], n: int) -> Sequence[int]:
        return self._ask(lambda done: self.app.push_screen(ChoiceModal(prompt, options, n), done))

    def confirm(self, question: str) -> bool:
        return self._ask(lambda done: self.query_one(ConfirmStrip).ask(question, done))

    def _ask(self, show: Callable[[Callable[[T], None]], object]) -> T:
        answer: Future[T] = Future()
        self.app.call_from_thread(show, answer.set_result)
        return answer.result()

    # Shown on the interface's thread

    def _write(self, lines: Sequence[str], kind: str = "line") -> None:
        log = self.query_one("#log", VerticalScroll)
        log.mount_all([Static(line, markup=False, classes=kind) for line in lines])
        log.scroll_end(animate=False)

    def _stream(self, text: str) -> None:
        if self._narration is None:
            self._narration = Static(markup=False, classes="narration")
            self._told = ""
            self.query_one("#log", VerticalScroll).mount(self._narration)
        self._told += text
        self._narration.update(self._told)
        self.query_one("#log", VerticalScroll).scroll_end(animate=False)

    def _retract(self) -> None:
        if self._narration is not None:
            self._narration.remove()
            self._narration = None
        self._write([t("tui.retracted")], "retracted")

    def _turn_over(self) -> None:
        self._narration = None
        self.busy = False
        self.turns += 1
        self._settle()

    def _settle(self) -> None:
        """Shows the game as it now stands, and saves it, or drops the save once it is over."""
        session = self.table.session
        self.query_one("#sheet", Static).update("\n".join(session.sheet()))
        self.query_one("#clocks", Static).update("\n".join(session.clocks()))
        command = self.query_one("#command", Input)
        if self.table.ending is None:
            self._save_path.parent.mkdir(parents=True, exist_ok=True)
            save_game(self._save_path, session.game.events)
            command.disabled = False
            command.focus()
        else:
            self._save_path.unlink(missing_ok=True)
            self._write([t("tui.ended")])
            command.disabled = True


class ConfirmStrip(Static, can_focus=True):
    """The line above the input where the player accepts or cancels a proposed action."""

    BINDINGS: ClassVar = [
        Binding("enter", "answer(True)", "Yes"),
        Binding("escape", "answer(False)", "No"),
    ]

    def __init__(self) -> None:
        super().__init__(markup=False)
        self.display = False
        self._done: Callable[[bool], None] | None = None

    def ask(self, question: str, done: Callable[[bool], None]) -> None:
        self._done = done
        self.update(t("tui.confirm", question=question))
        self.display = True
        self.focus()

    def action_answer(self, yes: bool) -> None:
        if self._done is None:
            return
        done, self._done = self._done, None
        self.display = False
        done(yes)


class ChoiceModal(ModalScreen[list[int]]):
    """Asks the player to pick `n` of a move's options."""

    def __init__(self, prompt: str, options: Sequence[str], n: int) -> None:
        super().__init__()
        self._prompt = prompt
        self._options = options
        self._n = n

    def compose(self) -> ComposeResult:
        with Vertical(id="choice"):
            yield Static(t("tui.choose", prompt=self._prompt, n=self._n), markup=False)
            if self._n == 1:
                yield OptionList(*(Content(option) for option in self._options))
            else:
                yield SelectionList[int](
                    *((Content(option), i) for i, option in enumerate(self._options))
                )
                yield Button(t("tui.done"), id="done")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss([event.option_index])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        picked = self.query_one(SelectionList).selected
        if len(picked) == self._n:
            self.dismiss(sorted(picked))
