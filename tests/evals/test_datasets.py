"""The shipped eval cases: enough of them, and every one sets up as written."""

from pathlib import Path

import pytest

from gminator.evals.cases import load_cases
from gminator.evals.harness import TASKS, Harness
from gminator.evals.report import load_bar

EVALS = Path(__file__).parents[2] / "evals"


@pytest.fixture(scope="module")
def cases():
    return load_cases(EVALS / "cases")


@pytest.mark.parametrize("task", TASKS)
def test_each_task_has_about_thirty_cases(cases, task):
    assert len(getattr(cases, task)) >= 30


def test_every_case_sets_up_in_the_scenario(cases, dungeon_world, rats):
    assert Harness(dungeon_world, rats).validate(cases) == []


def test_the_bar_loads():
    assert load_bar(EVALS / "bar.toml")
