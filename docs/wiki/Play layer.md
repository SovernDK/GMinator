# Play layer

The play layer runs turns. `Session` (`play/session.py`) is the game without AI: slash commands in, templated text out. `Table` (`play/table.py`) puts the AI in front of it. The scenario helpers they use live in `scenario/`.

## Session

```python
session = Session.begin(pack, scenario, seed, character_events)  # a new game
session = Session.resume(pack, scenario, events)  # a saved one
lines = session.handle("/move hack_and_slash corwin", decider)
```

`begin` records the character's creation events and the scenario's **opening** (`scenario/story.py`): every NPC created and placed, a clock per danger, and the player character at the start. `session.rules` is the pack with the scenario's moves and tags added (`Scenario.ruleset`).

### Slash commands

| Command | Changes the game | What it does |
|---|---|---|
| `/go <place>` | yes | go through an exit, unless an obstacle blocks it |
| `/move <move> [target] [stat] [then <place>]` | yes | make a move; with `then`, go on to `<place>` if the move doesn't miss |
| `/look` | no | location, exits, obstacles, who is here, remains |
| `/moves` | no | the moves available now |
| `/sheet` | no | the character sheet |
| `/clocks` | no | each danger's clock and the portents so far |
| `/secrets` | no | the secrets uncovered |
| `/say [@someone] <words>` | no | say something to someone here, who answers (needs the AI) |
| `/gm <question>` | no | ask the GM out of character (needs the AI) |
| `/help` | no | the list |

`/say` and `/gm` are handled by the `Table`, not the `Session`. `@someone` is an id or the start of a word of a name, ignoring case; without it, the words go to the only person here.

In `/move`, arguments that are stat names are the stat; the first other argument is the target (a character here, or an obstacle for `target: obstacle` moves).

### A turn

`Session._turn(act, decider, flags)` plays one game-changing command on a scratch copy of the game:

1. **Danger gate** (`_dares`), if `flags` is given; see below.
2. **The action** (`act`), unless the gate move missed.
3. **Aftermath** (`_aftermath`): walk the new events; for every `gm_move_triggered`, make a GM move, whose own events are walked too. If the player character is at 0 HP and not yet `dead`, make the pack's `dying_move` once and walk again.
4. **Ending**: record `game_ended` for the first ending that holds.

If any step raises `ResolveError` or `ReplayError`, the player sees why and nothing is recorded. Otherwise the events are copied to the real game and rendered twice:

- **lines** (`_describe`): the templated truth, with numbers (`Brakka rolls Hack and Slash: 11, a strong hit.`);
- **story** (`_tell`): the same turn without numbers or rules, HP in words, portents in place of clock counts, GM move text in place of names. `session.story` is what the narrator gets.

### The danger gate

From [ADR-0007](../adr/0007-engine-gates-danger.md). `danger_stat(flags)` is the stat to roll, or `None` when the pack has no gate, the action has an exempt flag, or no **threat** is here. `threats()` are the NPCs with `attitude: hostile` who are alive in the player character's location.

`/go` carries the `travel` flag; `/move` carries the move's flags, plus `travel` with `then`. The gate move itself is never gated, so the player can always make Defy Danger with a stat of their choice. One gate roll covers the whole command.

### GM moves

`scenario/gm.py` picks every GM move; the AI never does. For a `gm_move: soft|hard` request:

1. Candidates are the moves of every NPC alive and with the player character, every danger's GM moves, then the pack's general GM moves: those of that severity whose `requires` holds.
2. If any candidate comes from a **hostile** NPC here (its own move, or a move of a danger it drives), only those count. What is in front of the player acts.
3. One is picked with a recorded `d<n>`, so a replay picks the same one.
4. `make_gm_move` applies its effects to the player character, with the NPC behind it (if any) as `target`.

If there are no candidates, nothing happens.

A GM move is shown as its `text` only, never as "the GM makes a move". `session.gm_lines` holds those lines for the last turn: with the narrator on, `Table` leaves them out of the reply and the narrator tells the GM move from the story. If the narration fails or is retracted for good, the lines are shown in its place.

### Availability

`available_moves()` is what `/moves` lists and what the classifier may choose from. A move is out if it is the dying move, a class move of another class, a scenario move whose `requires` doesn't hold ("not now"), or an obstacle move where there is no obstacle.

## Table

```python
table = Table(session, providers)  # providers may be None
reply = table.handle(line, decider, confirmer)
reply.lines  # templated lines, shown at once
reply.narration  # an iterator of text chunks and Retract markers
```

`handle`:

- `/say` / `/gm` → `say(words)` / `ask_gm(question)`, without classifying; with no provider, a fixed line;
- `/...`, or any line with no provider → `play(line)`: the session handles it, and if it changed the game the story is narrated.
- a line that is only quoted speech → `say(speech)`;
- otherwise → `classify` the line without its quoted speech, then by intent kind:
  - `move` → a question naming the move, stat, target, `then` and any danger gate move, and a `/move …` command;
  - `travel` → a question (with any gate move) and `/go <place>`;
  - `talk` → `talk(npc, line)`: the NPC answers in character; nothing changes;
  - `look` / `inventory` → `/look` / `/sheet`;
  - `ooc` → `ask_gm(line)`: the GM answers out of character; nothing changes;
  - `unclear` → a fixed line.

  A move or travel is played only if `confirmer.confirm(question)` says yes.

`Table` keeps the recent story lines and NPC dialogue as **recent facts**, and the last narration actually told (after retractions), for the next prompt's context.

`Confirmer` and `Decider` are protocols the interfaces implement; see [Interfaces and saves](Interfaces%20and%20saves.md).

## Player-facing text — `play/en.toml`

Every string the engine shows is in `play/en.toml`, keyed by section and name, with `str.format` placeholders. `play/text.py` exposes `t("event.damage", who=…, amount=…)`. Add strings there, not inline.
