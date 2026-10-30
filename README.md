# GMinator

A single-player terminal RPG on a Powered by the Apocalypse engine, shipping with Dungeon World as its first rules pack. A small local AI narrates and voices NPCs; a deterministic engine owns every rule and fact.

Status: early development (milestone M6: the terminal interface). See [docs/PLAN.md](docs/PLAN.md).

## Play

```sh
uv run gminator play                  # Rats Under the Inn, in the full-screen interface
uv run gminator play --seed 7 --save ~/rats.json
uv run gminator play --plain --class thief --name Vex   # line by line, with a quick-start character
```

The game opens on a title screen: start a new game and make a character (name, class, scores,
gear), or continue the saved one. The game saves after every turn, to `~/.gminator/save.json`
unless `--save` says otherwise, and drops the save when the story ends.

Without a narrator, play goes through slash commands; type `/help` in the game for the list.
With one, type what you do in plain words: the game proposes a move to confirm, then narrates it.

```sh
ollama pull granite4.1:3b
uv run gminator play --provider ollama                   # default model granite4.1:3b
uv run gminator play --provider ollama --model qwen3.5:2b
uv run gminator play --provider openai --url http://localhost:8080/v1   # LM Studio, llama-server, vLLM
uv run gminator play --provider ollama --narrate-model other:3b       # a different model for one task
```

Each AI task (`classify`, `narrate`, `voice`) takes its own `--<task>-model`; the rest use `--model`.

## Evals

```sh
uv run gminator eval --model granite4.1:3b --out results.json
```

Scores models on the AI tasks against a quality bar; see [evals/README.md](evals/README.md).

## Development

```sh
uv sync                 # install dependencies
uv run pytest           # run tests
uv run ruff check .     # lint
uv run ruff format .    # format
```
