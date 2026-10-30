"""Resolves a pack move into events: roll, pick the band, apply its effects."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from gminator.core.events import (
    Band,
    CharacterMoved,
    ChoiceMade,
    ClockAdvanced,
    Event,
    ForwardChanged,
    GmMoveMade,
    GmMoveTriggered,
    HoldChanged,
    HpChanged,
    ItemUsed,
    MoveMade,
    ObstacleCleared,
    QuestionsAsked,
    SecretRevealed,
    TagAdded,
    TagRemoved,
    XpMarked,
)
from gminator.core.expr import ExpressionError
from gminator.core.game import Game
from gminator.core.state import Character, ReplayError
from gminator.packs.models import (
    AddForward,
    AddTag,
    AdvanceClock,
    AskQuestions,
    ChooseN,
    ClearObstacle,
    DealDamage,
    Effect,
    GainHold,
    GmMove,
    GmMoveDefinition,
    Heal,
    MarkXp,
    Move,
    MoveTo,
    Pack,
    RemoveTag,
    RevealSecret,
    SpendHold,
    TakeDamage,
    Target,
    UseItem,
)


class ResolveError(ValueError):
    """A move that cannot be made as asked. Nothing is recorded."""


class Decider(Protocol):
    """Makes the player's choices: returns `n` distinct indices into `options`."""

    def choose(self, prompt: str, options: Sequence[str], n: int) -> Sequence[int]: ...


@dataclass(frozen=True)
class Resolution:
    move_id: str
    band: Band | None
    total: int | None
    text: str
    events: tuple[Event, ...]


def resolve_move(
    game: Game,
    pack: Pack,
    move_id: str,
    actor_id: str,
    decider: Decider,
    *,
    target_id: str | None = None,
    stat: str | None = None,
) -> Resolution:
    move = pack.moves.get(move_id)
    if move is None:
        raise ResolveError(f"no move {move_id!r}")
    _check_request(game, move, actor_id, target_id, stat)

    def play(scratch: Game) -> tuple[Band | None, int | None, str]:
        return _Run(scratch, pack, move.id, move.name, actor_id, target_id, stat, decider).resolve(
            move
        )

    (band, total, text), events = _commit(game, play)
    return Resolution(move_id, band, total, text, events)


def make_gm_move(
    game: Game,
    pack: Pack,
    gm_move: GmMoveDefinition,
    pc_id: str,
    decider: Decider,
    *,
    target_id: str | None = None,
) -> Resolution:
    """The GM move happens to the player character; `target` is whoever it comes from."""

    def play(scratch: Game) -> None:
        scratch.record(GmMoveMade(gm_move_id=gm_move.id))
        run = _Run(scratch, pack, gm_move.id, gm_move.name, pc_id, target_id, None, decider)
        run.apply(gm_move.effects)

    _, events = _commit(game, play)
    return Resolution(gm_move.id, None, None, gm_move.text, events)


T = TypeVar("T")


def _commit(game: Game, play: Callable[[Game], T]) -> tuple[T, tuple[Event, ...]]:
    """Plays on a copy of the game and records its events only if all of it works."""
    scratch = Game(game.events)
    start = len(scratch.events)
    try:
        result = play(scratch)
    except (ReplayError, ExpressionError) as error:
        raise ResolveError(str(error)) from error
    events = scratch.events[start:]
    for event in events:
        game.record(event)
    return result, events


def _check_request(
    game: Game, move: Move, actor_id: str, target_id: str | None, stat: str | None
) -> None:
    characters = game.state.characters
    if actor_id not in characters:
        raise ResolveError(f"no character {actor_id!r}")
    if move.target and target_id is None:
        raise ResolveError(f"{move.name} needs a target")
    if not move.target and target_id is not None:
        raise ResolveError(f"{move.name} does not take a target")
    # Obstacles belong to the scenario, which checks them; characters are checked here.
    if move.target is True and target_id not in characters:
        raise ResolveError(f"no character {target_id!r}")
    if move.stat_options is not None:
        if stat is None:
            raise ResolveError(f"{move.name} needs a stat: {', '.join(move.stat_options)}")
        if stat not in move.stat_options:
            raise ResolveError(f"{move.name} cannot roll {stat!r}")


def armor(pack: Pack, character: Character) -> int:
    """The character's own armor plus the armor of everything they carry."""
    items = pack.items
    worn = sum(items[p.item_id].armor for p in character.inventory if p.item_id in items)
    return character.armor + worn


class _Run:
    def __init__(
        self,
        game: Game,
        pack: Pack,
        move_id: str,
        name: str,
        actor_id: str,
        target_id: str | None,
        stat: str | None,
        decider: Decider,
    ) -> None:
        self._game = game
        self._pack = pack
        self._move_id = move_id
        self._name = name
        self._actor = actor_id
        self._target = target_id
        self._stat = stat
        self._decider = decider

    def resolve(self, move: Move) -> tuple[Band | None, int | None, str]:
        if move.roll is None or move.outcomes is None:
            self._record(
                MoveMade(character_id=self._actor, move_id=move.id, target_id=self._target)
            )
            self.apply(move.effects)
            return None, None, move.text

        forward = self._game.state.characters[self._actor].forward
        total = self._roll(f"{self._pack.manifest.roll} + ({move.roll})") + forward
        band = self._pack.manifest.band(total)
        self._record(
            MoveMade(
                character_id=self._actor,
                move_id=move.id,
                target_id=self._target,
                total=total,
                band=band,
            )
        )
        if forward:
            self._record(ForwardChanged(character_id=self._actor, amount=-forward))
        outcome = getattr(move.outcomes, band)
        if band == "miss":
            self.apply(self._pack.manifest.miss_effects)
        self.apply(outcome.effects)
        return band, total, outcome.text

    def apply(self, effects: Sequence[Effect]) -> None:
        for effect in effects:
            self._apply_one(effect)

    def _apply_one(self, effect: Effect) -> None:
        actor = self._actor
        match effect:
            case DealDamage(deal_damage=args):
                self._hurt(self._who(args.target), args.amount)
            case TakeDamage(take_damage=args):
                self._hurt(actor, args.amount)
            case Heal(heal=args):
                amount = max(self._roll(args.amount), 0)
                self._record(HpChanged(character_id=self._who(args.target), amount=amount))
            case ChooseN(choose_n=args):
                picks = self._decide([option.label for option in args.options], args.n)
                chosen = [args.options[i] for i in picks]
                self._record(
                    ChoiceMade(
                        character_id=actor,
                        move_id=self._move_id,
                        chosen=[option.label for option in chosen],
                    )
                )
                for option in chosen:
                    self.apply(option.effects)
            case AskQuestions(ask_questions=args):
                picks = self._decide(args.questions, args.n)
                questions = [args.questions[i] for i in picks]
                self._record(QuestionsAsked(character_id=actor, questions=questions))
            case GainHold(gain_hold=args):
                self._record(
                    HoldChanged(character_id=actor, move_id=self._move_id, amount=args.amount)
                )
            case SpendHold(spend_hold=args):
                self._record(
                    HoldChanged(character_id=actor, move_id=args.move, amount=-args.amount)
                )
            case AddTag(add_tag=args):
                self._record(TagAdded(character_id=self._who(args.target), tag=args.tag))
            case RemoveTag(remove_tag=args):
                self._record(TagRemoved(character_id=self._who(args.target), tag=args.tag))
            case AdvanceClock(advance_clock=args):
                self._record(ClockAdvanced(clock_id=args.clock, amount=args.amount))
            case GmMove(gm_move=severity):
                self._record(GmMoveTriggered(severity=severity))
            case MarkXp(mark_xp=amount):
                self._record(XpMarked(character_id=actor, amount=amount))
            case AddForward(add_forward=args):
                self._record(
                    ForwardChanged(character_id=self._who(args.target), amount=args.amount)
                )
            case UseItem(use_item=args):
                self._record(ItemUsed(character_id=actor, item_id=self._item_tagged(args.tag)))
            case RevealSecret(reveal_secret=secret_id):
                self._record(SecretRevealed(secret_id=secret_id))
            case MoveTo(move_to=args):
                self._record(
                    CharacterMoved(character_id=self._who(args.target), location_id=args.location)
                )
            case ClearObstacle():
                assert self._target is not None
                self._record(ObstacleCleared(obstacle_id=self._target))

    def _hurt(self, character_id: str, amount: str) -> None:
        damage = self._roll(amount)
        loss = max(damage - self._armor(character_id), 0)
        self._record(HpChanged(character_id=character_id, amount=-loss))

    def _decide(self, options: list[str], n: int) -> list[int]:
        picks = list(self._decider.choose(self._name, options, n))
        valid = len(picks) == n == len(set(picks)) and all(0 <= i < len(options) for i in picks)
        if not valid:
            raise ResolveError(f"must choose {n} of {len(options)} options, got {picks}")
        return picks

    def _item_tagged(self, tag: str) -> str:
        for possession in self._game.state.characters[self._actor].inventory:
            item = self._pack.items.get(possession.item_id)
            if item and tag in item.tags and possession.uses:
                return possession.item_id
        raise ResolveError(f"{self._actor!r} has nothing tagged {tag!r} left")

    def _who(self, target: Target) -> str:
        if target == "self":
            return self._actor
        if self._target is None:
            raise ResolveError(f"{self._name} has no target")
        return self._target

    def _armor(self, character_id: str) -> int:
        return armor(self._pack, self._game.state.characters[character_id])

    def _roll(self, expression: str) -> int:
        return self._game.roll(expression, self._refs())

    def _refs(self) -> dict[str, int | str]:
        actor = self._game.state.characters[self._actor]
        refs: dict[str, int | str] = {f"stat.{name}": value for name, value in actor.stats.items()}
        if self._stat is not None:
            refs["stat.chosen"] = actor.stats.get(self._stat, 0)
        refs |= self._attributes("self", self._actor)
        if self._target in self._game.state.characters:
            refs |= self._attributes("target", self._target)
        return refs

    def _attributes(self, prefix: str, character_id: str) -> dict[str, int | str]:
        character = self._game.state.characters[character_id]
        attributes: dict[str, int | str] = {
            f"{prefix}.hp": character.hp,
            f"{prefix}.max_hp": character.max_hp,
            f"{prefix}.level": character.level,
            f"{prefix}.armor": self._armor(character_id),
        }
        if character.damage is not None:
            attributes[f"{prefix}.damage"] = character.damage
        return attributes

    def _record(self, event: Event) -> None:
        self._game.record(event)
