import pytest

from gminator.core.events import (
    CharacterCreated,
    CharacterMoved,
    ChoiceMade,
    ClockAdvanced,
    ClockCreated,
    DiceRolled,
    DieRoll,
    ForwardChanged,
    GameEnded,
    GameStarted,
    GmMoveMade,
    GmMoveTriggered,
    HoldChanged,
    HpChanged,
    ItemGained,
    ItemUsed,
    MoveMade,
    QuestionsAsked,
    SecretRevealed,
    TagAdded,
    TagRemoved,
    XpMarked,
)
from gminator.core.state import Possession, ReplayError, apply, replay

START = GameStarted(seed=12)
FIGHTER = CharacterCreated(character_id="pc", name="Brakka", stats={"str": 2, "dex": 0}, max_hp=18)


def test_game_start_records_seed_with_nothing_else():
    state = replay([START])

    assert state.seed == 12
    assert state.rng_position == 0
    assert state.characters == {}
    assert state.clocks == {}


def test_character_starts_at_full_hp_without_xp():
    pc = replay([START, FIGHTER]).characters["pc"]

    assert pc.name == "Brakka"
    assert pc.stats == {"str": 2, "dex": 0}
    assert (pc.hp, pc.max_hp, pc.xp) == (18, 18, 0)


def test_hp_changes_accumulate():
    state = replay(
        [
            START,
            FIGHTER,
            HpChanged(character_id="pc", amount=-5),
            HpChanged(character_id="pc", amount=-3),
        ]
    )

    assert state.characters["pc"].hp == 10


def test_hp_does_not_drop_below_zero():
    state = replay([START, FIGHTER, HpChanged(character_id="pc", amount=-30)])

    assert state.characters["pc"].hp == 0


def test_healing_does_not_exceed_max_hp():
    state = replay(
        [
            START,
            FIGHTER,
            HpChanged(character_id="pc", amount=-5),
            HpChanged(character_id="pc", amount=10),
        ]
    )

    assert state.characters["pc"].hp == 18


def test_xp_accumulates():
    state = replay(
        [
            START,
            FIGHTER,
            XpMarked(character_id="pc", amount=1),
            XpMarked(character_id="pc", amount=2),
        ]
    )

    assert state.characters["pc"].xp == 3


def test_dice_rolled_advances_rng_position_by_number_of_dice():
    two_dice = DiceRolled(
        expression="2d6", dice=[DieRoll(sides=6, value=3), DieRoll(sides=6, value=6)], total=9
    )
    one_die = DiceRolled(expression="d10", dice=[DieRoll(sides=10, value=2)], total=2)

    assert replay([START, two_dice, one_die]).rng_position == 3


def test_clock_starts_empty():
    state = replay([START, ClockCreated(clock_id="swarm", label="The swarm grows", segments=4)])

    clock = state.clocks["swarm"]
    assert (clock.label, clock.segments, clock.filled) == ("The swarm grows", 4, 0)


def test_clock_fills_but_not_past_its_segments():
    state = replay(
        [
            START,
            ClockCreated(clock_id="swarm", label="The swarm grows", segments=4),
            ClockAdvanced(clock_id="swarm", amount=3),
            ClockAdvanced(clock_id="swarm", amount=3),
        ]
    )

    assert state.clocks["swarm"].filled == 4


def test_apply_leaves_the_previous_state_untouched():
    before = replay([START, FIGHTER])

    after = apply(before, HpChanged(character_id="pc", amount=-4))

    assert before.characters["pc"].hp == 18
    assert after.characters["pc"].hp == 14


def test_empty_log_cannot_be_replayed():
    with pytest.raises(ReplayError):
        replay([])


def test_log_must_begin_with_game_started():
    with pytest.raises(ReplayError, match="game_started"):
        replay([FIGHTER])


def test_game_cannot_start_twice():
    with pytest.raises(ReplayError):
        replay([START, GameStarted(seed=13)])


def test_character_ids_are_unique():
    with pytest.raises(ReplayError, match="pc"):
        replay([START, FIGHTER, FIGHTER])


@pytest.mark.parametrize(
    "event",
    [
        HpChanged(character_id="ghost", amount=-1),
        XpMarked(character_id="ghost", amount=1),
        TagAdded(character_id="ghost", tag="dead"),
        TagRemoved(character_id="ghost", tag="dead"),
        HoldChanged(character_id="ghost", move_id="defend", amount=1),
        ForwardChanged(character_id="ghost", amount=1),
        ItemGained(character_id="ghost", item_id="dagger"),
        ItemUsed(character_id="ghost", item_id="dagger"),
        CharacterMoved(character_id="ghost", location_id="cellar"),
    ],
    ids=lambda event: event.type,
)
def test_events_for_unknown_character_are_rejected(event):
    with pytest.raises(ReplayError, match="ghost"):
        replay([START, FIGHTER, event])


def test_clock_ids_are_unique():
    clock = ClockCreated(clock_id="swarm", label="The swarm grows", segments=4)

    with pytest.raises(ReplayError, match="swarm"):
        replay([START, clock, clock])


def test_advancing_unknown_clock_is_rejected():
    with pytest.raises(ReplayError, match="doom"):
        replay([START, ClockAdvanced(clock_id="doom", amount=1)])


def test_character_keeps_class_damage_armor_and_level():
    created = CharacterCreated(
        character_id="pc",
        name="Brakka",
        stats={},
        max_hp=18,
        class_id="fighter",
        damage="d10",
        armor=1,
        level=2,
    )

    pc = replay([START, created]).characters["pc"]

    assert (pc.class_id, pc.damage, pc.armor, pc.level) == ("fighter", "d10", 1, 2)
    assert (pc.tags, pc.hold, pc.forward, pc.inventory) == ((), {}, 0, ())


def test_tag_is_added_once():
    state = replay(
        [
            START,
            FIGHTER,
            TagAdded(character_id="pc", tag="dead"),
            TagAdded(character_id="pc", tag="dead"),
        ]
    )

    assert state.characters["pc"].tags == ("dead",)


def test_tag_is_removed():
    state = replay(
        [
            START,
            FIGHTER,
            TagAdded(character_id="pc", tag="dead"),
            TagRemoved(character_id="pc", tag="dead"),
        ]
    )

    assert state.characters["pc"].tags == ()


def test_removing_an_absent_tag_changes_nothing():
    state = replay([START, FIGHTER, TagRemoved(character_id="pc", tag="dead")])

    assert state.characters["pc"].tags == ()


def test_hold_accumulates_per_move():
    state = replay(
        [
            START,
            FIGHTER,
            HoldChanged(character_id="pc", move_id="defend", amount=3),
            HoldChanged(character_id="pc", move_id="trap_expert", amount=1),
            HoldChanged(character_id="pc", move_id="defend", amount=-1),
        ]
    )

    assert state.characters["pc"].hold == {"defend": 2, "trap_expert": 1}


def test_hold_spent_to_zero_is_gone():
    state = replay(
        [
            START,
            FIGHTER,
            HoldChanged(character_id="pc", move_id="defend", amount=1),
            HoldChanged(character_id="pc", move_id="defend", amount=-1),
        ]
    )

    assert state.characters["pc"].hold == {}


def test_hold_cannot_go_below_zero():
    with pytest.raises(ReplayError, match="defend"):
        replay([START, FIGHTER, HoldChanged(character_id="pc", move_id="defend", amount=-1)])


def test_forward_accumulates():
    state = replay(
        [
            START,
            FIGHTER,
            ForwardChanged(character_id="pc", amount=1),
            ForwardChanged(character_id="pc", amount=-2),
        ]
    )

    assert state.characters["pc"].forward == -1


def test_items_are_kept_in_the_order_gained():
    state = replay(
        [
            START,
            FIGHTER,
            ItemGained(character_id="pc", item_id="rations", uses=5),
            ItemGained(character_id="pc", item_id="sword"),
        ]
    )

    assert state.characters["pc"].inventory == (
        Possession(item_id="rations", uses=5),
        Possession(item_id="sword", uses=None),
    )


def test_using_an_item_counts_down_the_first_one_with_uses_left():
    state = replay(
        [
            START,
            FIGHTER,
            ItemGained(character_id="pc", item_id="potion", uses=1),
            ItemGained(character_id="pc", item_id="rations", uses=5),
            ItemGained(character_id="pc", item_id="rations", uses=5),
            ItemUsed(character_id="pc", item_id="rations"),
        ]
    )

    assert state.characters["pc"].inventory == (
        Possession(item_id="potion", uses=1),
        Possession(item_id="rations", uses=4),
        Possession(item_id="rations", uses=5),
    )


def test_item_is_gone_when_its_last_use_is_spent():
    state = replay(
        [
            START,
            FIGHTER,
            ItemGained(character_id="pc", item_id="potion", uses=1),
            ItemUsed(character_id="pc", item_id="potion"),
        ]
    )

    assert state.characters["pc"].inventory == ()


@pytest.mark.parametrize("item_id", ["sword", "rope"], ids=["no-uses", "not-carried"])
def test_item_without_uses_cannot_be_used(item_id):
    with pytest.raises(ReplayError, match=item_id):
        replay(
            [
                START,
                FIGHTER,
                ItemGained(character_id="pc", item_id="sword"),
                ItemUsed(character_id="pc", item_id=item_id),
            ]
        )


@pytest.mark.parametrize(
    "event",
    [
        MoveMade(character_id="pc", move_id="defy_danger", total=8, band="partial"),
        ChoiceMade(character_id="pc", move_id="volley", chosen=["Take several shots"]),
        QuestionsAsked(character_id="pc", questions=["What is about to happen?"]),
        GmMoveTriggered(severity="soft"),
        GmMoveMade(gm_move_id="show_signs"),
    ],
    ids=lambda event: event.type,
)
def test_records_of_what_happened_do_not_change_state(event):
    before = replay([START, FIGHTER])

    assert apply(before, event) == before


def test_character_starts_nowhere_and_moves_between_locations():
    state = replay(
        [
            START,
            FIGHTER,
            CharacterMoved(character_id="pc", location_id="cellar"),
            CharacterMoved(character_id="pc", location_id="tunnel"),
        ]
    )

    assert replay([START, FIGHTER]).characters["pc"].location is None
    assert state.characters["pc"].location == "tunnel"


def test_revealed_secrets_are_kept_once_in_the_order_revealed():
    state = replay(
        [
            START,
            SecretRevealed(secret_id="wererat"),
            SecretRevealed(secret_id="ledger"),
            SecretRevealed(secret_id="wererat"),
        ]
    )

    assert replay([START]).revealed == ()
    assert state.revealed == ("wererat", "ledger")


def test_game_ends_with_its_ending():
    assert replay([START]).ending is None
    assert replay([START, GameEnded(ending_id="fled")]).ending == "fled"


@pytest.mark.parametrize(
    "event",
    [
        HpChanged(character_id="pc", amount=-1),
        DiceRolled(expression="d6", dice=[DieRoll(sides=6, value=2)], total=2),
        GameEnded(ending_id="fled"),
    ],
    ids=lambda event: event.type,
)
def test_nothing_happens_after_the_game_ends(event):
    with pytest.raises(ReplayError, match="ended"):
        replay([START, FIGHTER, GameEnded(ending_id="killed"), event])
