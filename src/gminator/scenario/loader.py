"""Loads a scenario folder against its system pack, reporting every problem with its file
and line."""

from collections.abc import Iterator
from pathlib import Path

from gminator.packs.loader import Checker, Loader, Located, PackError, Problem, references, unique
from gminator.packs.models import GmMoveDefinition, Pack, Tag
from gminator.scenario.models import (
    Danger,
    Ending,
    Front,
    Location,
    Npc,
    Obstacle,
    Scenario,
    ScenarioManifest,
    ScenarioMove,
    Secret,
)


def load_scenario(root: Path, pack: Pack) -> Scenario:
    root = Path(root)
    loader = Loader()

    manifest = loader.one(root / "scenario.yaml", ScenarioManifest, required=True)
    locations = loader.many(root / "locations.yaml", Location, required=True)
    endings = loader.many(root / "endings.yaml", Ending, required=True)
    npcs = loader.many(root / "npcs.yaml", Npc)
    secrets = loader.many(root / "secrets.yaml", Secret)
    fronts = loader.many(root / "fronts.yaml", Front)
    tags = loader.many(root / "tags.yaml", Tag)
    moves = [loader.one(path, ScenarioMove) for path in sorted(root.glob("moves/*.yaml"))]
    if loader.problems:
        raise PackError(loader.problems)
    assert manifest is not None

    problems = loader.problems
    locations_by_id = unique(locations, "location", problems)
    npcs_by_id = unique(npcs, "NPC", problems)
    secrets_by_id = unique(secrets, "secret", problems)
    fronts_by_id = unique(fronts, "front", problems)
    dangers_by_id = unique(_dangers(fronts), "danger", problems)
    obstacles_by_id = unique(_obstacles(locations), "obstacle", problems)
    problems += _shared_ids(
        locations_by_id, npcs_by_id, secrets_by_id, fronts_by_id, dangers_by_id, obstacles_by_id
    )
    endings_by_id = unique(endings, "ending", problems)
    tags_by_id = unique(tags, "tag", problems)
    moves_by_id = unique([m for m in moves if m], "move", problems)

    checker = Checker(
        pack.manifest,
        tags={*pack.tags, *tags_by_id},
        items=pack.items,
        moves={*pack.moves, *moves_by_id},
        secrets=secrets_by_id,
        locations=locations_by_id,
        clocks=dangers_by_id,
        npcs=npcs_by_id,
    )
    problems += _check_manifest(manifest, pack, checker)
    for located in locations_by_id.values():
        for index, exit_id in enumerate(located.model.exits):
            problems += checker.known(located, ("exits", index), "location", exit_id)
        for index, obstacle in enumerate(located.model.obstacles):
            if obstacle.blocks is not None and obstacle.blocks not in located.model.exits:
                problems.append(
                    located.problem(
                        ("obstacles", index, "blocks"), f"{obstacle.blocks!r} is not an exit here"
                    )
                )
    for located in npcs_by_id.values():
        problems += _check_npc(located, checker)
    for located in dangers_by_id.values():
        problems += _check_danger(located, checker)
    problems += _unique_gm_moves(pack, [*dangers_by_id.values(), *npcs_by_id.values()])
    for located in endings_by_id.values():
        problems += checker.condition(located, ("when",), located.model.when)
    for located in moves_by_id.values():
        problems += _check_move(located, pack, checker)
    if problems:
        raise PackError(problems)

    return Scenario(
        manifest=manifest.model,
        locations=_models(locations_by_id),
        endings=[located.model for located in endings_by_id.values()],
        npcs=_models(npcs_by_id),
        secrets=_models(secrets_by_id),
        fronts=_models(fronts_by_id),
        moves=_models(moves_by_id),
        tags=_models(tags_by_id),
    )


def _models(located: dict[str, Located]) -> dict:
    return {key: entry.model for key, entry in located.items()}


def _dangers(fronts: list[Located[Front]]) -> list[Located[Danger]]:
    return [
        Located(danger, front.path, front.node, (*front.loc, "dangers", index))
        for front in fronts
        for index, danger in enumerate(front.model.dangers)
    ]


def _obstacles(locations: list[Located[Location]]) -> list[Located[Obstacle]]:
    return [
        Located(obstacle, location.path, location.node, (*location.loc, "obstacles", index))
        for location in locations
        for index, obstacle in enumerate(location.model.obstacles)
    ]


def _gm_moves(located: Located[Danger] | Located[Npc]) -> list[Located[GmMoveDefinition]]:
    """The GM moves of a danger or an NPC, each located for reporting problems."""
    return [
        Located(gm_move, located.path, located.node, (*located.loc, "moves", index))
        for index, gm_move in enumerate(located.model.moves)
    ]


def _unique_gm_moves(pack: Pack, owners: list[Located]) -> Iterator[Problem]:
    """GM moves are told apart by id, so no two may share one, wherever they come from."""
    seen = set(pack.gm_moves)
    for owner in owners:
        for located in _gm_moves(owner):
            if located.model.id in seen:
                yield located.problem(("id",), f"GM move {located.model.id!r} is already used")
            seen.add(located.model.id)


def _shared_ids(*kinds: dict[str, Located]) -> Iterator[Problem]:
    """Locations, NPCs, secrets, fronts, dangers and obstacles are all entities, so share one
    id space."""
    seen: set[str] = set()
    for by_id in kinds:
        for key, located in by_id.items():
            if key in seen:
                yield located.problem(("id",), f"id {key!r} is already used in this scenario")
            seen.add(key)


def _check_manifest(
    located: Located[ScenarioManifest], pack: Pack, checker: Checker
) -> Iterator[Problem]:
    manifest = located.model
    if manifest.system != pack.manifest.id:
        yield located.problem(
            ("system",), f"scenario is for {manifest.system!r}, not {pack.manifest.id!r}"
        )
    yield from checker.known(located, ("start",), "location", manifest.start)


def _check_npc(located: Located[Npc], checker: Checker) -> Iterator[Problem]:
    npc = located.model
    yield from checker.known(located, ("location",), "location", npc.location)
    for index, secret_id in enumerate(npc.knows):
        yield from checker.known(located, ("knows", index), "secret", secret_id)
    if npc.damage is not None:
        yield from references(located, ("damage",), npc.damage, set())
    for gm_move in _gm_moves(located):
        yield from checker.gm_move(gm_move, target=True)


def _check_danger(located: Located[Danger], checker: Checker) -> Iterator[Problem]:
    danger = located.model
    if danger.npc is not None:
        yield from checker.known(located, ("npc",), "NPC", danger.npc)
    for gm_move in _gm_moves(located):
        yield from checker.gm_move(gm_move, target=danger.npc is not None)


def _check_move(located: Located[ScenarioMove], pack: Pack, checker: Checker) -> Iterator[Problem]:
    move = located.model
    if move.id in pack.moves:
        yield located.problem(("id",), f"move {move.id!r} is already in the pack")
    yield from checker.move(located)
    if move.requires is not None:
        yield from checker.condition(located, ("requires",), move.requires)
