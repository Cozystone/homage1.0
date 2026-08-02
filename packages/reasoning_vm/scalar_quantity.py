"""Closed exact scalar quantities and rational-v1 dimension checking.

This module is deliberately parallel to :mod:`packages.reasoning_vm.quantity`.
The existing quantity module is part of the sealed atomic-number candidate
scope and also permits opaque unit strings.  The scalar science profile needs a
smaller contract: a closed unit registry, exact ``Fraction`` values, explicit
SI-base dimensions, and no implicit tolerance.

Only the units required by the first complete-neutralization profile are
accepted:

``""`` (dimensionless), ``L``, ``mL``, ``mol/L``, and ``M``.

The numeric rational-v1 interpreter remains single-sourced in
``packages.evolution.rational_evolver``.  ``evaluate_dimension_ast`` mirrors
its ``var``/``const``/``op`` tree shape and checks the same expression's
dimensions without executing arbitrary code.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from itertools import islice
from types import MappingProxyType
import re
from typing import Any

from packages.reasoning_vm.quantity import format_number_exact, parse_number


DIMENSION_BASIS = ("M", "L", "T", "I", "Theta", "N", "J")
MAX_DIMENSION_EXPONENT = 64
MAX_EXACT_BITS = 4096
MAX_EXP10 = 300
MAX_QUANTITY_CHARS = 256
MAX_AST_NODES = 255
MAX_AST_STEPS = 16_384

_VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_DECIMAL_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_FRACTION_NUMBER = r"[-+]?\d+/\d+"
_NUMBER_TOKEN = rf"(?:{_FRACTION_NUMBER}|{_DECIMAL_NUMBER})"
_QUANTITY = re.compile(
    rf"(?P<number>{_NUMBER_TOKEN})(?: ?(?P<unit>mol/L|mL|L|M))?\Z"
)
_EXPONENT = re.compile(r"[eE]([+-]?\d+)")
_SMALL_CONSTANTS = frozenset((-2, -1, 0, 1, 2))
_OPS = frozenset(("+", "-", "*", "/"))


def _bounded_fraction(value: Any) -> bool:
    return (
        type(value) is Fraction
        and value.numerator.bit_length() <= MAX_EXACT_BITS
        and value.denominator.bit_length() <= MAX_EXACT_BITS
    )


def _bounded_exponent(token: str) -> bool:
    match = _EXPONENT.search(token)
    if match is None:
        return True
    digits = match.group(1).lstrip("+-").lstrip("0") or "0"
    ceiling = str(MAX_EXP10)
    return len(digits) < len(ceiling) or (
        len(digits) == len(ceiling) and digits <= ceiling
    )


@dataclass(frozen=True, slots=True)
class DimensionVector:
    """Exponents over ``(M, L, T, I, Theta, N, J)``.

    ``N`` is amount of substance and ``J`` is luminous intensity; these are
    basis labels rather than unit symbols.  Exponents are bounded so a hostile
    AST cannot manufacture an unbounded dimension object.
    """

    exponents: tuple[int, int, int, int, int, int, int]

    def __post_init__(self) -> None:
        if (
            type(self.exponents) is not tuple
            or len(self.exponents) != len(DIMENSION_BASIS)
            or any(type(value) is not int for value in self.exponents)
            or any(
                abs(value) > MAX_DIMENSION_EXPONENT
                for value in self.exponents
            )
        ):
            raise ValueError("dimension vector must be seven bounded integers")

    def multiplied_by(self, other: "DimensionVector") -> "DimensionVector":
        if type(other) is not DimensionVector:
            raise TypeError("dimension operand must be a DimensionVector")
        return DimensionVector(
            tuple(
                left + right
                for left, right in zip(
                    self.exponents,
                    other.exponents,
                    strict=True,
                )
            )
        )

    def divided_by(self, other: "DimensionVector") -> "DimensionVector":
        if type(other) is not DimensionVector:
            raise TypeError("dimension operand must be a DimensionVector")
        return DimensionVector(
            tuple(
                left - right
                for left, right in zip(
                    self.exponents,
                    other.exponents,
                    strict=True,
                )
            )
        )


DIMENSIONLESS = DimensionVector((0, 0, 0, 0, 0, 0, 0))
VOLUME = DimensionVector((0, 3, 0, 0, 0, 0, 0))
AMOUNT = DimensionVector((0, 0, 0, 0, 0, 1, 0))
CONCENTRATION = DimensionVector((0, -3, 0, 0, 0, 1, 0))


@dataclass(frozen=True, slots=True)
class UnitDef:
    """One member of the code-pinned unit registry."""

    unit_id: str
    symbol: str
    dimension: DimensionVector
    scale_to_si: Fraction

    def __post_init__(self) -> None:
        if (
            type(self.unit_id) is not str
            or not self.unit_id
            or type(self.symbol) is not str
            or type(self.dimension) is not DimensionVector
            or not _bounded_fraction(self.scale_to_si)
            or self.scale_to_si <= 0
        ):
            raise ValueError("invalid closed unit definition")


_UNITS = (
    UnitDef(
        unit_id="unit:dimensionless",
        symbol="",
        dimension=DIMENSIONLESS,
        scale_to_si=Fraction(1),
    ),
    UnitDef(
        unit_id="metric:liter",
        symbol="L",
        dimension=VOLUME,
        scale_to_si=Fraction(1, 1000),
    ),
    UnitDef(
        unit_id="metric:milliliter",
        symbol="mL",
        dimension=VOLUME,
        scale_to_si=Fraction(1, 1_000_000),
    ),
    UnitDef(
        unit_id="metric:mole_per_liter",
        symbol="mol/L",
        dimension=CONCENTRATION,
        scale_to_si=Fraction(1000),
    ),
    UnitDef(
        unit_id="metric:molar",
        symbol="M",
        dimension=CONCENTRATION,
        scale_to_si=Fraction(1000),
    ),
)

UNIT_REGISTRY: Mapping[str, UnitDef] = MappingProxyType(
    {unit.symbol: unit for unit in _UNITS}
)
UNIT_BY_ID: Mapping[str, UnitDef] = MappingProxyType(
    {unit.unit_id: unit for unit in _UNITS}
)


@dataclass(frozen=True, slots=True)
class ExactQuantity:
    """An exact scalar tagged with one unit from ``UNIT_REGISTRY``."""

    value: Fraction
    unit_id: str = "unit:dimensionless"

    def __post_init__(self) -> None:
        if not _bounded_fraction(self.value):
            raise ValueError("quantity value must be a bounded exact Fraction")
        if type(self.unit_id) is not str or self.unit_id not in UNIT_BY_ID:
            raise ValueError("quantity unit is outside the closed registry")

    @property
    def unit(self) -> UnitDef:
        return UNIT_BY_ID[self.unit_id]

    @property
    def dimension(self) -> DimensionVector:
        return self.unit.dimension

    def __str__(self) -> str:
        return format_exact_quantity(self)


def parse_exact_quantity(text: Any) -> ExactQuantity | None:
    """Parse one bounded exact scalar in the closed unit vocabulary.

    No trimming or approximate interpretation is performed.  Commas, ranges,
    tolerance markers, binary floats, unknown units, excessive exponents, and
    non-finite spellings therefore fail closed.
    """

    if (
        type(text) is not str
        or not text
        or len(text) > MAX_QUANTITY_CHARS
        or text != text.strip()
        or "\x00" in text
        or "," in text
    ):
        return None
    match = _QUANTITY.fullmatch(text)
    if match is None:
        return None
    number_token = match.group("number")
    if not _bounded_exponent(number_token):
        return None
    value = parse_number(number_token)
    if value is None or not _bounded_fraction(value):
        return None
    symbol = match.group("unit") or ""
    unit = UNIT_REGISTRY.get(symbol)
    if unit is None:  # Closed-registry invariant; defensive against drift.
        return None
    try:
        return ExactQuantity(value=value, unit_id=unit.unit_id)
    except ValueError:
        return None


def canonical_si(
    quantity: ExactQuantity,
) -> tuple[Fraction, DimensionVector]:
    """Return the exact SI-scaled value and its immutable dimension."""

    if type(quantity) is not ExactQuantity:
        raise TypeError("canonical_si requires an ExactQuantity")
    value = quantity.value * quantity.unit.scale_to_si
    if not _bounded_fraction(value):
        raise ValueError("canonical SI value exceeds exact resource limits")
    return value, quantity.dimension


def format_exact_quantity(quantity: ExactQuantity) -> str:
    """Render an exact, parseable spelling while retaining the chosen unit."""

    if type(quantity) is not ExactQuantity:
        raise TypeError("format_exact_quantity requires an ExactQuantity")
    value = format_number_exact(quantity.value)
    if value is None:  # Constructor bounds make this unreachable unless drift occurs.
        raise ValueError("quantity value cannot be formatted exactly")
    symbol = quantity.unit.symbol
    return f"{value} {symbol}" if symbol else value


def quantity_semantic_key(
    quantity: ExactQuantity,
) -> tuple[int, int, tuple[int, int, int, int, int, int, int]]:
    """Hashable equality key after exact unit conversion."""

    value, dimension = canonical_si(quantity)
    return value.numerator, value.denominator, dimension.exponents


def quantities_equal(left: ExactQuantity, right: ExactQuantity) -> bool:
    """Exact physical equality; no tolerance or float conversion."""

    if type(left) is not ExactQuantity or type(right) is not ExactQuantity:
        return False
    return quantity_semantic_key(left) == quantity_semantic_key(right)


def evaluate_dimension_ast(
    tree: Any,
    variable_dimensions: Mapping[str, DimensionVector],
    *,
    max_nodes: int = 15,
    max_steps: int = 128,
) -> DimensionVector | None:
    """Evaluate the dimension sidecar of a bounded rational-v1 AST.

    Syntax mirrors rational-v1 exactly:

    ``["var", name]``
    ``["const", -2 | -1 | 0 | 1 | 2]``
    ``["op", "+" | "-" | "*" | "/", left, right]``

    Addition and subtraction require identical dimensions.  Multiplication and
    division add and subtract exponent vectors.  Malformed, cyclic, oversized,
    or dimensionally inconsistent trees return ``None``.
    """

    if (
        type(max_nodes) is not int
        or type(max_steps) is not int
        or not 1 <= max_nodes <= MAX_AST_NODES
        or not 1 <= max_steps <= MAX_AST_STEPS
        or not isinstance(variable_dimensions, Mapping)
    ):
        return None
    try:
        items = list(islice(iter(variable_dimensions.items()), 65))
    except Exception:
        return None
    if (
        len(items) > 64
        or any(
            type(name) is not str
            or _VARIABLE.fullmatch(name) is None
            or type(dimension) is not DimensionVector
            for name, dimension in items
        )
        or len({name for name, _dimension in items}) != len(items)
    ):
        return None
    dimensions = dict(items)
    active: set[int] = set()
    nodes = 0
    steps = 0

    def evaluate(node: Any) -> DimensionVector | None:
        nonlocal nodes, steps
        steps += 1
        if steps > max_steps or type(node) not in (list, tuple) or not node:
            return None
        identity = id(node)
        if identity in active:
            return None
        nodes += 1
        if nodes > max_nodes:
            return None
        active.add(identity)
        try:
            kind = node[0]
            if type(kind) is not str:
                return None
            if kind == "var":
                if (
                    len(node) != 2
                    or type(node[1]) is not str
                    or node[1] not in dimensions
                ):
                    return None
                return dimensions[node[1]]
            if kind == "const":
                if (
                    len(node) != 2
                    or type(node[1]) is not int
                    or node[1] not in _SMALL_CONSTANTS
                ):
                    return None
                return DIMENSIONLESS
            if (
                kind != "op"
                or len(node) != 4
                or type(node[1]) is not str
                or node[1] not in _OPS
            ):
                return None
            left = evaluate(node[2])
            right = evaluate(node[3])
            if left is None or right is None:
                return None
            operator = node[1]
            if operator in ("+", "-"):
                return left if left == right else None
            try:
                return (
                    left.multiplied_by(right)
                    if operator == "*"
                    else left.divided_by(right)
                )
            except (TypeError, ValueError):
                return None
        finally:
            active.remove(identity)

    return evaluate(tree)
