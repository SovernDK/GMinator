# ADR-0006: MIT code, per-pack content licences

**Status:** Accepted — 2026-10-29

## Context
GMinator will be published. The Dungeon World SRD is licensed CC-BY 3.0, which requires attribution. Future packs may carry different licences.

## Decision
- Code (`src/`, tests, tools): **MIT**.
- Each pack lives in its own folder with its own licence file. `packs/dungeon-world/` is **CC-BY 3.0**, crediting the Dungeon World SRD by Sage LaTorra and Adam Koebel.
- Scenarios likewise carry their own licence file.

## Consequences
- \+ Content and code licences stay clearly separate, and third-party packs can choose their own.
- − The pack loader should surface each pack's licence and attribution, for example on the title or credits screen.
