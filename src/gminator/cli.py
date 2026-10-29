"""Command-line entry point."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from ruamel.yaml import YAML

from gminator import __version__
from gminator.ai import ollama, openai_compat
from gminator.ai.provider import LLMProvider
from gminator.ai.tasks import Retract
from gminator.core.characters import create_character
from gminator.packs.loader import load_pack
from gminator.play.session import Session
from gminator.play.table import Reply, Table
from gminator.play.text import t
from gminator.scenario.loader import load_scenario

_ROOT = Path(__file__).parents[2]
PACKS = _ROOT / "packs"
SCENARIO = _ROOT / "scenarios" / "rats-under-the-inn"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gminator")
    parser.add_argument("--version", action="version", version=f"gminator {__version__}")
    commands = parser.add_subparsers(dest="command")
    play_parser = commands.add_parser("play", help="play a scenario with slash commands")
    play_parser.add_argument("--scenario", type=Path, default=SCENARIO)
    play_parser.add_argument("--packs", type=Path, default=PACKS, help="where system packs live")
    play_parser.add_argument("--class", dest="class_id", default="fighter")
    play_parser.add_argument("--name", default="Hero")
    play_parser.add_argument("--seed", type=int, default=0)
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
    args = parser.parse_args(argv)
    if args.command == "play":
        provider = make_provider(args.provider, args.model, args.url)
        play(args.scenario, args.packs, args.class_id, args.name, args.seed, provider)


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
    provider: LLMProvider | None = None,
) -> None:
    system = YAML(typ="safe").load(scenario_root / "scenario.yaml")["system"]
    pack = load_pack(packs / system)
    scenario = load_scenario(scenario_root, pack)
    # Scores go to the stats in the pack's order: a quick start, not character creation.
    scores = dict(zip(pack.manifest.stats, pack.manifest.score_array or [], strict=False))
    character = create_character(pack, class_id, "pc", name, scores)
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
