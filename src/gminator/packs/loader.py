"""Loads a pack folder, reporting every problem with its file and line."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError
from ruamel.yaml import YAML, CommentedMap, CommentedSeq
from ruamel.yaml.error import MarkedYAMLError, YAMLError

from gminator.core.expr import parse
from gminator.packs.models import (
    AddForward,
    AddTag,
    CharacterClass,
    ChooseN,
    DealDamage,
    Effect,
    Heal,
    Item,
    Manifest,
    Move,
    Pack,
    RemoveTag,
    SpendHold,
    Tag,
    TakeDamage,
    UseItem,
)

CHARACTER_ATTRIBUTES = ("damage", "armor", "hp", "max_hp", "level")

Loc = tuple[str | int, ...]
M = TypeVar("M", bound=BaseModel)


@dataclass(frozen=True)
class Problem:
    path: Path
    line: int | None
    message: str

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else f"{self.path}"
        return f"{where}: {self.message}"


class PackError(Exception):
    def __init__(self, problems: Sequence[Problem]) -> None:
        self.problems = list(problems)
        super().__init__("\n".join(str(problem) for problem in self.problems))


@dataclass(frozen=True)
class _Located(Generic[M]):
    """A validated model plus where it came from, for reporting cross-reference problems."""

    model: M
    path: Path
    node: Any
    loc: Loc = ()

    def problem(self, loc: Loc, message: str) -> Problem:
        return Problem(self.path, _line(self.node, (*self.loc, *loc)), message)


def load_pack(root: Path) -> Pack:
    root = Path(root)
    loader = _Loader()

    manifest = loader.one(root / "pack.yaml", Manifest, required=True)
    tags = loader.many(root / "tags.yaml", Tag)
    items = loader.many(root / "gear.yaml", Item)
    moves = [loader.one(path, Move) for path in sorted(root.glob("moves/*.yaml"))]
    classes = [loader.one(path, CharacterClass) for path in sorted(root.glob("classes/*.yaml"))]
    if loader.problems:
        raise PackError(loader.problems)
    assert manifest is not None

    tags_by_id = _unique(tags, "tag", loader.problems)
    items_by_id = _unique(items, "item", loader.problems)
    moves_by_id = _unique([m for m in moves if m], "move", loader.problems)
    classes_by_id = _unique([c for c in classes if c], "class", loader.problems)

    checker = _Checker(manifest.model, tags_by_id, items_by_id, moves_by_id)
    loader.problems += checker.manifest(manifest)
    for located in items_by_id.values():
        loader.problems += checker.item(located)
    for located in moves_by_id.values():
        loader.problems += checker.move(located)
    for located in classes_by_id.values():
        loader.problems += checker.character_class(located)
    if loader.problems:
        raise PackError(loader.problems)

    return Pack(
        manifest=manifest.model,
        moves={key: located.model for key, located in moves_by_id.items()},
        classes={key: located.model for key, located in classes_by_id.items()},
        items={key: located.model for key, located in items_by_id.items()},
        tags={key: located.model for key, located in tags_by_id.items()},
    )


class _Loader:
    def __init__(self) -> None:
        self.problems: list[Problem] = []
        self._yaml = YAML(typ="rt")

    def _read(self, path: Path, required: bool) -> tuple[bool, Any]:
        if not path.exists():
            if required:
                self.problems.append(Problem(path, None, "missing"))
            return False, None
        try:
            return True, self._yaml.load(path)
        except MarkedYAMLError as error:
            line = error.problem_mark.line + 1 if error.problem_mark else None
            self.problems.append(Problem(path, line, f"invalid YAML: {error.problem}"))
        except YAMLError as error:
            self.problems.append(Problem(path, None, f"invalid YAML: {error}"))
        return False, None

    def _validate(self, path: Path, node: Any, adapter: TypeAdapter) -> Any:
        try:
            return adapter.validate_python(node)
        except ValidationError as error:
            for detail in error.errors():
                where = _describe(detail["loc"])
                message = f"{where}: {detail['msg']}" if where else detail["msg"]
                self.problems.append(Problem(path, _line(node, detail["loc"]), message))
            return None

    def one(self, path: Path, model: type[M], required: bool = False) -> _Located[M] | None:
        found, node = self._read(path, required)
        if not found:
            return None
        validated = self._validate(path, node, TypeAdapter(model))
        return _Located(validated, path, node) if validated is not None else None

    def many(self, path: Path, model: type[M]) -> list[_Located[M]]:
        found, node = self._read(path, required=False)
        if not found:
            return []
        validated = self._validate(path, node, TypeAdapter(list[model]))
        if validated is None:
            return []
        return [_Located(item, path, node, (index,)) for index, item in enumerate(validated)]


def _unique(located: list[_Located], kind: str, problems: list[Problem]) -> dict[str, _Located]:
    by_id: dict[str, _Located] = {}
    for entry in located:
        if entry.model.id in by_id:
            problems.append(entry.problem(("id",), f"duplicate {kind} id {entry.model.id!r}"))
        else:
            by_id[entry.model.id] = entry
    return by_id


class _Checker:
    """Checks references between pack files."""

    def __init__(
        self,
        manifest: Manifest,
        tags: dict[str, _Located],
        items: dict[str, _Located],
        moves: dict[str, _Located],
    ) -> None:
        self._manifest = manifest
        self._tags = tags
        self._items = items
        self._moves = moves
        self._stat_refs = {f"stat.{stat}" for stat in manifest.stats}
        self._self_refs = {f"self.{attribute}" for attribute in CHARACTER_ATTRIBUTES}
        self._target_refs = {f"target.{attribute}" for attribute in CHARACTER_ATTRIBUTES}

    def manifest(self, located: _Located[Manifest]) -> Iterator[Problem]:
        yield from _references(located, ("roll",), located.model.roll, set())
        allowed = self._stat_refs | self._self_refs
        yield from self._effects(located, ("miss_effects",), located.model.miss_effects, allowed)

    def item(self, located: _Located[Item]) -> Iterator[Problem]:
        for index, tag in enumerate(located.model.tags):
            if tag not in self._tags:
                yield located.problem(("tags", index), f"unknown tag {tag!r}")

    def move(self, located: _Located[Move]) -> Iterator[Problem]:
        move = located.model
        allowed = self._stat_refs | self._self_refs
        if move.target:
            allowed |= self._target_refs
        if move.stat_options is not None:
            allowed |= {"stat.chosen"}
            for index, stat in enumerate(move.stat_options):
                if stat not in self._manifest.stats:
                    yield located.problem(("stat_options", index), f"unknown stat {stat!r}")
        if move.roll is not None:
            yield from _references(located, ("roll",), move.roll, allowed)
        if move.outcomes is not None:
            for band in ("strong", "partial", "miss"):
                effects = getattr(move.outcomes, band).effects
                yield from self._effects(located, ("outcomes", band, "effects"), effects, allowed)
        yield from self._effects(located, ("effects",), move.effects, allowed)

    def character_class(self, located: _Located[CharacterClass]) -> Iterator[Problem]:
        cls = located.model
        yield from _references(located, ("damage",), cls.damage, set())
        scores = {f"score.{stat}" for stat in self._manifest.stats}
        yield from _references(located, ("max_hp",), cls.max_hp, scores | self._stat_refs)
        for index, move_id in enumerate(cls.moves):
            if move_id not in self._moves:
                yield located.problem(("moves", index), f"unknown move {move_id!r}")
        for index, item_id in enumerate(cls.starting_gear):
            yield from self._known_item(located, ("starting_gear", index), item_id)
        for c, choice in enumerate(cls.gear_choices):
            for o, option in enumerate(choice.options):
                for i, item_id in enumerate(option):
                    yield from self._known_item(
                        located, ("gear_choices", c, "options", o, i), item_id
                    )

    def _known_item(self, located: _Located, loc: Loc, item_id: str) -> Iterator[Problem]:
        if item_id not in self._items:
            yield located.problem(loc, f"unknown item {item_id!r}")

    def _effects(
        self, located: _Located, loc: Loc, effects: list[Effect], allowed: set[str]
    ) -> Iterator[Problem]:
        has_target = bool(allowed & self._target_refs)
        for index, effect in enumerate(effects):
            at = (*loc, index)
            target = None
            match effect:
                case DealDamage(deal_damage=args):
                    yield from _references(
                        located, (*at, "deal_damage", "amount"), args.amount, allowed
                    )
                    target = args.target
                case TakeDamage(take_damage=args):
                    yield from _references(
                        located, (*at, "take_damage", "amount"), args.amount, allowed
                    )
                case Heal(heal=args):
                    yield from _references(located, (*at, "heal", "amount"), args.amount, allowed)
                    target = args.target
                case AddTag(add_tag=args) | RemoveTag(remove_tag=args):
                    if args.tag not in self._tags:
                        yield located.problem(at, f"unknown tag {args.tag!r}")
                    target = args.target
                case AddForward(add_forward=args):
                    target = args.target
                case UseItem(use_item=args):
                    if args.tag not in self._tags:
                        yield located.problem(at, f"unknown tag {args.tag!r}")
                case SpendHold(spend_hold=args):
                    if args.move not in self._moves:
                        yield located.problem(at, f"unknown move {args.move!r}")
                case ChooseN(choose_n=args):
                    for o, option in enumerate(args.options):
                        option_loc = (*at, "choose_n", "options", o, "effects")
                        yield from self._effects(located, option_loc, option.effects, allowed)
            if target == "target" and not has_target:
                yield located.problem(
                    at, "this effect hits the move's target, but the move has none (target: true)"
                )


def _references(located: _Located, loc: Loc, source: str, allowed: set[str]) -> Iterator[Problem]:
    for name in sorted(parse(source).references - allowed):
        hint = " (needs stat_options)" if name == "stat.chosen" else ""
        yield located.problem(loc, f"unknown reference {name!r}{hint}")


def _line(node: Any, loc: Loc) -> int | None:
    """The 1-based line of the deepest part of `loc` found in the YAML node tree.

    Parts that are not in the tree (such as pydantic's union tags) are skipped.
    """
    line = node.lc.line if isinstance(node, CommentedMap | CommentedSeq) else None
    for part in loc:
        if isinstance(node, CommentedMap) and part in node:
            line = node.lc.key(part)[0]
            node = node[part]
        elif isinstance(node, CommentedSeq) and isinstance(part, int) and 0 <= part < len(node):
            line = node.lc.item(part)[0]
            node = node[part]
    return line + 1 if line is not None else None


def _describe(loc: Loc) -> str:
    parts: list[str] = []
    for part in map(str, loc):
        if not parts or parts[-1] != part:
            parts.append(part)
    return ".".join(parts)
