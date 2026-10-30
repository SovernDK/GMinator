"""The small factual context each AI call works from, built from the state and the entity
graph. It is where vector retrieval will plug in later.

Everything here comes through the entity graph, which leaves unrevealed secrets out; so no
prompt can carry a secret the engine has not revealed.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from gminator.core.conditions import is_dead
from gminator.core.state import GameState
from gminator.packs.models import Pack
from gminator.scenario.graph import build_graph
from gminator.scenario.models import Scenario

RECENT_FACTS = 5
NARRATION_SENTENCES = 2


@dataclass(frozen=True)
class Context:
    location: str
    description: str
    exits: list[str]
    present: list[str]
    pc: str
    secrets: list[str]
    recent: list[str]
    narration: str
    in_the_way: list[str] = field(default_factory=list)
    remains: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"Location: {self.location}"]
        if self.description:
            lines.append(self.description)
        lines.append(f"Ways on: {', '.join(self.exits) or 'none'}")
        if self.in_the_way:
            lines.append(f"In the way: {'; '.join(self.in_the_way)}")
        lines.append(f"Also here: {'; '.join(self.present) or 'no one'}")
        if self.remains:
            lines.append(f"Remains: {', '.join(self.remains)}")
        lines.append(f"Player character: {self.pc}")
        if self.secrets:
            lines += ["Known secrets:", *(f"- {secret}" for secret in self.secrets)]
        if self.recent:
            lines += ["Recent events:", *(f"- {fact}" for fact in self.recent)]
        if self.narration:
            lines.append(f"Last narration: {self.narration}")
        return "\n".join(lines)


class ContextBuilder:
    def __init__(self, scenario: Scenario, rules: Pack, pc_id: str) -> None:
        self.scenario = scenario
        self.rules = rules
        self.pc_id = pc_id

    def build(self, state: GameState, recent: Sequence[str] = (), narration: str = "") -> Context:
        graph = build_graph(self.scenario, state, self.pc_id)
        pc = state.characters[self.pc_id]
        assert pc.location is not None
        location = self.scenario.locations[pc.location]

        present, remains = [], []
        for entity in graph.subjects("at", location.id):
            if entity.id == self.pc_id:
                continue
            if is_dead(state.characters[entity.id]):
                remains.append(f"the body of {entity.name}")
                continue
            npc = self.scenario.npcs.get(entity.id)
            name = entity.name
            present.append(f"{name}: {npc.description}" if npc and npc.description else name)

        in_the_way = []
        for obstacle in location.obstacles:
            if obstacle.id in state.cleared:
                continue
            text = (
                f"{obstacle.name}: {obstacle.description}"
                if obstacle.description
                else obstacle.name
            )
            if obstacle.blocks is not None:
                text += f" (blocks the way to {self.scenario.locations[obstacle.blocks].name})"
            in_the_way.append(text)

        return Context(
            location=location.name,
            description=location.description,
            exits=[e.name for e in graph.objects(location.id, "connects")],
            in_the_way=in_the_way,
            present=present,
            remains=remains,
            pc=self._describe_pc(state),
            secrets=[e.name for e in graph.entities("secret")],
            recent=list(recent)[-RECENT_FACTS:],
            narration=" ".join(sentences(narration)[-NARRATION_SENTENCES:]),
        )

    def profile(self, state: GameState, npc_id: str) -> str:
        """Who an NPC is, for voicing them: their role-play data and the revealed secrets
        they know."""
        npc = self.scenario.npcs[npc_id]
        graph = build_graph(self.scenario, state, self.pc_id)
        lines = [f"Name: {npc.name}"]
        for label, value in [
            ("Description", npc.description),
            ("Drive", npc.drive),
            ("Voice", npc.voice),
            ("Attitude", npc.attitude),
        ]:
            if value:
                lines.append(f"{label}: {value}")
        known = [secret.name for secret in graph.objects(npc_id, "knows")]
        if known:
            lines += ["Knows:", *(f"- {secret}" for secret in known)]
        return "\n".join(lines)

    def _describe_pc(self, state: GameState) -> str:
        pc = state.characters[self.pc_id]
        cls = self.rules.classes.get(pc.class_id) if pc.class_id else None
        parts = [f"{pc.name}, {cls.name}" if cls else pc.name, _condition(pc.hp, pc.max_hp)]
        if pc.tags:
            parts.append(f"tags: {', '.join(pc.tags)}")
        items = [
            item.name if (item := self.rules.items.get(p.item_id)) else p.item_id
            for p in pc.inventory
        ]
        if items:
            parts.append(f"carrying: {', '.join(items)}")
        return "; ".join(parts)


def _condition(hp: int, max_hp: int) -> str:
    """How hurt a character is, in words: the numbers are the engine's to show."""
    if hp >= max_hp:
        return "unhurt"
    if hp == 0:
        return "down"
    return "wounded" if hp * 2 > max_hp else "badly hurt"


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
