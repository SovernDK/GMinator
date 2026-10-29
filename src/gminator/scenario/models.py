"""What a scenario pack may contain. Like the pack models, these are the single source of
truth for scenario files; the JSON Schemas in `schemas/` are generated from them."""

from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt

from gminator.packs.models import (
    Condition,
    Expr,
    GmMoveDefinition,
    Id,
    Move,
    Pack,
    PackId,
    Tag,
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScenarioManifest(_Model):
    id: PackId
    name: str
    version: str
    license: str
    attribution: str
    system: PackId = Field(description="The id of the system pack the scenario is played with")
    start: Id = Field(description="The location the player character starts in")
    intro: str = ""


class Location(_Model):
    id: Id
    name: str
    description: str = ""
    exits: list[Id] = Field(default=[], description="Locations reachable from here")


class Npc(_Model):
    """An NPC's stat block plus the role-play data the narrator works from."""

    id: Id
    name: str
    description: str = ""
    location: Id
    max_hp: PositiveInt
    armor: NonNegativeInt = 0
    damage: Expr | None = None
    drive: str = ""
    voice: str = ""
    attitude: str = ""
    knows: list[Id] = Field(default=[], description="Secrets this NPC knows")


class Secret(_Model):
    id: Id
    text: str


class Danger(_Model):
    id: Id
    name: str
    type: str
    impulse: str
    npc: Id | None = Field(
        default=None, description="The NPC behind the danger; its moves can refer to `target.*`"
    )
    portents: list[str] = Field(
        min_length=1, description="Grim portents, in order. The danger's clock has one per portent"
    )
    moves: list[GmMoveDefinition] = []


class Front(_Model):
    id: Id
    name: str
    impending_doom: str
    dangers: list[Danger] = Field(min_length=1)


class Ending(_Model):
    id: Id
    title: str
    text: str
    when: Condition


class ScenarioMove(Move):
    requires: Condition | None = Field(
        default=None, description="The move can only be made while this condition holds"
    )


class Scenario(_Model):
    """A loaded scenario. Built by the loader, never written by hand."""

    manifest: ScenarioManifest
    locations: dict[str, Location]
    endings: list[Ending]
    npcs: dict[str, Npc] = {}
    secrets: dict[str, Secret] = {}
    fronts: dict[str, Front] = {}
    moves: dict[str, ScenarioMove] = {}
    tags: dict[str, Tag] = {}

    def dangers(self) -> Iterator[Danger]:
        for front in self.fronts.values():
            yield from front.dangers

    def ruleset(self, pack: Pack) -> Pack:
        """The pack with the scenario's own moves and tags added."""
        return pack.model_copy(
            update={"moves": {**pack.moves, **self.moves}, "tags": {**pack.tags, **self.tags}}
        )
