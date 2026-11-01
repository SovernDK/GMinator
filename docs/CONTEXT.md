# GMinator — Domain Glossary

Shared terms used across code, docs and packs. When a term here and the code disagree, fix one of them.

## Rules (PbtA)

- **PbtA (Powered by the Apocalypse):** the rules family GMinator's core implements. Players act through moves; the GM responds with GM moves.
- **Stat:** a character attribute with a modifier added to rolls. In DW the scores are STR/DEX/CON/INT/WIS/CHA, each mapped to a modifier from −3 to +3.
- **Roll:** 2d6 + a modifier.
- **Outcome band:** the result tier of a roll. **strong** (10+), **partial** (7–9), **miss** (6-). Packs may define different thresholds.
- **Move:** a rule triggered by fiction ("when you…"). It has a trigger, optionally a roll, and effects for each band. Moves are data, defined in packs.
- **Basic move / Special move / Class move:** move categories. Special moves cover situations like Last Breath and Make Camp; class moves belong to a class.
- **Move flag:** a keyword saying what kind of action a move is (`combat`). Going through an exit carries the built-in flag `travel`. The danger gate reads flags.
- **Danger gate:** the pack's rule for acting near a hostile NPC: the engine makes the gate move first (Defy Danger in DW) with a fixed stat per flag. A miss stops the action. Actions with an exempt flag (`combat`) and the gate move itself are never gated. One gate covers one input.
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
- **GM move selector:** the engine component that picks a GM move from the NPCs here, the scenario's dangers and the pack's GM moves. The candidates are every move of the asked-for severity whose condition holds: the moves of NPCs alive and with the player character, danger moves and pack GM moves. If a hostile NPC here has a candidate, only theirs count. One is picked with a recorded die.
- **NPC move:** a GM move an NPC makes itself (DW's monster moves), only while alive and with the player character.
- **Front:** a group of related **dangers** with **grim portents** and an **impending doom**.
- **Danger:** a threat within a front, with its own type, impulse and moves.
- **Grim portent:** a step on a danger's path. Each danger has a clock with one segment per portent; a full clock means the danger has run its course.
- **Impending doom:** what happens if a front runs its course.

## Content

- **Pack (system pack):** a folder of YAML defining a rules system: stats, moves, classes, gear, tags, GM moves. Dungeon World is the first.
- **Scenario (scenario pack):** a folder of YAML defining one adventure: locations, NPCs, fronts, items, clues, secrets, start and end conditions. It declares which system pack it uses.
- **Location:** a node in the scenario graph, with exits, tags, description seeds, hazards, obstacles and NPCs present.
- **Obstacle:** something in a location's way, optionally **blocking** one of its exits. A move made against it (`target: obstacle`, like Bend Bars) clears it with `clear_obstacle`; once cleared it is gone for good.
- **Remains:** what a dead NPC becomes: a feature of the location where they died. Never a person, a target or a threat.
- **Hostile:** an NPC with `attitude: hostile`. While alive in the player character's location, they trigger the danger gate.
- **NPC profile:** an NPC's stat block plus role-play data: drive, voice, attitude, knowledge, secrets, and its own GM moves.
- **Condition:** a check against the state, written in YAML like an effect (`secret_revealed`, `pc_at`, `npc_dead`, `all`/`any`/`not`, …). Endings, scenario moves and GM moves use conditions.
- **Ending:** a way the scenario can end, with the condition that ends it. After every turn the engine checks the endings in order; the first that holds ends the story.
- **Scenario move:** a move defined by a scenario rather than the system pack, available only while its `requires` condition holds (`Search the cache` only in the cache).
- **Secret:** a fact that is hidden until the engine reveals it through a `reveal_secret` effect. Unrevealed secrets never appear in an AI prompt.
- **Entity graph (ontology):** the typed entities and relations of scenario and world state (`NPC knows Secret`, `Location connects Location`). It is the structured source of facts for prompts.

## Engine

- **Engine:** the deterministic core that owns all state and rules.
- **Event:** an immutable record of one state change. The **event log** is the source of truth.
- **Snapshot:** cached state at a point in the log, used for fast loading.
- **Seeded RNG:** dice randomness from a seed stored in the log, so replays are exact.
- **Turn controller:** runs one turn: input → classify → confirm → resolve → narrate → display. A turn includes the GM moves it calls for, the dying move if the player character drops to 0 HP, and the ending check, and is recorded whole or not at all. Without AI it is the `Session`, driven by slash commands; the `Table` puts the AI in front of it, turning free text into a confirmed slash command and narrating the result.

## AI

- **LLMProvider:** the interface to a language model backend. Implementations: Ollama, OpenAI-compatible, Fake (for tests).
  Each task can have its own provider, and so its own model.
- **AI tasks:** the four jobs the AI may do.
  - **Classify:** player text → `{kind, move_id?, stat?, target?, then?}`. `then` is the place a move goes on to if it doesn't miss (`/move … then <place>`); it is kept only if the player's words name the place.
  - **Narrate:** prose for an outcome the engine has already decided, told from the **story**: the turn's events without numbers or rules.
  - **NPC voice:** dialogue in character, based on the NPC profile. `/say [@someone] <words>` goes straight to it.
  - **GM answer:** an out-of-character answer to the player (`/gm <question>`, or free text classified `ooc`). It may talk about the rules; it never changes the game.
- **Quoted speech:** speech in quotes in the player's words. It is left out of what is classified, so one input can be an action and speech; a line that is only a quote is said to the only person here.
- **Intent kind:** `move | travel | talk | look | inventory | ooc | unclear`.
- **ContextBuilder:** assembles the small factual context for each AI call from state, the entity graph and recent events. It is where vector retrieval will plug in later.
- **Fact check:** a post-check that flags narration naming an NPC, place, obstacle or item of the scenario or pack that the prompt never gave the model, or talking about the rules (numbers, dice, HP, damage, stats). Streamed text that fails is **retracted**; the model is asked once more, and a second failure leaves the template alone. Names the scenario has never heard of are beyond it.
- **Retract:** the marker in a streamed narration that throws away the text streamed so far.
- **Template fallback:** engine-generated text used when the AI is unavailable or fails.
- **Evals:** the offline evaluation suite that scores models on the three AI tasks. It is used to pick models; it is not part of unit tests.
  - **Eval case:** one question for a model: a **scene** (a quick-start character in a new game plus the slash commands that get somewhere), what the player says, and what a good answer looks like.
  - **Check:** one deterministic test of an answer (`intent`, `fact_check`, `no_rules_talk`, `length`, …). A case passes when all its checks pass; no model judges another.
  - **Quality bar:** the share of cases each task must pass, and the time budget, that a model must meet to be chosen.

## Interface

- **Slash command:** an explicit command (`/go`, `/move`, `/sheet`, …) that bypasses classify. `/say` and `/gm` still need the AI to answer.
- **Confirmation strip:** the TUI prompt where the player accepts or cancels the suggested move.
- **Story log:** the main TUI pane showing narration, dialogue and roll results.
- **Choice modal:** the TUI dialog where the player picks the options a move offers (`choose_n`).
- **Save:** the event log written to disk after every turn. Continuing a save replays it into a new `Session`; reaching an ending removes it.
