"""What a system pack may contain. These models are the single source of truth for pack
files; the JSON Schemas in `schemas/` are generated from them."""

from typing import Annotated, Any, Literal, Union

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    NonNegativeInt,
    PositiveInt,
    StringConstraints,
    WithJsonSchema,
    model_validator,
)
from pydantic import Tag as UnionTag

from gminator.core.events import Band
from gminator.core.expr import ExpressionError, parse

Id = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
PackId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]*$")]
Target = Literal["self", "target"]


def _number_to_source(value: Any) -> Any:
    return str(value) if isinstance(value, int) and not isinstance(value, bool) else value


def _check_expression(source: str) -> str:
    try:
        parse(source)
    except ExpressionError as error:
        raise ValueError(str(error)) from None
    return source


Expr = Annotated[
    str,
    BeforeValidator(_number_to_source),
    AfterValidator(_check_expression),
    WithJsonSchema(
        {"type": ["string", "integer"], "description": "An expression, e.g. `stat.str` or `d6 + 1`"}
    ),
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _at_most_options(n: int, count: int, what: str) -> None:
    if n > count:
        raise ValueError(f"cannot pick {n} from {count} {what}")


# Effect arguments


class DamageArgs(_Model):
    amount: Expr
    target: Target = "target"


class TakeDamageArgs(_Model):
    amount: Expr


class HealArgs(_Model):
    amount: Expr
    target: Target = "self"


class Option(_Model):
    label: str
    effects: list["Effect"] = []


class ChooseArgs(_Model):
    n: PositiveInt
    options: list[Option]

    @model_validator(mode="after")
    def _enough_options(self) -> "ChooseArgs":
        _at_most_options(self.n, len(self.options), "options")
        return self


class AskArgs(_Model):
    n: PositiveInt
    questions: list[str]

    @model_validator(mode="after")
    def _enough_questions(self) -> "AskArgs":
        _at_most_options(self.n, len(self.questions), "questions")
        return self


class GainHoldArgs(_Model):
    amount: PositiveInt


class SpendHoldArgs(_Model):
    move: Id
    amount: PositiveInt = 1


class TagArgs(_Model):
    tag: Id
    target: Target = "self"


class ClockArgs(_Model):
    clock: Id
    amount: PositiveInt = 1


class ForwardArgs(_Model):
    amount: int
    target: Target = "self"


class UseItemArgs(_Model):
    tag: Id


# Effects: each is a mapping with exactly one key, the effect's name.


class DealDamage(_Model):
    deal_damage: DamageArgs


class TakeDamage(_Model):
    take_damage: TakeDamageArgs


class Heal(_Model):
    heal: HealArgs


class ChooseN(_Model):
    choose_n: ChooseArgs


class AskQuestions(_Model):
    ask_questions: AskArgs


class GainHold(_Model):
    gain_hold: GainHoldArgs


class SpendHold(_Model):
    spend_hold: SpendHoldArgs


class AddTag(_Model):
    add_tag: TagArgs


class RemoveTag(_Model):
    remove_tag: TagArgs


class AdvanceClock(_Model):
    advance_clock: ClockArgs


class GmMove(_Model):
    gm_move: Literal["soft", "hard"]


class MarkXp(_Model):
    mark_xp: PositiveInt


class AddForward(_Model):
    add_forward: ForwardArgs


class UseItem(_Model):
    use_item: UseItemArgs


EFFECT_TYPES: tuple[type[_Model], ...] = (
    DealDamage,
    TakeDamage,
    Heal,
    ChooseN,
    AskQuestions,
    GainHold,
    SpendHold,
    AddTag,
    RemoveTag,
    AdvanceClock,
    GmMove,
    MarkXp,
    AddForward,
    UseItem,
)


def effect_name(effect_type: type[BaseModel]) -> str:
    return next(iter(effect_type.model_fields))


def _effect_kind(value: Any) -> str | None:
    if isinstance(value, BaseModel):
        return effect_name(type(value))
    if isinstance(value, dict) and len(value) == 1:
        return next(iter(value))
    return None


Effect = Annotated[
    Union[tuple(Annotated[cls, UnionTag(effect_name(cls))] for cls in EFFECT_TYPES)],  # noqa: UP007
    Discriminator(
        _effect_kind,
        custom_error_type="invalid_effect",
        custom_error_message="an effect is a mapping with exactly one key, one of: "
        + ", ".join(effect_name(cls) for cls in EFFECT_TYPES),
    ),
]

Option.model_rebuild()


# Moves


class Outcome(_Model):
    text: str = ""
    effects: list[Effect] = []


class Outcomes(_Model):
    strong: Outcome
    partial: Outcome
    miss: Outcome


class Move(_Model):
    id: Id
    name: str
    category: Literal["basic", "special", "class"]
    trigger: str
    target: bool = Field(default=False, description="Whether the move is made against a target")
    roll: Expr | None = Field(
        default=None, description="The modifier added to the pack's roll, e.g. `stat.str`"
    )
    stat_options: list[Id] | None = Field(
        default=None, description="Stats the player picks from; the roll refers to `stat.chosen`"
    )
    outcomes: Outcomes | None = None
    text: str = ""
    effects: list[Effect] = []

    @model_validator(mode="after")
    def _roll_and_outcomes_go_together(self) -> "Move":
        if self.roll is not None:
            if self.outcomes is None:
                raise ValueError("a move with a roll needs outcomes")
            if self.effects:
                raise ValueError("a move with a roll puts effects under outcomes, not effects")
        else:
            if self.outcomes is not None:
                raise ValueError("outcomes need a roll")
            if self.stat_options is not None:
                raise ValueError("stat_options need a roll")
        return self


# Manifest


class Bands(_Model):
    strong: int = 10
    partial: int = 7

    @model_validator(mode="after")
    def _strong_above_partial(self) -> "Bands":
        if self.strong <= self.partial:
            raise ValueError("strong must start above partial")
        return self


class ModifierStep(_Model):
    up_to: int
    modifier: int


class Manifest(_Model):
    id: PackId
    name: str
    version: str
    license: str
    attribution: str
    stats: list[Id] = Field(min_length=1)
    roll: Expr = "2d6"
    bands: Bands = Bands()
    modifiers: list[ModifierStep] = Field(
        min_length=1, description="Score to modifier table, ascending by `up_to`"
    )
    score_array: list[int] | None = Field(
        default=None, description="The scores a new character assigns, one per stat"
    )
    miss_effects: list[Effect] = Field(default=[], description="Applied on every rolled miss")

    @model_validator(mode="after")
    def _consistent(self) -> "Manifest":
        limits = [step.up_to for step in self.modifiers]
        if limits != sorted(set(limits)):
            raise ValueError("the modifier table must ascend by up_to")
        if self.score_array is not None and len(self.score_array) != len(self.stats):
            raise ValueError("score_array needs exactly one score per stat")
        return self

    def band(self, total: int) -> Band:
        if total >= self.bands.strong:
            return "strong"
        if total >= self.bands.partial:
            return "partial"
        return "miss"

    def modifier(self, score: int) -> int:
        for step in self.modifiers:
            if score <= step.up_to:
                return step.modifier
        raise ValueError(f"no modifier for score {score}")


# Gear, tags, classes


class Tag(_Model):
    id: Id
    description: str


class Item(_Model):
    id: Id
    name: str
    description: str = ""
    weight: NonNegativeInt = 0
    armor: NonNegativeInt = 0
    uses: PositiveInt | None = None
    tags: list[Id] = []


class GearChoice(_Model):
    label: str
    n: PositiveInt = 1
    options: list[list[Id]] = Field(min_length=1, description="Each option is a list of item ids")

    @model_validator(mode="after")
    def _enough_options(self) -> "GearChoice":
        _at_most_options(self.n, len(self.options), "options")
        return self


class CharacterClass(_Model):
    id: Id
    name: str
    description: str = ""
    damage: Expr
    max_hp: Expr = Field(description="May refer to `score.<stat>` and `stat.<stat>`")
    moves: list[Id] = []
    starting_gear: list[Id] = []
    gear_choices: list[GearChoice] = []


class Pack(_Model):
    """A loaded pack. Built by the loader, never written by hand."""

    manifest: Manifest
    moves: dict[str, Move] = {}
    classes: dict[str, CharacterClass] = {}
    items: dict[str, Item] = {}
    tags: dict[str, Tag] = {}
