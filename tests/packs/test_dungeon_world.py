"""M2 exit criteria: every DW basic move resolves from YAML; a move added in YAML alone works."""

import shutil
from textwrap import dedent

import pytest

from gminator.core.characters import create_character
from gminator.core.events import (
    CharacterCreated,
    ForwardChanged,
    GmMoveTriggered,
    HpChanged,
    MoveMade,
    QuestionsAsked,
    XpMarked,
)
from gminator.core.game import Game
from gminator.core.moves import resolve_move
from gminator.packs.loader import load_pack
from support import DUNGEON_WORLD, ScriptedDecider, seed_for

SCORES = {"str": 16, "con": 15, "dex": 13, "wis": 12, "int": 9, "cha": 8}
GOBLIN = CharacterCreated(
    character_id="goblin", name="Goblin", stats={}, max_hp=30, damage="d6", armor=1
)

BASIC_MOVES = {
    "hack_and_slash": ("str", True),
    "volley": ("dex", True),
    "defy_danger": ("dex", False),
    "defend": ("con", False),
    "spout_lore": ("int", False),
    "discern_realities": ("wis", False),
    "parley": ("cha", True),
    "aid_or_interfere": (None, True),
}
CLASS_MOVES = {
    "fighter": {"bend_bars_lift_gates": ("str", False)},
    "thief": {
        "tricks_of_the_trade": ("dex", False),
        "trap_expert": ("dex", False),
        "backstab": ("dex", True),
    },
}
MODIFIERS = {"str": 2, "con": 1, "dex": 1, "wis": 0, "int": 0, "cha": -1, None: 0}


def start(pack, class_id="fighter", band=None, stat=None, *, extra=(), gear_choices=None):
    seed = seed_for(band, MODIFIERS[stat]) if band else 0
    game = Game.new(seed)
    hero = create_character(pack, class_id, "pc", "Hero", SCORES, gear_choices=gear_choices)
    for event in (*hero, GOBLIN, *extra):
        game.record(event)
    return game


def make(game, pack, move_id, decider=None, target=False, **kwargs):
    return resolve_move(
        game,
        pack,
        move_id,
        "pc",
        decider or ScriptedDecider(),
        target_id="goblin" if target else None,
        **kwargs,
    )


def test_pack_credits_the_dungeon_world_srd(dungeon_world):
    assert dungeon_world.manifest.license == "CC-BY-3.0"
    assert "Sage LaTorra" in dungeon_world.manifest.attribution
    assert "Adam Koebel" in dungeon_world.manifest.attribution


def test_pack_has_every_basic_and_special_move(dungeon_world):
    categories = {move_id: move.category for move_id, move in dungeon_world.moves.items()}

    for move_id in BASIC_MOVES:
        assert categories[move_id] == "basic"
    assert categories["last_breath"] == categories["make_camp"] == "special"


def test_classes_list_their_moves(dungeon_world):
    for class_id, moves in CLASS_MOVES.items():
        assert set(moves) <= set(dungeon_world.classes[class_id].moves)
        assert all(dungeon_world.moves[move].category == "class" for move in moves)


@pytest.mark.parametrize("band", ["strong", "partial", "miss"])
@pytest.mark.parametrize("move_id", list(BASIC_MOVES))
def test_every_basic_move_resolves_in_every_band(dungeon_world, move_id, band):
    stat, needs_target = BASIC_MOVES[move_id]
    game = start(dungeon_world, "fighter", band, stat)
    kwargs = {"stat": "dex"} if move_id == "defy_danger" else {}

    resolution = make(game, dungeon_world, move_id, target=needs_target, **kwargs)

    assert resolution.band == band
    assert resolution.text
    assert isinstance(resolution.events[1], MoveMade)
    if band == "miss":
        assert XpMarked(character_id="pc", amount=1) in resolution.events
        assert GmMoveTriggered(severity="hard") in resolution.events


@pytest.mark.parametrize(
    ("class_id", "move_id"),
    [(class_id, move_id) for class_id, moves in CLASS_MOVES.items() for move_id in moves],
)
@pytest.mark.parametrize("band", ["strong", "partial", "miss"])
def test_every_class_move_resolves(dungeon_world, class_id, move_id, band):
    stat, needs_target = CLASS_MOVES[class_id][move_id]
    game = start(dungeon_world, class_id, band, stat)

    resolution = make(game, dungeon_world, move_id, target=needs_target)

    assert resolution.band == band


def test_hack_and_slash_partial_trades_blows(dungeon_world):
    game = start(dungeon_world, "fighter", "partial", "str")

    resolution = make(game, dungeon_world, "hack_and_slash", target=True)

    hurt = {e.character_id for e in resolution.events if isinstance(e, HpChanged)}
    assert hurt == {"goblin", "pc"}


def test_hack_and_slash_strong_can_trade_safety_for_extra_damage(dungeon_world):
    game = start(dungeon_world, "fighter", "strong", "str")

    resolution = make(game, dungeon_world, "hack_and_slash", ScriptedDecider([1]), target=True)

    hurt = {e.character_id for e in resolution.events if isinstance(e, HpChanged)}
    assert hurt == {"goblin", "pc"}


def test_defend_holds_and_hold_is_spent_to_strike_back(dungeon_world):
    game = start(dungeon_world, "fighter", "strong", "con")

    make(game, dungeon_world, "defend")
    assert game.state.characters["pc"].hold == {"defend": 3}

    resolution = make(game, dungeon_world, "defend_spend_hold", ScriptedDecider([3]), target=True)
    assert game.state.characters["pc"].hold == {"defend": 2}
    assert HpChanged(character_id="goblin", amount=0) in resolution.events  # level 1 vs armor 1


def test_discern_realities_strong_asks_three_questions(dungeon_world):
    game = start(dungeon_world, "fighter", "strong", "wis")

    resolution = make(game, dungeon_world, "discern_realities")

    asked = next(e for e in resolution.events if isinstance(e, QuestionsAsked))
    assert len(asked.questions) == 3


def test_volley_taking_several_shots_uses_ammo(dungeon_world):
    game = start(dungeon_world, "thief", "partial", "dex", gear_choices=[[0], [1], [0]])

    make(game, dungeon_world, "volley", ScriptedDecider([2]), target=True)

    inventory = game.state.characters["pc"].inventory
    arrows = next(p for p in inventory if p.item_id == "bundle_of_arrows")
    assert arrows.uses == 2


def test_aid_gives_the_target_forward(dungeon_world):
    game = start(dungeon_world, "fighter", "strong")

    resolution = make(game, dungeon_world, "aid_or_interfere", ScriptedDecider([0]), target=True)

    assert ForwardChanged(character_id="goblin", amount=1) in resolution.events


def test_last_breath_miss_kills(dungeon_world):
    game = start(dungeon_world, "fighter", "miss")

    make(game, dungeon_world, "last_breath")

    assert "dead" in game.state.characters["pc"].tags


def test_last_breath_strong_cheats_death(dungeon_world):
    game = start(dungeon_world, "fighter", "strong")

    make(game, dungeon_world, "last_breath")

    assert "dead" not in game.state.characters["pc"].tags


def test_make_camp_eats_a_ration_and_heals_half_max_hp(dungeon_world):
    game = start(dungeon_world, extra=[HpChanged(character_id="pc", amount=-20)])

    make(game, dungeon_world, "make_camp")

    pc = game.state.characters["pc"]
    assert pc.hp == 5 + 12
    rations = next(p for p in pc.inventory if p.item_id == "dungeon_rations")
    assert rations.uses == 4


def test_trap_expert_hold_is_spent_on_a_question(dungeon_world):
    game = start(dungeon_world, "thief", "strong", "dex")

    make(game, dungeon_world, "trap_expert")
    resolution = make(game, dungeon_world, "trap_expert_spend_hold")

    assert game.state.characters["pc"].hold == {"trap_expert": 2}
    assert any(isinstance(e, QuestionsAsked) for e in resolution.events)


def test_a_move_added_in_yaml_alone_works(tmp_path):
    pack_root = tmp_path / "dungeon-world"
    shutil.copytree(DUNGEON_WORLD, pack_root)
    (pack_root / "moves" / "shield_bash.yaml").write_text(
        dedent(
            """\
            id: shield_bash
            name: Shield Bash
            category: basic
            trigger: When you slam your shield into a foe
            target: true
            roll: stat.str
            outcomes:
              strong:
                text: They reel back.
                effects:
                  - deal_damage: {amount: "3"}
                  - add_forward: {amount: 1}
              partial:
                text: They reel, and so do you.
                effects:
                  - deal_damage: {amount: "3"}
                  - take_damage: {amount: "2"}
              miss:
                text: You bounce off.
            """
        ),
        encoding="utf-8",
    )
    pack = load_pack(pack_root)
    game = start(pack, "fighter", "strong", "str")

    resolution = make(game, pack, "shield_bash", target=True)

    assert resolution.band == "strong"
    assert game.state.characters["goblin"].hp == 30 - (3 - 1)
    assert game.state.characters["pc"].forward == 1
