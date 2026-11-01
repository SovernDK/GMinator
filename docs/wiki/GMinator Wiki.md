# GMinator Wiki

GMinator is a single-player terminal RPG on a Powered by the Apocalypse engine. Dungeon World is its first rules pack and *Rats Under the Inn* its first scenario. A small local AI narrates and voices NPCs; a deterministic engine owns every rule and fact.

This wiki explains how the code works and how to write content for it. For the *why*, see the [plan](../PLAN.md) and the [ADRs](../adr/); for terms, see the [glossary](../CONTEXT.md). When the wiki and the code disagree, the code wins: fix the wiki.

## Pages

**Understanding the code**

- [Architecture](Architecture.md): the layers, which way dependencies point, and how one turn flows through them
- [Engine](Engine.md): events, state, dice, move resolution and conditions (`core/`)
- [Play layer](Play%20layer.md): the `Session` and `Table` turn controllers, slash commands, the danger gate, templated text (`play/`, `scenario/`)
- [AI layer](AI%20layer.md): providers, the three tasks, the context builder and the fact check (`ai/`)
- [Interfaces and saves](Interfaces%20and%20saves.md): the CLI, the Textual TUI and the save file (`cli.py`, `tui/`, `persistence/`)

**Writing content**

- [Writing a system pack](Writing%20a%20system%20pack.md): manifest, moves, classes, gear, tags, GM moves
- [Writing a scenario](Writing%20a%20scenario.md): locations, obstacles, NPCs, secrets, fronts, endings, scenario moves
- [Effects and conditions reference](Effects%20and%20conditions%20reference.md): every effect and condition, with arguments
- [Expression language](Expressions.md): dice, references and arithmetic in pack strings

**Working on GMinator**

- [Development](Development.md): setup, tests and their helpers, schemas, CI, conventions
- [Evals](../../evals/README.md): scoring models on the AI tasks

## Quick start

```sh
uv sync
uv run gminator play                         # full-screen TUI, no AI
uv run gminator play --plain --class thief   # line by line, quick-start character
uv run gminator play --provider ollama       # with the narrator (granite4.1:3b)
uv run pytest
```

## Source map

| Path | What lives there | Page |
|---|---|---|
| `src/gminator/core/` | events, state, game, dice, expressions, moves, conditions, characters | [Engine](Engine.md), [Expressions](Expressions.md) |
| `src/gminator/packs/` | pack models, YAML loader, JSON Schema export | [Writing a pack](Writing%20a%20system%20pack.md) |
| `src/gminator/scenario/` | scenario models and loader, entity graph, GM move selector, opening and endings | [Writing a scenario](Writing%20a%20scenario.md), [Play layer](Play%20layer.md) |
| `src/gminator/play/` | `Session`, `Table`, player-facing strings (`en.toml`) | [Play layer](Play%20layer.md) |
| `src/gminator/ai/` | `LLMProvider`, Ollama and OpenAI-compatible backends, tasks, context, fact check | [AI layer](AI%20layer.md) |
| `src/gminator/evals/` | eval cases, harness, scoring, report | [Evals](../../evals/README.md) |
| `src/gminator/tui/` | Textual app | [Interfaces and saves](Interfaces%20and%20saves.md) |
| `src/gminator/persistence/` | save files | [Interfaces and saves](Interfaces%20and%20saves.md) |
| `src/gminator/cli.py` | `gminator play` and `gminator eval` | [Interfaces and saves](Interfaces%20and%20saves.md) |
| `packs/dungeon-world/` | the Dungeon World rules pack (CC-BY 3.0) | [Writing a pack](Writing%20a%20system%20pack.md) |
| `scenarios/rats-under-the-inn/` | the MVP scenario | [Writing a scenario](Writing%20a%20scenario.md) |
| `schemas/` | JSON Schemas generated from the models | [Development](Development.md#json-schemas) |
| `evals/` | eval cases, the quality bar, results | [Evals](../../evals/README.md) |
