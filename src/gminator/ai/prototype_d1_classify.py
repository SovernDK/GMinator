"""PROTOTYPE — throwaway, do not import. Question: can d1-omni:600m (a decision model on
Ollama's /v1/systemone) classify the player's words as well as granite4.1:3b (56%)?

Runs evals/cases/classify.yaml through d1-omni with two state variants:
  full  — the classify context (scene, recent events) plus the player's words
  said  — the player's words only

    uv run python src/gminator/ai/prototype_d1_classify.py [--variant full|said] [-v]
"""

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from gminator.ai.tasks import Intent, Options, _names
from gminator.cli import _load
from gminator.evals.cases import load_cases
from gminator.evals.harness import Harness
from gminator.evals.scoring import intent_check

URL = "http://localhost:11434/v1/systemone"
MODEL = "d1:2b-nvfp4"
ROOT = Path(__file__).resolve().parents[3]

KINDS = {
    "move": "the player does something in the story that triggers one of the listed moves: "
    "fighting, sneaking, persuading, studying, recalling lore, resting, helping",
    "travel": "the player goes, walks or heads to another place",
    "talk": "the player just speaks to or asks a person here something, without a move",
    "look": "the player looks around at where they are",
    "inventory": "the player checks their own character, health or gear",
    "ooc": "the player talks to the game itself or about real life, not in the story",
    "unclear": "the words make no sense or fit nothing else",
}
NONE = "none of these"
MOVE_FIRST = False


def questions(options: Options) -> dict:
    def choice(instructions: str, criteria: dict[str, str]) -> dict:
        return {"type": "choice", "instructions": instructions, "criteria": criteria}

    moves = {id: move.description for id, move in options.moves.items()}
    stats = sorted({stat for move in options.moves.values() for stat in move.stats})
    q = {
        "kind": choice("What kind of action is the player taking?", KINDS),
        "move": choice(
            "If the player does something that triggers a move, which move?",
            {**moves, NONE: "the player triggers no move"},
        ),
    }
    # A choice needs 2+ candidates: with no one or nowhere, the answer is simply none.
    if options.people:
        q["person"] = choice(
            "Which person here is the player acting on or speaking to?",
            {**options.people, NONE: "no one"},
        )
    if options.places:
        q["place"] = choice(
            "Which place does the player say they go to?",
            {**options.places, NONE: "the player names no place to go"},
        )
    if options.obstacles:
        q["obstacle"] = choice(
            "Which obstacle is the player acting on?", {**options.obstacles, NONE: "none"}
        )
    if stats:
        q["stat"] = choice(
            "Which ability does the player use?", {**{s: s for s in stats}, NONE: "unsure"}
        )
    return q


def ask(state: str, qs: dict) -> dict:
    body = json.dumps({"model": MODEL, "state": state, "questions": qs}).encode()
    request = urllib.request.Request(URL, body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)["answers"]
    except urllib.error.HTTPError as error:
        detail = f"{error}: {error.read().decode()}\nquestions: {json.dumps(qs)}"
        raise SystemExit(detail) from error


def intent(answers: dict, options: Options, said: str) -> Intent:
    pick = {name: a["choice"] for name, a in answers.items()}
    pick = {name: None if value == NONE else value for name, value in pick.items()}
    kind = pick["kind"]
    if MOVE_FIRST and pick["move"] is not None:
        kind = "move"
    if kind == "move":
        move_id = pick["move"]
        if move_id not in options.moves:
            return Intent(kind="unclear")
        move = options.moves[move_id]
        aims = {False: None, True: pick.get("person"), "obstacle": pick.get("obstacle")}
        target = aims[move.targeted]
        if move.targeted and target is None:
            return Intent(kind="unclear")
        stat = pick.get("stat") if pick.get("stat") in move.stats else None
        then = (
            pick.get("place")
            if pick.get("place") and _names(said, pick.get("place"), options)
            else None
        )
        return Intent(kind="move", move_id=move_id, stat=stat, target=target, then=then)
    if kind == "travel":
        return (
            Intent(kind="travel", target=pick.get("place"))
            if pick.get("place")
            else Intent(kind="unclear")
        )
    if kind == "talk":
        return (
            Intent(kind="talk", target=pick.get("person"))
            if pick.get("person")
            else Intent(kind="unclear")
        )
    return Intent(kind=kind)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=["full", "said"], default="full")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--move-first", action="store_true", help="a named move wins over kind")
    args = parser.parse_args()
    global MOVE_FIRST
    MOVE_FIRST = args.move_first

    pack, scenario = _load(ROOT / "scenarios" / "rats-under-the-inn", ROOT / "packs")
    harness = Harness(pack, scenario)
    cases = load_cases(ROOT / "evals" / "cases").classify

    passed, times = 0, []
    for case in cases:
        table = harness._sit(case.scene, None)
        options = table.options()
        state = f"Player: {case.said}"
        if args.variant == "full":
            state = f"{table.context().render()}\n\n{state}"
        start = time.perf_counter()
        answers = ask(state, questions(options))
        times.append(time.perf_counter() - start)
        got = intent(answers, options, case.said)
        ok = intent_check(got, case.expect).passed
        passed += ok
        expected = " | ".join(e.model_dump_json(exclude_none=True) for e in case.expect)
        print(
            f"{'PASS' if ok else 'FAIL'} {case.id:28} got {got.model_dump_json(exclude_none=True)}"
        )
        if not ok:
            print(f"     {'':28} want {expected}")
        if args.verbose or not ok:
            for name, a in answers.items():
                print(f"     {'':28} {name}: {a['choice']} ({a['confidence']:.2f})")

    times.sort()
    print(
        f"\n{MODEL} [{args.variant}]: {passed}/{len(cases)} = {passed / len(cases):.0%}"
        f"  median {times[len(times) // 2]:.2f}s  p90 {times[int(len(times) * 0.9)]:.2f}s"
    )


if __name__ == "__main__":
    main()
