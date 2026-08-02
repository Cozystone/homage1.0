"""ATANOR Reasoning VM — deterministic Logic/Math Cortex (no LLM, no web).

GPT's critique #4: " · ." This module
answers that head-on. Word problems and arithmetic do NOT need a neural forward
pass — they need a parser + a state machine. The VM:

 1. compiles a natural-language question into a small, typed operation plan
 (base quantity → +/-/×/÷ steps in textual order), and
 2. executes it deterministically, tracking running state, and
 3. emits a per-step reasoning certificate (every operation is auditable).

Same honesty contract as the rest of ATANOR: if the question can't be parsed
into an unambiguous plan, it returns None (abstains) — it never guesses.

Runs fully offline (this is the " , " differentiator):
no Wikipedia, no GPU, no matrix multiply — just Python integers and a trace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ── number words ──────────────────────────────────────────────────────────────
# Korean native numerals (counting things) and a few sino forms, plus English.
_WORD_NUM = {
    # native Korean
    "하나": 1, "한": 1, "둘": 2, "두": 2, "셋": 3, "세": 3, "넷": 4, "네": 4,
    "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10,
    # sino Korean (small)
    "영": 0, "일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9, "십": 10,
    # english
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}

# Counting-question cues — required (with the numeric content) to treat a sentence
# as a word problem rather than a factual lookup.
_COUNT_CUE = re.compile(
    r"몇\s*(?:개|명|마리|권|장|살|원|병|잔|대|판|송이|그루|자루)?|얼마|남(?:아|는|지|을까|니)|"
    r"모두|전부|합(?:이|쳐|계)|총\s|how\s+many|how\s+much|left|remain|in\s+total|altogether|sum\b",
    re.IGNORECASE,
)

# Operation lexicon. Each cue maps to one of: add / sub / mul / div.
# Order matters only within a class; we search the trailing window of each number.
_OP_CUES: tuple[tuple[str, str], ...] = (


    # multiplicatively, not additively.
    (r"씩|마다|each\b|apiece|per\s", "mul"),
    # multiply / divide (more specific than add/sub)
    (r"곱하|곱한|×|\*|times\b|multipli|product\s+of", "mul"),
    (r"배(?:로|를|만큼|\s|$)", "mul"),
    (r"나누|나눠|나눈|÷|/|divid|split", "div"),
    # subtract
    (r"먹|팔|잃|훔|뺏|빼앗|뺀|빼|덜|줄(?:어|여|이)|쓰|썼|써\b|마시|마셔|마신|사용|소비|없어|버(?:려|린)|"
     r"가져가|가져간|떼|차감|제외|줬|주(?:었|고|면)|도둑|훔쳐|eat|ate|drank|drink|sold|sell|los[te]|"
     r"stole|stolen|spend|spent|gave\s+away|remove|drop|minus|fewer|less|took\s+away", "sub"),
    # add (last — most generic). NOTE: "buy" must be matched as a real verb form


    (r"샀|산\b|사(?:다|서|고|면|려|자|는다|ㄴ다|들|왔|온)|구매|더(?:\s|했|한|하)|추가|받|생기|얻|보태|합|들어와|더해|모(?:으|아|은)|"
     r"buy|bought|add|added|get|got|gain|receiv|gave\s+me|find|found|plus|more\b|total", "add"),
)

_COMPILED_OPS = [(re.compile(p, re.IGNORECASE), op) for p, op in _OP_CUES]


@dataclass(frozen=True)
class _Num:
    value: float
    start: int
    end: int
    raw: str


def _normalize(q: str) -> str:
    return re.sub(r"\s+", " ", str(q or "")).strip()


def _find_numbers(text: str) -> list[_Num]:
    """All numbers in textual order: digit groups (with comma/decimal and /),
 plus spelled-out numerals."""
    nums: list[_Num] = []

    for m in re.finditer(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(억|만)?", text):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        unit = m.group(2)
        v *= 1e8 if unit == "억" else 1e4 if unit == "만" else 1.0
        nums.append(_Num(v, m.start(1), m.end(), m.group(0)))
    # spelled-out numerals as standalone tokens (avoid matching inside words)
    for m in re.finditer(r"(?<![\w가-힣])(" + "|".join(map(re.escape, _WORD_NUM)) + r")(?![\w가-힣])", text):

        word = m.group(1)
        tail = text[m.end(): m.end() + 6]

        if re.match(r"\s*[가-힣]{0,2}\s*당", tail):
            continue
        if word in {"이", "일", "사", "오", "육", "삼", "구", "십", "영", "칠", "팔"} and not re.match(r"\s*(?:개|명|마리|권|장|살|병|잔|대|판|곱|더|배|나누)", tail):
            continue
        nums.append(_Num(float(_WORD_NUM[word]), m.start(1), m.end(), word))
    nums.sort(key=lambda n: n.start)
    # de-overlap (a digit match and word match shouldn't both fire on same span)
    out: list[_Num] = []
    last_end = -1
    for n in nums:
        if n.start >= last_end:
            out.append(n)
            last_end = n.end
    return out


def _op_in(segment: str) -> str | None:
    for rx, op in _COMPILED_OPS:
        if rx.search(segment):
            return op
    return None


def _is_int(x: float) -> bool:
    return abs(x - round(x)) < 1e-9


def _fmt(x: float) -> str:
    return str(int(round(x))) if _is_int(x) else f"{x:g}"


# ── arithmetic expression evaluator (safe; no eval) ───────────────────────────
_OP_WORDS = [
    (r"곱하기|곱한\s*값|times|multiplied\s+by|\*|×", "*"),
    (r"나누기|나눈\s*값|divided\s+by|÷", "/"),
    (r"더하기|플러스|plus|\+", "+"),
    (r"빼기|마이너스|minus", "-"),
]


def _to_expr(text: str) -> str | None:
    """Rewrite a worded arithmetic question into a bare expression, or None."""
    s = text
    # Phrasal Korean arithmetic where the operator is a verb between two numbers:



    _C = r"(?:개|명|마리|권|장|살|원|병|잔|대|판|송이|그루|자루|쪽|편)?"
    s = re.sub(r"(\d[\d,]*)\s*" + _C + r"\s*에서\s*(\d[\d,]*)\s*" + _C + r"\s*(?:을|를)?\s*(?:빼|뺀|덜)", r"\1 - \2", s)
    s = re.sub(r"(\d[\d,]*)\s*" + _C + r"\s*에\s*(\d[\d,]*)\s*" + _C + r"\s*(?:을|를)?\s*(?:더|추가|보태)", r"\1 + \2", s)
    s = re.sub(r"(\d[\d,]*)\s*" + _C + r"\s*에\s*(\d[\d,]*)\s*" + _C + r"\s*(?:을|를)?\s*곱", r"\1 * \2", s)


    s = re.sub(r"(\d[\d,]*)\s*" + _C + r"\s*(?:을|를)\s*(\d[\d,]*)\s*" + _C + r"\s*(?:으로|로|이|가)?\s*나누", r"\1 / \2", s)
    has_word_op = False
    for pat, sym in _OP_WORDS:
        if re.search(pat, s, re.IGNORECASE):
            has_word_op = True
        s = re.sub(pat, f" {sym} ", s, flags=re.IGNORECASE)
    # A standalone function variable (x) means this is a function/plot, not bare
    # arithmetic — don't strip it to digits and miscompute (e.g. "x^2+1" → "2+1").
    if re.search(r"(?<![a-z0-9])x(?![a-z0-9])", s, re.IGNORECASE):
        return None
    # keep only digits, operators, parentheses, dots, spaces
    s = re.sub(r"[^0-9+\-*/().\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s or not re.search(r"\d", s):
        return None
    # need at least one binary operator between two numbers
    if not re.search(r"\d\s*[*/+\-]\s*[-(]?\s*\d", s) and not has_word_op:
        return None
    return s


def _eval_expr(expr: str) -> float | None:
    """Recursive-descent evaluator for + - * / and parentheses. Returns None on
    any malformed input — never raises into the caller."""
    tokens = re.findall(r"\d+\.?\d*|[+\-*/()]", expr)
    if not tokens:
        return None
    pos = 0

    def peek() -> str | None:
        return tokens[pos] if pos < len(tokens) else None

    def nxt() -> str:
        nonlocal pos
        t = tokens[pos]
        pos += 1
        return t

    def factor() -> float | None:
        t = peek()
        if t is None:
            return None
        if t == "(":
            nxt()
            v = expr_p()
            if peek() == ")":
                nxt()
            return v
        if t in {"+", "-"}:
            nxt()
            v = factor()
            return None if v is None else (-v if t == "-" else v)
        if re.match(r"^\d", t):
            nxt()
            return float(t)
        return None

    def term() -> float | None:
        v = factor()
        if v is None:
            return None
        while peek() in {"*", "/"}:
            op = nxt()
            r = factor()
            if r is None:
                return None
            if op == "/":
                if abs(r) < 1e-12:
                    return None
                v /= r
            else:
                v *= r
        return v

    def expr_p() -> float | None:
        v = term()
        if v is None:
            return None
        while peek() in {"+", "-"}:
            op = nxt()
            r = term()
            if r is None:
                return None
            v = v + r if op == "+" else v - r
        return v

    val = expr_p()
    return val if pos == len(tokens) else (val if pos >= len(tokens) - 0 else None)


def _certificate(steps: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    return {
        "derivation_kind": kind,
        "anchor_concept": {"id": "reasoning_vm", "label": "결정론적 추론 VM", "match": "compute"},
        "steps": steps,
        "evidence_concepts": [],
        "confidence": 0.97,
        "confidence_basis": "deterministic_symbolic_execution",
        "guarantees": {
            "external_llm": False,
            "external_sllm": False,
            "fabricated_facts": False,
            "matrix_multiply": False,
            "offline_capable": True,
            "deterministic": True,
            "multi_hop": True,
        },
    }


def _solve_expression(q: str, language: str) -> dict[str, Any] | None:
    expr = _to_expr(q)
    if not expr:
        return None
    value = _eval_expr(expr)
    if value is None:
        return None
    pretty = expr.replace("*", "×").replace("/", "÷")
    if language == "en":
        answer = f"{pretty} = {_fmt(value)}. (computed deterministically — no LLM)"
    else:
        answer = f"{pretty} = {_fmt(value)} 입니다. (외부 LLM 없이 결정론적으로 계산했어요)"
    steps = [
        {"type": "parse", "fact": f"expression := {expr}"},
        {"type": "evaluate", "fact": f"{expr} = {_fmt(value)}"},
    ]
    return {
        "answer": answer,
        "reasoning_certificate": _certificate(steps, "deterministic_arithmetic"),
        "confidence": 0.97,
        "result_value": value,
        "answer_visual": _formula_visual(
            "계산" if language != "en" else "Calculation",
            f"{pretty} = {_fmt(value)}",
            registry_hint="arithmetic_expression",
        ),
    }


def _solve_word_problem(q: str, language: str) -> dict[str, Any] | None:
    if not _COUNT_CUE.search(q):
        return None
    nums = _find_numbers(q)


    if len(nums) < 2:
        return None


    # it BEFORE ("ate 3"). Inspect the adjacent window on the right side first for
    # Korean, left side first for English.
    prefer_before = language == "en"
    result: float | None = None
    steps: list[dict[str, Any]] = []
    applied = 0
    for i, n in enumerate(nums):
        before = q[(nums[i - 1].end if i > 0 else 0): n.start]
        after = q[n.end: (nums[i + 1].start if i + 1 < len(nums) else len(q))]
        op = (_op_in(before) or _op_in(after)) if prefer_before else (_op_in(after) or _op_in(before))
        if result is None:
            result = n.value
            base_label = "start" if language == "en" else "시작 수량"
            steps.append({"type": "base", "fact": f"{base_label} = {_fmt(n.value)}"})
            continue
        if op is None:
            # a number with no governing operation in a counting problem is ambiguous
            return None
        before = result
        if op == "add":
            result += n.value
            sym = "+"
        elif op == "sub":
            result -= n.value
            sym = "−"
        elif op == "mul":
            result *= n.value
            sym = "×"
        else:  # div
            if abs(n.value) < 1e-12:
                return None
            result /= n.value
            sym = "÷"
        applied += 1
        steps.append({"type": op, "fact": f"{_fmt(before)} {sym} {_fmt(n.value)} = {_fmt(result)}"})

    if result is None or applied == 0:
        return None

    if language == "en":
        answer = f"{_fmt(result)}. " + " → ".join(s["fact"] for s in steps) + "  (step-by-step, no LLM)"
    else:
        chain = " → ".join(s["fact"] for s in steps)
        answer = f"답은 {_fmt(result)}이에요. {chain} 순서로, 외부 LLM 없이 단계별로 계산했어요."
    formula = " ; ".join(s["fact"] for s in steps if s.get("type") != "base") or f"= {_fmt(result)}"
    return {
        "answer": answer,
        "reasoning_certificate": _certificate(steps, "deterministic_word_problem"),
        "confidence": 0.95,
        "result_value": result,
        "answer_visual": _formula_visual(
            "단계별 계산" if language != "en" else "Step-by-step",
            formula,
            registry_hint="word_problem_steps",
        ),
    }



_RATE_RE = re.compile(r"시속\s*(\d[\d,]*(?:\.\d+)?)\s*(?:km|킬로미터|킬로|미터|m)?", re.IGNORECASE)
_TIME_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(시간|분|초)")


def _solve_rate_time(q: str, language: str) -> dict[str, Any] | None:
    # Specific, deterministic template (arithmetic is calculator territory — no need to
    # "emerge" it): speed × time = distance. Requires a motion cue so it never fires on an

    if not re.search(r"가면|간다|갈까|달리|이동|거리|얼마나|몇\s*(?:km|킬로|미터|m)\b", q):
        return None
    sm, tm = _RATE_RE.search(q), _TIME_RE.search(q)
    if not (sm and tm):
        return None
    speed = float(sm.group(1).replace(",", ""))
    tval, unit = float(tm.group(1).replace(",", "")), tm.group(2)
    hours = tval if unit == "시간" else (tval / 60 if unit == "분" else tval / 3600)
    dist = speed * hours
    steps = [
        {"type": "base", "fact": f"속력 = {_fmt(speed)} km/h, 시간 = {_fmt(tval)}{unit}"},
        {"type": "mul", "fact": f"{_fmt(speed)} × {_fmt(hours)} = {_fmt(dist)} (거리 = 속력 × 시간)"},
    ]
    if language == "en":
        answer = f"{_fmt(dist)} km. distance = speed × time = {_fmt(speed)} × {_fmt(hours)} = {_fmt(dist)}  (no LLM)"
    else:
        answer = f"{_fmt(dist)}km예요. 거리 = 속력 × 시간 = {_fmt(speed)} × {_fmt(hours)} = {_fmt(dist)}km로, 외부 LLM 없이 계산했어요."
    return {
        "answer": answer,
        "reasoning_certificate": _certificate(steps, "deterministic_rate_time"),
        "confidence": 0.95,
        "result_value": dist,
        "answer_visual": _formula_visual(
            "거리 = 속력 × 시간" if language != "en" else "distance = speed × time",
            f"{_fmt(speed)} × {_fmt(hours)} = {_fmt(dist)}",
            registry_hint="rate_time",
        ),
    }


# ── experimental answer-interface surface ─────────────────────────────────────
# A structured spec the dashboard renders as a GeoGebra-like figure or a formula
# card. It is DATA, not code, on purpose: the mapping "this kind of question →
# this interface" is a registry ATANOR can later extend on its own. Each solver
# emits an `answer_visual`; the frontend has one renderer per `kind`.
def _formula_visual(title: str, formula: str, *, registry_hint: str) -> dict[str, Any]:
    return {"kind": "formula", "title": title, "formula": formula, "registry_hint": registry_hint}



_EXP_POW_RE = re.compile(r"(\d+(?:\.\d+)?)\s*의\s*(\d+)\s*제곱")
_EXP_CUBE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*세제곱(?!미터|센티|킬로)")
_EXP_SQ_RE = re.compile(r"(\d+(?:\.\d+)?)\s*제곱(?!미터|센티|킬로|\s*미)")
_EXP_EN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\^|\*\*|to the power of)\s*(\d+)", re.IGNORECASE)


def _solve_exponent(q: str, language: str) -> dict[str, Any] | None:
    base = exp = None
    m = _EXP_POW_RE.search(q) or _EXP_EN_RE.search(q)
    if m:
        base, exp = float(m.group(1)), int(m.group(2))
    elif _EXP_CUBE_RE.search(q):
        base, exp = float(_EXP_CUBE_RE.search(q).group(1)), 3
    elif _EXP_SQ_RE.search(q):
        base, exp = float(_EXP_SQ_RE.search(q).group(1)), 2
    if base is None or exp is None or exp > 64:  # bound the work
        return None
    value = base ** exp
    formula = f"{_fmt(base)}^{exp} = {_fmt(value)}"
    if language == "en":
        answer = f"{_fmt(base)} to the power of {exp} = {_fmt(value)}. (deterministic, no LLM)"
    else:
        answer = f"{_fmt(base)}의 {exp}제곱은 {_fmt(value)}입니다. (외부 LLM 없이 결정론적으로 계산했어요)"
    steps = [{"type": "power", "fact": formula}]
    return {
        "answer": answer,
        "reasoning_certificate": _certificate(steps, "deterministic_exponent"),
        "confidence": 0.97,
        "result_value": value,
        "answer_visual": _formula_visual("거듭제곱" if language != "en" else "Exponent", formula, registry_hint="arithmetic_power"),
    }


# ── geometry: square / rectangle / circle / triangle → number + a figure ──────
_PI = 3.141592653589793


def _nums_only(q: str) -> list[float]:
    # Geometry uses digit measurements only — never spelled-out determiners like

    out: list[float] = []
    for m in re.finditer(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)", q):
        try:
            out.append(float(m.group(1).replace(",", "")))
        except ValueError:
            continue
    return out


def _solve_geometry(q: str, language: str) -> dict[str, Any] | None:
    ko = language != "en"
    wants_area = bool(re.search(r"넓이|면적|area", q, re.IGNORECASE))
    wants_perim = bool(re.search(r"둘레|perimeter|circumference", q, re.IGNORECASE))
    if not (wants_area or wants_perim):
        return None
    nums = _nums_only(q)

    def pack(shape, params, metric, value, formula, answer):
        return {
            "answer": answer,
            "reasoning_certificate": _certificate([{"type": "geometry", "fact": formula}], "deterministic_geometry"),
            "confidence": 0.96,
            "result_value": value,
            "answer_visual": {
                "kind": "geometry_figure",
                "title": ("도형" if ko else "Figure"),
                "shape": shape,
                "params": params,
                "metric": metric,
                "result": value,
                "formula": formula,
                "registry_hint": f"geometry_{shape}_{metric}",
            },
        }


    if re.search(r"정사각형|square", q, re.IGNORECASE) and nums:
        s = nums[0]
        if wants_perim:
            v = 4 * s
            f = f"둘레 = 4 × {_fmt(s)} = {_fmt(v)}" if ko else f"perimeter = 4 × {_fmt(s)} = {_fmt(v)}"
            a = (f"정사각형 둘레는 {_fmt(v)}입니다. (한 변 {_fmt(s)})" if ko else f"The square's perimeter is {_fmt(v)} (side {_fmt(s)}).")
            return pack("square", {"side": s}, "perimeter", v, f, a)
        v = s * s
        f = f"넓이 = {_fmt(s)}² = {_fmt(v)}" if ko else f"area = {_fmt(s)}² = {_fmt(v)}"
        a = (f"정사각형 넓이는 {_fmt(v)}입니다. (한 변 {_fmt(s)})" if ko else f"The square's area is {_fmt(v)} (side {_fmt(s)}).")
        return pack("square", {"side": s}, "area", v, f, a)


    if re.search(r"직사각형|rectangle", q, re.IGNORECASE) and len(nums) >= 2:
        w, h = nums[0], nums[1]
        if wants_perim:
            v = 2 * (w + h)
            f = f"둘레 = 2 × ({_fmt(w)} + {_fmt(h)}) = {_fmt(v)}" if ko else f"perimeter = 2 × ({_fmt(w)} + {_fmt(h)}) = {_fmt(v)}"
            a = (f"직사각형 둘레는 {_fmt(v)}입니다." if ko else f"The rectangle's perimeter is {_fmt(v)}.")
            return pack("rectangle", {"width": w, "height": h}, "perimeter", v, f, a)
        v = w * h
        f = f"넓이 = {_fmt(w)} × {_fmt(h)} = {_fmt(v)}" if ko else f"area = {_fmt(w)} × {_fmt(h)} = {_fmt(v)}"
        a = (f"직사각형 넓이는 {_fmt(v)}입니다." if ko else f"The rectangle's area is {_fmt(v)}.")
        return pack("rectangle", {"width": w, "height": h}, "area", v, f, a)


    if re.search(r"\b원\b|원의|원\s|circle", q, re.IGNORECASE) and nums:
        r = nums[0]


        if re.search(r"(?<!반)지름|diameter", q, re.IGNORECASE) and not re.search(r"반지름", q):
            r = r / 2
        if wants_perim:
            v = 2 * _PI * r
            f = f"둘레 = 2 × π × {_fmt(r)} ≈ {_fmt(round(v, 2))}" if ko else f"circumference = 2πr ≈ {_fmt(round(v, 2))}"
            a = (f"원 둘레는 약 {_fmt(round(v, 2))}입니다. (반지름 {_fmt(r)})" if ko else f"The circle's circumference is ≈ {_fmt(round(v, 2))} (radius {_fmt(r)}).")
            return pack("circle", {"radius": r}, "perimeter", round(v, 4), f, a)
        v = _PI * r * r
        f = f"넓이 = π × {_fmt(r)}² ≈ {_fmt(round(v, 2))}" if ko else f"area = πr² ≈ {_fmt(round(v, 2))}"
        a = (f"원 넓이는 약 {_fmt(round(v, 2))}입니다. (반지름 {_fmt(r)})" if ko else f"The circle's area is ≈ {_fmt(round(v, 2))} (radius {_fmt(r)}).")
        return pack("circle", {"radius": r}, "area", round(v, 4), f, a)


    if re.search(r"삼각형|triangle", q, re.IGNORECASE) and wants_area and len(nums) >= 2:
        b, h = nums[0], nums[1]
        v = 0.5 * b * h
        f = f"넓이 = ½ × {_fmt(b)} × {_fmt(h)} = {_fmt(v)}" if ko else f"area = ½ × {_fmt(b)} × {_fmt(h)} = {_fmt(v)}"
        a = (f"삼각형 넓이는 {_fmt(v)}입니다. (밑변 {_fmt(b)}, 높이 {_fmt(h)})" if ko else f"The triangle's area is {_fmt(v)} (base {_fmt(b)}, height {_fmt(h)}).")
        return pack("triangle", {"base": b, "height": h}, "area", v, f, a)

    return None



import ast
import math as _math

_PLOT_CUE_RE = re.compile(r"그려|그래프|plot|graph|곡선", re.IGNORECASE)
_PLOT_FUNCS = {
    "sin": _math.sin, "cos": _math.cos, "tan": _math.tan, "sqrt": _math.sqrt,
    "abs": abs, "exp": _math.exp, "log": _math.log, "ln": _math.log,
}
_PLOT_CONSTS = {"pi": _math.pi, "e": _math.e}


def _safe_fx(node: ast.AST, x: float) -> float:
    """Evaluate a whitelisted arithmetic AST in one variable x. Raises on anything
    outside the whitelist — never a general eval."""
    if isinstance(node, ast.Expression):
        return _safe_fx(node.body, x)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id == "x":
            return x
        if node.id in _PLOT_CONSTS:
            return _PLOT_CONSTS[node.id]
        raise ValueError(f"name {node.id}")
    if isinstance(node, ast.BinOp):
        a, b = _safe_fx(node.left, x), _safe_fx(node.right, x)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, ast.Div):
            return a / b
        if isinstance(node.op, ast.Pow):
            return a ** b
        if isinstance(node.op, ast.Mod):
            return a % b
        raise ValueError("op")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _safe_fx(node.operand, x)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _PLOT_FUNCS:
        return float(_PLOT_FUNCS[node.func.id](*[_safe_fx(a, x) for a in node.args]))
    raise ValueError("unsupported node")


def _extract_plot_expr(q: str) -> str | None:
    s = q
    s = _PLOT_CUE_RE.sub(" ", s)
    # Strip the domain phrase first so its numbers don't leak into the function

    s = re.sub(r"(구간|범위)\s*-?\d+(?:\.\d+)?\s*(?:~|에서|to|,|부터)\s*-?\d+(?:\.\d+)?\s*(?:까지)?", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"-?\d+(?:\.\d+)?\s*(?:~|에서|부터)\s*-?\d+(?:\.\d+)?\s*까지?", " ", s)
    s = re.sub(r"(을|를|좀|해\s*줘|해|주세요|보여\s*줘|보여|의|함수|구간|범위|까지)", " ", s)
    s = re.sub(r"^\s*y\s*=\s*", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bf\s*\(\s*x\s*\)\s*=\s*", " ", s, flags=re.IGNORECASE)
    s = s.replace("^", "**")
    # keep only math-expression characters in one variable x
    s = re.sub(r"[^0-9xX+\-*/().\s a-z]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s or "x" not in s.lower():
        return None
    return s


def _solve_function_plot(q: str, language: str) -> dict[str, Any] | None:
    if not _PLOT_CUE_RE.search(q):
        return None
    raw = _extract_plot_expr(q)
    if not raw:
        return None
    try:
        tree = ast.parse(raw, mode="eval")
    except SyntaxError:
        return None
    # validate by sampling; abstain if the expression isn't a clean function of x
    try:
        _safe_fx(tree, 1.0)
    except Exception:
        return None
    lo, hi = -5.0, 5.0
    rng = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:~|에서|to|,)\s*(-?\d+(?:\.\d+)?)", q)
    if rng:
        lo, hi = float(rng.group(1)), float(rng.group(2))
        if hi <= lo:
            lo, hi = -5.0, 5.0
    n = 80
    points: list[list[float]] = []
    for i in range(n + 1):
        xv = lo + (hi - lo) * i / n
        try:
            yv = _safe_fx(tree, xv)
        except Exception:
            continue
        if isinstance(yv, complex) or yv != yv or yv in (float("inf"), float("-inf")):
            continue
        if abs(yv) > 1e6:
            continue
        points.append([round(xv, 4), round(yv, 4)])
    if len(points) < 5:
        return None
    display = raw.replace("**", "^")
    if language == "en":
        answer = f"Plotted y = {display} on [{_fmt(lo)}, {_fmt(hi)}]. (deterministic, no LLM)"
    else:
        answer = f"y = {display} 그래프를 구간 [{_fmt(lo)}, {_fmt(hi)}]에서 그렸어요. (외부 LLM 없이)"
    return {
        "answer": answer,
        "reasoning_certificate": _certificate(
            [{"type": "plot", "fact": f"y = {display} on [{_fmt(lo)}, {_fmt(hi)}], {len(points)} pts"}],
            "deterministic_function_plot",
        ),
        "confidence": 0.93,
        "answer_visual": {
            "kind": "function_plot",
            "title": "함수 그래프" if language != "en" else "Function plot",
            "expr": display,
            "formula": f"y = {display}",
            "domain": [lo, hi],
            "points": points,
            "registry_hint": "function_plot",
        },
    }


def solve_reasoning(question: str, language: str = "ko") -> dict[str, Any] | None:
    """Answer an arithmetic / geometry / counting problem deterministically, or None.

    Order: geometry (most specific) → exponent → bare arithmetic expression →
    multi-step counting word problem. Abstains on anything it cannot compile into
    an unambiguous plan. Each math answer may carry an `answer_visual` the
    dashboard renders as a figure or formula card.
    """
    q = _normalize(question)
    if not q:
        return None

    # numeric gate that the arithmetic paths rely on.
    plot = _solve_function_plot(q, language)
    if plot:
        return plot

    # so run it before the numeric gate. It COMPOSES the stated comparative relations (a
    # transitive-closure traversal), not a per-question template — the graph-native reasoning
    # shape that scales as the relation store grows.
    try:
        from app.services.transitive_reasoner import solve_transitive

        order = solve_transitive(question, language)
        if order:
            return order
    except Exception:  # pragma: no cover - reasoner must never break chat
        pass

    # also digit-less and composes stated relations via transitive closure — same shape,
    # different relation type. Runs before the numeric gate too.
    try:
        from app.services.entailment_reasoner import solve_entailment

        entail = solve_entailment(question, language)
        if entail:
            return entail
    except Exception:  # pragma: no cover - reasoner must never break chat
        pass
    if not re.search(r"\d|" + "|".join(map(re.escape, _WORD_NUM)), q):
        return None

    # composition the single-actor word-problem solver can't do — try it first.
    try:
        from app.services.compound_reasoner import solve_compound

        compound = solve_compound(question, language)
        if compound:
            return compound
    except Exception:  # pragma: no cover - reasoner must never break chat
        pass
    result = (
        _solve_geometry(q, language)
        or _solve_rate_time(q, language)
        or _solve_exponent(q, language)
        or _solve_expression(q, language)
        or _solve_word_problem(q, language)
    )
    return result
