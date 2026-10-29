# ADR-0002: Event-sourced state with seeded RNG

**Status:** Accepted — 2026-10-29

## Context
Saves are required from the start. Future features (hot-seat play, AI companions, undo, debugging AI sessions, building prompt context from recent history) all benefit from knowing *what happened*, not just the current state.

## Decision
- Every state change is an immutable **event** appended to an **event log**, which is the source of truth.
- State is built by replaying events (pure functions). **Snapshots** are caches for fast loading.
- Dice use a **seeded RNG** whose seed is recorded in the log, so replays are exact.
- A save is the event log, optionally with the latest snapshot.

## Consequences
- \+ Saves, replays, undo and full session transcripts come almost for free.
- \+ Deterministic, so full games can be tested with pytest.
- \+ Recent events feed the AI's context as templated facts.
- − More design up front: event schemas need versioning once saves are public.
- − The code that rebuilds state from events must stay pure, with no I/O and no AI calls.
