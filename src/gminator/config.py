"""Settings: the defaults in config.toml, with the player's own file over them key by key."""

import sys
import tomllib
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

USER_CONFIG = Path.home() / ".gminator" / "config.toml"

Platform = Literal["macos", "linux", "windows"]
ProviderKind = Literal["none", "ollama", "openai"]
Task = Literal["classify", "narrate", "voice"]


class ConfigError(Exception):
    """A settings file that cannot be read or does not fit."""


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Models(_Model):
    """The model for each AI task."""

    classify: str
    narrate: str
    voice: str


class Backend(_Model):
    url: str
    timeout: float
    api_key: str = ""
    models: Models
    platforms: dict[Platform, dict[Task, str]] = {}

    def models_on(self, platform: Platform) -> Models:
        """The models, with those set for `platform` in place of the defaults."""
        return self.models.model_copy(update=self.platforms.get(platform, {}))


class Backends(_Model):
    ollama: Backend
    openai: Backend


class Config(_Model):
    provider: ProviderKind
    save: Path
    providers: Backends

    def backend(self, kind: Literal["ollama", "openai"]) -> Backend:
        return getattr(self.providers, kind)


def load_config(path: Path | None = None) -> Config:
    """The settings: the defaults, then `path` over them if it exists."""
    settings = tomllib.loads(files("gminator").joinpath("config.toml").read_text(encoding="utf-8"))
    if path is not None and path.exists():
        try:
            own = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as error:
            raise ConfigError(f"{path} is not valid TOML: {error}") from error
        settings = _merged(settings, own)
    try:
        config = Config.model_validate(settings)
    except ValidationError as error:
        where = path or "config.toml"
        raise ConfigError(f"{where} has settings that do not fit:\n{error}") from error
    return config.model_copy(update={"save": config.save.expanduser()})


def current_platform() -> Platform:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    return "linux"


def _merged(base: dict, over: dict) -> dict:
    """`base` with `over` on top; tables merge, everything else is replaced."""
    merged = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merged(merged[key], value)
        else:
            merged[key] = value
    return merged
