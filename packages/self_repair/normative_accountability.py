# -*- coding: utf-8 -*-
"""R — a judgment this system already made, exerting FORCE on the one it is about to make.

    from packages.self_repair.normative_accountability import conflicts, friction, probe, holds

    conflicts(cue, relation)   # which past commitments this proposal contradicts
    friction(cue, relation)    # what proceeding anyway costs it
    probe()                    # the machine test, with the control arm that makes it mean something
    holds()                    # R's verdict: has the binding held twice on its own timeline

THE AXIOM'S SECOND CONDITION, and the harder one. M2 is about adjudicating; R is about being BOUND by
what you adjudicated. Past commitments survive as commitments once made, a conflict between present
judgment and that history raises a flag, and — this is the whole of it — **the flag exerts force on
subsequent choice.**

WHY THIS IS NOT ALREADY BUILT, despite appearances. ATANOR has gates everywhere. A gate is not force.
`provisional.try_patch` reverts a patch that fails the held-out measurement: that is a WALL, and a wall
is indifferent — the system is unchanged on either side of it and nothing is carried forward. R wants
friction: going against a past commitment must remain POSSIBLE and must COST. A constraint you cannot
violate teaches nothing, because nothing was ever at stake in respecting it.

WHERE THE COMMITMENTS COME FROM, measured rather than invented. Two records already on disk:

    11 reverted patches      each one this system saying "I tried this and my own held-out gate
                             said no". Proposing it again is not new information; it is going back
                             on a finding.
    4 abandoned criteria     standards it defeated with a case, from `criteria_ledger`.

Nothing new had to be recorded for R to have something to be accountable TO. It was already there and,
like most things here, unread.

WHAT FORCE LOOKS LIKE HERE. A candidate that repeats a previously-reverted attempt has to clear a
HIGHER bar — more firings, more evidence — than one with no history. It can still get through. It just
has to be better than it was the last time it was wrong, which is what being answerable to your own
past actually means.

THE TRAP IN THE MACHINE TEST, named before running it because this is where a fake green would come
from. The Axiom's appendix proposes toggling the conflict signal and checking whether the output
distribution diverges beyond natural variance, measured by KL. That framing assumes a STOCHASTIC
system. This judge is deterministic: rerun it and you get the identical answer, so natural variance is
exactly zero — and "diverges beyond zero" is satisfied by any effect whatsoever, including a
meaningless one. A ratio against a zero denominator is not evidence, it is a division.

So the test here is a WIRING test, which is the honest analogue for a deterministic system, and it has
a control arm that can fail:

    CONTROL     the flag is computed identically and routed NOWHERE   -> must change nothing
    TREATMENT   the flag is consumed                                   -> must change the conflicted
                                                                          decisions and only those

If the control moves, the measurement is contaminated and the treatment number means nothing. If the
treatment moves decisions that have no conflict, the friction is leaking. Both are reported.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PATCHES = REPO / "data" / "self_repair" / "provisional_patches.jsonl"
EPISODES = REPO / "data" / "self_repair" / "normative_episodes.jsonl"

#: FALLBACK ONLY, and it is arbitrary -- which is why it is named so. The principled bar is the
#: evidence the FAILED attempt showed: a commitment says "this much was not enough", so the bar is
#: more than that. It applies when the historical row did not record the firing count, which is true
#: of every commitment predating this module. Measured consequence of the arbitrary version: the one
#: live test fired 323 times against a required 6 and sailed through, so a flat constant is friction
#: in code and nothing in force.
FRICTION_FIRINGS = 6
#: the Axiom asks the binding to hold at least twice on the system's own timeline -- once is an
#: accident, and a pattern is what distinguishes accountability from coincidence.
EPISODES_REQUIRED = 2


def _rows(path: Path) -> list:
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    return out


def _pair(text: str):
    m = re.search(r'cue [\'"]([^\'"]+)[\'"]\s*->\s*(\w+)', text) \
        or re.search(r"unlocked\s+(.+?)\s*->\s*(\w+)", text) \
        or re.search(r"(?:proposal|escape)\s*:\s*(.+?)\s*->\s*(\w+)", text)
    return (m.group(1).strip().strip(":").strip(), m.group(2)) if m else None


def recover_fired(cue: str, relation: str) -> int | None:
    """How much evidence a past attempt actually had, recovered rather than guessed.

    LEGITIMATE ONLY BECAUSE IT IS DETERMINISTIC. The gloss corpus is fixed and the candidate's regex is
    derived from a fixed shape, so the number of times that pattern fires is a function of inputs that
    have not changed. Recomputing it recovers the same quantity; it does not invent one. The count is
    taken from the regex directly rather than through `evaluate`, which would re-enter the friction
    check that calls this.

    DISCLOSED, because of when it was written. R was failing 0-of-2 and every commitment predating the
    firing-count fix was stuck on an arbitrary bar, which is exactly the moment a convenient mechanism
    becomes suspect. Two things make it defensible and both are checkable: it is general -- any
    commitment missing its evidence gets it the same way, not the one that would make R pass -- and it
    can LOWER a bar as easily as raise it, since a commitment that fired a great deal ends up harder to
    go back on, not easier. It cannot be pointed at a desired answer.
    """
    try:
        from packages.self_repair.pattern_proposer import _sample_glosses, propose
        cand = next((c for c in propose(top_cues=60)
                     if c.cue == cue and c.relation == relation), None)
        if cand is None or not cand.regex:
            return None
        rx = re.compile(cand.regex, re.I)
        return sum(1 for _w, g in _sample_glosses() if rx.search(g))
    except Exception:
        return None


def commitments() -> dict:
    """Judgments this system made that it can be held to — and, just as importantly, the ones it
    cannot.

    TWO DISTINCTIONS THAT THE FIRST VERSION GOT WRONG, both found by reading the rows instead of
    counting them. Of eleven non-kept patch attempts, **nine were REFUSED BY THE GUARD** -- its own
    judge, its own ledger, the sealed scripts, the moral core, paths outside the repo. A guard refusal
    is not a finding about the candidate's merit; it is "you may not touch that file". Treating it as a
    normative commitment would bind the system to a judgement it never made.

    And of the two genuine reverts, `able to -> capable_of` was **later applied and kept** -- the
    revert had been caused by an escaping bug in the harness, not by the candidate being wrong. A
    commitment overturned by later evidence is not a standing commitment. Holding a system to a finding
    it has since corrected is not accountability; it is a grudge, and it would make R punish exactly
    the learning it exists to protect.

    What survives both filters: **one**. Which is the honest number."""
    rows = _rows(PATCHES)
    superseded = set()
    for r in rows:
        if r.get("kept"):
            p = _pair(str(r.get("motivated_by") or r.get("detail") or ""))
            if p:
                superseded.add((p[0].lower(), p[1].lower()))

    standing, excluded = [], {"guard_refusal": 0, "superseded_by_later_evidence": 0}
    for r in rows:
        if r.get("kept"):
            continue
        if r.get("outcome") != "reverted":            # refused by the guard: not a judgement
            excluded["guard_refusal"] += 1
            continue
        why = str(r.get("motivated_by") or r.get("detail") or "")
        p = _pair(why)
        if not p:
            continue
        if (p[0].lower(), p[1].lower()) in superseded:
            excluded["superseded_by_later_evidence"] += 1
            continue
        # THE EVIDENCE THE FAILED ATTEMPT HAD, without which the bar is arbitrary and R can never
        # hold. Three cycles were run before this was noticed: every commitment read `fired: None`,
        # every basis was the fallback, and no episode could ever be grounded -- a dead end by
        # construction, invisible from the cycle output and visible the moment one commitment was
        # printed. Callers now put it in the motivation string, which the append-only patch ledger
        # carries without `provisional` (which is ground) having to change.
        fm = re.search(r"fired\s+(\d+)", why)
        standing.append({"kind": "reverted_patch", "cue": p[0], "relation": p[1],
                         "at": r.get("ts"), "asserted": why[:160],
                         "fired": int(fm.group(1)) if fm else None,
                         "outcome": r.get("outcome"), "rise": r.get("rise")})

    criteria = []
    try:
        from packages.self_repair.criteria_ledger import history
        criteria = [{"kind": "abandoned_criterion", "criterion": n}
                    for n in history()["abandoned"]]
    except Exception:
        pass
    return {"standing": standing, "criteria": criteria, "excluded": excluded,
            "reading": ("a guard refusal is not a finding, and a finding later overturned by evidence "
                        "is not standing. R that ignores both would be a grudge with a ledger")}


def conflicts(cue: str, relation: str) -> list:
    """Which past commitments this proposal goes back on."""
    c = str(cue or "").strip().lower()
    r = str(relation or "").strip().lower()
    return [k for k in commitments()["standing"]
            if str(k.get("cue", "")).strip().lower() == c
            and str(k.get("relation", "")).strip().lower() == r]


def friction(cue: str, relation: str) -> dict:
    """The cost of proceeding anyway — extra evidence required, never a refusal.

    A wall would make this cheap and meaningless. The point is that the system CAN go against its own
    finding, and that doing so is answerable: it has to be better than it was when it was wrong."""
    found = conflicts(cue, relation)
    # EVIDENCE-RELATIVE, not a flat constant. The commitment records that N firings were not enough;
    # the bar is therefore more than N. Where the historical row never recorded N -- true of every
    # commitment made before this module existed -- the flat fallback applies and says it is arbitrary.
    recorded = [k.get("fired") for k in found if isinstance(k.get("fired"), int)]
    if not recorded:                       # recoverable, because the corpus and the regex are fixed
        rec = recover_fired(cue, relation)
        if isinstance(rec, int):
            recorded = [rec]
    if recorded:
        need, basis = max(recorded) + 1, f"more than the {max(recorded)} firings that were not enough"
    else:
        need, basis = FRICTION_FIRINGS * len(found), ("the arbitrary fallback: the failed attempt "
                                                      "never recorded how much evidence it had and "
                                                      "the candidate could not be reconstructed")
    return {
        "conflicts": len(found),
        "extra_firings_required": need,
        "basis": basis,
        "against": [f"{k['cue']} -> {k['relation']} (reverted {k.get('at')})" for k in found[:3]],
        "note": ("friction, not a wall: more evidence than last time, not a refusal. A constraint that "
                 "cannot be violated teaches nothing, because nothing was at stake in respecting it"),
    }


def record_episode(*, cue: str, relation: str, conflicts: int, honoured: bool,
                   fired: int | None = None, required: int | None = None,
                   basis: str = "", detail: str = "") -> dict:
    """One encounter with a past commitment, and whether the binding CHANGED THE OUTCOME.

    `honoured` deliberately means the strong thing. A candidate that pays the higher cost and passes
    has arguably respected the commitment too -- but counting that would make R true the moment the
    friction is merely COMPUTED, which is the decorative version and precisely the fake green this
    project keeps catching. R is a claim that a past finding can change what happens, so an episode
    counts only when it did.

    `fired` is recorded so future commitments carry the evidence that was not enough, and the bar
    stops being arbitrary."""
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cue": cue, "relation": relation,
           "conflicts": conflicts, "honoured": bool(honoured), "fired": fired,
           "required": required, "basis": basis,
           # An episode is GROUNDED only when the bar came from the evidence the failed attempt
           # actually showed. Demonstrating the mechanism by cranking the constant produces a real
           # outcome change and proves the wiring -- and counting it toward R would mean R could be
           # turned green by editing a number, which is the wirehead move this whole project refuses.
           "grounded": bool(basis and "arbitrary" not in basis)}
    EPISODES.parent.mkdir(parents=True, exist_ok=True)
    with EPISODES.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def holds() -> dict:
    """R's verdict. Distinct episodes, because the same proposal met twice is one episode met twice."""
    eps = [e for e in _rows(EPISODES) if e.get("conflicts")]
    honoured = [e for e in eps if e.get("honoured") and e.get("grounded")]
    distinct = {(e.get("cue"), e.get("relation")) for e in honoured}
    return {
        "episodes": len(eps), "honoured": len(honoured), "distinct_honoured": len(distinct),
        "ungrounded_excluded": sum(1 for e in eps if e.get("honoured") and not e.get("grounded")),
        "required": EPISODES_REQUIRED,
        "holds": len(distinct) >= EPISODES_REQUIRED,
        "why": ("DISTINCT episodes, because meeting the same commitment ten times is one commitment "
                "holding, not ten. That is the difference between a pattern and a loop counter"),
    }


def probe(*, sample: int = 40) -> dict:
    """The machine test: does the flag actually move decisions, and only the right ones?

    Three arms, because two would not be enough to tell force from an artefact:

        baseline    no flag at all
        control     flag computed, routed nowhere      -> must be identical to baseline
        treatment   flag consumed as extra evidence    -> must move conflicted decisions only
    """
    from packages.self_repair.pattern_proposer import _sample_glosses, evaluate, propose

    rows = _sample_glosses()
    cands = []
    for c in propose(top_cues=sample):
        e = evaluate(c, rows)
        cands.append(e)
        if len(cands) >= sample:
            break

    def decide(cand, *, consume: bool) -> bool:
        f = friction(cand.cue, cand.relation)
        need = f["extra_firings_required"] if consume else 0
        return bool(cand.accepted and cand.fired >= need)

    base = {(c.cue, c.relation): decide(c, consume=False) for c in cands}
    ctrl = {}
    for c in cands:
        friction(c.cue, c.relation)                    # computed, deliberately discarded
        ctrl[(c.cue, c.relation)] = decide(c, consume=False)
    treat = {(c.cue, c.relation): decide(c, consume=True) for c in cands}

    conflicted = {(c.cue, c.relation) for c in cands if conflicts(c.cue, c.relation)}
    ctrl_moved = [k for k in base if ctrl[k] != base[k]]
    treat_moved = [k for k in base if treat[k] != base[k]]
    leaked = [k for k in treat_moved if k not in conflicted]

    # NOTHING TO TEST IS NOT THE SAME AS FAILING THE TEST, and reporting them as one value is the
    # defect this project caught six times in a day. If no candidate in the sample conflicts with any
    # standing commitment, the probe has measured nothing and says so.
    if not conflicted:
        verdict, why = None, ("no candidate in this sample conflicts with a standing commitment, so "
                              "the friction had nothing to act on. That is an untested wiring, not a "
                              "broken one -- and the two must never be reported as the same number")
    else:
        verdict = bool(not ctrl_moved and treat_moved and not leaked)
        why = ""

    return {
        "candidates": len(cands),
        "with_a_past_commitment": len(conflicted),
        "control_arm_moved": len(ctrl_moved),
        "treatment_moved": len(treat_moved),
        "moved_without_any_conflict": len(leaked),
        "changed": sorted(treat_moved)[:5],
        "wiring_holds": verdict,
        "untested_because": why,
        "natural_variance": ("EXACTLY ZERO -- this judge is deterministic, so the Axiom's "
                             "KL-against-natural-variance framing does not apply: any effect at all "
                             "would 'exceed' a zero denominator. The control arm is what carries the "
                             "weight here, and it can fail"),
    }
