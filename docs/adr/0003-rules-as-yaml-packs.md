# ADR-0003: Generic PbtA core; rules and scenarios as YAML packs

**Status:** Accepted — 2026-10-29

## Context
The game must be easy to extend: new moves, new classes, new rules systems and new settings, written by people who don't write Python. Dungeon World is the first system, but it should not be hardcoded.

## Decision
- **Core (Python):** generic PbtA. Stats, the 2d6+mod roll, outcome bands, moves, effects, characters, harm, clocks, tags, the turn loop.
- **System packs (YAML):** rules as data. Dungeon World is `packs/dungeon-world/`.
- **Scenario packs (YAML):** adventures as data, each declaring which system pack it uses.
- **Pydantic models** are the single source of truth for what a pack may contain. YAML loads with validation errors that give file and line, and a **JSON Schema is exported** for editor autocomplete (VS Code YAML extension). There is no build step: YAML is both what authors write and what ships.
- Moves are written with a **fixed, documented set of effects** plus **expressions** in a small language parsed by **Lark** (dice, stat/property refs, `+ - *`, `min`/`max`, comparisons). Python `eval` is never used, because packs come from third parties.
- **Python plugin hooks** for moves that can't be expressed as data are planned in the design but not built in the MVP.

## Consequences
- \+ New moves and systems need no code changes. "A move added in YAML alone works" is an MVP acceptance test.
- \+ If DW can't be expressed in the pack format, that exposes a gap in the core rather than leading to a special case.
- \+ Lark gives a maintainable grammar instead of a hand-written parser.
- − The effect set needs careful growth, and every effect is a public API.
- − The pack schema needs versioning once third-party packs exist.
