"""The GM move selector. The engine, not the AI, picks every GM move.

The candidates are the scenario's danger moves whose conditions hold, then the pack's general
GM moves, all of the severity asked for. One is picked with a recorded die, so replays pick
the same move.
"""

from dataclasses import dataclass
from typing import Literal

from gminator.core.conditions import holds
from gminator.core.game import Game
from gminator.core.moves import Decider, Resolution, make_gm_move
from gminator.core.state import GameState
from gminator.packs.models import GmMoveDefinition, Pack
from gminator.scenario.models import Scenario

Severity = Literal["soft", "hard"]


@dataclass(frozen=True)
class Candidate:
    gm_move: GmMoveDefinition
    source_id: str | None
    """The NPC behind the move, if any; the move's effects refer to it as `target`."""


def gm_move_candidates(
    scenario: Scenario, pack: Pack, state: GameState, pc_id: str, severity: Severity
) -> list[Candidate]:
    sources = [(gm_move, danger.npc) for danger in scenario.dangers() for gm_move in danger.moves]
    sources += [(gm_move, None) for gm_move in pack.gm_moves.values()]
    return [
        Candidate(gm_move, source_id)
        for gm_move, source_id in sources
        if gm_move.severity == severity
        and (gm_move.requires is None or holds(gm_move.requires, state, pc_id))
    ]


def make_scenario_gm_move(
    game: Game,
    pack: Pack,
    scenario: Scenario,
    pc_id: str,
    severity: Severity,
    decider: Decider,
) -> Resolution | None:
    candidates = gm_move_candidates(scenario, pack, game.state, pc_id, severity)
    if not candidates:
        return None
    index = game.roll(f"d{len(candidates)}") - 1 if len(candidates) > 1 else 0
    chosen = candidates[index]
    return make_gm_move(game, pack, chosen.gm_move, pc_id, decider, target_id=chosen.source_id)
