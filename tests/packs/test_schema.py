import json
from pathlib import Path

import jsonschema
import pytest
from ruamel.yaml import YAML

from gminator.packs.schema import SCHEMA_FILES, generate_schemas
from support import DUNGEON_WORLD

SCHEMAS = Path(__file__).parents[2] / "schemas"


def load_yaml(path: Path):
    return YAML(typ="safe").load(path)


def schema_for(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def dungeon_world_files() -> list[tuple[str, Path]]:
    files = [("pack.schema.json", DUNGEON_WORLD / "pack.yaml")]
    files += [("tags.schema.json", DUNGEON_WORLD / "tags.yaml")]
    files += [("gear.schema.json", DUNGEON_WORLD / "gear.yaml")]
    files += [("move.schema.json", path) for path in sorted(DUNGEON_WORLD.glob("moves/*.yaml"))]
    files += [("class.schema.json", path) for path in sorted(DUNGEON_WORLD.glob("classes/*.yaml"))]
    return files


@pytest.mark.parametrize("name", SCHEMA_FILES)
def test_committed_schema_is_up_to_date(name):
    assert schema_for(name) == generate_schemas()[name], (
        "Regenerate with: uv run python -m gminator.packs.schema"
    )


@pytest.mark.parametrize(
    ("schema", "path"),
    dungeon_world_files(),
    ids=lambda value: value.name if isinstance(value, Path) else "",
)
def test_dungeon_world_file_matches_its_schema(schema, path):
    jsonschema.validate(load_yaml(path), schema_for(schema))


def test_move_schema_rejects_unknown_effects():
    move = {
        "id": "summon",
        "name": "Summon",
        "category": "basic",
        "trigger": "When you summon",
        "effects": [{"summon_dragon": {}}],
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(move, schema_for("move.schema.json"))


def test_dungeon_world_files_point_editors_at_their_schema():
    for schema, path in dungeon_world_files():
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith("# yaml-language-server: $schema=")
        assert (path.parent / first_line.split("=", 1)[1]).resolve() == SCHEMAS / schema
