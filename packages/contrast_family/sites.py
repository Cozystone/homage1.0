# -*- coding: utf-8 -*-
"""The sites G0 swaps contrasts into, each scored by ITS OWN existing notion of a right answer.

Inventing a metric here would let the swap be tuned toward it. So each site is scored on the
outcome its own module already treats as correct, taken from the fixtures those modules were
verified against -- not from anything written for this probe.

  A1b  an "upstairs" edge is FOREIGN and a genuine place edge is not.
  A1c  `made_of`/`creator` belong to the painting, `author` to the literary work, `located_in` to
       nothing, and `manufacturer` to nothing at all -- the shipyard case.

Both scores are plain accuracy over those judgements, so a contrast that is worse at the site's own
job scores lower, and a contrast that cannot tell anything apart scores at chance.
"""
from __future__ import annotations

from typing import Sequence

from packages.contrast_family.contrasts import Contrast
from packages.knowledge_repair.type_affinity import TypeProfile

# Measured prevalences from the shipped graph (see type_affinity's docstring), not invented.
PAINTING = TypeProfile("painting", 491561,
                       {"is_a": 1.00, "located_in": 0.83, "creator": 0.785, "made_of": 0.735,
                        "genre": 0.39, "author": 0.019, "manufacturer": 0.005})
LITERARY = TypeProfile("literary work", 229786,
                       {"is_a": 1.00, "author": 0.829, "genre": 0.36, "country": 0.34,
                        "located_in": 0.06, "creator": 0.044, "manufacturer": 0.008})
HILL = TypeProfile("hill", 221043,
                   {"is_a": 1.00, "country": 1.00, "located_in": 0.86, "creator": 0.004,
                    "author": 0.002, "made_of": 0.003, "manufacturer": 0.002})
GRAPE = TypeProfile("hybrid grape", 223,
                    {"is_a": 1.00, "country": 0.48, "located_in": 0.40, "creator": 0.386,
                     "made_of": 0.161, "manufacturer": 0.179, "author": 0.143})
KINDS = {"painting": PAINTING, "literary work": LITERARY, "hill": HILL, "hybrid grape": GRAPE}

# (predicate, the kind it should be attributed to, or None for "no candidate really has it")
KIND_TRUTH = [("made_of", "painting"), ("creator", "painting"), ("author", "literary work"),
              ("located_in", None), ("manufacturer", None), ("is_a", None)]

# A1b fixtures, from the real Athens node.
UPSTAIRS = [{"located", "higher", "floor", "level", "building"},
            {"upper", "storey", "building"},
            {"stairs", "higher", "floor", "level"}]
PLACES = [{"village", "claiborne", "parish", "louisiana"},
          {"town", "somerset", "county", "maine"},
          {"city", "county", "seat", "mcminn", "tennessee"}]
# words that DO distinguish (belong to one cluster) vs words that bridge everything
BRIDGE_TRUTH = {"building": False, "county": False,          # spans its cluster, distinguishes little
                "storey": True, "louisiana": True, "maine": True, "stairs": True}


def _score_kind(contrast: Contrast, *, min_prevalence: float = 0.5, margin: float = 1.6) -> float:
    """A1c's own job: which kind does this predicate speak for, if any."""
    correct = 0
    for pred, want in KIND_TRUTH:
        if pred == "is_a":
            correct += (want is None)                 # the declaring predicate is never attributed
            continue
        scores = {}
        for name, prof in KINDS.items():
            others = [p.rate(pred) for k, p in KINDS.items() if k != name]
            scores[name] = contrast(prof.rate(pred), others)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        top, runner = ranked[0], (ranked[1] if len(ranked) > 1 else (None, 0.0))
        prevalence = KINDS[top[0]].rate(pred)
        if prevalence < min_prevalence:
            got = None                                # absolute gate: the shipyard case
        elif runner[1] > 0 and top[1] < runner[1] * margin:
            got = None                                # too close to call
        else:
            got = top[0]
        correct += (got == want)
    return correct / len(KIND_TRUTH)


def _score_bridge(contrast: Contrast, *, cut: float = 0.5) -> float:
    """A1b's own job: does this word distinguish a cluster, or span everything?"""
    docs = UPSTAIRS + PLACES
    correct = 0
    for word, distinguishes in BRIDGE_TRUTH.items():
        here = float(sum(1 for d in docs if word in d))
        background = [float(sum(1 for d in docs if w in d))
                      for w in {t for d in docs for t in d} if w != word]
        got = contrast(here, background) >= cut
        correct += (got == distinguishes)
    return correct / len(BRIDGE_TRUTH)


SITES = {
    "A1c kind attribution": (_score_kind, "ratio_to_mean"),
    # A1b is offered so its refusal is on the record, not omitted. Its incumbent is not a
    # family member either (see contrasts.NON_MEMBERS), so it could not have had a swap row.
    "A1b bridging vocabulary": (_score_bridge, "(not a family member)"),
}
