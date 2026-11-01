# Evals

Offline evaluations that score models on the three AI tasks (classify, narrate, NPC voice)
so the choice of model is measured rather than guessed ([ADR-0004](../docs/adr/0004-llm-provider-and-small-models.md)).
They are not part of the unit tests: they need a running model and take minutes.

```sh
uv run gminator eval                                        # the default model, every task
uv run gminator eval --model granite4.1:3b --model qwen3.5:2b --out results.json
uv run gminator eval --task classify --model granite4.1:3b  # one task
uv run gminator eval --provider openai --url http://localhost:8080/v1 --model local
```

Each model gets a report: the share of cases passed per task, the share passing each check,
the failed case ids, times, and whether it meets the bar. `--out` saves every answer as JSON
for reading through.

## Cases

`cases/classify.yaml`, `cases/narrate.yaml` and `cases/voice.yaml` hold about 30 cases each,
all in *Rats Under the Inn*. A case's `scene` is a quick-start character (`class_id`, `seed`)
in a new game plus the slash `commands` played to get somewhere. Every scene command must
change the game, and a `/go` must get there (a danger move on the way can miss; pick
another `seed`), so a broken case is caught by `uv run pytest`, not by a confused score.

- **classify:** `said` and `expect`, one intent or a list of acceptable ones. A `stat` counts
  only when given; `then` (the place a move goes on to) must match, so a case without one
  wants none. The "speech without markers" section measures telling talk from action.
  Quoted speech is left out of `said` before classifying, as the table does (unless the
  quote is all there is); the "action with quoted speech" section measures what is left.
- **narrate:** the slash `command` whose outcome is narrated, what the player `said`, and
  optional `mentions` (at least one must appear) and `forbidden` words (such as a secret
  not yet revealed).
- **voice:** the `npc` spoken to, what the player `said`, `mentions` and `forbidden`.

## Checks

Scoring is deterministic: no model judges another.

| Check | Task | Passes when |
|---|---|---|
| answered | all | the model answered (not down, not retracted twice) |
| intent | classify | the intent is one of those expected |
| fact_check | narrate, voice | nothing was retracted by the fact check |
| no_rules_talk | narrate, voice | no digits, HP, dice, XP, damage, stats in capitals or hit bands; the same check retracts narration in play |
| length | narrate, voice | 2–4 sentences of narration, 1–3 of dialogue |
| speaker | narrate | the narration addresses the player as "you" |
| mentions | narrate, voice | at least one of the case's `mentions` |
| forbidden | narrate, voice | none of the case's `forbidden` words |

A case passes when all its checks pass.

## The bar

[`bar.toml`](bar.toml) sets the share of cases each task must pass and the time budget from
ADR-0004: narration starting within 2 s and a turn (classify plus narrate) within 10 s, both at
the 90th percentile.

## Results

**Chosen for now: `d1:2b-nvfp4` to classify, `granite4.1:3b` to narrate and voice.** granite
is the only 3–4B chat model with a valid result; together they meet the classify bar, and the
turn time is not yet measured with both. Raw answers are in [results/](results/).

Run on 2026-10-29, Ollama 0.40.2, Apple M1 (GPU, 16 GB), not the CPU-only reference machine:

| Model | Classify | Narrate | Voice | First text p90 | Turn p90 | Bar |
|---|---|---|---|---|---|---|
| `granite4.1:3b` | 56% | 87% | 100% | 1.2 s | 10.2 s | not met |
| `qwen3.5:2b` (nvfp4) | — | — | — | — | — | no valid result |
| `d1:2b-nvfp4` (decision model) | 84% | — | — | — | — | classify only; meets the classify bar |

- **granite4.1:3b:** classify is the weak task. It sends clear travel to the wrong place or a
  move ("I wade toward the water" became Make Camp), and takes scenario moves as talk
  (questioning Pip). Narration sometimes repeats numbers from the facts ("dealing 8
  damage"). Its voice answers were re-scored offline after the NPC speaker check was dropped
  and two `mentions` lists were loosened; nothing was asked of the model again.
- **d1:2b-nvfp4** (2026-10-30, same machine): a decision model, so it can only classify; it
  answers through `/v1/systemone` in one pass (p50 1.2 s, p90 1.4 s per case). Now the
  classify model in `config.toml`. It still fails on dodges read as other moves, speech to no
  one or to someone not here, and one bribe. Narrate and voice stay on granite4.1:3b.
- **qwen3.5:2b (nvfp4):** schema-forced classify calls ran into the 120 s timeout, then the
  Ollama server stopped, so the run measures the setup, not the model.
