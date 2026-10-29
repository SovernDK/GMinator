import pytest
from pydantic import ValidationError

from gminator.packs.models import (
    ChooseN,
    DealDamage,
    GmMove,
    Manifest,
    MarkXp,
    Move,
)

ROLLED = {
    "id": "hack_and_slash",
    "name": "Hack and Slash",
    "category": "basic",
    "trigger": "When you attack an enemy in melee",
    "target": True,
    "roll": "stat.str",
    "outcomes": {
        "strong": {"effects": [{"deal_damage": {"amount": "self.damage"}}]},
        "partial": {"text": "You trade blows."},
        "miss": {"effects": [{"gm_move": "hard"}]},
    },
}

UNROLLED = {
    "id": "make_camp",
    "name": "Make Camp",
    "category": "special",
    "trigger": "When you settle in to rest",
    "effects": [{"mark_xp": 1}],
}

MANIFEST = {
    "id": "tiny",
    "name": "Tiny",
    "version": "0.1.0",
    "license": "CC0",
    "attribution": "Test",
    "stats": ["str", "dex"],
    "modifiers": [{"up_to": 8, "modifier": -1}, {"up_to": 12, "modifier": 0}],
}


def with_changes(base: dict, **changes) -> dict:
    return {**base, **changes}


def test_effects_parse_from_single_key_mappings():
    move = Move.model_validate(ROLLED)

    assert isinstance(move.outcomes.strong.effects[0], DealDamage)
    assert isinstance(move.outcomes.miss.effects[0], GmMove)
    assert move.outcomes.miss.effects[0].gm_move == "hard"


def test_scalar_shorthand_effects_parse():
    move = Move.model_validate(UNROLLED)

    assert move.effects == [MarkXp(mark_xp=1)]


def test_effect_target_defaults_to_the_move_target():
    move = Move.model_validate(ROLLED)

    assert move.outcomes.strong.effects[0].deal_damage.target == "target"


def test_nested_choice_effects_parse():
    move = Move.model_validate(
        with_changes(
            UNROLLED,
            effects=[
                {
                    "choose_n": {
                        "n": 1,
                        "options": [
                            {"label": "Rest", "effects": [{"mark_xp": 1}]},
                            {"label": "Watch"},
                        ],
                    }
                }
            ],
        )
    )

    choice = move.effects[0]
    assert isinstance(choice, ChooseN)
    assert choice.choose_n.options[0].effects == [MarkXp(mark_xp=1)]
    assert choice.choose_n.options[1].effects == []


def test_unknown_effect_is_rejected_naming_the_known_ones():
    with pytest.raises(ValidationError, match="deal_damage"):
        Move.model_validate(with_changes(UNROLLED, effects=[{"summon_dragon": {}}]))


def test_effect_with_two_keys_is_rejected():
    with pytest.raises(ValidationError):
        Move.model_validate(with_changes(UNROLLED, effects=[{"mark_xp": 1, "gm_move": "hard"}]))


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError, match="dammage"):
        Move.model_validate(with_changes(UNROLLED, dammage="d6"))


def test_invalid_expression_is_rejected():
    with pytest.raises(ValidationError, match="invalid expression"):
        Move.model_validate(with_changes(UNROLLED, effects=[{"deal_damage": {"amount": "d6 +"}}]))


def test_rolled_move_needs_outcomes():
    with pytest.raises(ValidationError, match="outcomes"):
        Move.model_validate(with_changes(ROLLED, outcomes=None))


def test_rolled_move_needs_every_band():
    outcomes = {"strong": {}, "partial": {}}

    with pytest.raises(ValidationError, match="miss"):
        Move.model_validate(with_changes(ROLLED, outcomes=outcomes))


def test_rolled_move_cannot_also_have_flat_effects():
    with pytest.raises(ValidationError, match="effects"):
        Move.model_validate(with_changes(ROLLED, effects=[{"mark_xp": 1}]))


def test_unrolled_move_cannot_have_outcomes():
    with pytest.raises(ValidationError, match="outcomes"):
        Move.model_validate(with_changes(UNROLLED, outcomes=ROLLED["outcomes"]))


def test_stat_options_need_a_roll():
    with pytest.raises(ValidationError, match="stat_options"):
        Move.model_validate(with_changes(UNROLLED, stat_options=["str"]))


def test_choice_cannot_ask_for_more_than_its_options():
    choose_three = {"choose_n": {"n": 3, "options": [{"label": "a"}, {"label": "b"}]}}

    with pytest.raises(ValidationError, match="3"):
        Move.model_validate(with_changes(UNROLLED, effects=[choose_three]))


def test_question_count_cannot_exceed_the_questions():
    ask_two = {"ask_questions": {"n": 2, "questions": ["Who?"]}}

    with pytest.raises(ValidationError, match="2"):
        Move.model_validate(with_changes(UNROLLED, effects=[ask_two]))


@pytest.mark.parametrize("move_id", ["Hack and Slash", "hack-and-slash", "1st_move", ""])
def test_ids_are_snake_case(move_id):
    with pytest.raises(ValidationError):
        Move.model_validate(with_changes(UNROLLED, id=move_id))


def test_manifest_defaults_to_pbta_roll_and_bands():
    manifest = Manifest.model_validate(MANIFEST)

    assert manifest.roll == "2d6"
    assert (manifest.bands.strong, manifest.bands.partial) == (10, 7)


def test_strong_band_must_start_above_partial():
    with pytest.raises(ValidationError, match="strong"):
        Manifest.model_validate(with_changes(MANIFEST, bands={"strong": 7, "partial": 7}))


@pytest.mark.parametrize(
    ("total", "band"),
    [(13, "strong"), (10, "strong"), (9, "partial"), (7, "partial"), (6, "miss"), (-2, "miss")],
)
def test_band_for_total(total, band):
    assert Manifest.model_validate(MANIFEST).band(total) == band


@pytest.mark.parametrize(("score", "modifier"), [(1, -1), (8, -1), (9, 0), (12, 0)])
def test_modifier_for_score(score, modifier):
    assert Manifest.model_validate(MANIFEST).modifier(score) == modifier


def test_score_above_the_modifier_table_is_rejected():
    with pytest.raises(ValueError, match="13"):
        Manifest.model_validate(MANIFEST).modifier(13)


def test_modifier_table_must_ascend():
    steps = [{"up_to": 12, "modifier": 0}, {"up_to": 8, "modifier": -1}]

    with pytest.raises(ValidationError, match="ascend"):
        Manifest.model_validate(with_changes(MANIFEST, modifiers=steps))
