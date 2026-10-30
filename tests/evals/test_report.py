import json

import pytest

from gminator.evals.harness import CaseResult
from gminator.evals.report import Bar, load_bar, render, results_json, shortfalls, summarize
from gminator.evals.scoring import Check
from support import write_files

BAR = Bar(pass_rate={"classify": 0.8, "narrate": 0.8, "voice": 0.8}, first_text=2.0, turn=10.0)


def classified(case_id: str, passed: bool, seconds: float = 1.0) -> CaseResult:
    checks = [Check("answered", True), Check("intent", passed)]
    return CaseResult("classify", case_id, checks, "{}", seconds)


def narrated(
    case_id: str, *failed: str, seconds: float = 3.0, first_text: float = 1.0
) -> CaseResult:
    checks = [Check(name, name not in failed) for name in ("answered", "length", "speaker")]
    return CaseResult("narrate", case_id, checks, "You swing.", seconds, first_text)


def test_a_summary_counts_passes_per_task_and_per_check():
    results = [
        classified("a", True),
        classified("b", False),
        narrated("c"),
        narrated("d", "length"),
        narrated("e", "length", "speaker"),
        narrated("f"),
    ]

    summaries = summarize(results)

    assert summaries["classify"].pass_rate == 0.5
    assert summaries["narrate"].pass_rate == 0.5
    assert summaries["narrate"].checks == {"answered": 1.0, "length": 0.5, "speaker": 0.75}
    assert summaries["narrate"].failed == ["d", "e"]
    assert "voice" not in summaries


def test_a_summary_gives_the_median_and_90th_percentile_times():
    results = [narrated(str(n), seconds=n, first_text=n / 10) for n in range(1, 11)]

    summary = summarize(results)["narrate"]

    assert summary.seconds_p50 == 5
    assert summary.seconds_p90 == 9
    assert summary.first_text_p90 == pytest.approx(0.9)
    assert summarize([classified("a", True)])["classify"].first_text_p90 is None


def test_a_model_that_meets_the_bar_falls_short_nowhere():
    results = [classified("a", True, seconds=1), narrated("b", seconds=8, first_text=1.5)]

    assert shortfalls(summarize(results), BAR) == []


def test_a_task_passing_too_few_cases_falls_short():
    results = [classified("a", True), classified("b", False)]

    assert shortfalls(summarize(results), BAR) == ["classify passes 50% of cases; the bar is 80%"]


def test_slow_first_text_and_slow_turns_fall_short():
    results = [classified("a", True, seconds=3), narrated("b", seconds=8, first_text=2.5)]

    assert shortfalls(summarize(results), BAR) == [
        "narration starts after 2.5 s (90th percentile); the bar is 2.0 s",
        "a turn takes 11.0 s (90th percentile, classify and narrate); the bar is 10.0 s",
    ]


def test_the_turn_is_judged_only_when_both_classify_and_narrate_ran():
    assert shortfalls(summarize([classified("a", True, seconds=30)]), BAR) == []


def test_the_bar_loads_from_toml(tmp_path):
    write_files(
        tmp_path,
        {
            "bar.toml": """\
                [pass_rate]
                classify = 0.9
                narrate = 0.75
                voice = 0.7

                [seconds]
                first_text = 2.0
                turn = 10.0
                """
        },
    )

    assert load_bar(tmp_path / "bar.toml") == Bar(
        pass_rate={"classify": 0.9, "narrate": 0.75, "voice": 0.7}, first_text=2.0, turn=10.0
    )


def test_the_report_shows_rates_times_failures_and_the_verdict():
    results = [classified("a", True), classified("b", False), narrated("c", "length")]

    report = render("granite4.1:3b", summarize(results), BAR)

    assert "granite4.1:3b" in report
    assert "classify" in report
    assert "50%" in report
    assert "length 0%" in report
    assert "failed: c" in report
    assert "classify passes 50% of cases; the bar is 80%" in report
    assert "does not meet the bar" in report
    assert "meets the bar" in render("m", summarize([classified("a", True)]), BAR)


def test_results_are_saved_as_json_per_model():
    results = {"granite4.1:3b": [classified("a", True), narrated("c", "length")]}

    saved = json.loads(results_json(results))

    [first, second] = saved["granite4.1:3b"]
    assert first == {
        "task": "classify",
        "case_id": "a",
        "passed": True,
        "checks": {"answered": True, "intent": True},
        "output": "{}",
        "seconds": 1.0,
        "first_text": None,
    }
    assert second["passed"] is False
