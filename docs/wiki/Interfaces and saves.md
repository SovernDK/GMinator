# Interfaces and saves

## The CLI — `cli.py`

```sh
uv run gminator play [options]
uv run gminator eval [options]
```

### `gminator play`

| Option | Default | |
|---|---|---|
| `--scenario` | `scenarios/rats-under-the-inn` | the scenario folder |
| `--packs` | `packs/` | where system packs live; the scenario's `system` picks one |
| `--seed` | `0` | the dice seed |
| `--save` | `~/.gminator/save.json` | the save file |
| `--plain` | off | line-by-line play instead of the TUI, with a quick-start character |
| `--class`, `--name` | | with `--plain`: the quick-start class and name |
| `--provider` | none | `ollama` or `openai`; without it, play is by slash commands only |
| `--model`, `--url` | per backend | the model and where it listens |
| `--classify-model`, `--narrate-model`, `--voice-model` | `--model` | a different model for one task |

In `--plain` mode, `PromptDecider` asks for choices on the terminal, `PromptConfirmer` asks `y/n`, and `/quit` leaves. Plain mode does not save.

### `gminator eval`

Runs the eval cases against one or more `--model`s and prints a report against `evals/bar.toml`. See [evals/README.md](../../evals/README.md).

## The TUI — `tui/app.py`

A Textual app with three screens:

- **TitleScreen**: new game, or continue (enabled when the save file exists).
- **CreationScreen**: name, class, scores from the pack's `score_array`, and gear choices, then `create_character`.
- **GameScreen**: the story log, a sidebar with the character sheet and clocks, and the input.
  - **ConfirmStrip** asks the `Table`'s question; Enter accepts, Esc cancels.
  - **ChoiceModal** asks for `choose_n` and `ask_questions` picks.
  - Narration streams into the log; a `Retract` clears it.

`GameScreen` is both the `Decider` and the `Confirmer`. It saves the event log after every turn and deletes the save when an ending is reached. A resumed game opens on `/look`; the story log and the narrator's recent events are not restored.

## Saves — `persistence/saves.py`

A save is the event log as JSON:

```json
{
 "format": "gminator-save",
 "version": 1,
 "events": [{"type": "game_started", "seed": 0}, …]
}
```

`save_game(path, events)` writes it; `load_game(path)` checks the format and version, validates every event, and raises `SaveError` otherwise. `Session.resume` replays the events; the player character is the first character created.

Because state is rebuilt from events and dice from `(seed, position)`, a loaded game continues exactly as the original would have (`tests/test_replay.py`). Changing an event's fields changes the save format: bump `VERSION`.
