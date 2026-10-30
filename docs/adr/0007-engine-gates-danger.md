# ADR-0007: The engine decides when an action is made despite danger

**Status:** Accepted — 2026-10-30

## Context
In manual play, a player walked through the broken wall while the giant rats were in the cellar. No Defy Danger was rolled. The classifier picks one intent from the words alone. It wasn't told who is hostile, and a 3–4B model doesn't reliably spot that "I go through the wall" with rats around means acting despite danger. Whether a hostile NPC is close is a fact in the state, so there's nothing for the AI to judge.

## Decision
- A pack's manifest may declare a **danger gate**: the move to make first (in Dungeon World, Defy Danger), the default stat it rolls, optional stats per **move flag**, and the flags that are exempt.
- Moves carry **flags** saying what kind of action they are. Dungeon World marks Hack and Slash, Volley, Defend, Defend (spend hold) and Backstab as `combat`, which is exempt. Going through an exit carries the built-in flag `travel`. More flags can be added later.
- When a living NPC with `attitude: hostile` is in the player character's location, every action that changes the game is gated, unless it is exempt or is the gate move itself. That covers `/go` and every move. The engine makes the gate move first, with the fixed stat:
  - **strong:** the action happens.
  - **partial:** the action happens, plus the gate move's soft GM move.
  - **miss:** the action doesn't happen, plus a hard GM move.
- One gate covers the whole input. A move that goes on somewhere (`/move … then <place>`) is rolled for once.
- The confirmation strip names the gate move before the player accepts.

## Consequences
- \+ Defy Danger happens when the fiction calls for it, with no AI involved and no prompt tuning.
- \+ Packs other than Dungeon World can name their own gate move and flags, or leave the gate out.
- − The stat is fixed per flag, so the player can't choose how they defy the danger. They can still make Defy Danger themselves with any stat, and that is never gated.
- − Hostility is static scenario data. An NPC who is calmed or enraged during play will need hostility to become state.
- − Fiction-only actions (taking something from the pack, picking something up) are neither moves nor commands, so they are not gated yet.
