# -*- coding: utf-8 -*-
"""Quantitative kernel (Reasoning VM T1) — exact rational + units + scientific notation.

The integer arithmetic VM cannot touch 17% of MMLU-Pro (measured): "frequency given wavelength",
"pH", "concentration", unit conversions. This kernel adds the missing quantitative reasoning WITH
the same discipline — every result carries an auditable derivation, exact rationals (Fraction, so
no float error), scientific notation (6.022e23), SI prefixes, and dimensioned quantities whose
units cancel/convert deterministically.

No-LLM. The FORMULA is never hard-coded knowledge — a formula lives in the graph as an explicit
triple ('c = lambda * nu') and this kernel only EVALUATES it once the values are supplied; the
certificate cites the formula source. Here we ship the exact-arithmetic + unit engine; the
formula-from-graph binding is the wiring step (T2 router) built on top.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

# SI prefixes → exact power-of-ten multiplier (Fraction keeps micro/nano exact)
_PREFIX = {
    "Y": 24, "Z": 21, "E": 18, "P": 15, "T": 12, "G": 9, "M": 6, "k": 3, "h": 2, "da": 1,
    "d": -1, "c": -2, "m": -3, "u": -6, "µ": -6, "μ": -6, "n": -9, "p": -12, "f": -15,
    "a": -18, "z": -21, "y": -24,
}
# base units we track dimensionally (extend freely; unknown units pass through as opaque tags)
_BASE = {"m", "g", "s", "A", "K", "mol", "cd", "Hz", "N", "J", "W", "Pa", "C", "V", "L", "eV"}
# exact conversions to a COMMON unit — applied only when +/- needs two quantities compatible,
# never eagerly (so '2.5 mol / 0.5 L' stays mol/L for answer-convention matching, not mol/m³).
_CONV: dict[str, tuple[Fraction, str]] = {
    "min": (Fraction(60), "s"), "h": (Fraction(3600), "s"), "hr": (Fraction(3600), "s"),
    "day": (Fraction(86400), "s"), "ms": (Fraction(1, 1000), "s"), "us": (Fraction(1, 10**6), "s"),
    "µs": (Fraction(1, 10**6), "s"), "ns": (Fraction(1, 10**9), "s"),
    "cm": (Fraction(1, 100), "m"), "mm": (Fraction(1, 1000), "m"), "km": (Fraction(1000), "m"),
    "nm": (Fraction(1, 10**9), "m"), "um": (Fraction(1, 10**6), "m"), "µm": (Fraction(1, 10**6), "m"),
    "mL": (Fraction(1, 1000), "L"), "kJ": (Fraction(1000), "J"), "kg": (Fraction(1000), "g"),
    "mg": (Fraction(1, 1000), "g"), "kmol": (Fraction(1000), "mol"),
}
_MAX_EXACT_BITS = 4096
_MAX_EXP10 = 1000
_MAX_TOKEN_CHARS = 8192


def _fraction_bounded(value: Any) -> bool:
    return type(value) is Fraction \
        and value.numerator.bit_length() <= _MAX_EXACT_BITS \
        and value.denominator.bit_length() <= _MAX_EXACT_BITS


def _to_common(q: "Quantity") -> tuple[Fraction, str]:
    """Value + canonical unit for +/- compatibility (km→m, min→s …); unknown units unchanged."""
    if q.unit in _CONV:
        mul, base = _CONV[q.unit]
        return q.value * mul, base
    return q.value, q.unit


@dataclass
class Quantity:
    value: Fraction
    unit: str = ""          # canonical-ish unit tag, "" = dimensionless

    def __str__(self) -> str:
        return format_quantity_exact(self) or "<quantity-out-of-bounds>"


@dataclass
class QuantResult:
    quantity: Quantity
    steps: list[str] = field(default_factory=list)
    method: str = "quantity_eval"

    def certificate(self) -> dict[str, Any]:
        value = format_number_exact(self.quantity.value)
        return {"value": value, "unit": self.quantity.unit,
                "method": self.method, "derivation": self.steps,
                "error": None if value is not None else "exact-value resource limit",
                "basis": "exact rational arithmetic (Fraction, zero float error); units cancelled "
                         "by dimensional algebra; every step re-checkable"}


def _fmt(x: Fraction) -> str:
    """Human form: integer if whole, else shortest exact decimal or scientific for extremes."""
    if x.denominator == 1:
        v = x.numerator
        return f"{v:.3e}".replace("e", "e") if abs(v) >= 10**7 else str(v)
    f = float(x)
    if f != 0 and (abs(f) < 1e-3 or abs(f) >= 1e7):
        return f"{f:.4e}"
    return f"{f:.6g}"


def format_number_exact(x: Fraction) -> str | None:
    """Round-trippable exact text for a rational.

    Terminating base-10 values are emitted as decimals; every other rational stays ``n/d``.
    Unlike ``_fmt`` this is a storage/proof representation, so it never converts through float.
    """
    if not _fraction_bounded(x):
        return None
    if x.denominator == 1:
        return str(x.numerator)
    den = x.denominator
    twos = fives = 0
    while den % 2 == 0:
        den //= 2
        twos += 1
    while den % 5 == 0:
        den //= 5
        fives += 1
    if den != 1:
        return f"{x.numerator}/{x.denominator}"
    scale = max(twos, fives)
    scaled = abs(x.numerator) * (2 ** (scale - twos)) * (5 ** (scale - fives))
    digits = str(scaled).rjust(scale + 1, "0")
    whole = digits[:-scale] if scale else digits
    frac = digits[-scale:].rstrip("0") if scale else ""
    text = whole if not frac else f"{whole}.{frac}"
    return f"-{text}" if x.numerator < 0 else text


def format_quantity_exact(q: Quantity) -> str | None:
    """Exact, parseable graph/proof representation of a quantity."""
    if type(q) is not Quantity or type(q.unit) is not str:
        return None
    value = format_number_exact(q.value)
    if value is None:
        return None
    return f"{value} {q.unit}" if q.unit else value


_DECIMAL_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_FRACTION_NUMBER = r"[-+]?\d+/\d+"
_NUMBER_TOKEN = rf"(?:{_FRACTION_NUMBER}|{_DECIMAL_NUMBER})"
_NUM = re.compile(_DECIMAL_NUMBER)
_QTY = re.compile(rf"({_NUMBER_TOKEN})\s*([a-zA-Zµμ°/^0-9·]*)")


def parse_number(tok: str) -> Fraction | None:
    """Exact Fraction from an int/decimal/scientific literal ('6.022e23', '3/4', '0.005')."""
    if type(tok) is not str or len(tok) > _MAX_TOKEN_CHARS:
        return None
    tok = tok.strip().replace(",", "")
    if not tok:
        return None
    if "/" in tok and re.fullmatch(r"[-+]?\d+/\d+", tok):
        try:
            value = Fraction(tok)
            return value if _fraction_bounded(value) else None
        except (ValueError, ZeroDivisionError, OverflowError):
            return None
    if not _NUM.fullmatch(tok):
        return None
    try:
        if "e" in tok.lower():
            mant, _e, exp = tok.lower().partition("e")
            digits = exp.lstrip("+-").lstrip("0") or "0"
            if len(digits) > len(str(_MAX_EXP10)) \
                    or len(digits) == len(str(_MAX_EXP10)) and digits > str(_MAX_EXP10):
                return None
            value = Fraction(mant) * (Fraction(10) ** int(exp))
        else:
            value = Fraction(tok)
        return value if _fraction_bounded(value) else None
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def parse_quantity(tok: str) -> Quantity | None:
    """'3.0 km' / '6.022e23' / '25 mL' → Quantity with SI prefix + unit-conversion applied."""
    m = _QTY.fullmatch(tok.strip())
    if not m:
        n = parse_number(tok)
        return Quantity(n) if n is not None else None
    num = parse_number(m.group(1))
    if num is None:
        return None
    unit = m.group(2).strip()
    if not unit:
        return Quantity(num)
    if unit in _CONV:                                   # exact unit conversion (min→s, L→m3…)
        mul, base = _CONV[unit]
        value = num * mul
        return Quantity(value, base) if _fraction_bounded(value) else None
    # SI prefix on a known base unit (km, mL handled above; kJ, mA, µs, nm …)
    for p, power in sorted(_PREFIX.items(), key=lambda kv: -len(kv[0])):
        if unit.startswith(p) and unit[len(p):] in _BASE:
            value = num * (Fraction(10) ** power)
            return Quantity(value, unit[len(p):]) if _fraction_bounded(value) else None
    return Quantity(num, unit)                          # opaque unit — passes through


def op(a: Quantity, operator: str, b: Quantity) -> QuantResult | None:
    """One dimensioned binary op with a proof step. Add/sub require matching units; mul/div
    combine unit tags (a/a cancels to dimensionless)."""
    if type(a) is not Quantity or type(b) is not Quantity \
            or not _fraction_bounded(a.value) or not _fraction_bounded(b.value) \
            or type(a.unit) is not str or type(b.unit) is not str:
        return None
    steps: list[str] = []
    if operator in ("+", "-"):
        av, au = _to_common(a)                          # km→m, min→s … so mixed prefixes add
        bv, bu = _to_common(b)
        if au != bu:
            return None                                 # dimensional mismatch → refuse, never fudge
        v = av + bv if operator == "+" else av - bv
        q = Quantity(v, au)
    elif operator == "*":
        u = "" if not a.unit and not b.unit else (a.unit or b.unit) if (not a.unit or not b.unit) \
            else f"{a.unit}·{b.unit}"
        q = Quantity(a.value * b.value, u)
    elif operator == "/":
        if b.value == 0:
            return None
        # compound-unit cancellation: (X/Y)/X = 1/Y  (c[m/s] / λ[m] = frequency[1/s]); X/X = 1
        if a.unit == b.unit:
            u = ""
        elif "/" in a.unit and a.unit.split("/", 1)[0] == b.unit:
            u = f"1/{a.unit.split('/', 1)[1]}"
        elif not b.unit:
            u = a.unit
        elif not a.unit:
            u = f"1/{b.unit}"
        else:
            u = f"{a.unit}/{b.unit}"
        q = Quantity(a.value / b.value, u)
    else:
        return None
    if not _fraction_bounded(q.value):
        return None
    steps.append(f"{a} {operator} {b} = {q}")
    return QuantResult(q, steps, method="dimensioned_op")


def evaluate(expr: str) -> QuantResult | None:
    """Evaluate a quantitative expression like '299792458 m/s / 500e-9 m' or '2.5 mol / 0.5 L'.
    Left-to-right over dimensioned quantities (single operator for v1; the T2 router supplies
    formula-shaped multi-step programs). Returns None when it is not a clean quantitative op."""
    # split on a WHITESPACE-surrounded operator so compound units keep their slash intact
    # ('299792458 m/s / 500e-9 m' → operands '…m/s' and '500e-9 m', operator the spaced '/').
    m = re.match(r"^\s*(.+?)\s+([*/+\-])\s+(.+?)\s*$", expr)
    if not m:
        unit_token = r"[a-zA-Zµμ°/^0-9·]*"
        m = re.match(
            rf"^\s*({_NUMBER_TOKEN}\s*{unit_token})\s*([+*\-])\s*"
            rf"({_NUMBER_TOKEN}\s*{unit_token})\s*$",
            expr,
        )
    if not m:
        m = re.match(rf"^\s*({_DECIMAL_NUMBER})(/)({_DECIMAL_NUMBER})\s*$", expr)
    if not m:
        simple_unit = r"[a-zA-Zµμ°^·]+[0-9]*"
        m = re.match(
            rf"^\s*({_NUMBER_TOKEN}\s*{simple_unit})(/)"
            rf"({_NUMBER_TOKEN}\s*(?:{simple_unit})?)\s*$",
            expr,
        )
    if not m:
        return None
    a = parse_quantity(m.group(1))
    b = parse_quantity(m.group(3))
    if a is None or b is None:
        return None
    r = op(a, m.group(2), b)
    if r:
        r.steps.insert(0, f"parse: {m.group(1).strip()} → {a} ; {m.group(3).strip()} → {b}")
    return r
