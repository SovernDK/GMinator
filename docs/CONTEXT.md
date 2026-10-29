# GMinator — Domain Glossary

Shared terms used across code, docs and packs. When a term here and the code disagree, fix one of them.

## Rules (PbtA)

- **PbtA (Powered by the Apocalypse):** the rules family GMinator's core implements. Players act through moves; the GM responds with GM moves.
- **Stat:** a character attribute with a modifier added to rolls. In DW the scores are STR/DEX/CON/INT/WIS/CHA, each mapped to a modifier from −3 to +3.
- **Roll:** 2d6 + a modifier.
- **Outcome band:** the result tier of a roll. **strong** (10+), **partial** (7–9), **miss** (6-). Packs may define different thresholds.
- **Move:** a rule triggered by fiction ("when you…"). It has a trigger, optionally a roll, and effects for each band. Moves are data, defined in packs.
- **Basic move / Special move / Class move:** move categories. Special moves cover situations like Last Breath and Make Camp; class moves belong to a class.
- **Effect:** one step from the fixed set of operations a move can perform (`deal_damage`, `choose_n`, `advance_clock`, …). New mechanics are built by combining effects.
- **Expression:** a small formula in a pack string (`class.damage + 1`, `b[2d8]`), parsed by Lark. It is never run with Python `eval`.
- **Hold:** a resource a move grants, spent later on listed options.
- **Forward:** a bonus or penalty (`+1 forward`) added to a character's next roll, then used up.
- **Tag:** a keyword on an item, location, NPC or character that affects rules or fiction (`reach`, `dark`, `stealthy`).
- **Harm / HP / Armor / Damage:** the damage model. DW uses HP, armor reduction and class damage dice.
- **Clock:** a progress track with N segments (for example 4 or 6). Clocks advance through effects or over time and trigger something when full.
- **XP:** experience. Gained on a miss and from other triggers.

## GM

- **GM move:** the GM's response, chosen by the **engine** and not the AI. A **soft** move sets up a threat; a **hard** move delivers it.
- **GM move selector:** the engine component that picks a GM move from the scenario's fronts, dangers and the pack's GM moves.
- **Front:** a group of related **dangers** with **grim portents** and an **impending doom**.
- **Danger:** a threat within a front, with its own type, impulse and moves.
- **Grim portent:** a step on a danger's path, usually tracked as a clock segment.
- **Impending doom:** what happens if a front runs its course.

## Content

- **Pack (system pack):** a folder of YAML defining a rules system: stats, moves, classes, gear, tags, GM moves. Dungeon World is the first.
- **Scenario (scenario pack):** a folder of YAML defining one adventure: locations, NPCs, fronts, items, clues, secrets, start and end conditions. It declares which system pack it uses.
- **Location:** a node in the scenario graph, with exits, tags, description seeds, hazards and NPCs present.
- **NPC profile:** an NPC's stat block plus role-play data: drive, voice, attitude, knowledge, secrets.
- **Secret:** a fact that is hidden until the engine reveals it through a `reveal_secret` effect. Unrevealed secrets never appear in an AI prompt.
- **Entity graph (ontology):** the typed entities and relations of scenario and world state (`NPC knows Secret`, `Location connects Location`). It is the structured source of facts for prompts.

## Engine

- **Engine:** the deterministic core that owns all state and rules.
- **Event:** an immutable record of one state change. The **event log** is the source of truth.
- **Snapshot:** cached state at a point in the log, used for fast loading.
- **Seeded RNG:** dice randomness from a seed stored in the log, so replays are exact.
- **Turn controller:** runs one turn: input → classify → confirm → resolve → narrate → display.

## AI

- **LLMProvider:** the interface to a language model backend. Implementations: Ollama, OpenAI-compatible, Fake (for tests).
- **AI tasks:** the three jobs the AI may do.
  - **Classify:** player text → `{kind, move_id?, stat?, target?}`.
  - **Narrate:** prose for an outcome the engine has already decided.
  - **NPC voice:** dialogue in character, based on the NPC profile.
- **Intent kind:** `move | travel | talk | look | inventory | ooc | unclear`.
- **ContextBuilder:** assembles the small factual context for each AI call from state, the entity graph and recent events. It is where vector retrieval will plug in later.
- **Fact check:** a post-check that flags narration naming items or NPCs that don't exist in state. It regenerates once, then falls back to the template.
- **Template fallback:** engine-generated text used when the AI is unavailable or fails.
- **Evals:** the offline evaluation suite that scores models on the three AI tasks. It is used to pick models; it is not part of unit tests.

## Interface

- **Slash command:** an explicit command (`/go`, `/sheet`, `/save`) that bypasses the AI.
- **Confirmation strip:** the TUI prompt where the player accepts, changes or cancels the suggested move.
- **Story log:** the main TUI pane showing narration, dialogue and roll results.
