# GMinator

A single-player terminal RPG on a Powered by the Apocalypse engine, shipping with Dungeon World as its first rules pack. A small local AI narrates and voices NPCs; a deterministic engine owns every rule and fact.

Status: early development (milestone M4: the AI layer; free text is classified, confirmed and narrated). See [docs/PLAN.md](docs/PLAN.md).

## Play

```sh
uv run gminator play                  # Rats Under the Inn, as a fighter
uv run gminator play --class thief --name Vex --seed 7
```

Without a narrator, play goes through slash commands; type `/help` in the game for the list.
With one, type what you do in plain words: the game proposes a move to confirm, then narrates it.

```sh
ollama pull granite4.1:3b
uv run gminator play --provider ollama                   # default model granite4.1:3b
uv run gminator play --provider ollama --model qwen3.5:2b
uv run gminator play --provider openai --url http://localhost:8080/v1   # LM Studio, llama-server, vLLM
```

## Development

```sh
uv sync                 # install dependencies
uv run pytest           # run tests
uv run ruff check .     # lint
uv run ruff format .    # format
```
