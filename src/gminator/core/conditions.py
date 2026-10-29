"""Checks a pack or scenario condition against the game state."""

from gminator.core.state import Character, GameState
from gminator.packs.models import (
    AllOf,
    AnyOf,
    ClockFull,
    Condition,
    Not,
    NpcDead,
    NpcHasTag,
    NpcWithPc,
    PcAt,
    PcHasTag,
    SecretRevealedIs,
)


def holds(condition: Condition, state: GameState, pc_id: str) -> bool:
    pc = state.characters[pc_id]
    match condition:
        case AllOf(all=conditions):
            return all(holds(c, state, pc_id) for c in conditions)
        case AnyOf(any=conditions):
            return any(holds(c, state, pc_id) for c in conditions)
        case Not(not_=inner):
            return not holds(inner, state, pc_id)
        case SecretRevealedIs(secret_revealed=secret_id):
            return secret_id in state.revealed
        case ClockFull(clock_full=clock_id):
            clock = state.clocks.get(clock_id)
            return clock is not None and clock.filled >= clock.segments
        case PcAt(pc_at=location_id):
            return pc.location == location_id
        case PcHasTag(pc_has_tag=tag):
            return tag in pc.tags
        case NpcHasTag(npc_has_tag=args):
            npc = state.characters.get(args.npc)
            return npc is not None and args.tag in npc.tags
        case NpcDead(npc_dead=npc_id):
            npc = state.characters.get(npc_id)
            return npc is not None and is_dead(npc)
        case NpcWithPc(npc_with_pc=npc_id):
            npc = state.characters.get(npc_id)
            return npc is not None and not is_dead(npc) and npc.location == pc.location
    raise AssertionError(f"unhandled condition {condition!r}")


def is_dead(character: Character) -> bool:
    return character.hp == 0 or "dead" in character.tags
