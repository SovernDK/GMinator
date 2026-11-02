"""The turn controller with the AI: free text in, classified and confirmed, then played as a
slash command through the `Session`, then narrated. `/say` and `/gm` go to an NPC or the GM
without being classified; quoted speech is left out of what is classified.

The AI only ever proposes. Every change to the game goes through a session command the
player has confirmed, so the engine stays the only thing that changes state.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Protocol

from gminator.ai.context import Context, ContextBuilder
from gminator.ai.factcheck import FactCheck
from gminator.ai.provider import LLMProvider, ProviderError, Providers
from gminator.ai.tasks import (
    Intent,
    MoveOption,
    Options,
    Part,
    Retract,
    answer_gm,
    classify,
    narrate,
    split_speech,
    voice_npc,
)
from gminator.core.conditions import is_dead
from gminator.core.moves import Decider
from gminator.play.session import TRAVEL, Session
from gminator.play.text import t
from gminator.scenario.graph import build_graph
from gminator.scenario.models import Ending

LINE_DELAY = 0.4
"""Seconds between one line of a turn's result and the next, so they don't land all at once."""


class Confirmer(Protocol):
    """Asks the player to accept or cancel what their words were taken to mean."""

    def confirm(self, question: str) -> bool: ...


@dataclass
class Reply:
    """Templated lines, then any prose, streamed. The lines are the truth; the prose is
    flavour. A turn that changed the game shows its lines `pause` seconds apart, and pauses
    as long again before the prose; anything else comes at once."""

    lines: list[str]
    narration: Iterator[Part] = field(default_factory=lambda: iter(()))
    pause: float = 0.0


class Table:
    def __init__(self, session: Session, provider: LLMProvider | Providers | None) -> None:
        self.session = session
        self.providers = (
            Providers.one(provider)
            if provider is not None and not isinstance(provider, Providers)
            else provider
        )
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
        command, _, rest = line.partition(" ")
        if command in ("/say", "/gm"):
            if self.providers is None:
                return Reply([t("table.no_narrator")])
            return self.say(rest) if command == "/say" else self.ask_gm(rest)
        if line.startswith("/") or self.providers is None:
            return self.play(line, decider)
        action, speech = split_speech(line)
        if not action:
            return self.say(speech)
        try:
            intent = classify(self.providers.classify, self.context(), self.options(), action)
        except ProviderError as error:
            return Reply([t("table.offline", reason=error)])

        match intent:
            case Intent(kind="move", move_id=move_id) if move_id is not None:
                question, command = self._proposed_move(intent, move_id)
            case Intent(kind="travel", target=place) if place is not None:
                question = t("table.confirm_go", place=self._place(place))
                question = self._danger([TRAVEL]) + question
                command = f"/go {place}"
            case Intent(kind="travel"):
                places = ", ".join(self.options().places.values())
                return Reply([t("table.no_way", places=places)])
            case Intent(kind="talk", target=npc_id) if npc_id is not None:
                return self.talk(npc_id, line)
            case Intent(kind="look"):
                return Reply(self.session.handle("/look", decider))
            case Intent(kind="inventory"):
                return Reply(self.session.handle("/sheet", decider))
            case Intent(kind="ooc"):
                return self.ask_gm(line)
            case _:
                return Reply([t("table.unclear")])

        if not confirmer.confirm(question):
            return Reply([t("table.cancelled")])
        return self.play(command, decider, said=line)

    def play(self, command: str, decider: Decider, said: str = "") -> Reply:
        """Plays a slash command; narrates it if it changed the game. The narrator tells the
        turn's GM moves and describes where it arrived, so their lines are only shown if it
        can't."""
        before = len(self.session.game.events)
        lines = self.session.handle(command, decider)
        if len(self.session.game.events) == before:
            return Reply(lines)
        if self.providers is None:
            return Reply(lines, pause=LINE_DELAY)
        gm_lines = self.session.gm_lines
        told_by_narrator = [*self.session.arrival_lines, *gm_lines]
        context = self.context()
        story = self.session.story
        self._recent += story
        prose = narrate(self.providers.narrate, self._check, context, story, said)
        kept = _kept(prose, self._remember_narration, fallback=" ".join(told_by_narrator))
        return Reply([line for line in lines if line not in told_by_narrator], kept, LINE_DELAY)

    def say(self, words: str) -> Reply:
        """`/say [@someone] <words>`: the words to someone here, who answers. Without
        `@someone`, to the only person here."""
        target, _, rest = words.strip().partition(" ")
        if not target.startswith("@"):
            target, rest = "", words.strip()
        if not rest:
            return Reply([t("table.say_what")])
        people = self.options().people
        if not people:
            return Reply([t("table.no_one")])
        named = target[1:].lower()
        matches = [
            npc_id
            for npc_id, name in people.items()
            if named
            and (npc_id.startswith(named) or any(w.startswith(named) for w in name.lower().split()))
        ]
        if not target and len(people) == 1:
            matches = list(people)
        if len(matches) != 1:
            here = ", ".join(
                t("look.named", name=name, id=npc_id) for npc_id, name in people.items()
            )
            return Reply([t("table.say_to_whom", people=here)])
        return self.talk(matches[0], rest)

    def ask_gm(self, question: str) -> Reply:
        """The GM's answer to the player, out of character. Nothing in the game changes."""
        assert self.providers is not None
        if not question.strip():
            return Reply([t("table.ask_what")])
        answer = answer_gm(
            self.providers.narrate, self._check, self.context(), self.options(), question
        )
        return Reply([t("table.gm")], _kept(answer, lambda text: None))

    def talk(self, npc_id: str, said: str) -> Reply:
        assert self.providers is not None
        name = self.session.state.characters[npc_id].name
        profile = self._builder.profile(self.session.state, npc_id)
        words = voice_npc(self.providers.voice, self._check, self.context(), profile, said)

        def remember(text: str) -> None:
            if text:
                self._recent.append(t("table.said", name=name, words=text))

        return Reply([t("table.speaks", name=name)], _kept(words, remember))

    def _proposed_move(self, intent: Intent, move_id: str) -> tuple[str, str]:
        session = self.session
        move = session.rules.moves[move_id]
        stat = t("table.stat", stat=intent.stat.upper()) if intent.stat else ""
        target = ""
        if intent.target:
            if move.target == "obstacle":
                name = session.obstacles_here()[intent.target].name
            else:
                name = session.state.characters[intent.target].name
            target = t("table.target", target=name)
        then = t("table.then", place=self._place(intent.then)) if intent.then else ""
        question = t("table.confirm_move", move=move.name, stat=stat, target=target, then=then)
        danger = session.rules.manifest.danger
        if danger is None or move_id != danger.move:
            question = self._danger([*move.flags, *([TRAVEL] if intent.then else [])]) + question
        args = [arg for arg in (move_id, intent.target, intent.stat) if arg]
        if intent.then:
            args += ["then", intent.then]
        return question, f"/move {' '.join(args)}"

    def _danger(self, flags: list[str]) -> str:
        """The danger move the action will take first, if any, to put before the question."""
        session = self.session
        stat = session.danger_stat(flags)
        if stat is None:
            return ""
        danger = session.rules.manifest.danger
        assert danger is not None
        threats = ", ".join(session.state.characters[npc].name for npc in session.threats())
        move = session.rules.moves[danger.move].name
        return t("table.danger", threats=threats, move=move, stat=stat.upper())

    def _place(self, place: str) -> str:
        return self.session.scenario.locations[place].name

    def _remember_narration(self, text: str) -> None:
        self._narration = text

    def context(self) -> Context:
        return self._builder.build(self.session.state, self._recent, self._narration)

    def options(self) -> Options:
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
        obstacles = {o.id: o.name for o in session.obstacles_here().values()}
        return Options(moves=moves, people=people, places=places, obstacles=obstacles)


def _kept(parts: Iterator[Part], keep: Callable[[str], None], fallback: str = "") -> Iterator[Part]:
    """Passes `parts` through, then the `fallback` if nothing was told in the end; hands
    `keep` the text that was finally told."""
    told: list[str] = []
    for part in parts:
        if isinstance(part, Retract):
            told.clear()
        else:
            told.append(part)
        yield part
    if not told and fallback:
        told.append(fallback)
        yield fallback
    keep("".join(told))
