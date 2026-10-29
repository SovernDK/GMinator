"""JSON Schemas for pack and scenario files, generated from their models for editor
autocomplete.

Regenerate the committed schemas with: uv run python -m gminator.packs.schema
"""

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from gminator.packs.models import CharacterClass, GmMoveDefinition, Item, Manifest, Move, Tag
from gminator.scenario.models import (
    Ending,
    Front,
    Location,
    Npc,
    ScenarioManifest,
    ScenarioMove,
    Secret,
)

_SOURCES: dict[str, tuple[str, Any]] = {
    "pack.schema.json": ("GMinator pack manifest (pack.yaml)", Manifest),
    "tags.schema.json": ("GMinator pack tags (tags.yaml)", list[Tag]),
    "gear.schema.json": ("GMinator pack gear (gear.yaml)", list[Item]),
    "move.schema.json": ("GMinator move (moves/*.yaml)", Move),
    "class.schema.json": ("GMinator class (classes/*.yaml)", CharacterClass),
    "gm_moves.schema.json": ("GMinator pack GM moves (gm_moves.yaml)", list[GmMoveDefinition]),
    "scenario.schema.json": ("GMinator scenario manifest (scenario.yaml)", ScenarioManifest),
    "locations.schema.json": ("GMinator scenario locations (locations.yaml)", list[Location]),
    "npcs.schema.json": ("GMinator scenario NPCs (npcs.yaml)", list[Npc]),
    "secrets.schema.json": ("GMinator scenario secrets (secrets.yaml)", list[Secret]),
    "fronts.schema.json": ("GMinator scenario fronts (fronts.yaml)", list[Front]),
    "endings.schema.json": ("GMinator scenario endings (endings.yaml)", list[Ending]),
    "scenario_move.schema.json": ("GMinator scenario move (moves/*.yaml)", ScenarioMove),
}
SCHEMA_FILES = list(_SOURCES)


def generate_schemas() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            **TypeAdapter(source).json_schema(),
            "title": title,
        }
        for name, (title, source) in _SOURCES.items()
    }


def export_schemas(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, schema in generate_schemas().items():
        (directory / name).write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    export_schemas(Path(sys.argv[1] if len(sys.argv) > 1 else "schemas"))
