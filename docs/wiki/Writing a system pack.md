# Writing a system pack

A system pack is a folder of YAML that defines a rules system: stats, the roll, moves, classes, gear, tags and GM moves. Dungeon World in `packs/dungeon-world/` is the worked example. No Python is needed: the Pydantic models in `src/gminator/packs/models.py` say what a pack may contain, and the loader checks it.

## Layout

```
packs/my-pack/
  pack.yaml         the manifest (required)
  LICENSE.md        the content licence (ADR-0006)
  tags.yaml         a list of tags
  gear.yaml         a list of items
  gm_moves.yaml     a list of general GM moves
  moves/*.yaml      one move per file
  classes/*.yaml    one class per file
```

Ids are lowercase `snake_case` (`hack_and_slash`); a pack's own id may also use hyphens (`dungeon-world`).

Start each file with a schema comment so the VS Code YAML extension gives autocomplete and errors as you type:

```yaml
# yaml-language-server: $schema=../../../schemas/move.schema.json
```

## The manifest — `pack.yaml`

```yaml
id: dungeon-world
name: Dungeon World
version: 0.1.0
license: CC-BY-3.0
attribution: Adapted from the Dungeon World SRD by Sage LaTorra and Adam Koebel, licensed under CC BY 3.0.
stats: [str, dex, con, int, wis, cha]
roll: 2d6                            # added to every rolled move's modifier
bands: {strong: 10, partial: 7}      # strong 10+, partial 7–9, miss below
modifiers:                           # score → modifier, ascending by up_to
  - {up_to: 3, modifier: -3}
  - {up_to: 8, modifier: -1}
  - {up_to: 12, modifier: 0}
  - {up_to: 18, modifier: 3}
score_array: [16, 15, 13, 12, 9, 8]  # one per stat, each used once at creation
miss_effects:                        # applied on every rolled miss
  - mark_xp: 1
dying_move: last_breath              # made when a player character reaches 0 HP
danger:                              # optional; see "The danger gate"
  move: defy_danger
  default_stat: dex
  stat_by_flag: {travel: dex}
  exempt: [combat]
```

## Moves — `moves/*.yaml`

```yaml
id: hack_and_slash
name: Hack and Slash
category: basic              # basic | special | class
trigger: When you attack an enemy in melee
flags: [combat]              # what kind of action it is; read by the danger gate
target: true                 # false (default) | true (a character here) | obstacle
roll: stat.str               # the modifier; the manifest's roll is added
outcomes:
  strong:
    text: You deal your damage to the enemy and avoid their attack.
    effects:
      - deal_damage: {amount: self.damage}
  partial:
    text: You deal your damage, and the enemy attacks you.
    effects:
      - deal_damage: {amount: self.damage}
      - take_damage: {amount: target.damage}
  miss:
    text: The GM makes a move.
    effects:
      - gm_move: hard
```

- A **rolled** move has `roll` and `outcomes` (all three bands). An **unrolled** move has neither, and puts its `effects` and `text` at the top level.
- `stat_options: [str, dex, …]` lets the player pick the stat; the roll then refers to `stat.chosen`.
- `target: obstacle` makes the move against a scenario obstacle, and lets it use `clear_obstacle`.
- A move spent later from hold (Defend, Trap Expert) is usually a second, unrolled move whose effects start with `spend_hold: {move: defend}`.
- `text` is the templated line shown with the outcome; the narrator gets the story, not this text.

The effects are listed in the [reference](Effects%20and%20conditions%20reference.md#effects); the formulas in the [expression language](Expressions.md).

### Which moves the player can make

- `basic` and `special` moves: always (except the `dying_move`, which only the engine makes).
- `class` moves: only if the character's class lists them.
- A move with `target: obstacle`: only where an uncleared obstacle is.

## The danger gate

If the manifest has a `danger` section, acting near a living NPC with `attitude: hostile` means acting despite danger ([ADR-0007](../adr/0007-engine-gates-danger.md)). Before any game-changing action, the engine makes `danger.move` first:

- the stat is `stat_by_flag` for the first of the action's flags that has one, else `default_stat`;
- an action with an `exempt` flag, or the gate move itself, is never gated;
- going through an exit carries the built-in flag `travel`;
- a miss stops the action.

The gate move must have `stat_options` that include every stat named here; the loader checks this.

## Classes — `classes/*.yaml`

```yaml
id: fighter
name: Fighter
damage: d10                  # an expression; available as self.damage
max_hp: 10 + score.con       # may use score.<stat> and stat.<stat>, no dice
moves: [bend_bars_lift_gates]
starting_gear: [dungeon_rations]
gear_choices:
  - label: Choose your defenses
    options:                 # each option is a list of item ids; n defaults to 1
      - [chainmail, adventuring_gear]
      - [scale_armor]
  - label: Choose two
    n: 2
    options:
      - [healing_potion, healing_potion]
      - [shield]
      - [antitoxin, dungeon_rations, poultices_and_herbs]
```

## Gear and tags

```yaml
# gear.yaml
- id: dungeon_rations
  name: Dungeon rations
  uses: 5                    # optional; use_item spends them
  tags: [ration]
- id: chainmail
  name: Chainmail
  armor: 1                   # added to the wearer's armor
  weight: 1
```

```yaml
# tags.yaml
- id: ration
  description: Food that keeps.
```

Every tag used by an item, a tag effect, or a condition must be defined in the pack's or the scenario's `tags.yaml`.

## General GM moves — `gm_moves.yaml`

```yaml
- id: show_signs
  name: Show signs of an approaching threat
  severity: soft             # soft | hard
  text: Something stirs at the edge of your senses. Trouble is coming.
  # requires: a condition    (optional) only picked while it holds
  # effects: [...]           (optional) applied to the player character
```

When a move calls for `gm_move: soft` or `hard`, the engine picks one GM move of that severity from the NPCs here, the scenario's dangers and these general ones. See [GM moves](Play%20layer.md#gm-moves).

A GM move's `text` is what the player is told happens, so write it as fiction. A miss outcome needs no text of its own: the GM move it brings tells it.

## Checking a pack

The loader reports every problem at once, each with its file and line: schema errors, duplicate ids, unknown moves, items, tags or stats, unknown expression references, `target` effects on a move without a target, `clear_obstacle` on a move not made against an obstacle, and a danger gate that can't roll its stats.

```
packs/my-pack/classes/fighter.yaml:7: moves.0: unknown move 'bend_bars'
```

Loading a pack in a test is the quickest check:

```python
from gminator.packs.loader import load_pack

load_pack(Path("packs/my-pack"))
```

`tests/packs/test_schema.py` also validates every content file against its schema.
