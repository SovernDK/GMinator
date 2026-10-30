"""Runs eval cases against a model, through the same table the game plays at.

Each case sets up its scene in a new game by playing slash commands, then asks the model
to do one task there, and scores what comes back.
"""

import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Literal, get_args

from gminator.ai.provider import LLMProvider, ProviderError
from gminator.ai.tasks import Retract, classify
from gminator.core.characters import quick_start
from gminator.evals.cases import Cases, ClassifyCase, NarrateCase, Scene, VoiceCase
from gminator.evals.scoring import Check, Speaker, intent_check, prose_checks
from gminator.packs.models import Pack
from gminator.play.session import Session
from gminator.play.table import Reply, Table
from gminator.scenario.models import Scenario

Task = Literal["classify", "narrate", "voice"]
TASKS: tuple[Task, ...] = get_args(Task)


class CaseError(Exception):
    """A case that cannot be set up as written."""


@dataclass(frozen=True)
class CaseResult:
    task: Task
    case_id: str
    checks: list[Check]
    output: str
    """The intent as JSON, the text the player was finally told, or why the model failed."""
    seconds: float
    first_text: float | None = None
    """For narration and NPC voice: how long until the first text arrived."""

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


class FirstChoices:
    """Takes the first options of every choice, so a scene plays the same way every time."""

    def choose(self, prompt: str, options: Sequence[str], n: int) -> Sequence[int]:
        return range(n)


class Harness:
    def __init__(
        self, pack: Pack, scenario: Scenario, clock: Callable[[], float] = time.perf_counter
    ) -> None:
        self.pack = pack
        self.scenario = scenario
        self.clock = clock

    def run(self, task: Task, cases: Sequence, provider: LLMProvider) -> list[CaseResult]:
        run = {"classify": self._classify, "narrate": self._narrate, "voice": self._voice}[task]
        return [run(case, provider) for case in cases]

    def validate(self, cases: Cases) -> list[str]:
        """What is wrong with the cases, without asking any model."""
        checks: dict[Task, Callable] = {
            "classify": self._check_classify,
            "narrate": self._check_narrate,
            "voice": self._check_voice,
        }
        problems = []
        for task in TASKS:
            for case in getattr(cases, task):
                try:
                    found = list(checks[task](case))
                except CaseError as error:
                    found = [str(error)]
                problems += [f"{task} case {case.id}: {problem}" for problem in found]
        return problems

    # Running

    def _classify(self, case: ClassifyCase, provider: LLMProvider) -> CaseResult:
        table = self._sit(case.scene, provider)
        start = self.clock()
        try:
            intent = classify(provider, table.context(), table.options(), case.said)
        except ProviderError as error:
            checks = [Check("answered", False), Check("intent", False)]
            return CaseResult("classify", case.id, checks, str(error), self.clock() - start)
        checks = [Check("answered", True), intent_check(intent, case.expect)]
        output = intent.model_dump_json(exclude_none=True)
        return CaseResult("classify", case.id, checks, output, self.clock() - start)

    def _narrate(self, case: NarrateCase, provider: LLMProvider) -> CaseResult:
        table = self._sit(case.scene, provider)
        start = self.clock()
        reply = self._play(table, case.command, case.said)
        return self._told("narrate", case, "narrator", reply, start)

    def _voice(self, case: VoiceCase, provider: LLMProvider) -> CaseResult:
        table = self._sit(case.scene, provider)
        start = self.clock()
        return self._told("voice", case, "npc", table.talk(case.npc, case.said), start)

    def _told(
        self,
        task: Task,
        case: NarrateCase | VoiceCase,
        speaker: Speaker,
        reply: Reply,
        start: float,
    ) -> CaseResult:
        told: list[str] = []
        retracted = False
        first_text = None
        for part in reply.narration:
            if isinstance(part, Retract):
                told.clear()
                retracted = True
                continue
            if first_text is None:
                first_text = self.clock() - start
            told.append(part)
        text = "".join(told)
        checks = prose_checks(
            text,
            retracted=retracted,
            speaker=speaker,
            mentions=case.mentions,
            forbidden=case.forbidden,
        )
        return CaseResult(task, case.id, checks, text, self.clock() - start, first_text)

    # Setting up

    def _sit(self, scene: Scene, provider: LLMProvider | None) -> Table:
        """A table in the case's scene. The scene's own commands are never narrated: their
        narration is never read."""
        character = quick_start(self.pack, scene.class_id, "pc", "Hero")
        table = Table(Session.begin(self.pack, self.scenario, scene.seed, character), provider)
        for command in scene.commands:
            self._play(table, command)
            place = command.removeprefix("/go ")
            if place != command and table.session.state.characters["pc"].location != place:
                # A danger move in the way missed: another seed gets the scene there.
                raise CaseError(f"{command} does not get there with seed {scene.seed}")
        return table

    def _play(self, table: Table, command: str, said: str = "") -> Reply:
        before = len(table.session.game.events)
        reply = table.play(command, FirstChoices(), said)
        if len(table.session.game.events) == before:
            raise CaseError(f"{command} changes nothing")
        return reply

    # Checking cases

    def _check_classify(self, case: ClassifyCase) -> Iterator[str]:
        options = self._sit(case.scene, None).options()
        for expected in case.expect:
            move = options.moves.get(expected.move_id) if expected.move_id else None
            if expected.move_id and move is None:
                yield f"{expected.move_id} is not a move here"
            if move and expected.stat and expected.stat not in move.stats:
                yield f"{expected.move_id} does not take {expected.stat}"
            targets = {*options.people, *options.places, *options.obstacles}
            if expected.target and expected.target not in targets:
                yield f"{expected.target} is not here"
            if expected.then and expected.then not in options.places:
                yield f"{expected.then} is not a way on from here"

    def _check_narrate(self, case: NarrateCase) -> Iterator[str]:
        self._play(self._sit(case.scene, None), case.command)
        return iter(())

    def _check_voice(self, case: VoiceCase) -> Iterator[str]:
        if case.npc not in self._sit(case.scene, None).options().people:
            yield f"{case.npc} is not here"
