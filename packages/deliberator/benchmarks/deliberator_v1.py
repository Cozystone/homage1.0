# -*- coding: utf-8 -*-
"""deliberator_v1 — the System-2 benchmark: multi-step grounded reasoning that single-shot cannot do.

~20 MULTI-HOP tasks (2-4 hops) composed from the domains our organs cover — blocked-path + timing,
false-belief + a property of the believed place, relational comparison, and L3-synthesized predicate
checks — each built so a single organ CANNOT answer the composite question but a VERIFIED chain can.

~6 ABSTAIN tasks that require an ungrounded fact somewhere in the chain: the deliberation must abstain
honestly, never fabricate the bridge. Each abstain task exercises a different organ's honesty floor
(relational gap, mechanism material-gap, unwitnessed belief, non-numeric arithmetic, unsynthesizable
predicate) and one abstains MID-CHAIN (its first hop grounds, the second cannot).

Report: multi-hop solved via verified chain vs single-shot baseline, abstain-correct count, and the
FAIL count (a fabricated or wrong composed answer) which MUST be 0.
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from packages.deliberator.controller import Deliberation, deliberate, single_shot
from packages.deliberator.steps import SubGoal

# isolate L3 program synthesis from the shared authored library during the benchmark
_LIB = Path(tempfile.mkdtemp(prefix="deliberator_bench_lib_")) / "library.jsonl"


@dataclass
class Case:
    name: str
    kind: str                       # "multi_hop" | "abstain"
    deliberation: Deliberation
    expect_contains: str = ""       # multi_hop: the composed answer must contain this (decisive) token
    hops: int = 0


# ── reusable grounding fragments ─────────────────────────────────────────────────────────────────

_SALLY_ANNE = [
    "Sally and Anne were in the room.",
    "The marble was in the basket.",
    "Sally stepped out.",
    "Anne put down the marble.",
]                                    # Sally (absent) still believes 'basket'; Anne believes 'room'

_TOM_JANE = [
    "Tom and Jane were in the office.",
    "The report was on the desk.",
]                                    # co-present: each believes the other saw report -> desk


def _mech(question: str, text: str, binds: str | None = None) -> SubGoal:
    return SubGoal("mechanism", question, {"question": question, "text": text}, binds=binds)


def _rel(query: str, facts: list, binds: str | None = None) -> SubGoal:
    return SubGoal("relational", query, {"query": query, "facts": facts}, binds=binds)


def _arith(desc: str, expr: str, binds: str | None = None) -> SubGoal:
    return SubGoal("arithmetic", desc, {"expr": expr}, binds=binds)


def _belief(desc: str, kind: str, binds: str | None = None, **kw) -> SubGoal:
    payload = {"sentences": kw.pop("sentences"), "kind": kind}
    payload.update(kw)
    return SubGoal("belief", desc, payload, binds=binds)


def _pred(name: str, signature: str, docstring: str, test: str, apply: list, binds: str) -> SubGoal:
    return SubGoal("predicate", docstring,
                   {"name": name, "signature": signature, "docstring": docstring, "test": test,
                    "apply": apply, "library": _LIB}, binds=binds)


# ── the suite ────────────────────────────────────────────────────────────────────────────────────

def build_suite() -> list[Case]:
    cases: list[Case] = []

    # ---- Family A: mechanism(blocked) -> relational(detour length) -> arithmetic(<= budget) --------
    def reach_in_time(name, place, length, budget, expect):
        goal = f"Will the ambulance reach {place} in time (within {budget} minutes)?"
        plan = [
            _mech(f"Can the ambulance cross the bridge to {place}?",
                  "The bridge was blocked by the flood.", binds="blocked"),
            _rel(f"what is the length of the bypass to {place}?",
                 [(f"bypass to {place}", "length", length)], binds="detour_len"),
            _arith("is the bypass within the time budget?", f"{{detour_len}} <= {budget}", binds="in_time"),
        ]
        compose = (lambda b: (f"The direct bridge is blocked, so the ambulance takes the bypass "
                              f"({b['detour_len']} min); that is "
                              f"{'within' if b['in_time'] else 'OVER'} the {budget}-minute budget, so it "
                              f"{'arrives in time' if b['in_time'] else 'does NOT arrive in time'}."))
        return Case(name, "multi_hop", Deliberation(goal, plan, compose), expect, hops=3)

    cases.append(reach_in_time("reach_general_22", "General Hospital", 22, 30, "arrives in time"))
    cases.append(reach_in_time("reach_riverside_15", "Riverside Clinic", 15, 20, "arrives in time"))
    cases.append(reach_in_time("reach_far_40", "Far Regional", 40, 30, "does not arrive in time"))
    cases.append(reach_in_time("reach_tight_28", "Central Trauma", 28, 30, "arrives in time"))
    cases.append(reach_in_time("reach_boundary_30", "Boundary Hospital", 30, 30, "arrives in time"))

    # ---- Family B: belief(false-belief) -> mechanism(locked place) --------------------------------
    def belief_locked(name):
        goal = "When Sally comes back, will she be able to get the marble where she looks?"
        plan = [
            _belief("where does Sally think the marble is?", "believes",
                    sentences=_SALLY_ANNE, agent="Sally", entity="marble", binds="place"),
            _mech("Can Sally open the {place}?",
                  "The {place} was locked. The key is inside.", binds="can_open"),
        ]
        compose = (lambda b: (f"Sally will look in the {b['place']} (where she last saw the marble), "
                              f"but the {b['place']} is locked with the key inside, so she cannot open "
                              f"it — she will not get the marble."))
        return Case(name, "multi_hop", Deliberation(goal, plan, compose), "cannot open", hops=2)

    cases.append(belief_locked("belief_locked_basket"))

    # ---- Family C: belief(false-belief) -> relational(property of believed place) -----------------
    def belief_property(name, material):
        goal = "What is the container Sally will search made of?"
        plan = [
            _belief("where does Sally think the marble is?", "believes",
                    sentences=_SALLY_ANNE, agent="Sally", entity="marble", binds="place"),
            _rel("what is the {place} made of?", [("basket", "made_of", material)], binds="material"),
        ]
        compose = (lambda b: (f"Sally will search the {b['place']} (her last sighting); the {b['place']} "
                              f"is made of {b['material']}."))
        return Case(name, "multi_hop", Deliberation(goal, plan, compose), material, hops=2)

    cases.append(belief_property("belief_prop_wicker", "wicker"))
    cases.append(belief_property("belief_prop_oak", "oak"))

    # ---- Family D: relational -> relational -> arithmetic (comparison + threshold) -----------------
    def compare_threshold(name, pa, pb, thresh, expect):
        goal = (f"Is Town A more populous than the village, and does Town A exceed the charter "
                f"minimum of {thresh}?")
        plan = [
            _rel("what is the population of Town A?", [("Town A", "population", pa)], binds="a"),
            _rel("what is the population of the village?", [("village", "population", pb)], binds="b"),
            _arith("does Town A beat the village AND clear the charter minimum?",
                   f"{{a}} > {{b}} and {{a}} >= {thresh}", binds="verdict"),
        ]
        compose = (lambda b: (f"Town A has {b['a']} people and the village {b['b']}; Town A "
                              f"{'is larger and clears' if b['verdict'] else 'does NOT clear'} the "
                              f"charter minimum of {thresh}."))
        return Case(name, "multi_hop", Deliberation(goal, plan, compose), expect, hops=3)

    cases.append(compare_threshold("compare_pass_5000", 5000, 800, 1000, "is larger and clears"))
    cases.append(compare_threshold("compare_pass_2200", 2200, 1900, 2000, "is larger and clears"))
    cases.append(compare_threshold("compare_fail_small", 900, 800, 1000, "does not clear"))
    cases.append(compare_threshold("compare_fail_under", 1500, 1600, 1000, "does not clear"))

    # ---- Family E: relational(numeric attr) -> predicate (L3 synthesize + apply) -------------------
    def rel_predicate(name, area, cap, expect):
        goal = "Does the warehouse floor fit within the permitted capacity?"
        plan = [
            _rel("what is the area of the warehouse?", [("warehouse", "area", area)], binds="area"),
            _pred("within", "def within(load, cap):",
                  "Return True if load is less than or equal to cap.",
                  "assert within(20, 30) is True\nassert within(40, 30) is False\n"
                  "assert within(30, 30) is True",
                  apply=["{area}", cap], binds="fits"),
        ]
        compose = (lambda b: (f"The warehouse area is {b['area']}; a synthesized-and-verified capacity "
                              f"check finds it {'WITHIN' if b['fits'] else 'OVER'} the permitted {cap} "
                              f"— {'fits' if b['fits'] else 'does not fit'}."))
        return Case(name, "multi_hop", Deliberation(goal, plan, compose), expect, hops=2)

    cases.append(rel_predicate("pred_fits_40", 40, 50, "fits"))
    cases.append(rel_predicate("pred_over_60", 60, 50, "does not fit"))

    # ---- Family F: mechanism(blocked) -> relational -> predicate (3-hop L3) ------------------------
    def mech_rel_predicate(name, length, expect):
        goal = "Bridge is out — is the detour an EVEN number of kilometres (for the paired-convoy rule)?"
        plan = [
            _mech("Can the convoy cross the bridge?", "The bridge was blocked by a landslide.",
                  binds="blocked"),
            _rel("what is the length of the detour?", [("detour", "length", length)], binds="len"),
            _pred("is_even", "def is_even(n):", "Return True if n is even.",
                  "assert is_even(4) is True\nassert is_even(7) is False\nassert is_even(0) is True",
                  apply=["{len}"], binds="even"),
        ]
        compose = (lambda b: (f"The bridge is blocked, so the convoy detours {b['len']} km; a "
                              f"synthesized parity check says that is "
                              f"{'EVEN (paired-convoy rule satisfied)' if b['even'] else 'ODD (rule NOT satisfied)'}."))
        return Case(name, "multi_hop", Deliberation(goal, plan, compose), expect, hops=3)

    cases.append(mech_rel_predicate("mrp_even_12", 12, "paired-convoy rule satisfied"))
    cases.append(mech_rel_predicate("mrp_odd_15", 15, "rule not satisfied"))

    # ---- Family G: second-order belief -> relational ----------------------------------------------
    goal_g = "Where does Tom expect Jane to look for the report, and what is that surface made of?"
    plan_g = [
        _belief("where does Tom think Jane will look for the report?", "believes_second",
                sentences=_TOM_JANE, holder="Tom", subject="Jane", entity="report", binds="place"),
        _rel("what is the {place} made of?", [("desk", "made_of", "oak")], binds="material"),
    ]
    compose_g = (lambda b: (f"Tom expects Jane to look on the {b['place']} (both saw it there); the "
                            f"{b['place']} is made of {b['material']}."))
    cases.append(Case("second_order_desk", "multi_hop", Deliberation(goal_g, plan_g, compose_g),
                      "oak", hops=2))

    # ---- Family H: mechanism -> relational -> relational -> arithmetic (4-hop) ---------------------
    def four_hop(name, length, load, expect):
        goal = ("Bridge blocked — can the ambulance still make it via the bypass within 30 min AND "
                "stay under the 5-tonne bypass weight limit?")
        plan = [
            _mech("Can the ambulance cross the bridge?", "The bridge was blocked by the flood.",
                  binds="blocked"),
            _rel("what is the length of the bypass?", [("bypass", "length", length)], binds="len"),
            _rel("what is the mass of the ambulance?", [("ambulance", "mass", load)], binds="load"),
            _arith("within time AND under weight?", f"{{len}} <= 30 and {{load}} <= 5", binds="ok"),
        ]
        def compose(b):
            verdict = "BOTH limits hold, so yes" if b["ok"] else "a limit is exceeded, so no"
            return (f"The bridge is blocked; the bypass is {b['len']} min and the ambulance "
                    f"{b['load']} tonnes — {verdict}.")
        return Case(name, "multi_hop", Deliberation(goal, plan, compose), expect, hops=4)

    cases.append(four_hop("four_ok", 22, 3, "both limits hold"))
    cases.append(four_hop("four_overweight", 22, 7, "a limit is exceeded"))

    # ---- Family J: belief -> relational -> arithmetic (3-hop) -------------------------------------
    goal_j = "Sally looks for the marble — is the shelf she checks tall enough (>= 3) to reach?"
    plan_j = [
        _belief("where does Sally think the marble is?", "believes",
                sentences=_SALLY_ANNE, agent="Sally", entity="marble", binds="place"),
        _rel("what is the height of the {place}?", [("basket", "height", 4)], binds="h"),
        _arith("is it tall enough?", "{h} >= 3", binds="tall"),
    ]
    compose_j = (lambda b: (f"Sally checks the {b['place']}, whose height is {b['h']}; that is "
                            f"{'tall enough' if b['tall'] else 'too short'} to reach."))
    cases.append(Case("belief_rel_arith", "multi_hop", Deliberation(goal_j, plan_j, compose_j),
                      "tall enough", hops=3))

    # =============================================================== ABSTAIN SET (must NOT fabricate)

    # 1) MID-CHAIN gap: hop0 (blocked) grounds, hop1 needs a detour length the store does not hold.
    ab1 = Deliberation(
        "Will the ambulance reach the clinic in time?",
        [_mech("Can the ambulance cross the bridge?", "The bridge was blocked by the flood.",
               binds="blocked"),
         _rel("what is the length of the bypass?", [("bypass", "surface", "gravel")], binds="len"),
         _arith("within budget?", "{len} <= 30", binds="in_time")],
        compose=lambda b: "unreachable")
    cases.append(Case("abstain_midchain_relgap", "abstain", ab1, hops=3))

    # 2) mechanism MATERIAL-gap: needs a material property (fragility) the text does not state.
    ab2 = Deliberation(
        "If the shelf is bumped, will the vase shatter?",
        [_mech("Will the vase shatter if bumped?", "Mia placed a vase on the shelf.", binds="shatters"),
         _rel("what is the vase made of?", [("vase", "made_of", "glass")], binds="mat")],
        compose=lambda b: "shatters")
    cases.append(Case("abstain_mechanism_material", "abstain", ab2, hops=1))

    # 3) belief NOT witnessed: Bob never co-present with the placement, so his belief is ungrounded.
    story = ["Ann was in the kitchen.", "The key was in the drawer.", "Ann moved the key to the bag."]
    ab3 = Deliberation(
        "Where will Bob look for the key, and what is that made of?",
        [_belief("where does Bob think the key is?", "believes",
                 sentences=story, agent="Bob", entity="key", binds="place"),
         _rel("what is the {place} made of?", [("drawer", "made_of", "wood")], binds="mat")],
        compose=lambda b: "unknown")
    cases.append(Case("abstain_belief_unwitnessed", "abstain", ab3, hops=1))

    # 4) NON-numeric arithmetic: a grounded relational binds a word; the arithmetic cannot compare it.
    ab4 = Deliberation(
        "Is the basket's material within the 30-minute budget?",
        [_rel("what is the basket made of?", [("basket", "made_of", "wicker")], binds="x"),
         _arith("within budget?", "{x} <= 30", binds="ok")],
        compose=lambda b: "within budget")
    cases.append(Case("abstain_arith_nonnumeric", "abstain", ab4, hops=2))

    # 5) UNSYNTHESIZABLE predicate: a spec code_author cannot verify a program for -> abstain.
    ab5 = Deliberation(
        "How many depots exceed the threshold, and is that acceptable?",
        [_rel("what is the area of the warehouse?", [("warehouse", "area", 40)], binds="area"),
         _pred("count_over", "def count_over(xs, t):",
               "Return how many numbers in xs are strictly greater than t.",
               "assert count_over([1, 5, 9], 4) == 2\nassert count_over([], 3) == 0\n"
               "assert count_over([10, 2, 8], 5) == 2",
               apply=[[1, 5, 9], 4], binds="cnt")],
        compose=lambda b: "acceptable")
    cases.append(Case("abstain_predicate_unsynthesizable", "abstain", ab5, hops=2))

    # 6) HOP-0 relational gap: an out-of-vocabulary relation the graph lane will not resolve.
    ab6 = Deliberation(
        "What is the secret handshake of the guild, and does it match?",
        [_rel("what is the secret handshake of the guild?",
              [("guild", "founded", "1450")], binds="hs"),
         _rel("what is the {hs} made of?", [("x", "made_of", "y")], binds="mat")],
        compose=lambda b: "match")
    cases.append(Case("abstain_relational_oov", "abstain", ab6, hops=1))

    return cases


# ── scoring ──────────────────────────────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    return " ".join(str(s or "").lower().split())


def run_benchmark(resteer: bool = True) -> dict[str, Any]:
    cases = build_suite()
    multi = [c for c in cases if c.kind == "multi_hop"]
    abstain = [c for c in cases if c.kind == "abstain"]

    solved_chain = 0
    solved_single = 0
    abstain_correct = 0
    fails: list[dict[str, Any]] = []
    detail: list[dict[str, Any]] = []
    one_cert: dict[str, Any] | None = None

    for c in multi:
        res = deliberate(c.deliberation, resteer=resteer, mec=True)
        base = single_shot(c.deliberation)
        ok_chain = (not res.abstained) and (_normalize(c.expect_contains) in _normalize(res.answer))
        ok_single = (not base.abstained) and (_normalize(c.expect_contains) in _normalize(base.answer or ""))
        if ok_chain:
            solved_chain += 1
        # FAIL = the chain produced a NON-abstained answer that is WRONG (fabricated / wrong chain)
        if (not res.abstained) and not ok_chain:
            fails.append({"case": c.name, "why": "wrong composed answer", "answer": res.answer})
        if ok_single:
            solved_single += 1
        if ok_chain and one_cert is None and c.hops >= 3:
            one_cert = res.certificate
        detail.append({"case": c.name, "kind": "multi_hop", "hops": c.hops,
                       "chain_solved": ok_chain, "single_shot_solved": ok_single,
                       "abstained": res.abstained, "answer": res.answer,
                       "reordered": res.mec.get("reordered")})

    for c in abstain:
        res = deliberate(c.deliberation, resteer=resteer, mec=True)
        if res.abstained:
            abstain_correct += 1
        else:                              # produced an answer where it should have abstained = fabrication
            fails.append({"case": c.name, "why": "fabricated instead of abstaining",
                          "answer": res.answer})
        detail.append({"case": c.name, "kind": "abstain", "hops": c.hops,
                       "abstained": res.abstained, "reason": res.reason,
                       "ungrounded_step": (res.certificate.get("ungrounded_step") or {}).get("organ")})

    return {
        "multi_hop_total": len(multi),
        "multi_hop_solved_via_chain": solved_chain,
        "single_shot_solved": solved_single,
        "abstain_total": len(abstain),
        "abstain_correct": abstain_correct,
        "FAIL_fabricated_or_wrong": len(fails),
        "fails": fails,
        "one_verified_3hop_certificate": one_cert,
        "detail": detail,
    }


def main() -> None:
    rep = run_benchmark()
    slim = {k: v for k, v in rep.items() if k not in ("one_verified_3hop_certificate", "detail", "fails")}
    print(json.dumps(slim, ensure_ascii=False, indent=2))
    print("\nFAILS:", json.dumps(rep["fails"], ensure_ascii=False))
    print("\nONE VERIFIED 3-HOP CERTIFICATE:")
    print(json.dumps(rep["one_verified_3hop_certificate"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
