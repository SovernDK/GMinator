"""Command-line entry point."""

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from ruamel.yaml import YAML

from gminator import __version__
from gminator.ai import ollama, openai_compat
from gminator.ai.provider import LLMProvider, Providers
from gminator.ai.tasks import Retract
from gminator.core.characters import quick_start
from gminator.evals.cases import load_cases
from gminator.evals.harness import TASKS, CaseResult, Harness, Task
from gminator.evals.report import load_bar, render, results_json, summarize
from gminator.packs.loader import load_pack
from gminator.packs.models import Pack
from gminator.play.session import Session
from gminator.play.table import Reply, Table
from gminator.play.text import t
from gminator.scenario.loader import load_scenario
from gminator.scenario.models import Scenario
from gminator.tui.app import GameApp

_ROOT = Path(__file__).parents[2]
PACKS = _ROOT / "packs"
SCENARIO = _ROOT / "scenarios" / "rats-under-the-inn"
EVALS = _ROOT / "evals"
SAVE = Path.home() / ".gminator" / "save.json"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gminator")
    parser.add_argument("--version", action="version", version=f"gminator {__version__}")
    commands = parser.add_subparsers(dest="command")
    play_parser = commands.add_parser("play", help="play a scenario")
    play_parser.add_argument("--scenario", type=Path, default=SCENARIO)
    play_parser.add_argument("--packs", type=Path, default=PACKS, help="where system packs live")
    play_parser.add_argument("--seed", type=int, default=0)
    play_parser.add_argument("--save", type=Path, default=SAVE, help="where the game is saved")
    play_parser.add_argument(
        "--plain",
        action="store_true",
        help="play line by line instead of in the full-screen interface",
    )
    play_parser.add_argument(
        "--class", dest="class_id", default="fighter", help="with --plain: the character's class"
    )
    play_parser.add_argument("--name", default="Hero", help="with --plain: the character's name")
    play_parser.add_argument(
        "--provider",
        choices=["none", "ollama", "openai"],
        default="none",
        help="the narrator's backend; without one, play goes through slash commands",
    )
    play_parser.add_argument(
        "--model", help=f"the model to ask (Ollama default: {ollama.DEFAULT_MODEL})"
    )
    play_parser.add_argument("--url", help="where the backend listens")
    for task in TASKS:
        play_parser.add_argument(
            f"--{task}-model", help=f"the model to {task} with, if not the one from --model"
        )

    eval_parser = commands.add_parser("eval", help="score models on the AI tasks")
    eval_parser.add_argument("--scenario", type=Path, default=SCENARIO)
    eval_parser.add_argument("--packs", type=Path, default=PACKS, help="where system packs live")
    eval_parser.add_argument("--provider", choices=["ollama", "openai"], default="ollama")
    eval_parser.add_argument(
        "--model",
        dest="models",
        action="append",
        help="a model to score; repeat to compare several "
        f"(Ollama default: {ollama.DEFAULT_MODEL})",
    )
    eval_parser.add_argument("--url", help="where the backend listens")
    eval_parser.add_argument(
        "--task", dest="tasks", action="append", choices=TASKS, help="only this task; repeatable"
    )
    eval_parser.add_argument("--cases", type=Path, default=EVALS / "cases")
    eval_parser.add_argument("--bar", type=Path, default=EVALS / "bar.toml")
    eval_parser.add_argument("--out", type=Path, help="save every case result here, as JSON")

    args = parser.parse_args(argv)
    if args.command == "play":
        models = {task: getattr(args, f"{task}_model") or args.model for task in TASKS}
        providers = make_providers(args.provider, models, args.url)
        if args.plain:
            play(args.scenario, args.packs, args.class_id, args.name, args.seed, providers)
        else:
            pack, scenario = _load(args.scenario, args.packs)
            GameApp(pack, scenario, providers, save_path=args.save, seed=args.seed).run()
    elif args.command == "eval":
        evaluate(args)


def make_providers(
    kind: str, models: Mapping[Task, str | None], url: str | None
) -> Providers | None:
    """A provider for each task, sharing one where tasks use the same model."""
    if kind == "none":
        return None
    by_model = {model: make_provider(kind, model, url) for model in set(models.values())}
    return Providers(**{task: by_model[models[task]] for task in TASKS})


def make_provider(kind: str, model: str | None, url: str | None) -> LLMProvider | None:
    match kind:
        case "ollama":
            return ollama.OllamaProvider(model or ollama.DEFAULT_MODEL, url or ollama.DEFAULT_URL)
        case "openai":
            return openai_compat.OpenAICompatibleProvider(
                model or "", url or openai_compat.DEFAULT_URL
            )
    return None


def play(
    scenario_root: Path,
    packs: Path,
    class_id: str,
    name: str,
    seed: int,
    provider: LLMProvider | Providers | None = None,
) -> None:
    pack, scenario = _load(scenario_root, packs)
    character = quick_start(pack, class_id, "pc", name)
    table = Table(Session.begin(pack, scenario, seed, character), provider)

    print(t("cli.welcome", scenario=scenario.manifest.name))
    _show(table.opening())
    decider, confirmer = PromptDecider(), PromptConfirmer()
    while table.ending is None:
        try:
            line = input(t("cli.prompt"))
        except EOFError:
            return
        if line.strip() == "/quit":
            return
        _show_reply(table.handle(line, decider, confirmer))


def evaluate(args: argparse.Namespace) -> None:
    pack, scenario = _load(args.scenario, args.packs)
    harness = Harness(pack, scenario)
    cases = load_cases(args.cases)
    problems = harness.validate(cases)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        raise SystemExit(1)
    bar = load_bar(args.bar)

    results: dict[str, list[CaseResult]] = {}
    for model in args.models or [ollama.DEFAULT_MODEL]:
        provider = make_provider(args.provider, model, args.url)
        assert provider is not None
        results[model] = [
            result
            for task in args.tasks or TASKS
            for result in harness.run(task, getattr(cases, task), provider)
        ]
        print(render(model, summarize(results[model]), bar), flush=True)
    if args.out:
        args.out.write_text(results_json(results), encoding="utf-8")


def _load(scenario_root: Path, packs: Path) -> tuple[Pack, Scenario]:
    system = YAML(typ="safe").load(scenario_root / "scenario.yaml")["system"]
    pack = load_pack(packs / system)
    return pack, load_scenario(scenario_root, pack)


class PromptDecider:
    """Asks the player at the terminal."""

    def choose(self, prompt: str, options: Sequence[str], n: int) -> Sequence[int]:
        print(t("cli.choose", prompt=prompt, n=n))
        for number, option in enumerate(options, start=1):
            print(t("cli.option", number=number, option=option))
        while True:
            answer = input(t("cli.prompt")).split()
            picks = [int(a) - 1 for a in answer if a.isdigit()]
            valid = len(picks) == len(answer) == n == len(set(picks))
            if valid and all(0 <= pick < len(options) for pick in picks):
                return picks
            print(t("cli.answer", n=n, count=len(options)))


class PromptConfirmer:
    """Asks the player at the terminal: Enter or yes accepts, anything else cancels."""

    def confirm(self, question: str) -> bool:
        try:
            answer = input(t("cli.confirm", question=question))
        except EOFError:
            return False
        return answer.strip().lower() in ("", "y", "yes")


def _show_reply(reply: Reply) -> None:
    _show(reply.lines)
    mid_line = False
    for part in reply.narration:
        if isinstance(part, Retract):
            if mid_line:
                print()
            print(t("cli.retracted"))
            mid_line = False
        else:
            print(part, end="", flush=True)
            mid_line = True
    if mid_line:
        print()


def _show(lines: Sequence[str]) -> None:
    for line in lines:
        print(line)
