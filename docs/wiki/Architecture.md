# Architecture

Two ideas shape the code:

1. **The engine owns every fact** ([ADR-0001](../adr/0001-engine-owns-state.md)). Dice, HP, inventory, clocks and the choice of GM move are all code and data. The AI only proposes and describes.
2. **Everything is an event** ([ADR-0002](../adr/0002-event-sourcing.md)). State is never edited; it is rebuilt by replaying an append-only log of events from a seed.

## Layers

```
 cli.py · tui/            interfaces: read input, show lines and streamed prose
        │
        ▼
 play/table.py   Table    free text → AI classify → player confirms → slash command → narrate
        │
        ▼
 play/session.py Session  slash command → one turn: danger gate, action, GM moves, dying move, ending
        │
        ├──▶ scenario/    scenario models, entity graph, GM move selector, opening and endings
        ├──▶ core/        Game (event log + state), moves, conditions, dice, expressions
        └──▶ packs/       pack models and loader: the rules as data

 ai/                      providers and tasks; used by Table only, never by Session or core
 persistence/             the event log on disk
```

Dependencies point down. `core/` imports only the pack *models* (effects, conditions, moves) from `packs/`; it knows nothing of scenarios, sessions or the AI. `Session` never imports `ai/`, which is why the game is fully playable without a model.

## One turn, end to end

With the narrator on, a line of player text goes through these steps:

1. **Table.handle** gets the text. A line starting with `/`, or any line when there is no provider, goes straight to step 4.
2. **Classify.** `Table` builds the [context](AI%20layer.md#context) and the **options** (moves available now, people here, places to go, obstacles), and asks the classify model for an `Intent`. The JSON schema only allows ids from those options.
3. **Confirm.** `Table` turns the intent into a question ("Defy Danger first (Giant rats, DEX), then Hack and Slash against Corwin?") and a slash command. The player accepts or cancels.
4. **Session.handle** plays the slash command as one **turn** on a scratch copy of the game:
   - the [danger gate](Play%20layer.md#the-danger-gate) move, if a hostile NPC is here and the action is not exempt;
   - the action itself, unless the gate move missed;
   - every GM move the turn called for, picked by the [GM move selector](Play%20layer.md#gm-moves);
   - the pack's dying move if the player character dropped to 0 HP;
   - the first [ending](Writing%20a%20scenario.md#endings) whose condition holds.
   If all of it works, the events are recorded on the real game. If anything fails, nothing is.
5. **Render.** The new events become templated lines (the truth: `You take 4 damage (14/18 HP)`) and a **story** (the same turn without numbers or rules).
6. **Narrate.** `Table` sends the story to the narrate model, which streams 2–4 sentences. The [fact check](AI%20layer.md#fact-check) can retract the text and ask once more; a second failure leaves only the templated lines.
7. **Display and save.** The interface shows the lines, streams the prose, and (in the TUI) saves the event log.

Without the narrator, only steps 4, 5 and 7 run, driven by slash commands.

## Where the invariants are enforced

| Invariant | Enforced by |
|---|---|
| The AI never changes state | `Table` only ever calls `Session.handle` with a confirmed slash command; `ai/` has no access to `Game` |
| A turn is all or nothing | `Session._turn` and `core.moves._commit` play on a scratch `Game` and copy events across only on success |
| Replays are exact | `SeededDice` draws each die from `(seed, position)`; `DiceRolled` events advance `rng_position` |
| State is only built from events | `core/state.py`: `replay` and `apply` are pure and the models are frozen |
| Unrevealed secrets never reach a prompt | `scenario/graph.py` leaves them out of the entity graph, and the context is built only from the graph |
| Pack content is safe to load | expressions are parsed by Lark, never `eval`; every reference is checked at load time |
| Content errors point at a file and line | `packs/loader.py` validates YAML with Pydantic and reports `path:line: message` |
