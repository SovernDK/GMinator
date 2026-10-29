# ADR-0005: Typed entity graph now, vector memory later, both behind ContextBuilder

**Status:** Accepted — 2026-10-29

## Context
Prompts for a small model must stay small, yet keep the facts it needs. Facts come in two kinds:
- **Hard facts:** who is where, who knows what, which clue leads where. These are structured and must be exact.
- **Soft memory:** past conversations, long lore, earlier narration. These are fuzzy, and similarity search helps with them.

## Decision
- **MVP:** scenario and world state is an explicit **typed entity–relation graph** (an ontology) built from Pydantic models, e.g. `NPC knows Secret`, `Location connects Location`, `Faction opposes Faction`.
- A `ContextBuilder` interface assembles each AI prompt: current location, NPCs present, PC condition, the last 3–5 events as templated facts, and 1–2 lines of previous narration.
- **Secret gating:** unrevealed secrets are never put in a prompt. They enter only after a `reveal_secret` event.
- The AI never summarises its own output.
- **Later (sandbox / long campaigns):** a local vector index (`sqlite-vec` or LanceDB) with an embedding model run through Ollama (e.g. `embeddinggemma`), indexing the event log, dialogue and lore. It plugs in behind `ContextBuilder`.

## Consequences
- \+ Exact facts are retrieved exactly; prompt size stays the same across a session.
- \+ The model can't leak what it was never told.
- \+ Adding vectors later doesn't change callers.
- − Long one-shot sessions get no recall of old dialogue until vectors land. That's acceptable at MVP scenario size.
