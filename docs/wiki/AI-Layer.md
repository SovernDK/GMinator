# AI layer

`src/gminator/ai/` does three narrow jobs and nothing else ([ADR-0001](../adr/0001-engine-owns-state.md)): **classify** the player's words, **narrate** an outcome the engine has decided, and **voice** an NPC. None of them can change the game. The models are small (3–4B) and chosen by [evals](../../evals/README.md) ([ADR-0004](../adr/0004-llm-provider-and-small-models.md)).

## Providers — `ai/provider.py`

```python
class LLMProvider(Protocol):
    def complete(self, messages, *, schema=None, temperature=None) -> str: ...
    def stream(self, messages, *, temperature=None) -> Iterator[str]: ...
```

| Backend | Module | Default |
|---|---|---|
| Ollama | `ai/ollama.py` | `granite4.1:3b` at `http://localhost:11434` |
| OpenAI-compatible (LM Studio, llama-server, vLLM) | `ai/openai_compat.py` | `http://localhost:8080/v1` |
| Fake | `FakeProvider` in `ai/provider.py` | for tests: a list of replies, or a function of each request |

`complete` with a `schema` forces JSON output. Connection failures, HTTP errors and non-JSON answers become `ProviderError`. `Providers(classify, narrate, voice)` holds one provider per task; `Providers.one(p)` uses one for all. On the command line, `--classify-model`, `--narrate-model` and `--voice-model` override `--model` per task.

## The tasks — `ai/tasks.py`

### Classify

`classify(provider, context, options, text) -> Intent`

The prompt holds the context, the **options** (moves available now with their triggers and stats, people here, places to go, obstacles, all by id) and the player's words. The JSON schema allows only those ids, so the model can't name a move or place that isn't there. The answer is checked again (a targeted move needs a valid target, a stat must be one of the move's) and an unusable answer is asked for once more, then becomes `unclear`. `then` is kept only if the player's words contain a word of the place's name or id (articles aside): the model may not send the player somewhere they didn't say. Temperature is 0.

```python
Intent(kind="move", move_id="hack_and_slash", target="corwin", stat=None, then=None)
```

Kinds: `move | travel | talk | look | inventory | ooc | unclear`.

### Narrate

`narrate(provider, check, context, facts, said) -> Iterator[Part]`

Streams 2–4 sentences, second person, present tense, from the turn's **story** (see [Play layer](Play-Layer.md#a-turn)) and what the player said.

### Voice

`voice_npc(provider, check, context, profile, said) -> Iterator[Part]`

Streams 1–3 sentences of dialogue from the NPC's **profile**: description, drive, voice, attitude, and the revealed secrets they know.

### Streaming, capping and retraction

Narrate and voice share `_checked`:

1. Stream the reply, cut off at the sentence cap (the rest is never read).
2. Fact-check the whole text. If it fails, yield a `Retract()` marker and ask once more, telling the model what to leave out.
3. A second failure is retracted for good: only the templated lines stand.
4. A `ProviderError` mid-stream retracts what was shown and stops.

The interface clears streamed text when it sees `Retract`.

## Context — `ai/context.py`

`ContextBuilder.build(state, recent, narration) -> Context` assembles the small, factual block every prompt starts with:

```
Location: The cellar
Barrels and sacks, many of them gnawed open. …
Ways on: The common room, The broken wall
Also here: Giant rats: …
Player character: Brakka, Fighter; wounded; carrying: Chainmail, Dungeon rations
Known secrets:
- …
Recent events:
- …
Last narration: …
```

It is built only from the [entity graph](#the-entity-graph), so secrets the engine hasn't revealed can't appear. HP is given in words (unhurt, wounded, badly hurt, down) so the model has no numbers to repeat. Recent events are capped at 5 and the last narration at 2 sentences, so the prompt stays the same size all session. Vector retrieval will plug in here later ([ADR-0005](../adr/0005-ontology-now-vectors-later.md)).

### The entity graph

`scenario/graph.py` builds typed entities (`location`, `pc`, `npc`, `secret`, `front`, `danger`) and relations (`connects`, `at`, `knows`, `part_of`, `drives`) from the scenario and the current state. `Session.look` and `Table.options` use it too.

## Fact check — `ai/factcheck.py`

Two checks on every narration and NPC line:

- **Unknown names**: `FactCheck` knows every NPC, location, obstacle and item name in the scenario and pack. A name in the text that the prompt doesn't contain was brought in by the model. Names the scenario has never heard of are beyond it.
- **Rules talk**: digits, HP, dice, XP, damage, hit bands, modifiers, and stat names in capitals. The engine shows the numbers; the prose must not.

## Changing a prompt

Prompts are the `*_SYSTEM` constants in `ai/tasks.py`. A change should be measured, not judged by eye: run the evals before and after on a 3–4B model.

```sh
uv run gminator eval --task classify --model granite4.1:3b --out before.json
```
