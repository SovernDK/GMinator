# Development

## Setup

Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync                 # install
uv run pytest           # tests
uv run ruff check .     # lint
uv run ruff format .    # format
```

Runtime dependencies are deliberately few: `lark` (expressions), `pydantic` (models and validation), `ruamel-yaml` (YAML with line numbers) and `textual` (TUI). The AI backends use the standard library's `urllib`.

## Working style

- **Test first.** Every milestone was built red–green ([PLAN §1](../PLAN.md#1-principles)). Write the failing test, then the code.
- **Rules are data.** If Dungeon World can't be expressed in a pack, that is a gap in the core to close generically, not a special case.
- **Vocabulary.** Use the terms in [CONTEXT.md](../CONTEXT.md). When a term and the code disagree, fix one of them.
- **Decisions.** Record a significant decision as an ADR in `docs/adr/`.
- **Strings.** Player-facing text goes in `play/en.toml`.

## Tests

`pyproject.toml` runs pytest with `--strict-markers`, strict `xfail`, warnings as errors, and asyncio in auto mode. `tests/` is on the Python path, so test helpers import directly.

| Folder or file | Covers |
|---|---|
| `tests/core/` | dice, expressions, events, state, game, moves, conditions, characters |
| `tests/packs/` | models, loader errors, schema export, the Dungeon World pack |
| `tests/scenario/` | scenario loader, entity graph, GM move selector, opening and endings |
| `tests/play/` | `Session` and `Table` |
| `tests/ai/` | context, fact check, tasks, fake provider, Ollama and OpenAI-compatible backends |
| `tests/evals/` | cases, harness, scoring, report, and that every eval case sets up |
| `tests/tui/` | the Textual app, including a full playthrough |
| `test_replay.py` | a recorded log replays to identical state |
| `test_rats_under_the_inn.py` | every ending is reachable without AI |
| `test_ai_playthrough.py` | a full playthrough with the fake provider |
| `test_cli.py` | the command line |

Helpers:

- `support.py`: `DUNGEON_WORLD` path, `write_files` (build a pack or scenario in `tmp_path`), `ScriptedDecider`, `ScriptedConfirmer`, `BAND_TOTALS`, `seed_for(band, modifier)`.
- `tiny_cellar.py`: a two-room scenario on Dungeon World.
- `llm_server.py`: a local HTTP server standing in for Ollama or an OpenAI-compatible API.
- `fixtures/recorded_session.json`: the recorded log for the replay test.
- `FakeProvider` (in `ai/provider.py`): scripted model replies.

To make a roll land in a given band, pick a seed rather than mocking dice: `seed_for("partial", modifier=2)` finds a seed whose first 2d6 roll, plus the modifier, is a partial hit.

The **evals** are not unit tests: they need a running model and take minutes. Only case *setup* is tested in pytest. Run them with `uv run gminator eval` on 3–4B models.

## JSON Schemas

The files in `schemas/` are generated from the Pydantic models, for editor autocomplete in content files. After changing a model in `packs/models.py` or `scenario/models.py`:

```sh
uv run python -m gminator.packs.schema
```

`tests/packs/test_schema.py` fails if a committed schema is out of date, if a content file doesn't match its schema, or if a content file lacks its `yaml-language-server` schema comment.

## Adding things

| To add | Touch |
|---|---|
| An effect | the args and effect model and `EFFECT_TYPES` in `packs/models.py`; `_Run._apply_one` in `core/moves.py`; reference checks in `Checker._effects` in `packs/loader.py`; regenerate schemas; the [reference](Effects%20and%20conditions%20reference.md) |
| A condition | the model and `CONDITION_TYPES`; `core/conditions.py`; `Checker.condition`; regenerate schemas; the reference |
| An event | `core/events.py` and the `Event` union; `state.apply`; `Session._describe` (and `_tell`); consider the save `VERSION` |
| A slash command | `Session._commands`; help text in `en.toml` |
| An AI backend | a class with `complete` and `stream` raising `ProviderError`; `make_provider` in `cli.py` |
| A move, class or item | YAML only; see [Writing a pack](Writing%20a%20system%20pack.md) |

## CI

`.github/workflows/ci.yml` runs on pushes to `main` and on pull requests:

- **lint**: `ruff check` and `ruff format --check`;
- **test**: `pytest` on Ubuntu, macOS and Windows, with Python 3.11, 3.12 and 3.13.

Both use `uv sync --locked`, so commit `uv.lock` with any dependency change.
