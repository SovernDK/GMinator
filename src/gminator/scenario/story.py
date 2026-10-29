"""How a scenario begins and how it ends."""

from gminator.core.conditions import holds
from gminator.core.events import CharacterCreated, CharacterMoved, ClockCreated, Event
from gminator.core.state import GameState
from gminator.scenario.models import Ending, Scenario


def opening_events(scenario: Scenario, pc_id: str) -> list[Event]:
    """Places the NPCs, starts a clock for each danger and puts the PC at the start."""
    events: list[Event] = []
    for npc in scenario.npcs.values():
        events.append(
            CharacterCreated(
                character_id=npc.id,
                name=npc.name,
                stats={},
                max_hp=npc.max_hp,
                damage=npc.damage,
                armor=npc.armor,
            )
        )
        events.append(CharacterMoved(character_id=npc.id, location_id=npc.location))
    for danger in scenario.dangers():
        events.append(
            ClockCreated(clock_id=danger.id, label=danger.name, segments=len(danger.portents))
        )
    events.append(CharacterMoved(character_id=pc_id, location_id=scenario.manifest.start))
    return events


def reached_ending(scenario: Scenario, state: GameState, pc_id: str) -> Ending | None:
    """The first ending, in scenario order, whose condition holds."""
    return next((e for e in scenario.endings if holds(e.when, state, pc_id)), None)
