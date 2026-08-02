# -*- coding: utf-8 -*-
"""When the loop stops finding things, say WHICH dimension is saturated — not "try harder".

    from packages.self_repair.plateau_escape import diagnose
    d = diagnose()
    d["saturated"]      # e.g. "relation_vocabulary"
    d["next_kind"]      # what a NEW KIND of proposal would have to do

WHAT THIS AUTOMATES, and it is a specific thing I did by hand three times today. Each time the loop
plateaued, the escape came from the same move: read WHY the proposals were refused, and notice which
dimension the refusals all pointed at.

    refusals all "ambiguous / instances disagree"   -> the RELATION VOCABULARY is too small
                                                       (built relation discovery; found HasA)
    refusals all "margin under X"                   -> the DISCRIMINATOR is too weak
                                                       (measured first token vs last: 0.645 -> 0.810)
    nothing even proposed, every cue already covered -> the PROPOSAL SHAPE is exhausted
                                                       (needed a kind of proposal that was not
                                                        "add a cue for an existing relation")

The reason is not guesswork and it is not mine to invent: `judge()` refuses on exactly four
conditions — familiarity, wins, decisive, consistent — and stamps which one fired into its own
verdict string. A plateau where one condition dominates IS that condition being the binding
constraint. Reading the judge's own structure is all this does.

WHAT IT DOES NOT DO, stated because the gap is the whole remaining distance to RSI: it names the
direction, it does not build the organ. When it says the relation vocabulary is saturated, a person
still writes the discovery station. Diagnosing the escape and performing it are different acts, and
only the first has a free oracle — the refusal distribution is already measured, while "write the new
kind of proposer" is code synthesis against a spec nobody has written yet.

So: the loop can now say *what kind of thing it is missing*. It still cannot make one.
"""
from __future__ import annotations

import re
from collections import Counter

#: The judge's four refusal conditions, and what a plateau dominated by each one means. The keys are
#: matched against the verdict strings `judge()` already emits, so this stays in step with the gate
#: rather than describing an idea of it.
_CONDITIONS = (
    ("instances disagree", "relation_vocabulary",
     "the cue means something the relation set cannot say; a NEW RELATION has to be discoverable"),
    ("agree on", "relation_vocabulary",
     "the instances cohere but not on the relation proposed; the vocabulary is the constraint"),
    ("margin under", "discriminator",
     "relations are not separable by the current signal; a DIFFERENT SIGNAL has to be measured"),
    ("below", "profile_coverage",
     "the relation's own profile does not cover these objects; the profile source is the constraint"),
    ("fit", "proposal_targeting",
     "the cue was offered to the wrong relation and redirected; the cross-product is working"),
)
#: refusals that mean the machinery is working, not that it is stuck
_HEALTHY = {"proposal_targeting"}


def classify(verdict: str) -> str:
    """Which of the judge's conditions refused this proposal."""
    tail = verdict.split("REFUSED:", 1)[-1] if "REFUSED:" in verdict else verdict
    for needle, name, _why in _CONDITIONS:
        if needle in tail:
            return name
    return "unclassified"


def diagnose(survey_result: dict | None = None, *, plateau_runs: int = 3) -> dict:
    """Which dimension is saturated, read off the refusal distribution.

    Returns `saturated: None` when the loop is still finding things — a diagnosis offered while
    progress continues would be advice nobody asked for, and would train its reader to ignore it."""
    from packages.self_repair.autorun import status
    from packages.self_repair.pattern_proposer import already_covered, survey

    st = status()
    if not st.get("plateaued"):
        return {"plateaued": False, "saturated": None,
                "why": f"still finding things ({st.get('consecutive_runs_with_nothing_new', 0)} "
                       f"empty runs, plateau at {plateau_runs})"}

    result = survey_result if survey_result is not None else survey(top_cues=12)
    refusals = result.get("refused_detail") or []
    counts: Counter = Counter(classify(r.get("verdict", "")) for r in refusals)
    blocking = Counter({k: v for k, v in counts.items() if k not in _HEALTHY})

    # the other saturation: nothing was even PROPOSED, because every cue the harness surfaced is
    # already covered. That is the proposal SHAPE running out, and no refusal reason can report it
    # because no proposal was made.
    proposed = result.get("proposed", 0)
    shape_exhausted = proposed == 0

    if shape_exhausted:
        saturated, why = "proposal_shape", (
            "every cue the harness surfaced is already covered, so nothing was proposed at all. "
            "The constraint is the SHAPE of proposal available, not any judgement about one")
    elif blocking:
        saturated = blocking.most_common(1)[0][0]
        # A CONDITION `classify` CAN NAME BUT `_CONDITIONS` DOES NOT LIST used to raise StopIteration
        # here, and inside a generator that surfaces as RuntimeError. The unattended cycle wrapped this
        # call in `except Exception`, so the diagnosis simply reported no escape and the crash was
        # invisible -- the fourth time today a defensive catch turned a defect into a quiet zero. An
        # unnamed condition is a real state and is now reported as one.
        why = next((w for _n, name, w in _CONDITIONS if name == saturated),
                   f"'{saturated}' is the most common blocker and has no entry in _CONDITIONS, so "
                   f"there is no prescription for it yet -- the gap is in the condition table, not "
                   f"in the diagnosis")
    else:
        saturated, why = None, ("every refusal was the cross-product being filtered correctly; "
                                "nothing is blocking except that there is nothing new to propose")

    # DOES THE NAMED CAPABILITY ALREADY EXIST? The first run of this diagnosis said the relation
    # vocabulary was saturated and prescribed "build relation discovery" -- which had been built an
    # hour earlier and had already found HasA. The real blocker was not a missing organ but an organ
    # whose output nobody acted on. A diagnosis that cannot tell those apart sends you to rebuild
    # what you have.
    unacted = _unacted_findings(saturated)

    return {
        "plateaued": True,
        "empty_runs": st.get("consecutive_runs_with_nothing_new"),
        "refusals_by_condition": dict(counts),
        "blocking": dict(blocking),
        "saturated": saturated,
        "why": why,
        "capability_exists": bool(unacted is not None),
        "unacted_findings": unacted or [],
        "next_kind": (f"the capability already exists and has produced {len(unacted)} finding(s) "
                      f"nobody acted on — ACT ON THOSE, do not rebuild the organ"
                      if unacted else _NEXT_KIND.get(saturated)),
        "limit": ("this names the direction; it does not build the organ. Diagnosing an escape and "
                  "performing one are different acts, and only the first has a free oracle"),
    }


def oracle_coverage(cues=("intended to", "consisting of", "used to")) -> dict:
    """How much of what the loop extracts the external arbiter can even see.

    Measured after a cycle where the internal judge said capable_of, a reading of the objects said
    used_for, and the external oracle abstained for want of checkable pairs. When three judgements
    disagree and the arbiter has no data, the constraint is not the proposal or the gate -- it is the
    evidence available to settle them."""
    import re

    from packages.self_repair.pattern_proposer import _sample_glosses, pattern_shape
    from packages.self_repair.relation_discovery import conceptnet

    cn = conceptnet()
    shape = pattern_shape()
    if not shape or not cn:
        return {}

    def norm(s):
        return re.sub(r"[^a-z ]", "", str(s).lower().replace("_", " ")).strip()

    rows = _sample_glosses()
    out = {}
    for cue in cues:
        lead = r"\b" + r"\s+".join(re.escape(w) for w in cue.split()) + r"\s+"
        rx = re.compile(lead + shape, re.I)
        subs = [w for w, g in rows if rx.search(g)]
        known = sum(1 for w in subs if cn.get(norm(w)))
        out[cue] = {"subjects": len(subs), "oracle_knows": known,
                    "coverage": round(known / max(1, len(subs)), 3)}
    out["oracle_size"] = len(cn)
    return out


def _unacted_findings(saturated: str | None):
    """Findings the named capability has ALREADY produced that nothing has acted on.

    Returns None when the capability does not exist yet (so the prescription stands), and a list --
    possibly empty -- when it does. The distinction matters: "build the organ" and "the organ found
    something and you ignored it" are different instructions, and conflating them sends a reader to
    rebuild what they have."""
    if saturated != "relation_vocabulary":
        return None
    try:
        from packages.graph_scale.property_extraction import PATTERNS
        from packages.self_repair.autorun import _history
    except Exception:
        return None
    have = {p for p, _rx in PATTERNS}
    out = []
    for run in _history():
        for f in run.get("new_findings") or []:
            # a relation finding names a relation we do not extract; a pattern finding does not
            rel = str(f.get("relation", ""))
            if f.get("kind") != "pattern" and rel and rel.lower() not in {h.lower() for h in have}                     and rel.replace("_", "").lower() not in {h.replace("_", "").lower() for h in have}:
                if not any(o["relation"] == rel and o["cue"] == f.get("cue") for o in out):
                    out.append({"cue": f.get("cue"), "relation": rel,
                                "pairs": f.get("pairs"), "checkable": f.get("checkable")})
    return out


#: what a NEW KIND of proposal would have to be able to do, per saturated dimension. Written as a
#: REQUIREMENT rather than a design, because the design is the part that still needs a person.
_NEXT_KIND = {
    "relation_vocabulary": ("propose a RELATION, not a cue for an existing one — validated against a "
                            "vocabulary the system did not write (this is what relation_discovery "
                            "became, and it found HasA)"),
    "discriminator": ("measure a DIFFERENT PROPERTY of the objects than the current head signal, and "
                      "prove it separates held-out labelled pairs better than the one in use"),
    "profile_coverage": ("build the relation profiles from a source other than our own output, so "
                         "they stop inheriting our own confusion"),
    "oracle_coverage": ("stop proposing and start ACQUIRING. The loop can generate candidates it "
                        "cannot verify: the external vocabulary knows 9-16% of the subjects its cues "
                        "produce (4,731 subjects total), so the arbiter that settles a disputed "
                        "relation has no data on most of them. More extraction cannot fix this; the "
                        "constraint has moved from what we can read to what we can CHECK"),
    "proposal_shape": ("propose something that is not 'add a cue' at all — a change to the "
                       "normaliser, a new pattern SHAPE, or a relation. 15% of misses are objects "
                       "the patterns capture and clean_object refuses, and no cue proposal can reach "
                       "them"),
}
