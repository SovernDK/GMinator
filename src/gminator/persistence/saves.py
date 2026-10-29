"""Save files: the event log as a versioned JSON document."""

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from gminator.core.events import Event

FORMAT = "gminator-save"
VERSION = 1

_events_adapter: TypeAdapter[list[Event]] = TypeAdapter(list[Event])


class SaveError(Exception):
    """A save file that cannot be loaded."""


def save_game(path: Path, events: Iterable[Event]) -> None:
    document = {
        "format": FORMAT,
        "version": VERSION,
        "events": _events_adapter.dump_python(list(events), mode="json"),
    }
    path.write_text(json.dumps(document, indent=1), encoding="utf-8")


def load_game(path: Path) -> list[Event]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SaveError(f"{path} is not valid JSON: {error}") from error
    if not isinstance(document, dict) or document.get("format") != FORMAT:
        raise SaveError(f"{path} is not a GMinator save")
    if document.get("version") != VERSION:
        raise SaveError(f"{path} has unsupported save version {document.get('version')!r}")
    try:
        return _events_adapter.validate_python(document.get("events"))
    except ValidationError as error:
        raise SaveError(f"{path} contains invalid events:\n{error}") from error
