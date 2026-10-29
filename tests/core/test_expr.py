import pytest

from gminator.core.expr import ExpressionError, parse


class ScriptedDice:
    """Returns pre-set results in order and records which dice were asked for."""

    def __init__(self, *results: int) -> None:
        self._results = list(results)
        self.sides_rolled: list[int] = []

    def roll(self, sides: int) -> int:
        self.sides_rolled.append(sides)
        result = self._results.pop(0)
        assert 1 <= result <= sides, f"scripted {result} cannot come from a d{sides}"
        return result


def evaluate(source: str, *results: int, refs=None):
    return parse(source).evaluate(ScriptedDice(*results), refs or {})


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("7", 7),
        ("2 + 3", 5),
        ("10 - 4 - 3", 3),
        ("2 + 3 * 4", 14),
        ("(2 + 3) * 4", 20),
        ("-3 + 5", 2),
        ("2 * -3", -6),
        ("7 / 2", 3),
        ("18 / 2 + 1", 10),
        ("2 + 9 / 3", 5),
        ("min(3, 1, 2)", 1),
        ("max(1, 4)", 4),
        ("max(1, 2) + min(5, 6)", 7),
        ("3 > 2", True),
        ("3 >= 4", False),
        ("1 < 2", True),
        ("2 <= 2", True),
        ("2 == 2", True),
        ("2 != 2", False),
        ("1 + 1 == 2", True),
    ],
)
def test_arithmetic_and_comparisons(source, expected):
    assert evaluate(source) == expected


def test_dice_term_sums_each_die():
    dice = ScriptedDice(3, 5)

    assert parse("2d6").evaluate(dice, {}) == 8
    assert dice.sides_rolled == [6, 6]


def test_dice_count_defaults_to_one():
    dice = ScriptedDice(5)

    assert parse("d8").evaluate(dice, {}) == 5
    assert dice.sides_rolled == [8]


def test_best_of_keeps_highest_die():
    assert evaluate("b[2d8]", 2, 7) == 7


def test_worst_of_keeps_lowest_die():
    assert evaluate("w[2d8]", 2, 7) == 2


def test_dice_combine_with_arithmetic():
    assert evaluate("2d6 + 1", 4, 4) == 9


def test_parsed_expression_rolls_fresh_on_each_evaluation():
    expression = parse("d6")

    assert expression.evaluate(ScriptedDice(2), {}) == 2
    assert expression.evaluate(ScriptedDice(5), {}) == 5


def test_division_by_zero_is_an_error():
    with pytest.raises(ExpressionError, match="zero"):
        evaluate("4 / stat.str", refs={"stat.str": 0})


def test_references_lists_every_name_used():
    expression = parse("stat.str + max(self.damage, target.armor) - forward + d6")

    assert expression.references == {"stat.str", "self.damage", "target.armor", "forward"}


def test_expression_without_references_has_none():
    assert parse("2d6 + 1").references == frozenset()


def test_reference_reads_value_from_refs():
    assert evaluate("stat.str + 1", refs={"stat.str": 2}) == 3


def test_reference_to_negative_value():
    assert evaluate("2d6 + stat.dex", 3, 3, refs={"stat.dex": -1}) == 5


def test_reference_to_expression_string_is_evaluated():
    dice = ScriptedDice(7)

    assert parse("class.damage + 1").evaluate(dice, {"class.damage": "d10"}) == 8
    assert dice.sides_rolled == [10]


def test_unknown_reference_is_an_error():
    with pytest.raises(ExpressionError, match=r"stat\.wis"):
        evaluate("stat.wis", refs={"stat.str": 1})


def test_circular_references_are_an_error():
    with pytest.raises(ExpressionError, match="circular"):
        evaluate("a.x", refs={"a.x": "b.x", "b.x": "a.x"})


def test_invalid_expression_inside_a_reference_is_an_error():
    with pytest.raises(ExpressionError):
        evaluate("class.damage", refs={"class.damage": "d10 +"})


@pytest.mark.parametrize(
    "source",
    [
        "",
        "2 +",
        "1 + * 2",
        "(1 + 2",
        "2d",
        "0d6",
        "2d0",
        "b[2]",
        "1 < 2 < 3",
        "stat..str",
        "foo(1)",
        "min()",
        "__import__('os')",
        "1; 2",
    ],
)
def test_invalid_source_is_rejected_at_parse_time(source):
    with pytest.raises(ExpressionError):
        parse(source)


def test_syntax_error_reports_column():
    with pytest.raises(ExpressionError) as error:
        parse("2 + * 3")

    assert error.value.column == 5
