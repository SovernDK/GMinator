"""Command-line entry point."""

import argparse
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from ruamel.yaml import YAML

from gminator import __version__, config
from gminator.ai import ollama, openai_compat
from gminator.ai.provider import LLMProvider, Providers
from gminator.ai.tasks import Retract
from gminator.config import Backend, Config, ConfigError, current_platform, load_config
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


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gminator")
    parser.add_argument("--version", action="version", version=f"gminator {__version__}")
    commands = parser.add_subparsers(dest="command")
    play_parser = commands.add_parser("play", help="play a scenario")
    play_parser.add_argument("--scenario", type=Path, default=SCENARIO)
    play_parser.add_argument("--packs", type=Path, default=PACKS, help="where system packs live")
    play_parser.add_argument("--seed", type=int, default=0)
    play_parser.add_argument("--save", type=Path, help="where the game is saved")
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
        help="the narrator's backend; without one, play goes through slash commands",
    )
    play_parser.add_argument("--model", help="the model to ask for every task")
    play_parser.add_argument("--url", help="where the backend listens")
    for task in TASKS:
        play_parser.add_argument(
            f"--{task}-model", help=f"the model to {task} with, if not the one from --model"
        )

    eval_parser = commands.add_parser("eval", help="score models on the AI tasks")
    eval_parser.add_argument("--scenario", type=Path, default=SCENARIO)
    eval_parser.add_argument("--packs", type=Path, default=PACKS, help="where system packs live")
    eval_parser.add_argument("--provider", choices=["ollama", "openai"])
    eval_parser.add_argument(
        "--model",
        dest="models",
        action="append",
        help="a model to score; repeat to compare several (default: the configured ones)",
    )
    eval_parser.add_argument("--url", help="where the backend listens")
    eval_parser.add_argument(
        "--task", dest="tasks", action="append", choices=TASKS, help="only this task; repeatable"
    )
    eval_parser.add_argument("--cases", type=Path, default=EVALS / "cases")
    eval_parser.add_argument("--bar", type=Path, default=EVALS / "bar.toml")
    eval_parser.add_argument("--out", type=Path, help="save every case result here, as JSON")

    for command_parser in (play_parser, eval_parser):
        command_parser.add_argument(
            "--config",
            type=Path,
            help=f"a settings file over the defaults (default: {config.USER_CONFIG})",
        )

    args = parser.parse_args(argv)
    if args.command is None:
        return
    try:
        settings = load_config(args.config or config.USER_CONFIG)
    except ConfigError as error:
        raise SystemExit(str(error)) from error
    if args.command == "play":
        kind = args.provider or settings.provider
        providers = None
        if kind != "none":
            backend = settings.backend(kind)
            configured = backend.models_on(current_platform())
            models = {
                task: getattr(args, f"{task}_model") or args.model or getattr(configured, task)
                for task in TASKS
            }
            providers = make_providers(kind, backend, models, args.url)
        if args.plain:
            play(args.scenario, args.packs, args.class_id, args.name, args.seed, providers)
        else:
            pack, scenario = _load(args.scenario, args.packs)
            save = args.save or settings.save
            GameApp(pack, scenario, providers, save_path=save, seed=args.seed).run()
    elif args.command == "eval":
        evaluate(args, settings)


def make_providers(
    kind: str, backend: Backend, models: Mapping[Task, str], url: str | None
) -> Providers:
    """A provider for each task, sharing one where tasks use the same model."""
    by_model = {model: make_provider(kind, backend, model, url) for model in set(models.values())}
    return Providers(**{task: by_model[models[task]] for task in TASKS})


def make_provider(kind: str, backend: Backend, model: str, url: str | None) -> LLMProvider:
    url = url or backend.url
    if kind == "openai":
        api_key = backend.api_key or None
        return openai_compat.OpenAICompatibleProvider(model, url, api_key, backend.timeout)
    return ollama.OllamaProvider(model, url, backend.timeout)


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


def evaluate(args: argparse.Namespace, settings: Config) -> None:
    pack, scenario = _load(args.scenario, args.packs)
    harness = Harness(pack, scenario)
    cases = load_cases(args.cases)
    problems = harness.validate(cases)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        raise SystemExit(1)
    bar = load_bar(args.bar)

    kind = args.provider or ("ollama" if settings.provider == "none" else settings.provider)
    backend = settings.backend(kind)
    configured = backend.models_on(current_platform()).model_dump().values()
    results: dict[str, list[CaseResult]] = {}
    for model in args.models or list(dict.fromkeys(configured)):
        provider = make_provider(kind, backend, model, args.url)
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
    """The reply's lines, paced as it asks at a terminal, then its narration. The pause before
    the narration counts the time the narrator took to start."""
    pause = reply.pause if sys.stdout.isatty() else 0
    for i, line in enumerate(reply.lines):
        if i and pause:
            time.sleep(pause)
        print(line, flush=True)
    shown = time.monotonic()
    mid_line = False
    for i, part in enumerate(reply.narration):
        if not i and reply.lines and pause:
            time.sleep(max(0.0, pause - (time.monotonic() - shown)))
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
