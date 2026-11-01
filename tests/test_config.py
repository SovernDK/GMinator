from pathlib import Path

import pytest

from gminator.config import ConfigError, Models, load_config


def test_the_defaults_play_without_ai_and_classify_with_a_decision_model():
    config = load_config()

    assert config.provider == "none"
    assert config.save == Path.home() / ".gminator" / "save.json"
    ollama = config.backend("ollama")
    assert ollama.url == "http://localhost:11434"
    assert ollama.models == Models(
        classify="d1:2b-nvfp4", narrate="granite4.1:3b", voice="granite4.1:3b"
    )


def test_a_missing_file_leaves_the_defaults(tmp_path):
    assert load_config(tmp_path / "config.toml") == load_config()


def test_a_file_overrides_only_the_keys_it_sets(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        'provider = "ollama"\n[providers.ollama.models]\nnarrate = "big"\n', encoding="utf-8"
    )

    config = load_config(path)

    assert config.provider == "ollama"
    models = config.backend("ollama").models
    assert (models.classify, models.narrate) == ("d1:2b-nvfp4", "big")
    assert config.backend("ollama").url == "http://localhost:11434"


def test_a_platform_replaces_the_models_it_names(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[providers.ollama.platforms.macos]\nclassify = "fast"\n', encoding="utf-8")

    ollama = load_config(path).backend("ollama")

    assert ollama.models_on("macos").classify == "fast"
    assert ollama.models_on("macos").narrate == "granite4.1:3b"
    assert ollama.models_on("windows").classify == "d1:2b-nvfp4"


def test_the_save_path_may_start_at_home(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('save = "~/games/rats.json"\n', encoding="utf-8")

    assert load_config(path).save == Path.home() / "games" / "rats.json"


@pytest.mark.parametrize(
    "text",
    [
        'provider = "llamafile"\n',
        "[providers.ollama]\nmodel = 'misspelt'\n",
        "[providers.ollama.platforms.amiga]\nclassify = 'x'\n",
        "[providers.ollama.platforms.linux]\nsummarise = 'x'\n",
    ],
)
def test_settings_that_do_not_fit_are_refused(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ConfigError, match="do not fit"):
        load_config(path)


def test_a_file_that_is_not_toml_is_refused(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("provider = \n", encoding="utf-8")

    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(path)
