"""Templated text. The strings themselves live in en.toml, not in code."""

import tomllib
from importlib.resources import files

_STRINGS: dict[str, dict[str, str]] = tomllib.loads(
    files("gminator.play").joinpath("en.toml").read_text(encoding="utf-8")
)


def t(key: str, **values: object) -> str:
    """The string at `section.name`, filled in with `values`."""
    section, name = key.split(".")
    return _STRINGS[section][name].format(**values)
