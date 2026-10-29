"""The pack expression language: dice, references, arithmetic, min/max and comparisons.

Division (`/`) rounds down, as in "half your max HP".

Sources are parsed with Lark into a small node tree; nothing is ever run with `eval`.
"""

import operator
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from lark import Lark, Token, Transformer, v_args
from lark.exceptions import UnexpectedInput, VisitError

from gminator.core.dice import Dice

Refs = Mapping[str, "int | str"]

_GRAMMAR = r"""
?start: comparison

?comparison: sum
           | sum COMPARE sum      -> compare

?sum: product
    | sum "+" product             -> add
    | sum "-" product             -> sub

?product: unary
        | product "*" unary       -> mul
        | product "/" unary       -> div

?unary: atom
      | "-" unary                 -> neg

?atom: INT                        -> number
     | DICE                       -> dice
     | BEST                       -> best
     | WORST                      -> worst
     | NAME "(" [comparison ("," comparison)*] ")" -> call
     | NAME ("." NAME)*           -> ref
     | "(" comparison ")"

COMPARE: "<=" | ">=" | "==" | "!=" | "<" | ">"
DICE.2: /\d*d\d+\b/
BEST.2: /b\[\d*d\d+\]/
WORST.2: /w\[\d*d\d+\]/
NAME: /[A-Za-z_][A-Za-z0-9_]*/

%import common.INT
%import common.WS
%ignore WS
"""

_PARSER = Lark(_GRAMMAR, parser="lalr")
_DICE = re.compile(r"(\d*)d(\d+)")

_COMPARISONS: dict[str, Callable[[int, int], bool]] = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}
_FUNCTIONS: dict[str, Callable[..., int]] = {"min": min, "max": max}


class ExpressionError(ValueError):
    def __init__(self, message: str, column: int | None = None) -> None:
        super().__init__(message)
        self.column = column


@dataclass
class _Context:
    dice: Dice
    refs: Refs
    resolving: tuple[str, ...] = field(default=())


class _Node:
    def eval(self, ctx: _Context) -> int:
        raise NotImplementedError


@dataclass(frozen=True)
class _Number(_Node):
    value: int

    def eval(self, ctx: _Context) -> int:
        return self.value


@dataclass(frozen=True)
class _Roll(_Node):
    count: int
    sides: int
    keep: Callable[[list[int]], int]

    def eval(self, ctx: _Context) -> int:
        return self.keep([ctx.dice.roll(self.sides) for _ in range(self.count)])


@dataclass(frozen=True)
class _Ref(_Node):
    name: str

    def eval(self, ctx: _Context) -> int:
        if self.name not in ctx.refs:
            raise ExpressionError(f"unknown reference {self.name!r}")
        if self.name in ctx.resolving:
            chain = " -> ".join((*ctx.resolving, self.name))
            raise ExpressionError(f"circular reference: {chain}")
        value = ctx.refs[self.name]
        if isinstance(value, str):
            inner = _Context(ctx.dice, ctx.refs, (*ctx.resolving, self.name))
            return parse(value)._root.eval(inner)
        return value


@dataclass(frozen=True)
class _Apply(_Node):
    function: Callable[..., int]
    args: tuple[_Node, ...]

    def eval(self, ctx: _Context) -> int:
        return self.function(*(arg.eval(ctx) for arg in self.args))


def _divide(left: int, right: int) -> int:
    if right == 0:
        raise ExpressionError("division by zero")
    return left // right


def _roll(token: Token, keep: Callable[[list[int]], int]) -> _Roll:
    match = _DICE.search(token)
    assert match is not None
    count = int(match.group(1) or 1)
    sides = int(match.group(2))
    if count < 1 or sides < 1:
        raise ExpressionError(f"{token!s} rolls no dice", token.column)
    return _Roll(count, sides, keep)


@v_args(inline=True)
class _Compile(Transformer):
    def __init__(self) -> None:
        super().__init__()
        self.references: set[str] = set()

    def number(self, token: Token) -> _Node:
        return _Number(int(token))

    def dice(self, token: Token) -> _Node:
        return _roll(token, sum)

    def best(self, token: Token) -> _Node:
        return _roll(token, max)

    def worst(self, token: Token) -> _Node:
        return _roll(token, min)

    def ref(self, *names: Token) -> _Node:
        name = ".".join(names)
        self.references.add(name)
        return _Ref(name)

    def call(self, name: Token, *args: _Node | None) -> _Node:
        if name not in _FUNCTIONS:
            raise ExpressionError(f"unknown function {name!s}", name.column)
        present = tuple(arg for arg in args if arg is not None)
        if not present:
            raise ExpressionError(f"{name!s}() needs at least one argument", name.column)
        return _Apply(_FUNCTIONS[name], present)

    def neg(self, operand: _Node) -> _Node:
        return _Apply(operator.neg, (operand,))

    def add(self, left: _Node, right: _Node) -> _Node:
        return _Apply(operator.add, (left, right))

    def sub(self, left: _Node, right: _Node) -> _Node:
        return _Apply(operator.sub, (left, right))

    def mul(self, left: _Node, right: _Node) -> _Node:
        return _Apply(operator.mul, (left, right))

    def div(self, left: _Node, right: _Node) -> _Node:
        return _Apply(_divide, (left, right))

    def compare(self, left: _Node, op: Token, right: _Node) -> _Node:
        return _Apply(_COMPARISONS[op], (left, right))


class Expression:
    def __init__(self, source: str, root: _Node, references: frozenset[str]) -> None:
        self.source = source
        self.references = references
        self._root = root

    def evaluate(self, dice: Dice, refs: Refs) -> int:
        """Evaluate, rolling fresh dice. Comparisons yield bools."""
        return self._root.eval(_Context(dice, refs))

    def __repr__(self) -> str:
        return f"Expression({self.source!r})"


def parse(source: str) -> Expression:
    try:
        tree = _PARSER.parse(source)
    except UnexpectedInput as error:
        column = error.column if error.column > 0 else None
        raise ExpressionError(f"invalid expression {source!r}", column) from error
    compiler = _Compile()
    try:
        return Expression(source, compiler.transform(tree), frozenset(compiler.references))
    except VisitError as error:
        if isinstance(error.orig_exc, ExpressionError):
            raise error.orig_exc from None
        raise
