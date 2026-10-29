import pytest

from gminator.core.events import (
    CharacterCreated,
    ChoiceMade,
    ClockCreated,
    DiceRolled,
    ForwardChanged,
    GmMoveTriggered,
    HoldChanged,
    ItemGained,
    MoveMade,
    QuestionsAsked,
    XpMarked,
)
from gminator.core.game import Game
from gminator.core.moves import ResolveError, resolve_move
from gminator.packs.models import Item, Manifest, Move, Pack, Tag
from support import ScriptedDecider, first_roll, seed_for

MANIFEST = Manifest(
    id="tiny",
    name="Tiny",
    version="0.1.0",
    license="CC0",
    attribution="Test",
    stats=["str", "dex"],
    modifiers=[{"up_to": 18, "modifier": 0}],
    miss_effects=[{"mark_xp": 1}],
)

ITEMS = [
    Item(id="bread", name="Bread", uses=2, tags=["ration"]),
    Item(id="cake", name="Cake", uses=1, tags=["ration"]),
    Item(id="mail", name="Mail", armor=2),
]
TAGS = [Tag(id="ration", description="Food"), Tag(id="dazed", description="Reeling")]

HERO = CharacterCreated(
    character_id="hero", name="Hero", stats={"str": 0, "dex": 2}, max_hp=20, damage="4"
)
RAT = CharacterCreated(character_id="rat", name="Rat", stats={}, max_hp=10, damage="3")


def rolled(*, roll="stat.str", strong=(), partial=(), miss=(), **fields) -> dict:
    return {
        "id": "test_move",
        "name": "Test Move",
        "category": "basic",
        "trigger": "When testing",
        "roll": roll,
        "outcomes": {
            "strong": {"text": "Strong.", "effects": list(strong)},
            "partial": {"text": "Partial.", "effects": list(partial)},
            "miss": {"text": "Miss.", "effects": list(miss)},
        },
        **fields,
    }


def unrolled(*effects, **fields) -> dict:
    return {
        "id": "test_move",
        "name": "Test Move",
        "category": "basic",
        "trigger": "When testing",
        "effects": list(effects),
        **fields,
    }


def pack_with(*moves: dict) -> Pack:
    parsed = [Move.model_validate(move) for move in moves]
    return Pack(
        manifest=MANIFEST,
        moves={move.id: move for move in parsed},
        items={item.id: item for item in ITEMS},
        tags={tag.id: tag for tag in TAGS},
    )


def new_game(*events, seed: int = 0) -> Game:
    game = Game.new(seed)
    for event in (HERO, RAT, *events):
        game.record(event)
    return game


def resolve(game, move: dict, decider=None, **kwargs):
    return resolve_move(
        game, pack_with(move), "test_move", "hero", decider or ScriptedDecider(), **kwargs
    )


def hp(game: Game, character_id: str) -> int:
    return game.state.characters[character_id].hp


# Rolling and bands


@pytest.mark.parametrize("band", ["strong", "partial", "miss"])
def test_roll_lands_in_the_band_its_total_falls_in(band):
    seed = seed_for(band)
    game = new_game(seed=seed)

    resolution = resolve(game, rolled())

    assert resolution.band == band
    assert resolution.total == first_roll(seed)


def test_roll_adds_the_stat_modifier():
    seed = seed_for("partial")
    game = new_game(seed=seed)

    resolution = resolve(game, rolled(roll="stat.dex"))

    assert resolution.total == first_roll(seed) + 2


def test_resolution_records_the_dice_and_the_move():
    seed = seed_for("partial")
    game = new_game(seed=seed)

    resolution = resolve(game, rolled())

    dice, made = resolution.events[:2]
    assert isinstance(dice, DiceRolled)
    assert [die.sides for die in dice.dice] == [6, 6]
    assert made == MoveMade(
        character_id="hero", move_id="test_move", total=resolution.total, band="partial"
    )


def test_resolution_events_are_appended_to_the_game():
    game = new_game()
    before = len(game.events)

    resolution = resolve(game, rolled())

    assert game.events[before:] == resolution.events


def test_resolution_carries_the_band_text():
    game = new_game(seed=seed_for("miss"))

    assert resolve(game, rolled()).text == "Miss."


def test_only_the_band_rolled_applies_its_effects():
    game = new_game(seed=seed_for("strong"))

    resolve(
        game,
        rolled(
            strong=[{"mark_xp": 5}],
            partial=[{"mark_xp": 50}],
            miss=[{"mark_xp": 500}],
        ),
    )

    assert game.state.characters["hero"].xp == 5


def test_a_miss_also_applies_the_pack_miss_effects():
    game = new_game(seed=seed_for("miss"))

    resolution = resolve(game, rolled(miss=[{"gm_move": "hard"}]))

    assert XpMarked(character_id="hero", amount=1) in resolution.events
    assert GmMoveTriggered(severity="hard") in resolution.events


def test_chosen_stat_is_rolled():
    seed = seed_for("partial")
    game = new_game(seed=seed)

    resolution = resolve(game, rolled(roll="stat.chosen", stat_options=["str", "dex"]), stat="dex")

    assert resolution.total == first_roll(seed) + 2


def test_move_with_stat_options_needs_a_stat():
    move = rolled(roll="stat.chosen", stat_options=["str", "dex"])

    with pytest.raises(ResolveError, match="stat"):
        resolve(new_game(), move)


def test_stat_must_be_one_the_move_offers():
    move = rolled(roll="stat.chosen", stat_options=["str"])

    with pytest.raises(ResolveError, match="dex"):
        resolve(new_game(), move, stat="dex")


def test_forward_is_added_to_the_next_roll_and_used_up():
    seed = seed_for("partial")
    game = new_game(ForwardChanged(character_id="hero", amount=1), seed=seed)

    resolution = resolve(game, rolled())

    assert resolution.total == first_roll(seed) + 1
    assert ForwardChanged(character_id="hero", amount=-1) in resolution.events
    assert game.state.characters["hero"].forward == 0


def test_unrolled_move_applies_its_effects_without_dice():
    game = new_game()

    resolution = resolve(game, unrolled({"mark_xp": 1}))

    assert resolution.band is None
    assert resolution.total is None
    assert resolution.events == (
        MoveMade(character_id="hero", move_id="test_move"),
        XpMarked(character_id="hero", amount=1),
    )


# Validation


def test_unknown_move_is_rejected():
    with pytest.raises(ResolveError, match="fly"):
        resolve_move(new_game(), pack_with(unrolled()), "fly", "hero", ScriptedDecider())


def test_unknown_actor_is_rejected():
    with pytest.raises(ResolveError, match="ghost"):
        resolve_move(new_game(), pack_with(unrolled()), "test_move", "ghost", ScriptedDecider())


def test_move_with_a_target_needs_one():
    with pytest.raises(ResolveError, match="target"):
        resolve(new_game(), unrolled(target=True))


def test_target_must_exist():
    with pytest.raises(ResolveError, match="owl"):
        resolve(new_game(), unrolled(target=True), target_id="owl")


def test_move_without_a_target_refuses_one():
    with pytest.raises(ResolveError, match="target"):
        resolve(new_game(), unrolled(), target_id="rat")


def test_target_is_recorded_on_the_move():
    resolution = resolve(new_game(), unrolled(target=True), target_id="rat")

    assert resolution.events[0].target_id == "rat"


def test_failed_resolution_records_nothing():
    game = new_game()
    events_before = game.events

    with pytest.raises(ResolveError):
        resolve(game, unrolled({"mark_xp": 1}, {"spend_hold": {"move": "test_move"}}))

    assert game.events == events_before


# Effects


def test_deal_damage_hurts_the_target():
    game = new_game()

    resolve(
        game, unrolled({"deal_damage": {"amount": "self.damage"}}, target=True), target_id="rat"
    )

    assert hp(game, "rat") == 6


def test_damage_rolls_dice_and_records_them():
    game = new_game()

    resolution = resolve(
        game, unrolled({"deal_damage": {"amount": "d6 + 1"}}, target=True), target_id="rat"
    )

    damage = next(event for event in resolution.events if isinstance(event, DiceRolled))
    assert [die.sides for die in damage.dice] == [6]
    assert hp(game, "rat") == 10 - damage.total


def test_armor_reduces_damage():
    armored_rat = RAT.model_copy(update={"armor": 1})
    game = Game.new(0)
    for event in (HERO, armored_rat):
        game.record(event)

    resolve(game, unrolled({"deal_damage": {"amount": "5"}}, target=True), target_id="rat")

    assert hp(game, "rat") == 6


def test_armor_from_carried_gear_adds_up():
    game = new_game(ItemGained(character_id="rat", item_id="mail"))

    resolve(game, unrolled({"deal_damage": {"amount": "5"}}, target=True), target_id="rat")

    assert hp(game, "rat") == 7


def test_armor_cannot_turn_damage_into_healing():
    game = new_game(ItemGained(character_id="rat", item_id="mail"))

    resolve(game, unrolled({"deal_damage": {"amount": "1"}}, target=True), target_id="rat")

    assert hp(game, "rat") == 10


def test_deal_damage_can_hit_the_actor():
    game = new_game()

    resolve(game, unrolled({"deal_damage": {"amount": "2", "target": "self"}}))

    assert hp(game, "hero") == 18


def test_take_damage_hurts_the_actor_with_the_targets_damage():
    game = new_game()

    resolve(
        game, unrolled({"take_damage": {"amount": "target.damage"}}, target=True), target_id="rat"
    )

    assert hp(game, "hero") == 17


def test_heal_restores_hp():
    game = new_game()
    resolve(game, unrolled({"take_damage": {"amount": "15"}}))

    resolve(game, unrolled({"heal": {"amount": "self.max_hp / 2"}}))

    assert hp(game, "hero") == 15


def test_choice_applies_only_the_chosen_options():
    game = new_game()
    choose = {
        "choose_n": {
            "n": 2,
            "options": [
                {"label": "One", "effects": [{"mark_xp": 1}]},
                {"label": "Ten", "effects": [{"mark_xp": 10}]},
                {"label": "Hundred", "effects": [{"mark_xp": 100}]},
            ],
        }
    }

    resolution = resolve(game, unrolled(choose), ScriptedDecider([2, 0]))

    assert game.state.characters["hero"].xp == 101
    assert ChoiceMade(character_id="hero", move_id="test_move", chosen=["Hundred", "One"]) in (
        resolution.events
    )


def test_choice_asks_the_decider_with_labels_and_count():
    decider = ScriptedDecider()
    choose = {"choose_n": {"n": 1, "options": [{"label": "Left"}, {"label": "Right"}]}}

    resolve(new_game(), unrolled(choose), decider)

    assert decider.calls == [("Test Move", ["Left", "Right"], 1)]


@pytest.mark.parametrize(
    "picks", [[0], [0, 0], [0, 5], [-1, 0]], ids=["too-few", "repeat", "out-of-range", "negative"]
)
def test_invalid_decision_is_rejected(picks):
    choose = {"choose_n": {"n": 2, "options": [{"label": "A"}, {"label": "B"}, {"label": "C"}]}}

    with pytest.raises(ResolveError, match="choose"):
        resolve(new_game(), unrolled(choose), ScriptedDecider(picks))


def test_asked_questions_are_recorded():
    ask = {"ask_questions": {"n": 2, "questions": ["Who?", "What?", "Why?"]}}

    resolution = resolve(new_game(), unrolled(ask), ScriptedDecider([1, 2]))

    assert QuestionsAsked(character_id="hero", questions=["What?", "Why?"]) in resolution.events


def test_hold_is_gained_for_the_move():
    game = new_game()

    resolve(game, unrolled({"gain_hold": {"amount": 3}}))

    assert game.state.characters["hero"].hold == {"test_move": 3}


def test_hold_is_spent_from_the_named_move():
    game = new_game(HoldChanged(character_id="hero", move_id="defend", amount=2))

    resolve(game, unrolled({"spend_hold": {"move": "defend"}}))

    assert game.state.characters["hero"].hold == {"defend": 1}


def test_spending_hold_you_lack_is_rejected():
    with pytest.raises(ResolveError, match="defend"):
        resolve(new_game(), unrolled({"spend_hold": {"move": "defend", "amount": 1}}))


def test_tags_are_added_and_removed():
    game = new_game()

    resolve(
        game,
        unrolled({"add_tag": {"tag": "dazed", "target": "target"}}, target=True),
        target_id="rat",
    )
    assert game.state.characters["rat"].tags == ("dazed",)

    resolve(
        game,
        unrolled({"remove_tag": {"tag": "dazed", "target": "target"}}, target=True),
        target_id="rat",
    )
    assert game.state.characters["rat"].tags == ()


def test_tag_target_defaults_to_the_actor():
    game = new_game()

    resolve(game, unrolled({"add_tag": {"tag": "dazed"}}))

    assert game.state.characters["hero"].tags == ("dazed",)


def test_clock_advances():
    game = new_game(ClockCreated(clock_id="doom", label="Doom", segments=4))

    resolve(game, unrolled({"advance_clock": {"clock": "doom", "amount": 2}}))

    assert game.state.clocks["doom"].filled == 2


def test_advancing_a_missing_clock_is_rejected():
    with pytest.raises(ResolveError, match="doom"):
        resolve(new_game(), unrolled({"advance_clock": {"clock": "doom"}}))


def test_gm_move_is_recorded():
    resolution = resolve(new_game(), unrolled({"gm_move": "soft"}))

    assert GmMoveTriggered(severity="soft") in resolution.events


def test_xp_is_marked():
    game = new_game()

    resolve(game, unrolled({"mark_xp": 2}))

    assert game.state.characters["hero"].xp == 2


def test_forward_can_be_given_to_the_target():
    game = new_game()

    resolve(
        game,
        unrolled({"add_forward": {"amount": -2, "target": "target"}}, target=True),
        target_id="rat",
    )

    assert game.state.characters["rat"].forward == -2


def test_using_an_item_spends_the_first_with_the_tag():
    game = new_game(
        ItemGained(character_id="hero", item_id="mail"),
        ItemGained(character_id="hero", item_id="cake", uses=1),
        ItemGained(character_id="hero", item_id="bread", uses=2),
    )

    resolve(game, unrolled({"use_item": {"tag": "ration"}}))

    assert [p.item_id for p in game.state.characters["hero"].inventory] == ["mail", "bread"]


def test_using_an_item_you_lack_is_rejected():
    with pytest.raises(ResolveError, match="ration"):
        resolve(new_game(), unrolled({"use_item": {"tag": "ration"}}))
