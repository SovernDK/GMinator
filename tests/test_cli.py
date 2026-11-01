import io
import json
import subprocess
import sys
from importlib.metadata import version

import pytest

import gminator
from gminator.ai.provider import Providers
from gminator.cli import PromptConfirmer, PromptDecider, main
from gminator.play.text import t
from gminator.tui.app import GameApp
from llm_server import llm_server
from support import write_files


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
    main(["play", "--plain", *args])
    return capsys.readouterr().out


def launched(monkeypatch, *args: str) -> GameApp:
    apps: list[GameApp] = []
    monkeypatch.setattr(GameApp, "run", lambda self: apps.append(self))
    main(["play", *args])
    return apps[0]


def test_play_opens_the_game_in_the_terminal_interface(monkeypatch, tmp_path):
    app = launched(monkeypatch, "--seed", "3", "--save", str(tmp_path / "game.json"))

    assert app.scenario.manifest.name == "Rats Under the Inn"
    assert app.seed == 3
    assert app.save_path == tmp_path / "game.json"
    assert app.providers is None


def test_the_terminal_interface_gets_the_narrator(monkeypatch, tmp_path, unused_url):
    args = ["--provider", "ollama", "--url", unused_url, "--save", str(tmp_path / "game.json")]

    app = launched(monkeypatch, *args)

    assert isinstance(app.providers, Providers)


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


def test_each_task_can_use_its_own_model(monkeypatch, capsys, ollama):
    ollama.reply_json(classified(kind="travel", target="cellar"))
    ollama.reply(*stream("Damp stairs creak underfoot."))
    args = ["--provider", "ollama", "--url", ollama.url, "--model", "tiny"]
    args += ["--narrate-model", "big"]

    play(monkeypatch, capsys, *args, typed="I go down to the cellar\n\n/quit\n")

    assert [body["model"] for _, body, _ in ollama.requests] == ["tiny", "big"]


def test_play_takes_the_backend_and_models_from_the_config(monkeypatch, capsys, ollama, tmp_path):
    settings = f"""\
        provider = "ollama"
        [providers.ollama]
        url = "{ollama.url}"
        [providers.ollama.models]
        classify = "tiny"
        narrate = "big"
        """
    write_files(tmp_path, {"config.toml": settings})
    ollama.reply_json(classified(kind="travel", target="cellar"))
    ollama.reply(*stream("Damp stairs creak underfoot."))
    args = ["--config", str(tmp_path / "config.toml"), "--narrate-model", "flag"]

    play(monkeypatch, capsys, *args, typed="I go down to the cellar\n\n/quit\n")

    assert [body["model"] for _, body, _ in ollama.requests] == ["tiny", "flag"]


def test_play_refuses_a_config_that_does_not_fit(tmp_path):
    write_files(tmp_path, {"config.toml": 'provider = "llamafile"\n'})

    with pytest.raises(SystemExit, match="do not fit"):
        main(["play", "--plain", "--config", str(tmp_path / "config.toml")])


# Evals

CASES = {
    "classify.yaml": """\
        - id: down
          said: I go down to the cellar
          expect: {kind: travel, target: cellar}
        """,
    "voice.yaml": """\
        - id: ask_maud
          npc: maud
          said: Hello
        """,
}

BAR = {
    "bar.toml": """\
        [pass_rate]
        classify = 0.8
        narrate = 0.8
        voice = 0.8

        [seconds]
        first_text = 60.0
        turn = 60.0
        """
}


def test_eval_scores_each_model_against_the_bar(tmp_path, capsys, ollama):
    write_files(tmp_path / "cases", CASES)
    write_files(tmp_path, BAR)
    ollama.reply_json(classified(kind="travel", target="cellar"))
    ollama.reply_json(classified(kind="look"))
    args = ["eval", "--url", ollama.url, "--model", "good", "--model", "bad"]
    args += ["--task", "classify", "--cases", str(tmp_path / "cases")]
    args += ["--bar", str(tmp_path / "bar.toml"), "--out", str(tmp_path / "results.json")]

    main(args)

    output = capsys.readouterr().out
    good, bad = output.split("\nbad\n")
    assert "good" in good
    assert "meets the bar" in good
    assert "does not meet the bar" in bad
    assert "failed: down" in bad
    assert [body["model"] for _, body, _ in ollama.requests] == ["good", "bad"]
    saved = json.loads((tmp_path / "results.json").read_text())
    assert [result["passed"] for result in saved["good"]] == [True]
    assert [result["passed"] for result in saved["bad"]] == [False]


def test_eval_refuses_cases_that_cannot_be_set_up(tmp_path, capsys, unused_url):
    write_files(
        tmp_path / "cases",
        {"voice.yaml": "- {id: ask_swarm, npc: swarm, said: hi}\n"},
    )
    write_files(tmp_path, BAR)
    args = ["eval", "--url", unused_url, "--cases", str(tmp_path / "cases")]
    args += ["--bar", str(tmp_path / "bar.toml")]

    with pytest.raises(SystemExit) as exit_info:
        main(args)

    assert exit_info.value.code == 1
    assert "voice case ask_swarm: swarm is not here" in capsys.readouterr().err


def test_lines_of_a_turn_come_one_at_a_time(monkeypatch, capsys):
    from gminator import cli

    pauses = []
    monkeypatch.setattr(cli.time, "sleep", pauses.append)
    cli._show(["one", "two", "three"], delay=0.5)

    assert capsys.readouterr().out == "one\ntwo\nthree\n"
    assert pauses == [0.5, 0.5]
