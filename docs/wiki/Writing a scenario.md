# Writing a scenario

A scenario is a folder of YAML that defines one adventure on a system pack: where things are, who is there, what is hidden, what threatens, and how it ends. `scenarios/rats-under-the-inn/` is the worked example. The models are in `src/gminator/scenario/models.py`; the loader in `scenario/loader.py`.

## Layout

```
scenarios/my-scenario/
  scenario.yaml     the manifest (required)
  locations.yaml    the map (required)
  endings.yaml      how it ends (required)
  npcs.yaml
  secrets.yaml
  fronts.yaml       fronts, dangers and their GM moves
  tags.yaml         tags of the scenario's own, added to the pack's
  moves/*.yaml      scenario moves
  LICENSE.md
```

Locations, NPCs, secrets, fronts, dangers and obstacles share **one id space**: two of them can't have the same id.

## Manifest — `scenario.yaml`

```yaml
id: rats-under-the-inn
name: Rats Under the Inn
version: 0.1.0
license: CC-BY-4.0
attribution: Rats Under the Inn, written for GMinator by Damian Kwolek.
system: dungeon-world        # must match the pack's id
start: common_room           # where the player character begins
intro: Rain hammers the shutters of the Drowned Rat. …
```

## Locations and obstacles

```yaml
- id: gallery
  name: The flooded gallery
  description: Black water to the knee. …
  exits: [broken_wall, nest, river_exit, culvert]
  obstacles:
    - id: rusted_grate
      name: The rusted grate
      description: Thick iron bars across a side culvert.
      blocks: culvert        # optional; must be one of this location's exits
```

Exits are one-way: list the way back on the other location too. An obstacle that `blocks` an exit stops `/go` there until a move made against it (`target: obstacle`, like Bend Bars, Lift Gates) runs `clear_obstacle`. Cleared obstacles stay cleared.

## NPCs

```yaml
- id: corwin
  name: Corwin
  description: Maud's business partner, thin and well dressed, with very small teeth.
  location: common_room
  max_hp: 12
  armor: 1
  damage: d8                 # available to GM moves as target.damage; no references
  drive: Get rich, stay hidden, and get out before the swarm turns.
  voice: Soft, amused, always one joke away from a threat.
  attitude: ambiguous        # free text; only `hostile` has a rule: the danger gate
  knows: [inn_smuggling, corwin_is_wererat]
```

An NPC can have GM moves of its own (Dungeon World's monster moves), written like any [GM move](Writing%20a%20system%20pack.md#general-gm-moves--gm_movesyaml). They are candidates only while the NPC is alive and with the player character, and refer to the NPC as `target`. A **hostile** NPC's moves come before any other: when the player misses against the rats, the rats bite.

```yaml
  attitude: hostile
  moves:
    - id: rats_bite
      name: The rats bite
      severity: hard
      text: A rat darts in under your guard and sinks its teeth into your leg.
      effects:
        - take_damage: {amount: target.damage}
```

GM move ids must be unique across the pack, the dangers and the NPCs.

`description`, `drive`, `voice`, `attitude` and the *revealed* secrets the NPC `knows` make up the profile the AI voices them from. A dead NPC becomes remains in their location: no longer a target, a threat or someone to talk to.

## Secrets

```yaml
- id: corwin_is_wererat
  text: Corwin is a wererat, and the swarm answers to him.
```

A secret stays out of every prompt until a `reveal_secret` effect reveals it ([ADR-0005](../adr/0005-ontology-now-vectors-later.md)). Put the facts the player must earn here, not in descriptions.

## Fronts and dangers

```yaml
- id: undercellar
  name: The Undercellar
  impending_doom: The inn is overrun, and the village is infested.
  dangers:
    - id: smuggler           # also the id of the danger's clock
      name: Corwin's racket
      type: ambitious organisation (wererat)
      impulse: to grow rich and stay hidden
      npc: corwin            # optional; its GM moves can use target.*
      portents:              # one clock segment each, in order
        - A delivery goes missing, and Corwin is out of sorts.
        - Corwin silences a witness.
      moves:                 # GM moves, as in a pack's gm_moves.yaml
        - id: corwin_lashes_out
          name: Corwin lashes out
          severity: hard
          text: Corwin's hand snaps out, and his nails are claws.
          requires: {npc_with_pc: corwin}
          effects:
            - take_damage: {amount: target.damage}
```

At the start of a game each danger gets a clock with one segment per portent. `advance_clock: {clock: smuggler}` fills it, and each newly filled segment shows its portent. Use `clock_full` in an ending for the impending doom.

## Endings

```yaml
- id: corwin_killed
  title: Corwin Is Dead
  text: Corwin dies with a rat's snarl on a man's face. …
  when: {npc_dead: corwin}
```

After every turn the engine checks the endings **in order** and the first that holds ends the game. Put death first (`pc_has_tag: dead`, which DW's Last Breath sets) so it wins over anything else that turn. Conditions are listed in the [reference](Effects%20and%20conditions%20reference.md#conditions).

## Scenario moves

A move of the scenario's own, written like a [pack move](Writing%20a%20system%20pack.md#moves--movesyaml) plus a `requires` condition. It can only be made while the condition holds, and its id must not clash with a pack move.

```yaml
id: search_the_cache
name: Search the cache
category: special
trigger: When you go through the smugglers' crates and papers
requires: {pc_at: cache}
roll: stat.int
outcomes:
  strong:
    effects:
      - reveal_secret: corwin_is_wererat
      - reveal_secret: inn_smuggling
  partial:
    effects:
      - reveal_secret: corwin_is_wererat
      - gm_move: soft
  miss:
    effects:
      - gm_move: hard
```

Scenario moves are how the player uncovers secrets and reaches endings that hang on tags (Rats uses `denounce_corwin` to tag Maud `convinced`, and `strike_a_deal` to tag Corwin `bargained`).

## Testing a scenario

`tests/test_rats_under_the_inn.py` is the model to follow:

- **every ending has a play**: a list of slash commands, with a seed, that reaches it;
- **every location can be reached** from the start;
- the scenario is for the right system and carries a licence.

`tests/tiny_cellar.py` builds a two-room scenario in a temporary folder, for tests that need a scenario but not Rats.
