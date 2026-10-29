"""Creates player characters from a pack class."""

from collections.abc import Mapping, Sequence

from gminator.core.events import CharacterCreated, Event, ItemGained
from gminator.core.expr import ExpressionError, parse
from gminator.packs.models import GearChoice, Pack


class CharacterError(ValueError):
    """A character that cannot be created as asked."""


class _NoDice:
    def roll(self, sides: int) -> int:
        raise ExpressionError("character creation cannot roll dice")


def create_character(
    pack: Pack,
    class_id: str,
    character_id: str,
    name: str,
    scores: Mapping[str, int],
    gear_choices: Sequence[Sequence[int]] | None = None,
) -> list[Event]:
    """Events that create the character. Gear choices default to the first options."""
    cls = pack.classes.get(class_id)
    if cls is None:
        raise CharacterError(f"no class {class_id!r}")
    manifest = pack.manifest
    missing = [stat for stat in manifest.stats if stat not in scores]
    if missing:
        raise CharacterError(f"missing scores for {', '.join(missing)}")
    if manifest.score_array is not None and sorted(scores.values()) != sorted(manifest.score_array):
        allowed = ", ".join(map(str, manifest.score_array))
        raise CharacterError(f"scores must be {allowed}, each used once")

    try:
        stats = {stat: manifest.modifier(scores[stat]) for stat in manifest.stats}
    except ValueError as error:
        raise CharacterError(str(error)) from error
    refs = {f"score.{stat}": scores[stat] for stat in manifest.stats}
    refs |= {f"stat.{stat}": modifier for stat, modifier in stats.items()}
    max_hp = parse(cls.max_hp).evaluate(_NoDice(), refs)

    events: list[Event] = [
        CharacterCreated(
            character_id=character_id,
            name=name,
            stats=stats,
            max_hp=max_hp,
            class_id=class_id,
            damage=cls.damage,
        )
    ]
    item_ids = [*cls.starting_gear, *_chosen_gear(cls.gear_choices, gear_choices)]
    events += [
        ItemGained(character_id=character_id, item_id=item_id, uses=pack.items[item_id].uses)
        for item_id in item_ids
    ]
    return events


def _chosen_gear(choices: Sequence[GearChoice], picks: Sequence[Sequence[int]] | None) -> list[str]:
    if picks is None:
        picks = [range(choice.n) for choice in choices]
    if len(picks) != len(choices):
        raise CharacterError(f"expected {len(choices)} gear choices, got {len(picks)}")
    item_ids: list[str] = []
    for choice, picked in zip(choices, picks, strict=True):
        picked = list(picked)
        valid = len(picked) == choice.n == len(set(picked))
        if not valid or not all(0 <= i < len(choice.options) for i in picked):
            raise CharacterError(f"{choice.label}: pick {choice.n} gear option(s), got {picked}")
        for index in picked:
            item_ids += choice.options[index]
    return item_ids
