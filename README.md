# GMinator

A single-player terminal RPG on a Powered by the Apocalypse engine, shipping with Dungeon World as its first rules pack. A small local AI narrates and voices NPCs; a deterministic engine owns every rule and fact.

Status: early development (milestone M0). See [docs/PLAN.md](docs/PLAN.md).

## Development

```sh
uv sync                 # install dependencies
uv run pytest           # run tests
uv run ruff check .     # lint
uv run ruff format .    # format
```
