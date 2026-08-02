# -*- coding: utf-8 -*-
"""probe — the honest deliverable: measure the allocator against uniform baselines on three classes.

  E  EASY               R0 suffices; escalating only wastes compute. (allocator should STOP at R0)
  H  HARD               R0 is insufficient; R1/R2 are needed to get it right. (allocator should CLIMB)
  O  OVERTHINKING-PRONE R0 is right, but MORE thinking DRIFTS to wrong (Inverse Scaling) — either the
                        deep spread integrates a web distractor and its global argmax flips, or a deep
                        deliberation over-decomposes and ABSTAINS, losing the correct cheap answer.
                        (allocator should STOP at R0, before the drift)

Three policies over the SAME probe:
  * always-R0      — the cheap rung only.
  * always-R2      — uniform-deep: pay the deepest rung on every query.
  * ALLOCATOR      — the metacognitive controller (R0 first, climb only when the cheap signals say so).

The allocator WINS if it ≈ always-R2 accuracy at materially LOWER compute AND beats always-R2 on O.

Every rung runs a REAL engine (spread / deliberator); the class of each query is a fact about its
epistemic situation (is the answer directly present and dominant? does deep search meet a distractor
/ a gap?), and the engines' outputs on it are measured, not stipulated. The allocator sees ONLY the
cheap R0 signals — never the gold label, never R2's answer. A separate DECEPTIVE set (D) is reported
apart: R0 is confident but WRONG — the honest failure mode of any feeling-of-rightness allocator.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from packages.deliberator.controller import Deliberation
from packages.deliberator.steps import SubGoal

from .ladder import run_r0, run_r2
from .allocator import Allocator, AllocatorConfig, _features_from, escalate_score


# ── the probe query ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Query:
    qid: str
    cls: str                                # 'E' | 'H' | 'O' | 'D'
    text: str
    anchor: str
    intent: tuple
    gold: str
    facts_local: dict = field(default_factory=dict)
    facts_web: dict = field(default_factory=dict)
    delib: Deliberation | None = None
    delib_deep: Deliberation | None = None
    note: str = ""


# ── builders ─────────────────────────────────────────────────────────────────────────────────────

def _lookup(qid, anchor, rel, gold, text, extra=None, cls="E") -> Query:
    """A direct single-fact lookup: R0 reads the intent edge. For E, no distractor web (R2 also right)."""
    local = {anchor: [(anchor, rel, gold)] + (extra or [])}
    return Query(qid, cls, text, anchor, (rel,), gold, facts_local=local)


def _drift(qid, anchor, rel, gold, distractor, text, n_paths=11) -> Query:
    """O (drift): R0 reads the correct direct edge; a WEB distractor hub with n converging weighted
    paths makes the DEEP spread's global argmax flip to the distractor (a real over-integration
    failure). Shallow R0 (higher floor) never reaches the 3rd hop, so its field stays clean."""
    local = {anchor: [(anchor, rel, gold)] + [(anchor, "has_part", f"{qid}_a{i}") for i in range(n_paths)],
             gold: [(gold, "is_a", "thing")]}
    web = {}
    for i in range(n_paths):
        web[f"{qid}_a{i}"] = [(f"{qid}_a{i}", "part_of", f"{qid}_b{i}")]
        web[f"{qid}_b{i}"] = [(f"{qid}_b{i}", "located_in", distractor)]
    web[distractor] = [(distractor, "is_a", "thing")]
    return Query(qid, "O", text, anchor, (rel,), gold, facts_local=local, facts_web=web,
                 note=f"deep spread drifts to distractor '{distractor}'")


def _web(qid, anchor, rel, gold, text) -> Query:
    """H (web): the answer is NOT in local knowledge — only the web has the intent edge. R0 (local)
    cannot ground; R2 (local+web) lights the answer as its boosted argmax. Local is empty (no
    competing type-hub) so the web answer is the unambiguous deep argmax."""
    web = {anchor: [(anchor, rel, gold)]}          # gold is a leaf — no shared 'thing' hub to out-light it
    return Query(qid, "H", text, anchor, (rel,), gold, facts_local={}, facts_web=web,
                 note="answer only in web (2-rung climb)")


def _reach(qid, place, length, budget, gold) -> Query:
    """H (compositional): a 3-hop mechanism->relational->arithmetic deliberation single-shot cannot do.
    R0 (bare lookup, no intent edge) cannot ground -> the allocator escalates to the deliberator."""
    text = f"Will the ambulance reach {place} in time, within {budget} minutes?"
    plan = [
        SubGoal("mechanism", f"Can the ambulance cross the bridge to {place}?",
                {"question": f"Can the ambulance cross the bridge to {place}?",
                 "text": "The bridge was blocked by the flood."}, binds="blocked"),
        SubGoal("relational", f"length of the bypass to {place}?",
                {"query": f"what is the length of the bypass to {place}?",
                 "facts": [(f"bypass to {place}", "length", length)]}, binds="detour_len"),
        SubGoal("arithmetic", "is the bypass within the time budget?",
                {"expr": f"{{detour_len}} <= {budget}"}, binds="in_time"),
    ]
    compose = (lambda b: (f"The bridge is blocked, so the ambulance takes the {b['detour_len']}-min bypass; "
                          f"that is {'within' if b['in_time'] else 'OVER'} the {budget}-min budget, so it "
                          f"{'arrives in time' if b['in_time'] else 'does NOT arrive in time'}."))
    delib = Deliberation(text, plan, compose)
    return Query(qid, "H", text, "ambulance", (), gold, facts_local={"ambulance": [("ambulance", "is_a", "vehicle")]},
                 delib=delib, note="3-hop deliberation (single-shot cannot)")


def _compare(qid, pa, pb, thresh, gold) -> Query:
    text = (f"Is Town A more populous than the village, and does Town A exceed the charter minimum "
            f"of {thresh}?")
    plan = [
        SubGoal("relational", "population of Town A?",
                {"query": "what is the population of Town A?", "facts": [("Town A", "population", pa)]}, binds="a"),
        SubGoal("relational", "population of the village?",
                {"query": "what is the population of the village?", "facts": [("village", "population", pb)]}, binds="b"),
        SubGoal("arithmetic", "beats village AND clears minimum?",
                {"expr": f"{{a}} > {{b}} and {{a}} >= {thresh}"}, binds="verdict"),
    ]
    compose = (lambda b: (f"Town A has {b['a']} people and the village {b['b']}; Town A "
                          f"{'is larger and clears' if b['verdict'] else 'does NOT clear'} the "
                          f"charter minimum of {thresh}."))
    return Query(qid, "H", text, "town a", (), gold, facts_local={"town a": [("town a", "is_a", "place")]},
                 delib=Deliberation(text, plan, compose), note="3-hop comparison deliberation")


def _delib_abstain(qid, anchor, rel, gold, text) -> Query:
    """O (over-decompose -> abstain): R0 reads the correct direct answer; a DEEP deliberation adds a
    verification hop that hits a genuine gap and ABSTAINS — turning a correct cheap answer into 'I
    won't guess'. A strict loss from thinking too much (the deliberator's honest floor)."""
    local = {anchor: [(anchor, rel, gold)], gold: [(gold, "is_a", "thing")]}
    plan = [
        SubGoal("relational", f"{rel} of {anchor}?",
                {"query": f"what is the {rel} of {anchor}?", "facts": [(anchor, rel, gold)]}, binds="x"),
        # the over-decomposition: a spurious extra hop that needs an ungrounded material property
        SubGoal("mechanism", f"does {anchor} then satisfy the rare-certification rule?",
                {"question": "does it satisfy the rare-certification rule?",
                 "text": f"The {anchor} was noted in the registry."}, binds="cert"),
    ]
    delib_deep = Deliberation(text, plan, compose=lambda b: f"{b['x']} (certified)")
    return Query(qid, "O", text, anchor, (rel,), gold, facts_local=local, delib_deep=delib_deep,
                 note="deep deliberation over-decomposes and abstains")


def _deceptive(qid, anchor, rel, r0_wrong, gold, text, n_paths=13) -> Query:
    """D (deceptive-easy, reported apart): R0 confidently reads a WRONG local edge, with no rival in
    its shallow field, so it feels certain. The CORRECT answer is recoverable only by paying for the
    deep web integration (a reinforcement hub converging on `gold` that the deep argmax finds). So
    always-R2 RECOVERS gold, but the allocator — trusting R0's (mis-calibrated) confidence — stops and
    stays wrong. This isolates the honest limit the research names (§5): a feeling-of-rightness monitor
    cannot catch a confidently-wrong cheap answer. Not removed, only surfaced."""
    local = {anchor: [(anchor, rel, r0_wrong)] + [(anchor, "has_part", f"{qid}_a{i}") for i in range(n_paths)]}
    web = {}
    for i in range(n_paths):
        web[f"{qid}_a{i}"] = [(f"{qid}_a{i}", "part_of", f"{qid}_b{i}")]
        web[f"{qid}_b{i}"] = [(f"{qid}_b{i}", "located_in", gold)]
    web[gold] = [(gold, "is_a", "thing")]
    return Query(qid, "D", text, anchor, (rel,), gold, facts_local=local, facts_web=web,
                 note="R0 confident but WRONG; only deep web recovers gold")


# ── the suite ────────────────────────────────────────────────────────────────────────────────────

def build_probe() -> list[Query]:
    q: list[Query] = []

    # EASY — direct facts R0 nails; deep thinking only wastes compute -------------------------------
    q += [
        _lookup("E_capital_jp", "japan", "capital", "tokyo", "what is the capital of japan?"),
        _lookup("E_author_hamlet", "hamlet", "created_by", "shakespeare", "who wrote hamlet?"),
        _lookup("E_symbol_gold", "gold", "has_symbol", "au", "what is the chemical symbol of gold?"),
        _lookup("E_currency_jp", "japan", "currency", "yen", "what is the currency of japan?"),
        _lookup("E_capital_peru", "peru", "capital", "lima", "what is the capital of peru?"),
        _lookup("E_planet_star", "earth", "orbits", "sun", "what does the earth orbit?"),
        _lookup("E_lang_brazil", "brazil", "language", "portuguese", "what language is spoken in brazil?"),
        _lookup("E_inventor_bulb", "light bulb", "created_by", "edison", "who invented the light bulb?"),
        _lookup("E_capital_egypt", "egypt", "capital", "cairo", "what is the capital of egypt?"),
        _lookup("E_metal_symbol", "iron", "has_symbol", "fe", "what is the chemical symbol of iron?"),
    ]

    # HARD — R0 cannot; a climb is needed ----------------------------------------------------------
    q += [
        _web("H_treats_migraine", "acmedrug", "treats", "migraine", "what does acmedrug treat?"),
        _web("H_borders_x", "landia", "borders", "searia", "what country borders landia?"),
        _web("H_ceo_of", "novacorp", "led_by", "okafor", "who is the ceo of novacorp?"),
        _web("H_alloy_of", "bronzite", "made_of", "copper", "what is bronzite primarily made of?"),
        _reach("H_reach_general", "General Hospital", 22, 30, "arrives in time"),
        _reach("H_reach_far", "Far Regional", 40, 30, "does not arrive in time"),
        _reach("H_reach_tight", "Central Trauma", 28, 30, "arrives in time"),
        _compare("H_compare_pass", 5000, 800, 1000, "is larger and clears"),
        _compare("H_compare_fail", 900, 800, 1000, "does not clear"),
        _web("H_founder_of", "helio labs", "created_by", "vasquez", "who founded helio labs?"),
    ]

    # OVERTHINKING-PRONE — R0 right, deeper thinking drifts wrong -----------------------------------
    q += [
        _drift("O_capital_fr", "france", "capital", "paris", "lyon", "what is the capital of france?"),
        _drift("O_capital_it", "italy", "capital", "rome", "milan", "what is the capital of italy?"),
        _drift("O_capital_tr", "turkey", "capital", "ankara", "istanbul", "what is the capital of turkey?"),
        _drift("O_capital_au", "australia", "capital", "canberra", "sydney", "what is the capital of australia?"),
        _drift("O_capital_ca", "canada", "capital", "ottawa", "toronto", "what is the capital of canada?"),
        _drift("O_largest_us", "usa", "capital", "washington", "newyork", "what is the capital of the usa?"),
        _delib_abstain("O_deep_cap_br", "brazil", "capital", "brasilia", "what is the capital of brazil?"),
        _delib_abstain("O_deep_sym_ag", "silver", "has_symbol", "ag", "what is the chemical symbol of silver?"),
        _delib_abstain("O_deep_cur_uk", "uk", "currency", "pound", "what is the currency of the uk?"),
    ]

    # DECEPTIVE (reported apart) — R0 confidently wrong. Famous wrong-capital misconceptions: the cheap
    # read returns the well-known-but-wrong city with high confidence; the true capital needs the deep
    # web. A high-weight 'capital' relation makes R0 dominant, so the allocator cleanly STOPS (and is
    # wrong) — the sharpest form of the FOR mis-calibration limit. -------------------------------------
    q += [
        _deceptive("D_capital_za", "south africa", "capital", "johannesburg", "pretoria",
                   "what is the administrative capital of south africa?"),
        _deceptive("D_capital_tr", "turkeynation", "capital", "istanbul", "ankara",
                   "what is the capital of turkeynation?"),
        _deceptive("D_capital_kz", "kazakhstan", "capital", "almaty", "astana",
                   "what is the capital of kazakhstan?"),
    ]
    return q


# ── scoring ──────────────────────────────────────────────────────────────────────────────────────

def _norm(s: Any) -> str:
    return " ".join(str(s or "").lower().split())


def _correct(answer: str | None, gold: str) -> bool:
    if answer is None:
        return False
    return _norm(gold) in _norm(answer)


# ── the three policies ───────────────────────────────────────────────────────────────────────────

def _policy_r0(qs: list[Query]) -> list[dict]:
    out = []
    for q in qs:
        r = run_r0(q)
        out.append({"qid": q.qid, "cls": q.cls, "answer": r.answer, "cost": r.cost,
                    "correct": _correct(r.answer, q.gold), "abstained": r.abstained, "rung": "R0"})
    return out


def _policy_r2(qs: list[Query]) -> list[dict]:
    out = []
    for q in qs:
        # uniform-deep: pay R2 directly on every query (the strongest single-rung baseline)
        r = run_r2(q)
        out.append({"qid": q.qid, "cls": q.cls, "answer": r.answer, "cost": r.cost,
                    "correct": _correct(r.answer, q.gold), "abstained": r.abstained, "rung": "R2"})
    return out


def _policy_allocator(qs: list[Query], cfg: AllocatorConfig | None = None) -> list[dict]:
    alloc = Allocator(cfg)
    out = []
    for q in qs:
        tr = alloc.allocate(q)
        out.append({"qid": q.qid, "cls": q.cls, "answer": tr.answer, "cost": tr.total_cost,
                    "correct": _correct(tr.answer, q.gold), "abstained": tr.abstained,
                    "rung": tr.rung_reached, "final": tr.final_rung})
    return out


# ── aggregate + report ───────────────────────────────────────────────────────────────────────────

def _agg(rows: list[dict], classes: tuple) -> dict:
    per = {}
    for c in classes:
        crows = [r for r in rows if r["cls"] == c]
        n = len(crows)
        per[c] = {"n": n, "acc": (sum(r["correct"] for r in crows) / n if n else 0.0),
                  "cost": sum(r["cost"] for r in crows)}
    core = [r for r in rows if r["cls"] in ("E", "H", "O")]
    n = len(core)
    per["ALL"] = {"n": n, "acc": (sum(r["correct"] for r in core) / n if n else 0.0),
                  "cost": sum(r["cost"] for r in core)}
    return per


def run_probe() -> dict:
    qs = build_probe()
    core = [q for q in qs if q.cls in ("E", "H", "O")]
    decep = [q for q in qs if q.cls == "D"]

    pols = {"always_R0": _policy_r0(core), "always_R2": _policy_r2(core),
            "allocator": _policy_allocator(core)}
    aggs = {name: _agg(rows, ("E", "H", "O")) for name, rows in pols.items()}

    # per-class R0 feature means (to show the signal separation honestly)
    feat_means: dict[str, dict[str, float]] = {}
    for c in ("E", "H", "O"):
        cs = [q for q in core if q.cls == c]
        accum: dict[str, float] = {}
        for q in cs:
            r0 = run_r0(q)
            f = _features_from(r0, q, remaining_budget=1.0).as_dict()
            f["escalate_score"] = round(escalate_score(_features_from(r0, q, remaining_budget=1.0)), 4)
            for k, v in f.items():
                accum[k] = accum.get(k, 0.0) + v
        feat_means[c] = {k: round(v / len(cs), 4) for k, v in accum.items()} if cs else {}

    # deceptive set (reported apart)
    dec_pols = {"always_R0": _policy_r0(decep), "always_R2": _policy_r2(decep),
                "allocator": _policy_allocator(decep)}
    dec_aggs = {name: _agg(rows, ("D",))["D"] for name, rows in dec_pols.items()}

    return {"policies": pols, "aggregates": aggs, "feature_means": feat_means,
            "deceptive": {"rows": dec_pols, "aggregates": dec_aggs},
            "counts": {c: len([q for q in core if q.cls == c]) for c in ("E", "H", "O")}}


def _fmt_table(aggs: dict) -> str:
    classes = ("E", "H", "O", "ALL")
    lines = []
    head = f"{'policy':<12} " + " ".join(f"{c:>16}" for c in classes)
    lines.append(head)
    lines.append("-" * len(head))
    for name in ("always_R0", "always_R2", "allocator"):
        cells = []
        for c in classes:
            a = aggs[name][c]
            cells.append(f"{a['acc']*100:5.1f}% /{a['cost']:6.0f}")
        lines.append(f"{name:<12} " + " ".join(f"{c:>16}" for c in cells))
    lines.append("")
    lines.append("cell = accuracy% / total compute (op-units).  ALL = E+H+O combined.")
    return "\n".join(lines)


def main() -> None:
    rep = run_probe()
    print("=" * 78)
    print("CO ALLOCATOR (NS-4) — 3-policy comparison over E/H/O probe")
    print("=" * 78)
    print(f"class sizes: {rep['counts']}\n")
    print(_fmt_table(rep["aggregates"]))
    print("\nR0 cheap-signal means per class (what the allocator decides on):")
    for c in ("E", "H", "O"):
        print(f"  {c}: {rep['feature_means'][c]}")
    print("\nDECEPTIVE set (reported apart — R0 confident but WRONG):")
    for name in ("always_R0", "always_R2", "allocator"):
        a = rep["deceptive"]["aggregates"][name]
        print(f"  {name:<12} acc {a['acc']*100:5.1f}%  cost {a['cost']:.0f}  (n={a['n']})")
    print()
    # blunt verdict
    al = rep["aggregates"]["allocator"]; r2 = rep["aggregates"]["always_R2"]; r0 = rep["aggregates"]["always_R0"]
    print("VERDICT:")
    print(f"  allocator ALL acc {al['ALL']['acc']*100:.1f}% at {al['ALL']['cost']:.0f} ops "
          f"vs always-R2 {r2['ALL']['acc']*100:.1f}% at {r2['ALL']['cost']:.0f} ops "
          f"vs always-R0 {r0['ALL']['acc']*100:.1f}% at {r0['ALL']['cost']:.0f} ops")
    save = 100.0 * (1 - al['ALL']['cost'] / r2['ALL']['cost']) if r2['ALL']['cost'] else 0.0
    print(f"  compute saved vs always-R2: {save:.1f}%   |   O-class: allocator {al['O']['acc']*100:.0f}% "
          f"vs always-R2 {r2['O']['acc']*100:.0f}%")


if __name__ == "__main__":
    main()
