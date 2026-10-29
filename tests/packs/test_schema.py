import json
from pathlib import Path

import jsonschema
import pytest
from ruamel.yaml import YAML

from gminator.packs.schema import SCHEMA_FILES, generate_schemas
from support import DUNGEON_WORLD

SCHEMAS = Path(__file__).parents[2] / "schemas"
RATS = Path(__file__).parents[2] / "scenarios" / "rats-under-the-inn"


def load_yaml(path: Path):
    return YAML(typ="safe").load(path)


def schema_for(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def dungeon_world_files() -> list[tuple[str, Path]]:
    files = [("pack.schema.json", DUNGEON_WORLD / "pack.yaml")]
    files += [("tags.schema.json", DUNGEON_WORLD / "tags.yaml")]
    files += [("gear.schema.json", DUNGEON_WORLD / "gear.yaml")]
    files += [("gm_moves.schema.json", DUNGEON_WORLD / "gm_moves.yaml")]
    files += [("move.schema.json", path) for path in sorted(DUNGEON_WORLD.glob("moves/*.yaml"))]
    files += [("class.schema.json", path) for path in sorted(DUNGEON_WORLD.glob("classes/*.yaml"))]
    return files


def rats_files() -> list[tuple[str, Path]]:
    names = ["scenario", "locations", "npcs", "secrets", "tags", "fronts", "endings"]
    files = [(f"{name}.schema.json", RATS / f"{name}.yaml") for name in names]
    files += [("scenario_move.schema.json", path) for path in sorted(RATS.glob("moves/*.yaml"))]
    return files


def content_files() -> list[tuple[str, Path]]:
    return dungeon_world_files() + rats_files()


@pytest.mark.parametrize("name", SCHEMA_FILES)
def test_committed_schema_is_up_to_date(name):
    assert schema_for(name) == generate_schemas()[name], (
        "Regenerate with: uv run python -m gminator.packs.schema"
    )


@pytest.mark.parametrize(
    ("schema", "path"),
    content_files(),
    ids=lambda value: value.name if isinstance(value, Path) else "",
)
def test_content_file_matches_its_schema(schema, path):
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


def test_content_files_point_editors_at_their_schema():
    for schema, path in content_files():
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith("# yaml-language-server: $schema=")
        assert (path.parent / first_line.split("=", 1)[1]).resolve() == SCHEMAS / schema
