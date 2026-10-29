# ADR-0001: The engine owns all state; the AI does three narrow tasks

**Status:** Accepted — 2026-10-29

## Context
GMinator uses a local language model for narration and NPCs and will ship to players with ordinary hardware (CPU only, 8 GB RAM), so the model will be small (3–4B parameters). Small models forget numbers, invent items and lose track of rules over long contexts. Letting the AI "be the GM" would make the game unreliable and hard to extend.

## Decision
- The deterministic engine owns **all** state and rules: dice, stats, outcome bands, HP, XP, inventory, clocks, NPC state, and **GM move selection**.
- The AI does only three tasks, each with a narrow prompt and output forced to a schema:
  1. **Classify** player text into an intent chosen from engine-supplied options.
  2. **Narrate** outcomes the engine has already decided (prose only).
  3. **Voice NPCs** based on their profiles.
- AI output never changes state. The engine checks every AI proposal, and the player confirms each suggested move.
- Mechanical results appear in their own UI elements, separate from the prose.
- A fact check flags narration that names items or NPCs not in state. It regenerates once and then falls back to templated text.
- The game is fully playable with templated text and no AI.

## Consequences
- \+ Works with very small models. Hallucinated prose can't corrupt the game.
- \+ New rules are code and data, not prompt tuning.
- \+ The fallback mode doubles as a test and debug mode.
- − Prose may occasionally contradict the panel. The panel wins, and players need to learn that.
- − The GM move selector needs real design work, because it is no longer delegated to the AI.
