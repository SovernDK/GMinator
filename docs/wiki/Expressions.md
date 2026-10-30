# Expression language

Pack and scenario files use small formulas wherever a number is needed: a roll modifier, damage, healing, max HP. They are parsed by [Lark](https://github.com/lark-parser/lark) in `src/gminator/core/expr.py` and never run with Python `eval`, because packs come from third parties ([ADR-0003](../adr/0003-rules-as-yaml-packs.md)).

A plain integer is also accepted (`amount: 1`).

## Syntax

| Form | Example | Meaning |
|---|---|---|
| Integer | `3` | |
| Dice | `d6`, `2d6` | roll and sum |
| Best of | `b[2d8]` | roll, keep the highest |
| Worst of | `w[2d8]` | roll, keep the lowest |
| Reference | `stat.str`, `self.damage` | a value from the game; see below |
| Arithmetic | `d6 + 1`, `2 * stat.con`, `self.max_hp / 2` | `/` rounds down; division by 0 is an error |
| Negation | `-stat.cha` | |
| Functions | `min(d6, 3)`, `max(1, d4 - 1)` | `min` and `max` only, one or more arguments |
| Comparison | `stat.str >= 2` | `<`, `<=`, `>`, `>=`, `==`, `!=` |
| Grouping | `(d6 + 1) * 2` | |

## References

Which names an expression may use depends on where it is. The loader rejects any other name with `unknown reference`.

| Name | Where | Value |
|---|---|---|
| `stat.<stat>` | move rolls and effects, GM moves, `miss_effects`, class `max_hp` | the actor's modifier, e.g. `stat.dex` |
| `stat.chosen` | moves with `stat_options` | the modifier of the stat the player picked |
| `self.damage`, `self.armor`, `self.hp`, `self.max_hp`, `self.level` | moves, GM moves, `miss_effects` | the actor's |
| `target.damage`, `target.armor`, … | moves with `target: true`; GM moves of a danger with an `npc` | the target's (for a danger, the NPC behind it) |
| `score.<stat>` | class `max_hp` only | the raw score, e.g. `10 + score.con` |

Class and NPC `damage`, and the pack's `roll`, may not use references.

A reference whose value is itself an expression is evaluated in place. A Fighter's `self.damage` is `d10`, so `self.damage + d6` rolls a d10 and a d6. A reference that leads back to itself is an error.

## Errors

A bad expression fails when the pack loads, with the file and line:

```
packs/my-pack/moves/smash.yaml:9: outcomes.strong.effects.0.deal_damage.amount: unknown reference 'stat.chosen' (needs stat_options)
```
