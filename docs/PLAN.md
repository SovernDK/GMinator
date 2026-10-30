# GMinator — Big Picture Plan

A single-player, terminal-based tabletop RPG built on the **Powered by the Apocalypse (PbtA)** engine, shipping with **Dungeon World** as its first rules pack. A small local AI narrates and voices NPCs; a deterministic engine owns every rule and every fact.

Vocabulary is defined in [CONTEXT.md](CONTEXT.md). Key decisions are recorded in [adr/](adr/).

---

## 1. Principles

1. **The engine is the only source of truth.** Dice, stats, outcome bands, HP, XP, inventory, clocks, NPC state and GM move selection all live in code and data. The AI never mutates state. ([ADR-0001](adr/0001-engine-owns-state.md))
2. **The AI does three narrow jobs only:** classify player intent, narrate engine-decided outcomes, voice NPCs. Narrow prompts + schema-forced output are what let a 3–4B model work.
3. **Fully playable without AI.** Templated text is a permanent fallback (Ollama down, model fails twice) and a test/debug mode.
4. **Rules are data.** The code is a generic PbtA core; Dungeon World is a YAML pack. Anyone can author a new move, class, system or setting without touching Python. ([ADR-0003](adr/0003-rules-as-yaml-packs.md))
5. **Everything is an event.** Event-sourced state with seeded RNG gives saves, replays, undo and debuggable transcripts from day one. ([ADR-0002](adr/0002-event-sourcing.md))
6. **Small model, CPU-first.** Target: 8 GB RAM, CPU only, 3–4B model. Develop against the weakest supported model. ([ADR-0004](adr/0004-llm-provider-and-small-models.md))
7. **Test first.** Every milestone is built TDD: tests, then implementation.

---

## 2. MVP Scope

### In
| Area | Scope |
|---|---|
| Players | One player-controlled PC |
| Session | One hand-written one-shot scenario (~45–60 min) |
| Rules core | 2d6 + stat, bands 10+ / 7–9 / 6-, moves, characters, HP/harm, armor, damage, clocks, tags, XP on miss |
| DW pack | All basic moves (Hack & Slash, Volley, Defy Danger, Defend, Spout Lore, Discern Realities, Parley, Aid/Interfere), Last Breath, Make Camp; classes **Fighter** and **Thief**; gear, tags |
| Packs | YAML authoring, Pydantic validation with file/line errors, exported JSON Schema for editor autocomplete |
| Expressions | Lark-based mini-language: dice, stat/property refs, `+ - *`, `min`/`max`, comparisons. No `eval`. |
| AI | `LLMProvider` (Ollama default, OpenAI-compatible, fake); intent classification, narration, NPC voice; schema-forced JSON; streaming narration |
| Context | Typed entity–relation graph + recent events via `ContextBuilder`; secret gating; fact-check with one regeneration then template fallback |
| Input | Free text → AI suggests move → player confirms; slash commands bypass AI |
| UI | Textual TUI: story log, character sheet + clocks sidebar, input with confirmation strip, modals for choices, title screen, DW character creation |
| Persistence | Event log + snapshots; save / load / replay |
| Language | English (all player-facing engine strings externalised) |

### Out (planned later)
- AI-controlled companions; hot-seat multiplayer (state already models a *list* of characters)
- Open sandbox / long campaigns; procedural dungeons
- AI-generated scenarios, built by structured writing from content tables with optional user-supplied characters/locations
- Vector memory (event log, dialogue, lore) behind `ContextBuilder` ([ADR-0005](adr/0005-ontology-now-vectors-later.md))
- Python plugin hooks for moves that can't be expressed as data (designed for, not built)
- Spellcasting classes, bonds, alignment, remaining DW classes
- Dungeon World rules left out of the M2 pack:
  - Bonds: Aid or Interfere rolls +0 until bonds exist (DW rolls +Bond)
  - Load and weight limits
  - Weapon damage bonuses (`+1 damage`) and `piercing`
  - Armor stacking: only shields should stack; for now all carried armor adds up
  - The `precise` tag (Hack and Slash rolls +DEX with a precise weapon)
  - Passive class moves: Armored, Signature Weapon (Fighter); Poisoner, Flexible Morals (Thief)
  - Backstab's option to deal damage without rolling
  - Levelling up at Make Camp
- Left out of M3 (the no-AI game), for the narrator or later milestones:
  - Questions from Discern Realities and Spout Lore are recorded but get no answers until the narrator (M4)
  - NPCs act only through GM moves; there is no NPC turn or NPC-initiated movement beyond `move_to` effects
  - Character creation in the CLI is a quick start (scores in stat order, first gear options); real creation is M6 (done in the TUI; `--plain` keeps the quick start)
  - Save and resume from the command line (the event log already saves and replays); done in M6 for the TUI
- Left out of M4 (the AI layer), for the evals or later milestones:
  - The fact check catches scenario and pack names only; names the model invents outright pass
  - Discern Realities and Spout Lore questions still get no answers
  - Narration quality (numbers repeated from the facts, odd move choices) is for the M5 evals, as are per-task models and settings
- Left out of M5 (the evals), for later:
  - The quality bar is set but not met. `granite4.1:3b` is the model for every task for now; it fails the bar on classify (56% of cases against 80%) and on turn time (10.2 s against 10 s). Prompt work and other 3–4B models are left for later ([evals/README.md](../evals/README.md#results))
  - `qwen3.5:2b` (nvfp4, on Ollama 0.40.2) timed out on schema-forced classify and has no valid result
  - Times were measured on an Apple M1 GPU, not on the CPU-only 8 GB reference machine
  - Per-task settings other than the model (temperature, sentence caps); a config file for per-task models (flags only for now)
  - Scoring is deterministic only; there is no model-as-judge for prose quality
  - The CLI runs without AI unless `--provider` is given; first-run detection of Ollama is M7
- Left out of M6 (the TUI), for later:
  - The confirmation strip accepts or cancels; there is no `[Tab] other move` to pick a different move from it (type the slash command instead)
  - One save slot; the game saves after every turn and drops the save at an ending. No save list, undo or replay view
  - The story log is not restored on resume: a resumed game opens on `/look`, and the narrator starts without the last session's recent events
  - Character creation has no look, alignment, bonds or race choices (none are in the M2 pack)
  - Not yet played end to end on the CPU-only reference machine with a model
- Embedded inference backend (llama.cpp), standalone binaries
- Other languages

---

## 3. Architecture

```
            ┌───────────────────────── TUI (Textual) ─────────────────────────┐
 player ──▶ │ input · confirmation strip · story log · sheet/clocks · modals │
            └───────────────┬─────────────────────────────────▲──────────────┘
                            │ player text / commands          │ events + streamed prose
                            ▼                                 │
                 ┌────────────────────┐   intent?   ┌─────────┴──────────┐
                 │   Turn controller  │ ──────────▶ │   AI layer         │
                 │  (engine, pure)    │ ◀────────── │ classify / narrate │
                 │                    │  proposal   │ / npc voice        │
                 │ moves · effects ·  │             │ ContextBuilder     │
                 │ expr · GM selector │ ── facts ─▶ │ fact check         │
                 └─────────┬──────────┘             └─────────┬──────────┘
                           │ events                           │
                           ▼                                  ▼
                 ┌────────────────────┐             ┌────────────────────┐
                 │ Event log + state  │             │ LLMProvider        │
                 │ (seeded RNG)       │             │ Ollama · OpenAI-   │
                 └─────────┬──────────┘             │ compat · Fake      │
                           │                        └────────────────────┘
                           ▼
       packs/ (system rules, YAML)   scenarios/ (scenario data, YAML)
```

### Turn loop
1. Player types text (or a slash command, which skips step 2).
2. **Classify:** AI returns `{kind, move_id?, stat?, target?}`, where `kind ∈ move | travel | talk | look | inventory | ooc | unclear`, choosing only from options the engine offers right now.
3. **Confirm:** the TUI shows e.g. `Defy Danger +DEX? [Enter] roll · [Tab] other move · [Esc] cancel`.
4. **Resolve:** the engine rolls, picks the band, and applies the effects. On a miss or a lull it picks a GM move from the scenario's fronts, dangers and GM moves. It emits events.
5. **Narrate:** `ContextBuilder` assembles a small, factual prompt, and the AI streams 2–4 sentences. The fact check flags named items or NPCs that don't exist in state; on a failure it regenerates once, then falls back to the template.
6. **Display:** mechanical results appear as separate UI elements (`−4 HP`, `+1 XP`, `Clock 2/4`). Prose is flavour; the panel is the truth.

### AI context per call
Current location and its tags, NPCs present, PC condition, the last 3–5 events as templated facts, and 1–2 lines of previous narration. Unrevealed secrets are **never** included. The AI never summarises its own output, so prompt size stays constant over a session.

### Moves as data (sketch)
```yaml
id: hack_and_slash
trigger: "When you attack an enemy in melee"
roll: stat.str
outcomes:
  strong:
    - deal_damage: { target: target, amount: "class.damage" }
    - choose_n:
        n: 1
        options:
          - { label: "Deal +1d6 damage", effects: [ { deal_damage: { target: target, amount: "d6" } } ] }
          - { label: "Avoid the counterattack", effects: [] }
  partial:
    - deal_damage: { target: target, amount: "class.damage" }
    - take_damage: { amount: "target.damage" }
  miss:
    - mark_xp: 1
    - gm_move: hard
```
The effects built in M2 are `deal_damage`, `take_damage`, `heal`, `choose_n`, `ask_questions`, `gain_hold`, `spend_hold`, `add_tag`, `remove_tag`, `advance_clock`, `gm_move`, `mark_xp`, `add_forward` and `use_item`. `heal`, `add_forward` and `use_item` were added because Dungeon World needs them (Make Camp, Aid or Interfere, ammo and rations). `reveal_secret` and `move_to` need scenario data and come with M3. Extend the set only when a pack needs it.

---

## 4. Milestones

Every milestone is **test-first** and ends in something that can be demoed.

| # | Milestone | Contents | Exit criteria |
|---|---|---|---|
| **M0** | Skeleton | `uv` project, pytest, ruff, CI, repo layout | `uv run pytest` green in CI |
| **M1** | Core engine | Dice, Lark expression language, event types, seeded RNG, state built by replaying events, save/load/replay | A recorded event log replays to an identical state |
| **M2** | Pack system + DW pack | Pydantic pack models, YAML loader with file/line errors, JSON Schema export, effect set, DW basic moves + Last Breath + Make Camp, Fighter, Thief, gear, tags | A test resolves every DW basic move from YAML; a new move added in YAML alone works |
| **M3** | Scenario + GM | Scenario model and entity graph, fronts and clocks, GM move selector, NPC stat blocks, end conditions, `reveal_secret` and `move_to` effects, the *Rats Under the Inn* scenario; slash commands + templated text | The scenario plays to every ending with **no AI** |
| **M4** | AI layer | `LLMProvider` (Ollama, OpenAI-compatible, fake), classify/narrate/NPC tasks with schema output, `ContextBuilder`, secret gating, fact check + regeneration + fallback, streaming | A full playthrough with the fake provider; manual play on Ollama |
| **M5** | Evaluations | Harness, ~30 cases per task, scoring, model comparison (`granite4.1:3b`, `qwen3.5:2b`, others in the 2–4B range), per-task model config | A model chosen; the quality bar set and met (bar set, not yet met; see §2 Out) |
| **M6** | TUI | Textual layout, confirmation strip, modals, title screen, DW character creation, streaming display | The scenario plays end to end in the TUI (done: `tests/tui/test_app.py`) |
| **M7** | Ship | First-run Ollama check and model pull, `uvx` packaging, pack/scenario authoring guide | Shipping gate passes (see below) |

### Definition of done — two gates, in order
1. **Gameplay gate (M0–M6):** on the reference machine (CPU only, 8 GB RAM), a player creates a Fighter or Thief, plays the scenario to any ending, and saves, quits and resumes. The AI never changes state, the evals score above the bar, a turn is under 10 s with first text under 2 s, and a pack author can add a move with YAML only.
2. **Shipping gate (M7), tested only after gate 1 passes:** a fresh machine installs with `uvx gminator`, the model is pulled on first run, and the authoring guide is enough to write a new move and a small scenario.

---

## 5. MVP Scenario — *Rats Under the Inn* (draft, to be edited)

The basement under a village inn is overrun by giant rats, and it breaks through into a cave system.

- **Truth:** the innkeeper's business partner is a **wererat smuggler** who moves contraband through the caves using a half-trained rat swarm. The swarm is slipping out of his control.
- **Front: The Undercellar**
  - *Danger 1: the Smuggler* (ambitious organisation / wererat). Portents: deliveries go missing → he silences a witness → he floods the inn with rats to cover his escape.
  - *Danger 2: the Swarm* (horde). Portents: rats in the pantry → a child bitten → the swarm turns on its master → it boils up into the village.
  - *Impending doom:* the inn is overrun and the village is infested.
- **Locations (5–7):** inn common room · basement · broken wall / tunnel · smugglers' cache · flooded gallery · rat nest · the hidden exit to the river.
- **NPCs (4–5):** innkeeper (ally with a secret), the partner/wererat (ambiguous → villain), a frightened stable hand (witness), giant rats and the swarm (monsters), optionally a rival smuggler.
- **Endings:** expose him, kill him, strike a deal, flee, or the swarm wins.
- **Design goal:** every basic move gets a natural chance to trigger at least once.

---

## 6. Repository Layout

```
src/gminator/
  core/          dice, expr (lark), effects, moves, characters, clocks, events, state
  packs/         pydantic models, yaml loader, schema export
  scenario/      scenario model, entity graph, GM move selector
  ai/            provider + backends, tasks (classify/narrate/npc), context builder, fact check
  tui/           textual app
  persistence/   event log, saves
packs/dungeon-world/   DW rules pack (CC-BY 3.0 notice inside)
scenarios/rats-under-the-inn/
schemas/         exported JSON Schemas
evals/           datasets + harness
tests/
docs/            PLAN.md, CONTEXT.md, adr/
```

## 7. Licensing
Code: **MIT**. `packs/dungeon-world/`: **CC-BY 3.0**, with attribution to the Dungeon World SRD (Sage LaTorra & Adam Koebel). Each pack carries its own licence file. ([ADR-0006](adr/0006-licensing.md))
