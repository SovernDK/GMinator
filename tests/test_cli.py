import io
import json
import subprocess
import sys
from importlib.metadata import version

import pytest

import gminator
from gminator.cli import PromptConfirmer, PromptDecider, main
from gminator.play.text import t
from llm_server import llm_server


def test_package_version_matches_installed_metadata():
    assert gminator.__version__ == version("gminator")


def test_version_flag_prints_name_and_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"gminator {gminator.__version__}"


def test_module_is_runnable_with_python_m():
    result = subprocess.run(
        [sys.executable, "-m", "gminator", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == f"gminator {gminator.__version__}"


def play(monkeypatch, capsys, *args: str, typed: str) -> str:
    monkeypatch.setattr("sys.stdin", io.StringIO(typed))
    main(["play", *args])
    return capsys.readouterr().out


def test_play_opens_the_scenario_and_runs_commands(monkeypatch, capsys):
    output = play(monkeypatch, capsys, "--seed", "3", typed="/go cellar\n/quit\n")

    assert "Drowned Rat" in output
    assert "The common room" in output
    assert "The cellar" in output


def test_play_stops_when_the_story_ends(monkeypatch, capsys):
    typed = "/go cellar\n/go broken_wall\n/go gallery\n/go river_exit\n/go gallery\n"

    output = play(monkeypatch, capsys, "--class", "thief", "--name", "Vex", typed=typed)

    assert "Down the River" in output
    assert "Vex goes to The hidden river exit." in output
    assert output.count("goes to") == 4


def test_play_ends_at_the_end_of_input(monkeypatch, capsys):
    assert "The common room" in play(monkeypatch, capsys, typed="/look\n")


def test_prompt_decider_asks_until_the_answer_is_valid(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("x\n3\n1 1\n2\n"))

    picks = PromptDecider().choose("Volley", ["Take several shots", "Move to get the shot"], 1)

    assert picks == [1]
    assert "1. Take several shots" in capsys.readouterr().out


# Playing with the narrator


@pytest.fixture
def ollama():
    with llm_server() as server:
        yield server


def stream(*chunks: str) -> list[str]:
    lines = [{"message": {"content": c}, "done": False} for c in chunks]
    return [json.dumps(line) + "\n" for line in [*lines, {"done": True}]]


def classified(**intent) -> dict:
    content = json.dumps({"move_id": None, "stat": None, "target": None, **intent})
    return {"message": {"content": content}, "done": True}


def test_play_with_ollama_confirms_free_text_and_streams_narration(monkeypatch, capsys, ollama):
    ollama.reply_json(classified(kind="travel", target="cellar"))
    ollama.reply(*stream("Damp stairs ", "creak underfoot."))
    args = ["--provider", "ollama", "--model", "tiny", "--url", ollama.url]

    output = play(monkeypatch, capsys, *args, typed="I go down to the cellar\n\n/quit\n")

    assert "Go to The cellar?" in output
    assert "Hero goes to The cellar." in output
    assert "Damp stairs creak underfoot." in output
    assert [body["model"] for _, body, _ in ollama.requests] == ["tiny", "tiny"]


def test_play_with_the_narrator_lets_the_player_decline(monkeypatch, capsys, ollama):
    ollama.reply_json(classified(kind="travel", target="cellar"))
    args = ["--provider", "ollama", "--url", ollama.url]

    output = play(monkeypatch, capsys, *args, typed="I go down to the cellar\nn\n/look\n")

    assert "Nothing happens." in output
    assert "goes to" not in output
    assert len(ollama.requests) == 1


def test_play_shows_when_narration_is_taken_back(monkeypatch, capsys, ollama):
    ollama.reply(*stream("You raise your rapier."))
    ollama.reply(*stream("Your rapier gleams."))
    args = ["--provider", "ollama", "--url", ollama.url]

    output = play(monkeypatch, capsys, *args, typed="/go cellar\n")

    assert output.count(t("cli.retracted")) == 2


def test_play_with_an_openai_compatible_server(monkeypatch, capsys, ollama):
    content = json.dumps({"kind": "look", "move_id": None, "stat": None, "target": None})
    ollama.reply_json({"choices": [{"message": {"content": content}}]})
    args = ["--provider", "openai", "--model", "local", "--url", f"{ollama.url}/v1"]

    output = play(monkeypatch, capsys, *args, typed="Where am I?\n")

    assert output.count("The common room") >= 2
    assert ollama.requests[0][0] == "/v1/chat/completions"


def test_play_without_a_narrator_never_calls_one(monkeypatch, capsys):
    output = play(monkeypatch, capsys, typed="I go down to the cellar\n")

    assert "/help" in output


def test_prompt_confirmer_takes_enter_or_yes_and_anything_else_as_no(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("\ny\nYes\nn\nnope\n"))
    confirmer = PromptConfirmer()

    answers = [confirmer.confirm("Go to The cellar?") for _ in range(5)]

    assert answers == [True, True, True, False, False]
    assert "Go to The cellar?" in capsys.readouterr().out
