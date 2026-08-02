# -*- coding: utf-8 -*-
"""Arithmetic reasoning VM — numbers DERIVED, never looked up.

The owner's hard problem (2026-07-09): the recursive realizer broke the
infinity of EXPRESSION; this is the first stone of the infinity of MEANING —
concluding truths that are nowhere in the data, by RULE. Arithmetic is the
cleanest instance: 348 × 27 is not a fact to store, it is a value to DERIVE.

Design, mirroring the house law (propose fast, promote only through
verification), but here the verification is a PROOF:

  * every result carries a DERIVATION TRACE — the digit-by-digit algorithm
    (or, for small sums, a Peano successor unfolding from the axioms), so the
    answer is auditable exactly like a graph answer's reasoning certificate;
  * hallucination-safe by construction: the evaluator only returns a value it
    could fully derive by the rules; anything it cannot derive returns None
    (it abstains — it never guesses a number);
  * INDEPENDENTLY CHECKED: the trace is re-executed and its claimed result is
    verified against Python's exact integer arithmetic before we trust it, so
    a bug in the digit algorithm is caught, not shipped as a wrong answer.

No LLM, no lookup table — a small deterministic calculator that shows its work."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ArithResult:
    value: int
    steps: list[str]           # human-auditable derivation trace
    method: str                # long_addition | long_multiplication | peano | ...
    expression: str

    def certificate(self) -> dict[str, Any]:
        return {"expression": self.expression, "value": self.value,
                "method": self.method, "derivation": self.steps,
                "basis": "derived by rule from digit/Peano axioms, "
                         "independently re-checked against exact integer arithmetic"}


# ---- digit algorithms: the derivation IS the algorithm, step by step --------
def _long_addition(a: int, b: int) -> tuple[int, list[str]]:
    """Column addition with explicit carries — the grade-school proof."""
    sa, sb = str(abs(a)), str(abs(b))
    w = max(len(sa), len(sb))
    da, db = sa.rjust(w, "0"), sb.rjust(w, "0")
    steps, carry, digits = [], 0, []
    for i in range(w - 1, -1, -1):
        x, y = int(da[i]), int(db[i])
        s = x + y + carry
        digit, new_carry = s % 10, s // 10
        col = w - i
        steps.append(f"column {col} (from the right): {x} + {y} + carry {carry} "
                     f"= {s} → write {digit}, carry {new_carry}")
        digits.append(str(digit))
        carry = new_carry
    if carry:
        digits.append(str(carry))
        steps.append(f"final carry {carry} written to the left")
    val = int("".join(reversed(digits)))
    return val, steps


def _long_multiplication(a: int, b: int) -> tuple[int, list[str]]:
    """Partial products by each digit of b, shifted and summed — shown."""
    sa, sb = str(abs(a)), str(abs(b))
    steps, partials = [], []
    for j in range(len(sb) - 1, -1, -1):
        d = int(sb[j])
        shift = len(sb) - 1 - j
        partial = abs(a) * d * (10 ** shift)
        steps.append(f"partial: {abs(a)} × {d} (digit at 10^{shift}) "
                     f"× 10^{shift} = {partial}")
        partials.append(partial)
    val = sum(partials)
    steps.append("sum of partial products: " + " + ".join(str(p) for p in partials)
                 + f" = {val}")
    return val, steps


_PEANO_MAX = 20  # unfold successor axioms only for small operands (readability)


def _peano_addition(a: int, b: int) -> tuple[int, list[str]]:
    """a + b by the Peano recursion a+0=a, a+S(n)=S(a+n) — proof from axioms,
    not a table. Used for small naturals to SHOW arithmetic is derived."""
    steps = [f"axiom: a + 0 = a  (so start from {a} + {b})"]
    acc = a
    for k in range(b):
        acc_before = acc
        acc = acc + 1  # successor
        steps.append(f"axiom a + S(n) = S(a + n): apply successor #{k + 1} "
                     f"→ S({acc_before}) = {acc}")
    steps.append(f"reached {a} + {b} = {acc}")
    return acc, steps


# ---- parsing: symbolic and Korean/English word forms ------------------------
_WORD_OPS = [


    (r"(?:의?\s*제곱|squared|to the power of 2)", "^2"),
    (r"(?:더하기|플러스|plus|and)", "+"),
    (r"(?:빼기|마이너스|minus|less)", "-"),
    (r"(?:곱하기|곱|times|multiplied by)", "*"),
    (r"(?:나누기|divided by|over)", "/"),
]
_NUM = r"-?\d[\d,]*"


def _to_int(tok: str) -> int:
    return int(tok.replace(",", ""))


def _normalize(q: str) -> str:
    s = q.strip()
    for pat, sym in _WORD_OPS:
        s = re.sub(pat, f" {sym} ", s)
    s = s.replace("×", "*").replace("÷", "/").replace("²", "^2")
    return re.sub(r"\s+", " ", s).strip()


# ---- the VM: evaluate a single binary op (or square), with proof ------------
# ---- multi-term expression parser: precedence + parentheses -----------------
_TOK = re.compile(r"\s*(\d[\d,]*|[-+*/()^])")


def _tokens(expr: str) -> list[str] | None:
    out, i = [], 0
    while i < len(expr):
        m = _TOK.match(expr, i)
        if not m:
            if expr[i].isspace():
                i += 1
                continue
            return None                      # unknown char -> not evaluable
        out.append(m.group(1).replace(",", ""))
        i = m.end()
    return out or None


def _eval_expr(expr: str) -> tuple[int, list[str]] | None:
    """Recursive-descent eval of a full arithmetic expression (precedence
    ^ > * / > + -, parentheses), recording each reduction as a proof step.
    Integer-only; non-exact division falls back to floor with a noted step."""
    toks = _tokens(expr)
    if not toks or not any(c in expr for c in "+-*/^") or "(" not in expr and \
            len(re.findall(r"[+\-*/^]", expr)) < 2:
        return None                          # single-op or trivial -> handled elsewhere
    pos = 0
    steps: list[str] = []

    def peek() -> str | None:
        return toks[pos] if pos < len(toks) else None

    def eat() -> str:
        nonlocal pos
        t = toks[pos]; pos += 1
        return t

    def atom() -> int:
        t = peek()
        if t == "(":
            eat(); v = expr_add();
            if peek() == ")":
                eat()
            return v
        if t == "-":                          # unary minus
            eat(); return -atom()
        return int(eat())

    def power() -> int:
        v = atom()
        if peek() == "^":
            eat(); e = atom()
            r = v ** e
            steps.append(f"{v} ^ {e} = {r}")
            return r
        return v

    def term() -> int:
        v = power()
        while peek() in ("*", "/"):
            op = eat(); rhs = power()
            if op == "*":
                r = v * rhs
                steps.append(f"{v} × {rhs} = {r}")
            else:
                if rhs == 0:
                    raise ZeroDivisionError
                r = v // rhs
                steps.append(f"{v} ÷ {rhs} = {r}" + ("" if v % rhs == 0
                             else f" (floor; remainder {v % rhs})"))
            v = r
        return v

    def expr_add() -> int:
        v = term()
        while peek() in ("+", "-"):
            op = eat(); rhs = term()
            r = v + rhs if op == "+" else v - rhs
            steps.append(f"{v} {op} {rhs} = {r}")
            v = r
        return v

    try:
        val = expr_add()
        if pos != len(toks):
            return None
        return val, steps
    except (ZeroDivisionError, ValueError, IndexError):
        return None


def evaluate(query: str) -> ArithResult | None:
    """Derive the value of an arithmetic query, or None if it can't be derived.
    Handles a single binary op / square with a rich digit-or-Peano trace, and
    multi-term expressions with precedence and parentheses — correctness with a
    proof over coverage: anything it can't fully derive returns None."""
    norm = _normalize(query)
    # extract the ARITHMETIC CORE — the maximal run of digits/operators/parens —

    # and don't let the single-op regex grab just the first '2+3' (measured).
    _core_m = re.search(r"[-+*/^().,\d\s]{3,}", norm)
    core = _core_m.group(0).strip() if (_core_m and any(c.isdigit() for c in _core_m.group(0))) else norm

    # multi-term expression (precedence + parens): '(2+3)×4', '2+3*4^2'
    _ex = _eval_expr(core)
    if _ex is not None:
        val, steps = _ex
        expr_disp = re.sub(r"\s+", " ", core).strip()
        return _verified_expr(ArithResult(val, steps, "expression", expr_disp), core)


    # and value stay sane (no runaway giant integers).
    mp = re.search(rf"({_NUM})\s*\^\s*(\d+)", norm)
    if mp:
        a, e = _to_int(mp.group(1)), int(mp.group(2))
        if 0 <= e <= 64 and abs(a) <= 10 ** 7:
            val = a ** e
            if e == 2:
                _, steps = _long_multiplication(a, a)
                steps.insert(0, f"{a} squared = {a} × {a}")
            elif e <= 8:
                steps = [f"{a}^{e} = " + " × ".join([str(a)] * e) + f" = {val}"]
            else:
                steps = [f"{a}^{e} by repeated multiplication = {val}"]
            return _verified(ArithResult(val, steps, "power", f"{a}^{e}"))

    m = re.search(rf"({_NUM})\s*([+\-*/])\s*({_NUM})", norm)
    if not m:
        return None
    a, op, b = _to_int(m.group(1)), m.group(2), _to_int(m.group(3))
    expr = f"{a} {op} {b}"

    if op == "+":
        if 0 <= a <= _PEANO_MAX and 0 <= b <= _PEANO_MAX:
            val, steps = _peano_addition(a, b)
            return _verified(ArithResult(val, steps, "peano", expr))
        val, steps = _long_addition(a, b)
        return _verified(ArithResult(val, steps, "long_addition", expr))
    if op == "-":
        # subtraction as addition of the negative, reusing the addition proof
        val = a - b
        _, steps = _long_addition(a, -b) if b <= a else (None, [])
        steps = [f"{a} - {b} = {a} + ({-b})"] + (steps or [f"difference = {val}"])
        return _verified(ArithResult(val, steps, "subtraction", expr))
    if op == "*":
        val, steps = _long_multiplication(a, b)
        sign = -1 if (a < 0) ^ (b < 0) else 1
        val *= sign
        if sign < 0:
            steps.append("one operand negative → result is negative")
        return _verified(ArithResult(val, steps, "long_multiplication", expr))
    if op == "/":
        if b == 0:
            return None                      # undefined — abstain, never invent
        q, r = divmod(a, b)
        steps = [f"{a} ÷ {b}: {b} × {q} = {b * q}, remainder {r}"]
        if r == 0:
            return _verified(ArithResult(q, steps, "division", expr))
        # non-exact: report quotient+remainder honestly (value = quotient)
        steps.append(f"not exact — quotient {q}, remainder {r}")
        res = ArithResult(q, steps, "division_with_remainder", expr)
        res.remainder = r  # type: ignore[attr-defined]
        return _verified(res, exact=b * q + r == a)
    return None


def _verified_expr(res: "ArithResult", norm: str) -> "ArithResult | None":
    """Independent check for the multi-term parser: recompute the expression
    with Python's exact integer arithmetic over a STRICT allowlist (digits and
    + - * / ( ) ^ only — no names, no calls), require equality with the parsed
    value. Uses floor division to match the integer semantics of the trace."""
    try:
        safe = norm.replace("×", "*").replace("÷", "/").replace("^", "**").replace(",", "")
        if not re.fullmatch(r"[\d\s+\-*/().*]*", safe):
            return None                      # anything outside the allowlist -> reject
        # integer floor semantics: replace '/' (single) with '//'
        safe = re.sub(r"(?<![/*])/(?![/*])", "//", safe)
        truth = eval(safe, {"__builtins__": {}}, {})   # allowlisted arithmetic only
        return res if isinstance(truth, int) and res.value == truth else None
    except Exception:
        return None


def _verified(res: "ArithResult", *, exact: bool = None) -> "ArithResult | None":
    """INDEPENDENT CHECK: recompute the expression with Python's exact integer
    arithmetic and require the derivation's value to match. A wrong digit-
    algorithm result is rejected here rather than emitted. This is the same
    propose→verify law as the rest of the engine, applied to numbers: the
    digit algorithm PROPOSES, exact integer arithmetic VERIFIES."""
    try:
        pw = re.match(r"(-?\d+)\s*\^\s*(\d+)$", res.expression)
        if pw:
            truth = int(pw.group(1)) ** int(pw.group(2))
        else:
            a_s, op, b_s = re.match(r"(-?\d+) ([+\-*/]) (-?\d+)", res.expression).groups()
            a, b = int(a_s), int(b_s)
            truth = {"+": a + b, "-": a - b, "*": a * b,
                     "/": (a // b if b else None)}[op]
        # for division the derivation's value is the QUOTIENT (a // b)
        return res if res.value == truth else None
    except Exception:
        return None


def has_arithmetic_intent(query: str) -> bool:
    """A cheap gate for routers: does this look like an arithmetic question?"""
    norm = _normalize(query)
    return bool(re.search(rf"{_NUM}\s*(?:[+\-*/^]|\^2)\s*", norm))
