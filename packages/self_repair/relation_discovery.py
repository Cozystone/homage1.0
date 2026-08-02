# -*- coding: utf-8 -*-
"""Station 3b: notice that a relation is MISSING, rather than only that a cue is.

    from packages.self_repair.relation_discovery import discover
    d = discover("consisting of", pairs)     # pairs: [(subject, object), ...]
    d["missing_relation"]                    # e.g. "PartOf" -- a relation ATANOR does not extract

WHY THIS IS THE BINDING CONSTRAINT, measured rather than assumed. The loop ran end to end today and
proposed 24 candidates, of which the judge refused 24 and queued zero. That was correct behaviour, not
a failure: of 1,172 cue-bearing misses, 848 are genuinely uncovered cues, and the largest of those are
`consisting of` (266 fires) and `composed of`. The judge refuses them because their instances split
across every relation ATANOR has —

    consisting of -> capable_of 107, made_of 75, used_for 53

— which is exactly the signature of a cue that means something the vocabulary cannot say. The loop was
not short of candidates. Its proposal space was one shape wide: add a cue for an EXISTING relation.

WE DO NOT INVENT THE RELATION, AND THAT IS THE WHOLE TRICK. Naming a new predicate by hand is how a
hand rule gets in wearing a lab coat. Instead the pairs a cue produces are tested against an EXTERNAL
relation vocabulary that already exists on disk — ConceptNet's 13 relations, of which ATANOR extracts
three:

    has:  UsedFor, CapableOf, MadeOf
    not:  IsA, AtLocation, Causes, HasSubevent, HasProperty, HasA, PartOf, Desires,
          ReceivesAction, CreatedBy

If a cue's pairs are corroborated by a relation on the second list, the relation is not invented — it
is FOUND, named by a vocabulary nobody here wrote, and confirmed by an oracle that predates the
question.

THE GATE, and why it is comparative. A cue whose pairs match `PartOf` a little would prove nothing;
almost anything matches something a little. The discovered relation must beat every relation ATANOR
ALREADY has, on the same pairs, by a margin. Otherwise the honest reading is that the cue is a noisy
variant of a relation we can already express, and adding a predicate would buy vocabulary rather than
knowledge.

WHAT THIS STILL CANNOT DO. It can only find relations that exist in the external vocabulary. A
relation the world needs and ConceptNet lacks is invisible to it, and calling that "relation
invention" would be an overclaim: this is relation DISCOVERY against a fixed inventory. Genuine
invention — proposing a predicate no external source names — has no oracle, and by the rule this
project runs on, that means it is not ready to be built.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONCEPTNET = REPO / "data" / "perception" / "concept_properties.json"

#: what ATANOR extracts today, mapped to the external vocabulary. Read from the extractor's own table
#: so a relation added upstream stops counting as "missing" without this file being edited.
_ALIAS = {"used_for": "UsedFor", "capable_of": "CapableOf", "made_of": "MadeOf"}

_CN_CACHE: dict = {}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z ]", "", str(s).lower().replace("_", " ")).strip()


def conceptnet() -> dict:
    """The arbiter's evidence, from EVERY usable source rather than one bundled file.

    This read a single 4,731-subject file, and the loop correctly diagnosed oracle coverage as its
    next constraint -- the arbiter knew 9-16% of the subjects it was asked about. The evidence turned
    out to be on disk already: seven per-relation ConceptNet files totalling 140,913 subjects, 29.8x
    what was being read. Acquisition was never the constraint; enumeration was."""
    if "cn" not in _CN_CACHE:
        try:
            from packages.self_repair.oracle_sources import load_oracle
            _CN_CACHE["cn"] = load_oracle()
        except Exception:
            try:
                _CN_CACHE["cn"] = json.loads(CONCEPTNET.read_text(encoding="utf-8"))
            except Exception:
                _CN_CACHE["cn"] = {}
    return _CN_CACHE["cn"]


def external_relations() -> list[str]:
    """Every relation the oracle knows, counted from it rather than listed here."""
    counts: Counter = Counter()
    for ents in conceptnet().values():
        for e in ents:
            if ":" in e:
                counts[e.split(":", 1)[0]] += 1
    return [r for r, _n in counts.most_common()]


def have_today() -> set:
    """The external names of the relations ATANOR currently extracts, read off the extractor."""
    from packages.graph_scale.property_extraction import PATTERNS
    return {_ALIAS[p] for p, _rx in PATTERNS if p in _ALIAS} | {"CapableOf"}


def agreement(pairs, relation: str) -> tuple:
    """How often the oracle confirms these (subject, object) pairs under `relation`.

    Returns (checkable, agreed). Only subjects the oracle knows are checkable — an unknown subject is
    silence, not disagreement, and counting it either way would fabricate a signal."""
    cn = conceptnet()
    checkable = agreed = 0
    for subj, obj in pairs:
        ents = cn.get(_norm(subj))
        if not ents:
            continue
        gold = {_norm(e.split(":", 1)[1]) for e in ents if e.startswith(relation + ":")}
        if not gold:
            continue
        checkable += 1
        o = _norm(obj)
        if any(o == g or o in g or g in o for g in gold):
            agreed += 1
    return checkable, agreed


def null_rate(pairs, relation: str, *, shuffles: int = 3) -> float:
    """What this relation would score on the SAME subjects with the objects shuffled.

    The control that stops a common relation from winning by being common. ConceptNet holds 22,441
    IsA edges against 347 MadeOf, so a subject usually has several IsA objects and almost never a
    MadeOf one — and raw agreement rewards that. The first run of this module duly reported
    `consisting of -> IsA` at 15%, which is not a discovery, it is a base rate.

    Shuffling breaks the pairing while keeping both marginal distributions, so whatever survives is
    the association rather than the abundance."""
    objs = [o for _s, o in pairs]
    if len(objs) < 4:
        return 0.0
    total = 0.0
    for k in range(1, shuffles + 1):
        rotated = objs[k:] + objs[:k]                # deterministic derangement; no RNG needed
        checkable, agreed = agreement(list(zip((s for s, _o in pairs), rotated)), relation)
        total += (agreed / checkable) if checkable else 0.0
    return total / shuffles


def discover(cue: str, pairs, *, min_checkable: int = 12, margin: float = 1.5) -> dict:
    """Which relation do this cue's pairs actually belong to, and is it one we lack?

    `margin` is a RATIO, not a difference: the best external relation must agree at least 1.5x better
    than the best relation ATANOR already extracts. A cue that merely nudges ahead of what we can
    already say is a noisy variant, and adding a predicate for it would buy vocabulary, not knowledge."""
    pairs = [(s, o) for s, o in pairs if str(s).strip() and str(o).strip()]
    scores: dict = {}
    for rel in external_relations():
        checkable, agreed = agreement(pairs, rel)
        if checkable >= min_checkable:
            raw = agreed / checkable
            null = null_rate(pairs, rel)
            scores[rel] = {"checkable": checkable, "agreed": agreed, "raw": round(raw, 4),
                           "null": round(null, 4),
                           # what survives the base rate. A relation that scores no better than
                           # shuffled pairs has told us nothing about THESE pairs.
                           "agreement": round(max(0.0, raw - null), 4)}
    if not scores:
        return {"cue": cue, "verdict": "inconclusive", "missing_relation": None, "scores": {},
                "best_external": {}, "best_of_ours": {},
                "why": (f"no relation had {min_checkable} checkable pairs; the oracle does not know "
                        f"these subjects well enough to say anything")}

    ours = have_today()
    ranked = sorted(scores.items(), key=lambda kv: -kv[1]["agreement"])
    best_rel, best = ranked[0]
    mine = [(r, s) for r, s in ranked if r in ours]
    best_mine = mine[0][1]["agreement"] if mine else 0.0

    missing = best_rel not in ours
    beats = best["agreement"] >= max(best_mine * margin, 0.05)
    verdict = "missing_relation" if (missing and beats) else (
        "already_expressible" if not missing else "not_decisive")
    return {
        "cue": cue,
        "verdict": verdict,
        "missing_relation": best_rel if verdict == "missing_relation" else None,
        "best_external": {best_rel: best},
        "best_of_ours": {mine[0][0]: mine[0][1]} if mine else {},
        "scores": {r: s for r, s in ranked[:6]},
        "why": (f"{best_rel} agrees {best['agreement']:.0%} over {best['checkable']} checkable pairs "
                f"against {best_mine:.0%} for the best relation we already extract"
                + ("" if beats else f" — under the {margin}x margin, so this reads as a noisy variant "
                                    f"of something we can already say")),
    }
