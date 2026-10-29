"""Game state, built only by replaying events. Everything here is pure."""

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from gminator.core.events import (
    CharacterCreated,
    ChoiceMade,
    ClockAdvanced,
    ClockCreated,
    DiceRolled,
    Event,
    ForwardChanged,
    GameStarted,
    GmMoveTriggered,
    HoldChanged,
    HpChanged,
    ItemGained,
    ItemUsed,
    MoveMade,
    QuestionsAsked,
    TagAdded,
    TagRemoved,
    XpMarked,
)


class ReplayError(ValueError):
    """An event that cannot apply to the current state."""


class _State(BaseModel):
    model_config = ConfigDict(frozen=True)


class Possession(_State):
    item_id: str
    uses: int | None = None


class Character(_State):
    name: str
    stats: dict[str, int]
    hp: int
    max_hp: int
    xp: int = 0
    class_id: str | None = None
    damage: str | None = None
    armor: int = 0
    level: int = 1
    tags: tuple[str, ...] = ()
    hold: dict[str, int] = {}
    forward: int = 0
    inventory: tuple[Possession, ...] = ()


class Clock(_State):
    label: str
    segments: int
    filled: int = 0


class GameState(_State):
    seed: int
    rng_position: int = 0
    characters: dict[str, Character] = {}
    clocks: dict[str, Clock] = {}


def replay(events: Iterable[Event]) -> GameState:
    events = iter(events)
    first = next(events, None)
    if not isinstance(first, GameStarted):
        raise ReplayError("an event log must begin with game_started")
    state = GameState(seed=first.seed)
    for event in events:
        state = apply(state, event)
    return state


def apply(state: GameState, event: Event) -> GameState:
    match event:
        case GameStarted():
            raise ReplayError("the game has already started")
        case CharacterCreated():
            if event.character_id in state.characters:
                raise ReplayError(f"character {event.character_id!r} already exists")
            character = Character(
                name=event.name,
                stats=event.stats,
                hp=event.max_hp,
                max_hp=event.max_hp,
                class_id=event.class_id,
                damage=event.damage,
                armor=event.armor,
                level=event.level,
            )
            return _with_character(state, event.character_id, character)
        case DiceRolled():
            return state.model_copy(update={"rng_position": state.rng_position + len(event.dice)})
        case HpChanged():
            character = _character(state, event.character_id)
            hp = min(max(character.hp + event.amount, 0), character.max_hp)
            return _update(state, event.character_id, hp=hp)
        case XpMarked():
            character = _character(state, event.character_id)
            return _update(state, event.character_id, xp=character.xp + event.amount)
        case TagAdded():
            tags = _character(state, event.character_id).tags
            if event.tag not in tags:
                tags = (*tags, event.tag)
            return _update(state, event.character_id, tags=tags)
        case TagRemoved():
            tags = _character(state, event.character_id).tags
            return _update(state, event.character_id, tags=tuple(t for t in tags if t != event.tag))
        case HoldChanged():
            hold = dict(_character(state, event.character_id).hold)
            held = hold.get(event.move_id, 0) + event.amount
            if held < 0:
                raise ReplayError(f"{event.character_id!r} has no hold left from {event.move_id!r}")
            hold[event.move_id] = held
            return _update(state, event.character_id, hold={k: v for k, v in hold.items() if v})
        case ForwardChanged():
            character = _character(state, event.character_id)
            return _update(state, event.character_id, forward=character.forward + event.amount)
        case ItemGained():
            inventory = _character(state, event.character_id).inventory
            possession = Possession(item_id=event.item_id, uses=event.uses)
            return _update(state, event.character_id, inventory=(*inventory, possession))
        case ItemUsed():
            inventory = list(_character(state, event.character_id).inventory)
            index = next(
                (
                    i
                    for i, p in enumerate(inventory)
                    if p.item_id == event.item_id and p.uses is not None and p.uses > 0
                ),
                None,
            )
            if index is None:
                raise ReplayError(f"{event.character_id!r} has no usable {event.item_id!r}")
            uses = inventory[index].uses - 1
            if uses:
                inventory[index] = inventory[index].model_copy(update={"uses": uses})
            else:
                del inventory[index]
            return _update(state, event.character_id, inventory=tuple(inventory))
        case ClockCreated():
            if event.clock_id in state.clocks:
                raise ReplayError(f"clock {event.clock_id!r} already exists")
            clock = Clock(label=event.label, segments=event.segments)
            return _with_clock(state, event.clock_id, clock)
        case ClockAdvanced():
            clock = state.clocks.get(event.clock_id)
            if clock is None:
                raise ReplayError(f"no clock {event.clock_id!r}")
            filled = min(clock.filled + event.amount, clock.segments)
            return _with_clock(state, event.clock_id, clock.model_copy(update={"filled": filled}))
        case MoveMade() | ChoiceMade() | QuestionsAsked() | GmMoveTriggered():
            return state


def _character(state: GameState, character_id: str) -> Character:
    character = state.characters.get(character_id)
    if character is None:
        raise ReplayError(f"no character {character_id!r}")
    return character


def _update(state: GameState, character_id: str, **changes) -> GameState:
    character = _character(state, character_id).model_copy(update=changes)
    return _with_character(state, character_id, character)


def _with_character(state: GameState, character_id: str, character: Character) -> GameState:
    return state.model_copy(update={"characters": {**state.characters, character_id: character}})


def _with_clock(state: GameState, clock_id: str, clock: Clock) -> GameState:
    return state.model_copy(update={"clocks": {**state.clocks, clock_id: clock}})
