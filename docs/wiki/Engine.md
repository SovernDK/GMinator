# Engine

`src/gminator/core/` is the deterministic core: a generic PbtA rules engine that knows nothing of Dungeon World, scenarios or the AI.

## Events — `core/events.py`

Every change is a frozen Pydantic model with a `type` discriminator. `Event` is their union and `event_adapter` (de)serialises it.

| Event | Changes |
|---|---|
| `game_started` | the seed; must be the first event and only once |
| `character_created` | a new character: stats, max HP, class, damage, armor, level |
| `dice_rolled` | advances `rng_position` by the number of dice |
| `hp_changed` | HP, clamped to `0..max_hp` |
| `xp_marked` | XP |
| `clock_created`, `clock_advanced` | a clock; filling is capped at its segments |
| `tag_added`, `tag_removed` | a character's tags |
| `hold_changed` | hold per move; going below zero is an error |
| `forward_changed` | the bonus to the next roll |
| `item_gained`, `item_used` | inventory; a used item with no uses left is removed |
| `character_moved` | a character's location |
| `obstacle_cleared` | adds the obstacle to `cleared` |
| `secret_revealed` | adds the secret to `revealed` |
| `game_ended` | the ending; nothing may be applied after it |
| `move_made`, `choice_made`, `questions_asked`, `gm_move_triggered`, `gm_move_made` | nothing: they record what happened, for rendering, narration and the GM move selector |

Adding an event means adding the model, putting it in the `Event` union, handling it in `state.apply`, and rendering it in `Session._describe` (and `_tell` if the story should say it differently). Saves are versioned, so changing an existing event's fields breaks old saves.

## State — `core/state.py`

`GameState` holds the seed, `rng_position`, `characters`, `clocks`, `revealed`, `cleared` and `ending`. A `Character` holds stats (modifiers, not scores), HP, XP, class, damage, armor, level, tags, hold, forward, inventory and location. NPCs are characters too, with empty stats.

`replay(events)` builds state from a log; `apply(state, event)` is the single step. Both are pure. An event that can't apply raises `ReplayError`, and the state is unchanged.

## Game — `core/game.py`

`Game` is the event log plus the state it replays to.

- `Game.new(seed)` starts a log with `game_started`.
- `record(event)` applies the event, then appends it. A rejected event changes nothing.
- `roll(expression, refs)` evaluates an [expression](Expressions.md) with dice drawn at the current `rng_position`, and records `dice_rolled`.

## Dice — `core/dice.py`

`SeededDice(seed, position)` draws each die from `random.Random(f"{seed}:{position}")`. A die depends only on its position, so a game resumes at any point without replaying earlier rolls, and the same log always rolls the same dice.

## Move resolution — `core/moves.py`

`resolve_move(game, pack, move_id, actor_id, decider, target_id=, stat=)` turns a pack move into events and returns a `Resolution` (band, total, text, events).

1. **Check the request**: the actor exists; a move with `target` has one and one without doesn't; a character target exists; a move with `stat_options` gets an allowed stat.
2. **Unrolled move** (no `roll`): record `move_made`, apply `effects`.
3. **Rolled move**:
   - total = `manifest.roll + (move.roll)` + the actor's forward;
   - band from `manifest.bands` (strong 10+, partial 7–9, miss 6- by default);
   - record `move_made` with total and band, and use up the forward;
   - on a miss, apply the manifest's `miss_effects` (mark XP in DW);
   - apply the band's effects.

Effects are applied in order by `_Run._apply_one`; the full list is in the [reference](Effects-and-Conditions.md#effects). Damage is the rolled amount minus the victim's armor (their own plus every item they carry), never below 0.

Choices (`choose_n`, `ask_questions`) go to a **`Decider`**: an object with `choose(prompt, options, n) -> indices`. The TUI opens a modal, the plain CLI prompts, tests script it.

`make_gm_move(game, pack, gm_move, pc_id, decider, target_id=)` records `gm_move_made` and applies the GM move's effects with the player character as actor and the NPC behind it (if any) as target.

Both run through `_commit`: play on a copy of the game; record the new events on the real one only if nothing raised. A `ReplayError` or `ExpressionError` becomes a `ResolveError` and nothing is recorded.

## Conditions — `core/conditions.py`

`holds(condition, state, pc_id)` checks a [condition](Effects-and-Conditions.md#conditions) against the state. `is_dead(character)` is true at 0 HP or with the `dead` tag; dead NPCs become **remains**.

## Characters — `core/characters.py`

`create_character(pack, class_id, character_id, name, scores, gear_choices)` checks the scores against the manifest (every stat, and the `score_array` used once each), maps them to modifiers, evaluates the class's `max_hp` with `score.<stat>` and `stat.<stat>` (no dice allowed), and returns `character_created` plus an `item_gained` per starting and chosen item.

`quick_start(...)` assigns `score_array` to the stats in order and takes the first gear options. The plain CLI and the evals use it.
