"""Summaries of eval results, the quality bar a model must meet, and the report."""

import json
import math
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from gminator.evals.harness import TASKS, CaseResult, Task


@dataclass(frozen=True)
class Bar:
    pass_rate: dict[Task, float]
    """The share of cases each task must pass."""
    first_text: float
    """Seconds until narration starts, at the 90th percentile."""
    turn: float
    """Seconds for a turn, classify then narrate, at the 90th percentile."""


@dataclass(frozen=True)
class TaskSummary:
    task: Task
    cases: int
    failed: list[str]
    checks: dict[str, float]
    """The share of cases passing each check."""
    seconds_p50: float
    seconds_p90: float
    first_text_p90: float | None

    @property
    def pass_rate(self) -> float:
        return 1 - len(self.failed) / self.cases


def load_bar(path: Path) -> Bar:
    with path.open("rb") as file:
        bar = tomllib.load(file)
    return Bar(
        pass_rate={task: bar["pass_rate"][task] for task in TASKS},
        first_text=bar["seconds"]["first_text"],
        turn=bar["seconds"]["turn"],
    )


def summarize(results: Sequence[CaseResult]) -> dict[Task, TaskSummary]:
    summaries = {}
    for task in TASKS:
        mine = [result for result in results if result.task == task]
        if not mine:
            continue
        names = list(dict.fromkeys(check.name for result in mine for check in result.checks))
        checks = {
            name: _share([c.passed for r in mine for c in r.checks if c.name == name])
            for name in names
        }
        seconds = [result.seconds for result in mine]
        first_texts = [r.first_text for r in mine if r.first_text is not None]
        summaries[task] = TaskSummary(
            task=task,
            cases=len(mine),
            failed=[result.case_id for result in mine if not result.passed],
            checks=checks,
            seconds_p50=_percentile(seconds, 0.5),
            seconds_p90=_percentile(seconds, 0.9),
            first_text_p90=_percentile(first_texts, 0.9) if first_texts else None,
        )
    return summaries


def shortfalls(summaries: Mapping[Task, TaskSummary], bar: Bar) -> list[str]:
    """Where the summarized model falls short of the bar; nothing if it meets it."""
    found = [
        f"{task} passes {summary.pass_rate:.0%} of cases; the bar is {bar.pass_rate[task]:.0%}"
        for task, summary in summaries.items()
        if summary.pass_rate < bar.pass_rate[task]
    ]
    narrate = summaries.get("narrate")
    if narrate and narrate.first_text_p90 is not None and narrate.first_text_p90 > bar.first_text:
        found.append(
            f"narration starts after {narrate.first_text_p90:.1f} s (90th percentile); "
            f"the bar is {bar.first_text:.1f} s"
        )
    if narrate and "classify" in summaries:
        turn = summaries["classify"].seconds_p90 + narrate.seconds_p90
        if turn > bar.turn:
            found.append(
                f"a turn takes {turn:.1f} s (90th percentile, classify and narrate); "
                f"the bar is {bar.turn:.1f} s"
            )
    return found


def render(model: str, summaries: Mapping[Task, TaskSummary], bar: Bar) -> str:
    lines = [model]
    for task, summary in summaries.items():
        times = f"p50 {summary.seconds_p50:.1f} s, p90 {summary.seconds_p90:.1f} s"
        if summary.first_text_p90 is not None:
            times += f", first text p90 {summary.first_text_p90:.1f} s"
        lines.append(f"  {task:<9} {summary.pass_rate:>4.0%} of {summary.cases} cases  ({times})")
        checks = ", ".join(f"{name} {share:.0%}" for name, share in summary.checks.items())
        lines.append(f"            {checks}")
        if summary.failed:
            lines.append(f"            failed: {', '.join(summary.failed)}")
    short = shortfalls(summaries, bar)
    if short:
        lines.append("  does not meet the bar:")
        lines += [f"  - {reason}" for reason in short]
    else:
        lines.append("  meets the bar")
    return "\n".join(lines)


def results_json(results: Mapping[str, Sequence[CaseResult]]) -> str:
    """Every case result, by model, for reading through what each model said."""
    return json.dumps(
        {model: [_result(r) for r in model_results] for model, model_results in results.items()},
        indent=2,
    )


def _result(result: CaseResult) -> dict[str, object]:
    return {
        "task": result.task,
        "case_id": result.case_id,
        "passed": result.passed,
        "checks": {check.name: check.passed for check in result.checks},
        "output": result.output,
        "seconds": result.seconds,
        "first_text": result.first_text,
    }


def _share(passed: Sequence[bool]) -> float:
    return sum(passed) / len(passed)


def _percentile(values: Sequence[float], fraction: float) -> float:
    """The nearest-rank percentile."""
    ordered = sorted(values)
    return ordered[max(math.ceil(fraction * len(ordered)), 1) - 1]
