"""Immutable records of state changes. The event log is the source of truth."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class _Event(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GameStarted(_Event):
    type: Literal["game_started"] = "game_started"
    seed: int


class CharacterCreated(_Event):
    type: Literal["character_created"] = "character_created"
    character_id: str
    name: str
    stats: dict[str, int]
    max_hp: int
    class_id: str | None = None
    damage: str | None = None
    armor: int = 0
    level: int = 1


class DieRoll(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sides: int
    value: int


class DiceRolled(_Event):
    type: Literal["dice_rolled"] = "dice_rolled"
    expression: str
    dice: list[DieRoll]
    total: int


class HpChanged(_Event):
    type: Literal["hp_changed"] = "hp_changed"
    character_id: str
    amount: int


class XpMarked(_Event):
    type: Literal["xp_marked"] = "xp_marked"
    character_id: str
    amount: int


class ClockCreated(_Event):
    type: Literal["clock_created"] = "clock_created"
    clock_id: str
    label: str
    segments: int


class ClockAdvanced(_Event):
    type: Literal["clock_advanced"] = "clock_advanced"
    clock_id: str
    amount: int


class TagAdded(_Event):
    type: Literal["tag_added"] = "tag_added"
    character_id: str
    tag: str


class TagRemoved(_Event):
    type: Literal["tag_removed"] = "tag_removed"
    character_id: str
    tag: str


class HoldChanged(_Event):
    type: Literal["hold_changed"] = "hold_changed"
    character_id: str
    move_id: str
    amount: int


class ForwardChanged(_Event):
    type: Literal["forward_changed"] = "forward_changed"
    character_id: str
    amount: int


class ItemGained(_Event):
    type: Literal["item_gained"] = "item_gained"
    character_id: str
    item_id: str
    uses: int | None = None


class ItemUsed(_Event):
    type: Literal["item_used"] = "item_used"
    character_id: str
    item_id: str


Band = Literal["strong", "partial", "miss"]


class MoveMade(_Event):
    """A move was made; for rolled moves, with its total and band."""

    type: Literal["move_made"] = "move_made"
    character_id: str
    move_id: str
    target_id: str | None = None
    total: int | None = None
    band: Band | None = None


class ChoiceMade(_Event):
    type: Literal["choice_made"] = "choice_made"
    character_id: str
    move_id: str
    chosen: list[str]


class QuestionsAsked(_Event):
    type: Literal["questions_asked"] = "questions_asked"
    character_id: str
    questions: list[str]


class GmMoveTriggered(_Event):
    type: Literal["gm_move_triggered"] = "gm_move_triggered"
    severity: Literal["soft", "hard"]


class GmMoveMade(_Event):
    """The engine picked this GM move; its effects follow as their own events."""

    type: Literal["gm_move_made"] = "gm_move_made"
    gm_move_id: str


class CharacterMoved(_Event):
    type: Literal["character_moved"] = "character_moved"
    character_id: str
    location_id: str


class ObstacleCleared(_Event):
    type: Literal["obstacle_cleared"] = "obstacle_cleared"
    obstacle_id: str


class SecretRevealed(_Event):
    type: Literal["secret_revealed"] = "secret_revealed"
    secret_id: str


class GameEnded(_Event):
    type: Literal["game_ended"] = "game_ended"
    ending_id: str


Event = Annotated[
    GameStarted
    | CharacterCreated
    | DiceRolled
    | HpChanged
    | XpMarked
    | ClockCreated
    | ClockAdvanced
    | TagAdded
    | TagRemoved
    | HoldChanged
    | ForwardChanged
    | ItemGained
    | ItemUsed
    | MoveMade
    | ChoiceMade
    | QuestionsAsked
    | GmMoveTriggered
    | GmMoveMade
    | CharacterMoved
    | ObstacleCleared
    | SecretRevealed
    | GameEnded,
    Field(discriminator="type"),
]

event_adapter: TypeAdapter[Event] = TypeAdapter(Event)
