# -*- coding: utf-8 -*-
"""Hypothesis elimination — enumerate candidate worlds, test each against every observation, keep
the survivors with their evidence trail (Grand Plan v2, G4). No-LLM: pure search + verification.

This is the engine the owner's Black-Relay-class exams gate: a puzzle states a set of CANDIDATES
(who could be the culprit / which switch drives the light / what caused the failure), a set of
CONSTRAINTS the true answer must satisfy, and OBSERVATIONS that rule candidates in or out. The honest
method is deduction, not guessing:

  1. read the candidates and the constraints from the passage (domain-blind, like the situation model)
  2. for each candidate, check it against EVERY constraint; a violated constraint eliminates it,
     and the eliminating constraint is recorded as the reason
  3. report the surviving set. Exactly one survivor -> a definite answer WITH its proof. Several
     survivors -> honestly under-determined (name them, do not pick). Zero survivors -> the
     constraints are inconsistent (say so), never invent a culprit.

Fabrication is impossible: an answer is a candidate that survived elimination, and every elimination
cites the constraint that did it. This composes with the situation model (which supplies the events
the constraints are checked against) and generalizes the self-causal reasoner's counterfactual
checking from one scenario to an arbitrary candidate set.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .reasoner import _content


@dataclass
class Constraint:
    """A stated requirement the true answer must satisfy. `test(candidate, facts) -> bool`: True =
    the candidate is consistent with this constraint; False = it is eliminated by it."""
    text: str
    test: Callable[[str, dict], bool]


@dataclass
class Elimination:
    candidate: str
    by: str                      # the constraint text that eliminated it (the proof of exclusion)


@dataclass
class Verdict:
    survivors: list[str]
    eliminated: list[Elimination] = field(default_factory=list)
    determined: bool = False     # exactly one survivor
    reply: str = ""


# ── constraint DSL: the common Black-Relay-class shapes, as testable predicates ──────────────────
def not_candidate(name: str) -> Constraint:
    """'X is not the one' / 'X was cleared' -> eliminates X."""
    key = name.lower().strip()
    return Constraint(text=f"{name} is excluded",
                      test=lambda c, f: c.lower().strip() != key)


def must_have_property(prop: str, holders: set[str]) -> Constraint:
    """'the culprit had access' -> only candidates in `holders` (those the passage grants the
    property) survive."""
    hs = {h.lower().strip() for h in holders}
    return Constraint(text=f"must have: {prop}",
                      test=lambda c, f: c.lower().strip() in hs)


def must_not_have_property(prop: str, holders: set[str]) -> Constraint:
    """'the culprit was not present at the time' -> candidates WITH the (disqualifying) property are
    eliminated."""
    hs = {h.lower().strip() for h in holders}
    return Constraint(text=f"must not have: {prop}",
                      test=lambda c, f: c.lower().strip() not in hs)


def eliminate(candidates: list[str], constraints: list[Constraint], facts: dict | None = None) -> Verdict:
    """Run the elimination. Deterministic, total, and every exclusion carries its reason."""
    facts = facts or {}
    survivors: list[str] = []
    elim: list[Elimination] = []
    seen = set()
    for cand in candidates:
        k = cand.lower().strip()
        if not k or k in seen:
            continue
        seen.add(k)
        killed_by = None
        for con in constraints:
            try:
                ok = con.test(cand, facts)
            except Exception:
                ok = True
            if not ok:
                killed_by = con.text
                break
        if killed_by is None:
            survivors.append(cand)
        else:
            elim.append(Elimination(candidate=cand, by=killed_by))
    v = Verdict(survivors=survivors, eliminated=elim, determined=len(survivors) == 1)
    if len(survivors) == 1:
        why = "; ".join(f"{e.candidate} ({e.by})" for e in elim) or "no eliminations needed"
        v.reply = (f"It must be {survivors[0]}: every other candidate is ruled out — {why}. "
                   f"{survivors[0]} is the only one no constraint excludes.")
    elif len(survivors) == 0:
        v.reply = ("No candidate survives — the stated constraints are mutually inconsistent. I "
                   "won't name one; the passage rules them all out.")
    else:
        v.reply = (f"Under-determined: {', '.join(survivors)} all survive the stated constraints. "
                   f"The passage does not narrow it to one — I won't guess between them.")
    return v


# ── auto-extraction of a Black-Relay-shaped puzzle from free text (domain-blind) ─────────────────
_CAND_LINE = re.compile(
    r"\b(?:suspects?|candidates?|switches?|possible causes?)\s*(?:are|:)\s*(.+?)\.|"
    r"\b(?:people|persons?|ones?)\s+(?:who\s+)?could have done it:?\s*(.+?)\.", re.IGNORECASE)
_CLEARED = re.compile(r"\b([A-Z][a-z]+)\b[^.]{0,40}\b(?:was cleared|is innocent|has an alibi|"
                      r"was elsewhere|could not have|is ruled out|was not involved)", re.IGNORECASE)
# 'Only A and C had <property>' -> only those named survive the must-have constraint
_ONLY_HAVE = re.compile(r"\bonly\s+(.+?)\s+had\s+(.+?)[.,]", re.IGNORECASE)
# '<Name> also had <x>, placing them elsewhere' -> that name is excluded (a disqualifier)
_PLACED_ELSEWHERE = re.compile(r"\b([A-Z][a-z]+)\b[^.]{0,60}\bplacing (?:them|him|her) elsewhere",
                               re.IGNORECASE)


def _names_in(s: str) -> list[str]:
    return [re.sub(r"[.;].*$", "", c).strip()
            for c in re.split(r",|\band\b|/", s) if c.strip()]


def from_text(text: str) -> Verdict | None:
    """Extract a candidate set + elimination constraints from a passage and solve it — domain-blind.
    Handles explicit clearances (alibi/cleared), MUST-HAVE property restrictions ('only A and C had
    X'), and disqualifiers ('A also had Y, placing them elsewhere'). None when no candidate set is
    stated (not this genre)."""
    t = text or ""
    m = _CAND_LINE.search(t)
    if not m:
        return None
    cands = [c for c in _names_in(m.group(1) or m.group(2) or "") if c and len(c) < 40][:12]
    if len(cands) < 2:
        return None
    constraints: list[Constraint] = [not_candidate(name) for name in _CLEARED.findall(t)]
    oh = _ONLY_HAVE.search(t)
    if oh:
        holders = {h for h in _names_in(oh.group(1)) if h and h[0:1].isupper()}
        if holders:
            constraints.append(must_have_property(oh.group(2).strip()[:40], holders))
    for name in _PLACED_ELSEWHERE.findall(t):
        constraints.append(not_candidate(name))
    return eliminate(cands, constraints)


# ── control / system-identification: trials establish input->output; pick the input for a target ──
_TRIAL = re.compile(r"\binput\s+(\w+)\s+left the\s+(\w+)\s+(\w+)", re.IGNORECASE)
_ASK_INPUT = re.compile(r"which input.*\bleave the\s+(\w+)\s+(\w+)", re.IGNORECASE)


def solve_control(text: str, question: str) -> dict[str, Any] | None:
    """From stated trials (input X left the device in state S), pick the input that yields the asked
    target state — ONLY if a trial determined it; abstain otherwise. Generalizes the self-causal
    reasoner's competence to arbitrary devices/inputs. None when it is not a control question."""
    am = _ASK_INPUT.search(question or "")
    if not am:
        return None
    dev, target = am.group(1).lower(), am.group(2).lower()
    mapping = {out.lower(): inp for inp, d, out in _TRIAL.findall(text or "") if d.lower() == dev}
    if target in mapping:
        return {"answer": f"Send {mapping[target]} — a trial showed it leaves the {dev} {target}.",
                "determined": True, "input": mapping[target]}
    return {"answer": f"The trials do not determine how to leave the {dev} {target} — I won't guess.",
            "determined": False, "input": None}
