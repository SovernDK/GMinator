# Effects and conditions reference

Both are written as a YAML mapping with exactly one key, the effect's or condition's name. They are defined in `src/gminator/packs/models.py`, applied in `core/moves.py` and checked in `core/conditions.py`. The JSON Schemas in `schemas/` list them for editor autocomplete.

The effect set is a public API: extend it only when a pack needs something it can't express ([ADR-0003](../adr/0003-rules-as-yaml-packs.md)).

## Effects

`target` is `self` (the actor) or `target` (the character the move is made against). An effect that hits `target` needs a move with `target: true`, or a GM move from a danger with an `npc`.

| Effect | Arguments | What it does |
|---|---|---|
| `deal_damage` | `amount` ([expr](Expressions.md)), `target` = `target` | rolls `amount`, subtracts the victim's armor, takes that much HP |
| `take_damage` | `amount` | the same, to the actor |
| `heal` | `amount`, `target` = `self` | restores HP, up to max |
| `choose_n` | `n`, `options: [{label, effects}]` | the player picks `n` options; their effects apply in order |
| `ask_questions` | `n`, `questions: [str]` | the player picks `n` questions; they are recorded for the narrator |
| `gain_hold` | `amount` | hold on this move |
| `spend_hold` | `move`, `amount` = 1 | spends hold from `move`; fails if there is not enough |
| `add_tag` / `remove_tag` | `tag`, `target` = `self` | a tag must exist in the pack's or scenario's `tags.yaml` |
| `advance_clock` | `clock`, `amount` = 1 | in a scenario, clocks are the dangers' ids |
| `gm_move` | `soft` or `hard` | asks for a GM move; the [selector](Play%20layer.md#gm-moves) picks one after the action |
| `mark_xp` | a positive integer | XP for the actor |
| `add_forward` | `amount`, `target` = `self` | a bonus (or penalty) on the next roll |
| `use_item` | `tag` | uses one use of the first carried item with that tag and uses left; fails if there is none |
| `reveal_secret` | a secret id | the secret becomes known, and may now appear in prompts |
| `move_to` | `location`, `target` = `self` | moves a character |
| `clear_obstacle` | `target` | clears the obstacle the move is made against (`target: obstacle` moves only) |

```yaml
effects:
  - deal_damage: {amount: self.damage + d6}
  - take_damage: {amount: target.damage}
  - choose_n:
      n: 1
      options:
        - label: It takes a while
        - label: It makes an awful lot of noise
          effects:
            - gm_move: soft
  - reveal_secret: corwin_is_wererat
```

## Conditions

Used by endings (`when`), scenario moves and GM moves (`requires`).

| Condition | Argument | Holds when |
|---|---|---|
| `all` | a list of conditions | every one holds |
| `any` | a list of conditions | at least one holds |
| `not` | a condition | it doesn't hold |
| `secret_revealed` | a secret id | the secret has been revealed |
| `clock_full` | a clock id | the clock is full |
| `pc_at` | a location id | the player character is there |
| `pc_has_tag` | a tag | the player character has it |
| `npc_has_tag` | `{npc, tag}` | the NPC has it |
| `npc_dead` | an NPC id | the NPC is dead (0 HP or tagged `dead`) |
| `npc_with_pc` | an NPC id | the NPC is alive and in the player character's location |

```yaml
requires:
  all:
    - {not: {pc_at: common_room}}
    - {not: {npc_dead: swarm}}
```

Every id in a condition is checked when the scenario loads.
