# -*- coding: utf-8 -*-
"""Gate (c): THE honest ARC probe (read-only).

The ARC-1 recolour lookup (``packages.arc_agi.objects.strat_recolor``) learns an object-attribute→
colour TABLE and ABSTAINS on the test when a test object carries an attribute value unseen in
training (``k not in _m`` → ``[[]]``). NVSA cracked Raven's matrices by inferring the transformation
by unbinding — so: does our algebraic rule-inference lane solve ANY of those abstain-on-test recolour
tasks that the lookup could not?

This test REPRODUCES the abstain family from the sealed eval split (read-only), runs the algebraic
colour-map lane on each, and reports the exact-match count under a strict 0-fabrication rule. The
honest, measured answer is 0 — with a mechanical diagnosis asserted below: none of these tasks is a
cyclic colour rotation, because their recolour is keyed on object attributes, not on cell colour, and
the attribute→colour map is an arbitrary table, not an arithmetic progression. VSA algebra cracks
GROUP ACTIONS, not tables — this gate makes that boundary a measured, non-fabricating fact.
"""
import glob
import json
import os

import pytest

from packages.vsa_reasoning.rule_inference import infer_colormap_rule

_EVAL = os.path.join(
    "data", "arc_agi", "ARC-AGI-master", "data", "evaluation"
)


def _dims(g):
    return (len(g), len(g[0]) if g else 0)


def _is_empty(pred) -> bool:
    return (not pred) or (isinstance(pred, list) and (len(pred) == 0 or (len(pred) == 1 and pred[0] == [])))


def _load_abstain_family():
    """Recolour tasks that VERIFY on train but ABSTAIN on test (return [[]]). Derived live from the
    sealed split via the real strat_recolor — no hard-coded task ids."""
    from packages.arc_agi.objects import strat_recolor  # read-only import

    files = sorted(glob.glob(os.path.join(_EVAL, "*.json")))
    family = []
    for f in files:
        task = json.load(open(f))
        train = [(p["input"], p["output"]) for p in task.get("train", [])]
        if not train:
            continue
        prog = strat_recolor(train)
        if prog is None:
            continue
        test = task.get("test", [{}])[0]
        try:
            pred = prog(test["input"])
        except Exception:
            pred = [[]]
        if _is_empty(pred):
            family.append((os.path.basename(f)[:-5], train, test))
    return family


@pytest.mark.skipif(not os.path.isdir(_EVAL), reason="ARC eval split not present")
def test_arc_recolor_abstain_probe_no_fabrication_and_report_count():
    family = _load_abstain_family()
    # sanity: we are actually probing the real verify-on-train / abstain-on-test recolour family
    assert len(family) >= 5, f"expected the recolour abstain family, got {len(family)}"

    new_solves = []
    fabrications = []
    for tid, train, test in family:
        rule = infer_colormap_rule(train)
        if rule is None:
            continue                          # algebraic lane abstains too — honest, no guess
        pred = rule.apply_grid(test["input"])
        if "output" in test and pred == test["output"]:
            new_solves.append(tid)            # a genuine NEW solve the lookup could not make
        else:
            fabrications.append(tid)          # a non-abstaining WRONG answer would break honesty

    # 0-fabrication is non-negotiable: the lane must never emit a wrong grid on these tasks
    assert not fabrications, f"algebraic lane fabricated wrong outputs on {fabrications}"
    # honest measured finding: VSA algebra adds 0 solves on the ARC recolour abstain family
    assert len(new_solves) == 0, (
        f"unexpected new solves {new_solves} — update the sealed finding if this is a real gain"
    )


@pytest.mark.skipif(not os.path.isdir(_EVAL), reason="ARC eval split not present")
def test_arc_recolor_is_not_cell_colour_functional_diagnosis():
    """The mechanical WHY behind the 0: in every abstain task the same input colour maps to
    different outputs depending on the OBJECT, so the rule is not a cell colour→colour function at
    all — there is no colour ring for VSA to rotate."""
    family = _load_abstain_family()
    non_functional = 0
    for _tid, train, _test in family:
        cellmap = {}
        functional = True
        for gi, go in train:
            if _dims(gi) != _dims(go):
                functional = False
                break
            for ri, ro in zip(gi, go):
                for a, b in zip(ri, ro):
                    if a in cellmap and cellmap[a] != b:
                        functional = False
                    cellmap[a] = b
        if not functional:
            non_functional += 1
    # the entire abstain family is attribute-keyed (object-dependent), not cell-colour functional
    assert non_functional == len(family)
