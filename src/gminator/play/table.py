"""The turn controller with the AI: free text in, classified and confirmed, then played as a
slash command through the `Session`, then narrated.

The AI only ever proposes. Every change to the game goes through a session command the
player has confirmed, so the engine stays the only thing that changes state.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Protocol

from gminator.ai.context import Context, ContextBuilder
from gminator.ai.factcheck import FactCheck
from gminator.ai.provider import LLMProvider, ProviderError
from gminator.ai.tasks import (
    Intent,
    MoveOption,
    Options,
    Part,
    Retract,
    classify,
    narrate,
    voice_npc,
)
from gminator.core.conditions import is_dead
from gminator.core.moves import Decider
from gminator.play.session import Session
from gminator.play.text import t
from gminator.scenario.graph import build_graph
from gminator.scenario.models import Ending


class Confirmer(Protocol):
    """Asks the player to accept or cancel what their words were taken to mean."""

    def confirm(self, question: str) -> bool: ...


@dataclass
class Reply:
    """Templated lines, shown at once, then any prose, streamed. The lines are the truth;
    the prose is flavour."""

    lines: list[str]
    narration: Iterator[Part] = field(default_factory=lambda: iter(()))


class Table:
    def __init__(self, session: Session, provider: LLMProvider | None) -> None:
        self.session = session
        self.provider = provider
        self._builder = ContextBuilder(session.scenario, session.rules, session.pc_id)
        self._check = FactCheck(session.scenario, session.rules)
        self._recent: list[str] = []
        self._narration = ""

    @property
    def ending(self) -> Ending | None:
        return self.session.ending

    def opening(self) -> list[str]:
        return self.session.opening()

    def handle(self, line: str, decider: Decider, confirmer: Confirmer) -> Reply:
        line = line.strip()
        if line.startswith("/") or self.provider is None:
            return self._play(line, decider)
        try:
            intent = classify(self.provider, self._context(), self._options(), line)
        except ProviderError as error:
            return Reply([t("table.offline", reason=error)])

        match intent:
            case Intent(kind="move", move_id=move_id) if move_id is not None:
                question, command = self._proposed_move(intent, move_id)
            case Intent(kind="travel", target=place) if place is not None:
                question = t("table.confirm_go", place=self.session.scenario.locations[place].name)
                command = f"/go {place}"
            case Intent(kind="talk", target=npc_id) if npc_id is not None:
                return self._talk(npc_id, line)
            case Intent(kind="look"):
                return Reply(self.session.handle("/look", decider))
            case Intent(kind="inventory"):
                return Reply(self.session.handle("/sheet", decider))
            case Intent(kind="ooc"):
                return Reply([t("table.ooc")])
            case _:
                return Reply([t("table.unclear")])

        if not confirmer.confirm(question):
            return Reply([t("table.cancelled")])
        return self._play(command, decider, said=line)

    def _play(self, command: str, decider: Decider, said: str = "") -> Reply:
        """Plays a slash command; narrates it if it changed the game."""
        before = len(self.session.game.events)
        lines = self.session.handle(command, decider)
        if self.provider is None or len(self.session.game.events) == before:
            return Reply(lines)
        context = self._context()
        self._recent += lines
        prose = narrate(self.provider, self._check, context, lines, said)
        return Reply(lines, _kept(prose, self._remember_narration))

    def _talk(self, npc_id: str, said: str) -> Reply:
        assert self.provider is not None
        name = self.session.state.characters[npc_id].name
        profile = self._builder.profile(self.session.state, npc_id)
        words = voice_npc(self.provider, self._check, self._context(), profile, said)

        def remember(text: str) -> None:
            if text:
                self._recent.append(t("table.said", name=name, words=text))

        return Reply([t("table.speaks", name=name)], _kept(words, remember))

    def _proposed_move(self, intent: Intent, move_id: str) -> tuple[str, str]:
        move = self.session.rules.moves[move_id]
        stat = t("table.stat", stat=intent.stat.upper()) if intent.stat else ""
        target = ""
        if intent.target:
            name = self.session.state.characters[intent.target].name
            target = t("table.target", target=name)
        question = t("table.confirm_move", move=move.name, stat=stat, target=target)
        args = [arg for arg in (move_id, intent.target, intent.stat) if arg]
        return question, f"/move {' '.join(args)}"

    def _remember_narration(self, text: str) -> None:
        self._narration = text

    def _context(self) -> Context:
        return self._builder.build(self.session.state, self._recent, self._narration)

    def _options(self) -> Options:
        session = self.session
        state = session.state
        location = state.characters[session.pc_id].location
        assert location is not None
        graph = build_graph(session.scenario, state, session.pc_id)
        people = {
            e.id: e.name
            for e in graph.subjects("at", location)
            if e.id != session.pc_id and not is_dead(state.characters[e.id])
        }
        places = {e.id: e.name for e in graph.objects(location, "connects")}
        moves = {
            move.id: MoveOption(
                f"{move.name}: {move.trigger}",
                stats=move.stat_options or [],
                targeted=move.target,
            )
            for move in session.available_moves()
        }
        return Options(moves=moves, people=people, places=places)


def _kept(parts: Iterator[Part], keep: Callable[[str], None]) -> Iterator[Part]:
    """Passes `parts` through, then hands `keep` the text that was finally told."""
    told: list[str] = []
    for part in parts:
        if isinstance(part, Retract):
            told.clear()
        else:
            told.append(part)
        yield part
    keep("".join(told))
