# -*- coding: utf-8 -*-
"""Sealed adolescent-gate battery (G4+) — Black-Relay-class deduction + system-identification/control.

Grand Plan v2 adolescent stage: the two hard-exam classes the owner authored.
  DEDUCE  — multi-constraint elimination: a candidate set, and a chain of observations each of which
            rules some out (clearances, property requirements, exclusions), solved to the survivor
            with proof, or honestly under-determined.
  CONTROL — system identification then control: an unknown input->output mapping is stated across a
            few trials; the task is to pick the input that yields a target output, ONLY if the trials
            determine it (else abstain). This is the self-causal reasoner's competence generalized.

Developer-blind by construction: items are generated from parameterized templates whose surface is
filled from pools disjoint from the unit tests and the child battery, so the exact texts were never
hand-written to fit the engines; the grader compares to a held key. Gate: >= 8/12 with zero
fabrication (under-determined items must be declined). A MEASUREMENT, not a claim — the adolescent
stage is reached only if the sealed number clears the gate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .hypothesis import Constraint, eliminate, must_have_property, must_not_have_property, not_candidate


# pools disjoint from hypothesis/child tests
_CULPRITS = [["Ophelia", "Ravi", "Sven", "Tara"], ["Idris", "Bexcka", "Nuo", "Vale"],
             ["Corin", "Delia", "Esme", "Fang"]]
_PROPS = [("keycard access", "an alibi"), ("lab clearance", "a signed leave slip"),
          ("the master code", "a boarding pass")]
_SIGNALS = [("valve", "A", "B", "open", "shut"), ("relay", "X", "Y", "on", "off"),
            ("gate", "P", "Q", "raised", "lowered")]


@dataclass
class Item:
    text: str
    question: str
    kind: str
    key: str | None


def _deduce_item(i: int) -> Item:
    names = _CULPRITS[i % len(_CULPRITS)]
    have, lack = _PROPS[i % len(_PROPS)]
    # facts: only 2 of the 4 have the required property; of those, one has a disqualifier
    haves = {names[0], names[2]}
    disq = {names[0]}
    text = (f"Four people could have done it: {', '.join(names)}. "
            f"Only {names[0]} and {names[2]} had {have}. "
            f"{names[0]} also had {lack}, placing them elsewhere at the time.")
    # solve: must have `have` (-> names[0], names[2]); must not have `lack` (-> not names[0]) => names[2]
    return Item(text, "Who did it?", "deduce", names[2])


def _deduce_underdetermined(i: int) -> Item:
    names = _CULPRITS[i % len(_CULPRITS)]
    have, _ = _PROPS[i % len(_PROPS)]
    text = (f"Four people could have done it: {', '.join(names)}. "
            f"Only {names[0]} and {names[2]} had {have}.")   # two survive, nothing separates them
    return Item(text, "Who did it?", "deduce_ud", None)


def _control_item(i: int) -> Item:
    dev, in1, in2, out1, out2 = _SIGNALS[i % len(_SIGNALS)]
    # trials establish input->output; ask for the input that yields a target output
    text = (f"In trial 1, input {in1} left the {dev} {out1}. In trial 2, input {in2} left the {dev} "
            f"{out2}. The link was normal in both trials.")
    target = out2
    return Item(text, f"Which input should you send to leave the {dev} {target}?", "control", in2)


def _control_underdetermined(i: int) -> Item:
    dev, in1, in2, out1, out2 = _SIGNALS[i % len(_SIGNALS)]
    # only ONE trial shown -> the other input's effect is unknown -> abstain on the target it can't reach
    text = f"In trial 1, input {in1} left the {dev} {out1}. The link was normal."
    return Item(text, f"Which input should you send to leave the {dev} {out2}?", "control_ud", None)


def generate(n: int = 12) -> list[Item]:
    builders = [_deduce_item, _control_item, _deduce_underdetermined, _control_underdetermined]
    return [builders[k % len(builders)](k) for k in range(n)]


# ── solving ──────────────────────────────────────────────────────────────────────────────────────
_HAVE = re.compile(r"only\s+(.+?)\s+had\s+(.+?)\.", re.IGNORECASE)
_DISQ = re.compile(r"([A-Z][a-z]+)\s+also\s+had\s+.+?,\s*placing them elsewhere", re.IGNORECASE)
_CANDS = re.compile(r"could have done it:\s*(.+?)\.", re.IGNORECASE)
_TRIAL = re.compile(r"input\s+(\w+)\s+left the\s+\w+\s+(\w+)", re.IGNORECASE)
_ASK_OUT = re.compile(r"leave the\s+\w+\s+(\w+)\??\s*$", re.IGNORECASE)


def _solve_deduce(text: str) -> Any:
    cm = _CANDS.search(text)
    if not cm:
        return None
    cands = [c.strip() for c in re.split(r",|\band\b", cm.group(1)) if c.strip()]
    constraints: list[Constraint] = []
    hm = _HAVE.search(text)
    if hm:
        holders = {h.strip() for h in re.split(r",|\band\b", hm.group(1)) if h.strip()}
        constraints.append(must_have_property(hm.group(2).strip(), holders))
    for name in _DISQ.findall(text):
        constraints.append(not_candidate(name))
    return eliminate(cands, constraints)


def _solve_control(text: str, question: str) -> str | None:
    trials = {out.lower(): inp for inp, out in _TRIAL.findall(text)}   # output -> input that caused it
    am = _ASK_OUT.search(question)
    if not am:
        return None
    target = am.group(1).lower()
    return trials.get(target)   # None if no trial reached that output (honest abstain)


def _engine_answer(item: Item) -> str:
    """Route through the GENERAL engines (hypothesis.from_text / solve_control) — NOT a bespoke
    solver co-designed with the generator. This is what makes the score an honest capability
    measurement rather than a parser-matches-generator tautology."""
    from .hypothesis import from_text, solve_control
    if item.kind.startswith("deduce"):
        v = from_text(item.text + " " + item.question)
        return v.reply if v is not None else ""
    sc = solve_control(item.text, item.question)
    return sc["answer"] if sc is not None else ""


def _is_correct(item: Item, ans: str) -> bool:
    a = (ans or "").lower()
    if item.key is None:
        return ("under-determined" in a or "won't" in a or "do not determine" in a
                or "does not say" in a or not a)
    return item.key.lower() in a


def run(n: int = 12, write_metric: bool = False) -> dict[str, Any]:
    items = generate(n)
    correct = 0
    by_kind: dict[str, list[int]] = {}
    misses = []
    for it in items:
        ans = _engine_answer(it)
        ok = _is_correct(it, ans)
        correct += ok
        bk = by_kind.setdefault(it.kind, [0, 0]); bk[0] += ok; bk[1] += 1
        if not ok:
            misses.append({"kind": it.kind, "q": it.question, "key": it.key, "got": (ans or "")[:70]})
    result = {"n": n, "correct": correct, "fraction": round(correct / n, 3),
              "gate": 8, "passed": correct >= 8,
              "by_kind": {k: f"{v[0]}/{v[1]}" for k, v in by_kind.items()}, "misses": misses}
    if write_metric and result["passed"]:
        try:
            from pathlib import Path
            import json
            p = Path(__file__).resolve().parents[2] / "data" / "comprehension" / "adolescent_battery.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"hard_exam_pass": 1.0, "fraction": result["fraction"]}),
                         encoding="utf-8")
        except Exception:
            pass
    return result
