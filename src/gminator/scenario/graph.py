"""The entity graph: typed entities and the relations between them, built from the scenario
and the current state. It is the structured source of facts for prompts.

Unrevealed secrets are left out entirely, so nothing built from the graph can leak them.
"""

from dataclasses import dataclass
from typing import Literal

from gminator.core.state import GameState
from gminator.scenario.models import Scenario

Kind = Literal["location", "pc", "npc", "secret", "front", "danger"]
Predicate = Literal["connects", "at", "knows", "part_of", "drives"]


@dataclass(frozen=True)
class Entity:
    id: str
    kind: Kind
    name: str


@dataclass(frozen=True)
class Relation:
    subject: str
    predicate: Predicate
    object: str


class EntityGraph:
    def __init__(self, entities: list[Entity], relations: list[Relation]) -> None:
        self._entities = {entity.id: entity for entity in entities}
        self._relations = relations

    def entity(self, entity_id: str) -> Entity | None:
        return self._entities.get(entity_id)

    def entities(self, kind: Kind) -> list[Entity]:
        return [entity for entity in self._entities.values() if entity.kind == kind]

    def objects(self, subject: str, predicate: Predicate) -> list[Entity]:
        """What `subject` relates to, e.g. the locations a location `connects` to."""
        return [
            self._entities[r.object]
            for r in self._relations
            if r.subject == subject and r.predicate == predicate
        ]

    def subjects(self, predicate: Predicate, object_: str) -> list[Entity]:
        """What relates to `object_`, e.g. the characters `at` a location."""
        return [
            self._entities[r.subject]
            for r in self._relations
            if r.predicate == predicate and r.object == object_
        ]


def build_graph(scenario: Scenario, state: GameState, pc_id: str) -> EntityGraph:
    entities: list[Entity] = []
    relations: list[Relation] = []

    for location in scenario.locations.values():
        entities.append(Entity(location.id, "location", location.name))
        relations += [Relation(location.id, "connects", exit_id) for exit_id in location.exits]

    for character_id, character in state.characters.items():
        kind: Kind = "pc" if character_id == pc_id else "npc"
        entities.append(Entity(character_id, kind, character.name))
        if character.location is not None:
            relations.append(Relation(character_id, "at", character.location))

    for secret_id in state.revealed:
        entities.append(Entity(secret_id, "secret", scenario.secrets[secret_id].text))
    for npc in scenario.npcs.values():
        relations += [
            Relation(npc.id, "knows", secret_id)
            for secret_id in npc.knows
            if secret_id in state.revealed
        ]

    for front in scenario.fronts.values():
        entities.append(Entity(front.id, "front", front.name))
        for danger in front.dangers:
            entities.append(Entity(danger.id, "danger", danger.name))
            relations.append(Relation(danger.id, "part_of", front.id))
            if danger.npc is not None:
                relations.append(Relation(danger.npc, "drives", danger.id))

    return EntityGraph(entities, relations)
