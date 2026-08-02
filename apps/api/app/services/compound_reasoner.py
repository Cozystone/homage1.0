"""Compound relational-quantity word problems — deterministic CoT, no LLM.

The GPT "decompose then compose" pattern, done graph-natively for a real, common class the
single-actor arithmetic VM couldn't reach: quantities defined RELATIVE to each other.

 " 5 3 . ?" → 8
 "… 2 . ?" → 5 + 8 + 16 = 29
 "… ?" → 

Each premise becomes an equation over named quantities (X = N; X = Y ± N; X = Y × N); the
system is resolved by substitution (a dependency fixpoint — the same relation-composition idea
as the transitive/entailment reasoners, now carrying numeric values), then the question reads
off a value / the sum / the arg-max. Deterministic, cited step-by-step; abstains (None) on a
cycle or an unresolved reference — never guesses.
"""
from __future__ import annotations

import re
from typing import Any

_UNIT = r"(?:개|원|명|마리|권|장|살|병|잔|대|자루|송이|점|켤레|캔|줄)"
# Relational premises (checked before base; a bare number in these is a DELTA/FACTOR, not a total)
_REL_MORE = re.compile(rf"([^\s,.。]+?)(?:은|는|이|가)\s+([^\s,.。]+?)보다\s*(\d+)\s*{_UNIT}?\s*(?:더\s*)?(?:많|더|있)")
_REL_LESS = re.compile(rf"([^\s,.。]+?)(?:은|는|이|가)\s+([^\s,.。]+?)보다\s*(\d+)\s*{_UNIT}?\s*(?:더\s*)?(?:적|작|덜|없)")
_REL_TIMES = re.compile(r"([^\s,.。]+?)(?:은|는|이|가)\s+([^\s,.。]+?)의\s*(\d+)\s*배")

_BASE = re.compile(rf"([^\s,.。]+?)(?:은|는|이|가)\s+[^.。]*?(\d+)\s*{_UNIT}")

_ASK_WHO_MAX = re.compile(r"(?:누가|누구).*(?:제일|가장).*(?:많|큰|높)")
_ASK_WHO_MIN = re.compile(r"(?:누가|누구).*(?:제일|가장).*(?:적|작|낮)")
_ASK_SUM = re.compile(r"(?:모두|전부|다\s|합(?:쳐|치|계)|총)\s*.*?(?:몇|얼마)")
_ASK_ONE = re.compile(r"([^\s,.。]+?)(?:은|는|이|가)\s+(?:몇|얼마)")


def _n(word: str) -> float:
    return float(word.replace(",", ""))


def solve_compound(question: str, language: str = "ko") -> dict[str, Any] | None:
    text = (question or "").strip()
    if not text:
        return None
    sents = [s.strip() for s in re.split(r"(?<=[.。?？])\s+", text) if s.strip()]
    q_sent = next((s for s in reversed(sents) if s.rstrip().endswith(("?", "？"))), sents[-1] if sents else text)
    premises = " ".join(s for s in sents if s is not q_sent) or text

    # equations: name -> ("=", None, N) | ("+"/"-"/"*", ref, N)
    eq: dict[str, tuple[str, str | None, float]] = {}
    rel_names: set[str] = set()
    for x, y, n in _REL_MORE.findall(premises):
        eq[x] = ("+", y, _n(n)); rel_names.add(x)
    for x, y, n in _REL_LESS.findall(premises):
        eq[x] = ("-", y, _n(n)); rel_names.add(x)
    for x, y, n in _REL_TIMES.findall(premises):
        eq[x] = ("*", y, _n(n)); rel_names.add(x)
    for m in _BASE.finditer(premises):
        seg = m.group(0)
        x = m.group(1)
        if x in rel_names or "보다" in seg or "배" in seg:
            continue  # relational clause, already captured as a delta/factor
        eq.setdefault(x, ("=", None, _n(m.group(2))))
    if len(eq) < 2:
        return None  # nothing to compose — single-actor problems are the VM's job

    # Resolve by substitution (dependency fixpoint).
    val: dict[str, float] = {}
    steps: list[dict[str, Any]] = []
    for _ in range(len(eq) + 1):
        progressed = False
        for name, (op, ref, num) in eq.items():
            if name in val:
                continue
            if op == "=":
                val[name] = num
                steps.append({"type": "base", "fact": f"{name} = {_fmt(num)}"})
                progressed = True
            elif ref in val:
                base = val[ref]
                val[name] = base + num if op == "+" else base - num if op == "-" else base * num
                sym = {"+": "+", "-": "−", "*": "×"}[op]
                steps.append({"type": "rel", "fact": f"{name} = {ref}({_fmt(base)}) {sym} {_fmt(num)} = {_fmt(val[name])}"})
                progressed = True
        if not progressed:
            break
    if len(val) < len(eq):
        return None  # unresolved reference / cycle → abstain

    def _result(answer: str, detail: str) -> dict[str, Any]:
        return {
            "answer": answer,
            "reasoning_certificate": {
                "derivation_kind": "deterministic_compound_word_problem",
                "anchor_concept": None,
                "steps": steps + [{"type": "answer", "fact": detail}],
                "evidence_concepts": [],
                "confidence": 0.95,
                "confidence_basis": "relational_quantity_composition",
                "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
            },
            "confidence": 0.95,
        }

    if _ASK_WHO_MAX.search(q_sent):
        who = max(val, key=val.get)
        return _result(f"{who}{_josa(who, '이', '가')} 제일 많아요 ({_fmt(val[who])}).", f"argmax = {who}")
    if _ASK_WHO_MIN.search(q_sent):
        who = min(val, key=val.get)
        return _result(f"{who}{_josa(who, '이', '가')} 제일 적어요 ({_fmt(val[who])}).", f"argmin = {who}")
    if _ASK_SUM.search(q_sent):
        total = sum(val.values())
        return _result(f"모두 {_fmt(total)}개예요.", f"합계 = {' + '.join(_fmt(v) for v in val.values())} = {_fmt(total)}")
    am = _ASK_ONE.search(q_sent)
    if am and am.group(1) in val:
        name = am.group(1)
        return _result(f"{name}{_josa(name, '은', '는')} {_fmt(val[name])}개예요.", f"{name} = {_fmt(val[name])}")
    return None


def _josa(word: str, with_batchim: str, without_batchim: str) -> str:
    o = ord(word[-1]) if word else 0
    return with_batchim if (0xAC00 <= o <= 0xD7A3 and (o - 0xAC00) % 28 != 0) else without_batchim


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:g}"
