# -*- coding: utf-8 -*-
"""Blind assessors — one per indicator, each calling ATANOR's REAL organs through their PUBLIC
interfaces with HELD-OUT stimuli the self-battery never used, plus a FALSIFICATION control.

Author/judge separation (structural): this module imports ONLY real organ packages
(packages.perception.*, packages.perception_recurrence.*, packages.situation_model.*,
packages.continuous_self.*, packages.embodiment.*). It NEVER imports packages.consciousness_audit
(not its probes, not its indicators, not its battery) — every verdict is re-derived from scratch.

Each assessor returns a BlindResult with three measured signals:
  * positive_pass    — the STRICT held-out positive fired on the real organ;
  * positive_partial — a weaker/core-only version held (used when the strict bar is not met);
  * control_rejected — the FALSIFICATION attempt (a degenerate input or an injected frozen organ)
                       was correctly REJECTED — i.e. it did NOT reproduce the present-shaped reading.

Organ handles are dependency-injected (keyword args default to None -> import the real organ). The
judge injects `stubs.frozen_overrides(id)` for the adversarial pass; a genuine organ survives, a stub
is caught (`FALSELY-present-caught`). Nothing here measures phenomenal experience — see the header.
"""
from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from packages.consciousness_blind.result import BlindResult, combine, statement_for

REPO = Path(__file__).resolve().parents[2]


def _paths(*rel: str) -> list[str]:
    """Keep only module/evidence paths that ACTUALLY exist under the repo (evidence must be real)."""
    return [p for p in rel if (REPO / p).exists()]


def _result(indicator_id: str, *, positive_pass: bool, positive_partial: bool,
            control_rejected: bool, organ_paths: list[str], stimulus: str,
            positive_detail: str, control_detail: str, notes: str,
            strength: str = "strong") -> BlindResult:
    theory, statement = statement_for(indicator_id)
    verdict = combine(positive_pass, positive_partial, control_rejected)
    return BlindResult(
        id=indicator_id, theory=theory, statement=statement, verdict=verdict,
        positive_pass=positive_pass, positive_partial=positive_partial,
        control_rejected=control_rejected, strength=strength,
        organ_paths=organ_paths, stimulus=stimulus,
        positive_detail=positive_detail, control_detail=control_detail, notes=notes,
    )


# ================================================================ RPT
def assess_rpt1(refine=None) -> BlindResult:
    from packages.perception import attention as att
    from packages.perception_recurrence.refinement import ACCEPT
    if refine is None:
        from packages.perception_recurrence.refinement import refine

    # held-out GATE frames: a gradient field + a bright central patch (self-battery used zeros/220)
    base = np.tile(np.linspace(20, 200, 48, dtype=np.float32), (48, 1))[..., None].repeat(3, axis=2)
    patch = base.copy(); patch[8:40, 8:40, :] = 245.0
    s_base, s_patch = att.frame_signature(base), att.frame_signature(patch)
    st = att.new_state()
    att.decide(st, s_base, now=0.0); att.commit(st, s_base, now=0.0)
    d_static = att.decide(st, s_base, now=1.0)      # identical frame -> predicted -> skip
    att.decide(st, s_patch, now=2.0)                # motion burst -> state.moving
    d_settle = att.decide(st, s_base, now=3.0)      # SAME frame as d_static -> settled -> run
    gate = (d_static["run"] is False) and (d_settle["run"] is True)

    # held-out WITHIN-PERCEPT sharpening (labels/scores/context unused by the self-battery)
    sharp = refine(["pen", "key", "coin"], [0.40, 0.34, 0.26], context=[0.66, 0.20, 0.14])
    sharpened = (getattr(sharp, "resolved", False) and getattr(sharp, "status", "") == "sharpened"
                 and getattr(sharp, "converged", False)
                 and getattr(sharp, "initial_confidence", 1.0) < ACCEPT <= getattr(sharp, "confidence", 0.0))
    # state-dependence: identical evidence, different top-down context -> different settled percept
    ca = refine(["p", "q", "r"], [0.40, 0.38, 0.22], context=[0.72, 0.18, 0.10])
    cb = refine(["p", "q", "r"], [0.40, 0.38, 0.22], context=[0.18, 0.72, 0.10])
    state_dep = getattr(ca, "winner", None) != getattr(cb, "winner", None)

    # FALSIFICATION: a genuine refiner must HONESTLY GIVE UP on flat evidence + flat context (its
    # anti-wireheading fixed point is the uniform distribution). A frozen refiner that resolves
    # anyway is caught here.
    flat = refine(["a", "b", "c"], [1.0, 1.0, 1.0], context=[1.0, 1.0, 1.0])
    honest_giveup = (getattr(flat, "resolved", True) is False) and (getattr(flat, "confidence", 1.0) < ACCEPT)

    return _result(
        "RPT-1",
        positive_pass=gate and sharpened and state_dep,
        positive_partial=gate,
        control_rejected=honest_giveup,
        organ_paths=_paths("packages/perception_recurrence/refinement.py",
                           "packages/perception/attention.py"),
        stimulus="gate: 48x48 gradient frame + central bright patch; refine ['pen','key','coin'] "
                 "scores [.40,.34,.26] ctx [.66,.20,.14]; state-dep ctx [.72,.18,.10] vs [.18,.72,.10]",
        positive_detail=f"gate identical-frame '{d_static['reason']}'(run={d_static['run']}) then "
                        f"'{d_settle['reason']}'(run={d_settle['run']}); within-percept "
                        f"{getattr(sharp,'initial_confidence',0):.3f}->{getattr(sharp,'confidence',0):.3f} "
                        f"status='{getattr(sharp,'status','')}'; state-dep winners "
                        f"'{getattr(ca,'winner','?')}' vs '{getattr(cb,'winner','?')}'",
        control_detail=f"flat evidence+flat context -> resolved={getattr(flat,'resolved','?')} "
                       f"conf={getattr(flat,'confidence',0):.3f} (must give up < accept {ACCEPT})",
        notes="Recurrence at gate + within-percept; the honest give-up on flat input is the "
              "falsification a frozen refiner fails. Functional recurrent refinement, not experience.",
    )


def assess_rpt2(build=None, answer=None) -> BlindResult:
    if build is None:
        from packages.situation_model.builder import build
    if answer is None:
        from packages.situation_model.reasoner import answer

    text = "Sandra travelled to the garden. Sandra grabbed the football. Sandra journeyed to the bedroom."
    sit = build(text)
    a = answer("Where is the football?", sit)      # football -> held by Sandra -> Sandra in bedroom
    bound = str(a.get("answer", "")).lower() == "bedroom"
    # FALSIFICATION: an object never mentioned must be ABSTAINED on, not answered with a phantom
    # location (a reasoner that always answers is caught here).
    a2 = answer("Where is the piano?", sit)
    abstained = a2.get("answer") is None

    return _result(
        "RPT-2",
        positive_pass=bound,
        positive_partial=(len(getattr(sit, "entities", {})) > 0 and len(getattr(sit, "events", [])) >= 2),
        control_rejected=abstained,
        organ_paths=_paths("packages/situation_model/builder.py",
                           "packages/situation_model/reasoner.py",
                           "packages/situation_model/state_tracker.py"),
        stimulus="story 'Sandra travelled to the garden. Sandra grabbed the football. Sandra "
                 "journeyed to the bedroom.'; Q 'Where is the football?'; control Q 'Where is the piano?'",
        positive_detail=f"{len(getattr(sit,'entities',{}))} entities + {len(getattr(sit,'events',[]))} "
                        f"events; cross-sentence bind -> '{a.get('answer')}'",
        control_detail=f"never-mentioned object -> answer={a2.get('answer')!r} (must abstain / None)",
        notes="The bound answer is recoverable only from the integrated object->holder->location "
              "structure; abstaining on an absent object is the falsification a phantom-answerer fails.",
    )


# ================================================================ GWT
def assess_gwt1(gather_candidates=None) -> BlindResult:
    if gather_candidates is None:
        from packages.continuous_self.ignition import gather_candidates
    from packages.continuous_self.stakes import read_vitals

    v = read_vitals()
    inc = SimpleNamespace(concept="comets", act="ask")
    cands = gather_candidates(incoming=inc, curiosity=["aurora", "basalt"], vitals=v, now=2200.0)
    kinds = sorted({c.kind for c in cands})
    # contentfulness FALSIFICATION: with NO inputs the kind-set must shrink (driven by input, not constant)
    degen = gather_candidates(incoming=None, curiosity=[], vitals=None, now=2200.0)
    degen_kinds = sorted({c.kind for c in degen})
    contentful = len(degen_kinds) < len(kinds)
    # STRICT bar for "specialised systems operating in PARALLEL into the workspace": at least one of the
    # HEAVY parallel perceptual modules (vision 'percept' / situation_model) must actually SUBMIT.
    heavy = {"percept", "perception", "situation"} & set(kinds)
    specialised = _paths("packages/perception/attention.py", "packages/situation_model/builder.py",
                         "packages/continuous_self/stakes.py",
                         "packages/continuous_self/somatic_marker.py",
                         "packages/continuous_self/causal_self.py")

    return _result(
        "GWT-1",
        positive_pass=(len(kinds) >= 3) and bool(heavy),
        positive_partial=(len(kinds) >= 2),
        control_rejected=contentful,
        organ_paths=_paths("packages/continuous_self/ignition.py") + specialised,
        stimulus="gather_candidates(incoming='comets/ask', curiosity=['aurora','basalt'], vitals=live); "
                 "degenerate control gather(incoming=None, curiosity=[], vitals=None)",
        positive_detail=f"seam kinds {kinds} ({len(kinds)} distinct) from live state; degenerate input "
                        f"-> kinds {degen_kinds}; {len(specialised)} specialised modules on disk; "
                        f"heavy perceptual module submitted: {sorted(heavy) or 'none'}",
        control_detail=f"contentful={contentful} (degenerate {len(degen_kinds)} < live {len(kinds)} kinds)",
        notes="HONEST DROP vs self-audit: the seam receives >=3 distinct LIGHTWEIGHT candidate kinds "
              "(utterance/vital/curiosity) and is contentful, but the two heaviest parallel modules "
              "(vision, situation_model) do NOT submit to the competition — parallel EXISTENCE yes, "
              "parallel SUBMISSION to the workspace only partial.",
    )


def assess_gwt2(compete=None) -> BlindResult:
    from packages.continuous_self import ignition as ig
    if compete is None:
        from packages.continuous_self.ignition import compete
    from packages.continuous_self.ignition import Candidate

    tmp = Path(tempfile.mkdtemp()) / "led.jsonl"
    orig = ig.LEDGER
    try:
        ig.LEDGER = tmp                                     # empty ledger -> clean bottleneck test
        cands = [Candidate("utterance", "comets", 0.82), Candidate("vital", "coherence", 0.55),
                 Candidate("curiosity", "volcanoes", 0.44), Candidate("memory", "z", 0.28),
                 Candidate("percept", "lamp", 0.49)]
        out = compete(cands, now=2200.0)
        one_winner = bool(out and getattr(out, "winner", None)) and \
            len(getattr(out, "suppressed", [])) == len(cands) - 1
        winner_topic = getattr(getattr(out, "winner", None), "topic", "?")
        # FALSIFICATION: an EMPTY candidate set must yield NO winner (no phantom ignition).
        empty = compete([], now=2200.0)
        no_phantom = empty is None
    finally:
        ig.LEDGER = orig

    return _result(
        "GWT-2",
        positive_pass=one_winner,
        positive_partial=bool(out and getattr(out, "winner", None)),
        control_rejected=no_phantom,
        organ_paths=_paths("packages/continuous_self/ignition.py"),
        stimulus="compete over 5 candidates (utterance:comets .82 / vital:coherence .55 / "
                 "curiosity:volcanoes .44 / memory:z .28 / percept:lamp .49); control compete([])",
        positive_detail=f"5 candidates -> winner '{winner_topic}', "
                        f"{len(getattr(out,'suppressed',[])) if out else 0} suppressed",
        control_detail=f"empty candidate set -> winner={None if no_phantom else 'PHANTOM'} "
                       f"(must be None)",
        notes="Exactly one content ignites and the rest are suppressed; the empty-set control catches "
              "a competition that invents a winner from nothing.",
    )


def assess_gwt3(verify_chain=None) -> BlindResult:
    from packages.continuous_self import ignition as ig
    from packages.continuous_self import somatic_marker as sm
    if verify_chain is None:
        from packages.continuous_self.ignition import verify_chain

    live_ok = bool(verify_chain())
    n_ignite = 0
    if ig.LEDGER.exists():
        for ln in ig.LEDGER.read_text(encoding="utf-8").splitlines():
            if '"event": "ignite"' in ln or '"event":"ignite"' in ln:
                n_ignite += 1
    cross_organ = (sm._IGN == ig.LEDGER)                    # somatic_marker reads the same timeline

    # FALSIFICATION: build a VALID temp chain, tamper one record, require detection. A verifier that
    # rubber-stamps a tampered ledger is caught here (this is the property the self-audit never tested).
    tmp = Path(tempfile.mkdtemp()) / "led.jsonl"
    orig = ig.LEDGER
    try:
        ig.LEDGER = tmp
        ig._append({"event": "ignite", "ts": 1.0, "kind": "curiosity", "topic": "a", "key": "curiosity:a"})
        ig._append({"event": "ignite", "ts": 2.0, "kind": "vital", "topic": "b", "key": "vital:b"})
        valid = bool(verify_chain())
        lines = tmp.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[0]); rec["topic"] = "TAMPERED"     # mutate a field, leave the old hash
        lines[0] = json.dumps(rec, ensure_ascii=False)
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tampered_detected = (verify_chain() is False)
    finally:
        ig.LEDGER = orig

    return _result(
        "GWT-3",
        positive_pass=live_ok and n_ignite > 0 and cross_organ,
        positive_partial=n_ignite > 0,
        control_rejected=valid and tampered_detected,
        organ_paths=_paths("packages/continuous_self/ignition.py",
                           "packages/continuous_self/somatic_marker.py",
                           "data/selfhood/ignition_ledger.jsonl"),
        stimulus="live ignition_ledger.jsonl verify_chain + ignite count + cross-organ pointer; "
                 "control: temp 2-record chain, tamper record[0].topic, require detection",
        positive_detail=f"live verify_chain={live_ok}, {n_ignite} ignite records, "
                        f"cross-organ read by somatic_marker={cross_organ}",
        control_detail=f"temp chain valid={valid}; after tampering one field verify_chain "
                       f"detected corruption={tampered_detected}",
        notes="Global broadcast to one owned, hash-chained timeline other organs read; the tamper "
              "control catches a verifier that would rubber-stamp a corrupted ledger.",
    )


def assess_gwt4(compete=None) -> BlindResult:
    from packages.continuous_self import ignition as ig
    if compete is None:
        from packages.continuous_self.ignition import compete
    from packages.continuous_self.ignition import Candidate

    tmp = Path(tempfile.mkdtemp()) / "led.jsonl"
    orig = ig.LEDGER
    try:
        ig.LEDGER = tmp
        cs = [Candidate("curiosity", "aurora", 0.50), Candidate("curiosity", "basalt", 0.60)]
        if tmp.exists():
            tmp.unlink()
        w_empty = compete(cs, now=9000.0).winner.topic          # louder 'basalt' with no debt
        tmp.write_text(json.dumps({"event": "ignite", "key": "curiosity:aurora", "topic": "aurora",
                                   "kind": "curiosity", "ts": 9000.0 - 3600}) + "\n", encoding="utf-8")
        w_debt = compete(cs, now=9000.0).winner.topic           # open commitment on quiet 'aurora'
        flipped = (w_empty == "basalt") and (w_debt == "aurora")

        # FALSIFICATION part 1: determinism — identical state must give the SAME winner (a winner that
        # changes with nothing but call order is a spurious 'state-dependence').
        if tmp.exists():
            tmp.unlink()
        w1 = compete(cs, now=9000.0).winner.topic
        w2 = compete(cs, now=9000.0).winner.topic
        deterministic = (w1 == w2)
        # FALSIFICATION part 2: a commitment on an ABSENT key (not among candidates) must NOT move it.
        tmp.write_text(json.dumps({"event": "ignite", "key": "curiosity:elsewhere", "topic": "elsewhere",
                                   "kind": "curiosity", "ts": 9000.0 - 3600}) + "\n", encoding="utf-8")
        w_absent = compete(cs, now=9000.0).winner.topic
        absent_no_flip = (w_absent == w1)
    finally:
        ig.LEDGER = orig

    return _result(
        "GWT-4",
        positive_pass=flipped,
        positive_partial=(w_empty != w_debt),
        control_rejected=deterministic and absent_no_flip,
        strength="scoped",
        organ_paths=_paths("packages/continuous_self/ignition.py"),
        stimulus="compete([curiosity:aurora .50, curiosity:basalt .60]) empty ledger vs open "
                 "commitment on 'aurora'; control: determinism + commitment on absent key 'elsewhere'",
        positive_detail=f"no debt -> '{w_empty}'; open commitment on aurora -> '{w_debt}' "
                        f"(flipped={flipped})",
        control_detail=f"deterministic (same state same winner)={deterministic}; absent-key commitment "
                       f"leaves winner '{w_absent}' == baseline '{w1}' -> no spurious flip={absent_no_flip}",
        notes="The workspace's own commitment state re-weights the same competition; determinism + the "
              "absent-key control catch a winner that flips for reasons other than the commitment. "
              "Scope (deepening, not a falsification): closure-driven succession, not a full task controller.",
    )


# ================================================================ HOT
def assess_hot1(hot_correlate=None) -> BlindResult:
    from packages.continuous_self.self_state import SelfState, Observation, evolve
    if hot_correlate is None:
        from packages.continuous_self.consciousness_correlates import hot_correlate

    st = SelfState()
    for _ in range(7):
        evolve(st, Observation(learning_active=True, concepts_delta=1, relations_delta=1,
                               uncertainty_signal=0.35, user_present=True, deficit_count=2))
    hc = hot_correlate(st)
    orders = int(hc.get("orders", 0))
    # FALSIFICATION: an EMPTY / unevolved degenerate state must NOT read as higher-order (orders < 2).
    empty = SimpleNamespace(current_thought="", meta_thought="", awareness="", self_question="")
    e_orders = int(hot_correlate(empty).get("orders", 0))

    return _result(
        "HOT-1",
        positive_pass=orders >= 2,
        positive_partial=orders >= 1,
        control_rejected=e_orders < 2,
        organ_paths=_paths("packages/continuous_self/consciousness_correlates.py",
                           "packages/continuous_self/self_state.py",
                           "packages/continuous_self/attention_schema.py"),
        stimulus="SelfState evolved 7 steps (learning, concepts+relations delta, uncertainty .35, "
                 "user_present, deficit 2); control: empty state (all reflective fields blank)",
        positive_detail=f"evolved state orders={orders} (has_meta={hc.get('has_meta')})",
        control_detail=f"empty degenerate state orders={e_orders} (must be < 2)",
        notes="A first-order thought is accompanied by a higher-order representation (awareness of "
              "attention / metacognition); the empty-state control catches a correlate that reports "
              "higher-order structure that is not there.",
    )


def assess_hot2(needs_reverify=None, is_confident=None) -> BlindResult:
    if needs_reverify is None or is_confident is None:
        from packages.perception import plausibility as pl
        needs_reverify = needs_reverify or pl.needs_reverify
        is_confident = is_confident or pl.is_confident

    plausible, implausible = "lamp", "비행기"     # held-out labels (self-battery used '냉장고')
    both_dirs = (needs_reverify(plausible, 0.15) is True          # low conf plausible -> doubt
                 and needs_reverify(plausible, 0.85) is False     # high conf plausible -> trust (skipped by self-audit)
                 and is_confident(plausible, 0.85, 5) is True      # confirmed -> accept
                 and is_confident(plausible, 0.15, 1) is False     # doubtful on 1 frame -> reject (skipped)
                 and needs_reverify(implausible, 0.85) is True)    # implausible always re-verified
    # STRICT bar: graded CALIBRATOR vs hard THRESHOLD? a fresh score sweep with a single flip is a step.
    sweep = [0.05, 0.25, 0.45, 0.65, 0.95]
    decisions = [bool(needs_reverify(plausible, s)) for s in sweep]
    flips = sum(1 for i in range(1, len(decisions)) if decisions[i] != decisions[i - 1])
    graded_calibrator = flips >= 2
    # FALSIFICATION: the monitor must discriminate on FRESH (unseen) scores, not memorise the probe.
    control_rejected = (needs_reverify(plausible, 0.02) is True) and (needs_reverify(plausible, 0.98) is False)

    return _result(
        "HOT-2",
        positive_pass=both_dirs and graded_calibrator,
        positive_partial=both_dirs,
        control_rejected=control_rejected,
        organ_paths=_paths("packages/perception/plausibility.py"),
        stimulus="both-direction discrimination on held-out 'lamp'@{.15,.85} + '비행기'@.85; strict "
                 "sweep {.05,.25,.45,.65,.95}; fresh control scores {.02,.98}",
        positive_detail=f"both-directions={both_dirs}; fresh-score decisions {decisions} "
                        f"(flips={flips}); graded_calibrator={graded_calibrator}",
        control_detail=f"fresh unseen scores: reverify(.02)={needs_reverify(plausible,0.02)}, "
                       f"reverify(.98)={needs_reverify(plausible,0.98)} (must be True/False)",
        notes="HONEST DROP vs self-audit: reliability DISCRIMINATION holds in BOTH directions (a "
              "stronger test than the self-audit ran), but the decision is a single hard THRESHOLD, "
              "not a graded metacognitive calibrator — so partial, not present.",
    )


def assess_hot3(induce_laws=None) -> BlindResult:
    from packages.continuous_self import causal_self as cs
    if induce_laws is None:
        from packages.continuous_self.causal_self import induce_laws

    cov = cs.coverage()
    n_trans = int(cov.get("transitions_observed", 0))
    laws_known = int(cov.get("laws_known", 0))
    from_lived = int(cov.get("promoted_from_lived", 0))
    strict_lived = int(cov.get("laws_lived_strict", 0))

    def _mk(k, s, c, e):
        return {"knowledge": k, "social": s, "coherence": c, "energy": e}

    # COHERENT held-out journal: 'explore' consistently raises knowledge -> a law MUST be induced.
    coherent = Path(tempfile.mkdtemp()) / "coh.jsonl"
    rows, k = [], 0.2
    for _ in range(6):
        rows.append({"vitals": _mk(k, 0.5, 0.5, 0.9), "decision": "explore"})
        k = min(0.95, k + 0.2)
        rows.append({"vitals": _mk(k, 0.5, 0.5, 0.9), "decision": "rest"})
    coherent.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    coherent_laws = induce_laws(coherent)
    learns = len(coherent_laws) >= 1

    # FALSIFICATION: an INCOHERENT journal ('explore' followed by alternating up/down, no consistent
    # direction) must promote NO law (honest abstention). An inducer that promotes anyway is caught.
    noise = Path(tempfile.mkdtemp()) / "noise.jsonl"
    nrows, kk, sign = [], 0.5, 1
    for _ in range(12):
        nrows.append({"vitals": _mk(kk, 0.5, 0.5, 0.9), "decision": "explore"})
        kk = min(0.95, max(0.05, kk + 0.2 * sign)); sign = -sign     # alternate -> conf ~ 0.5 < bar
        nrows.append({"vitals": _mk(kk, 0.5, 0.5, 0.9), "decision": "rest"})
    noise.write_text("\n".join(json.dumps(r) for r in nrows) + "\n", encoding="utf-8")
    abstains = len(induce_laws(noise)) == 0

    return _result(
        "HOT-3",
        positive_pass=(n_trans > 0) and (laws_known > 0) and (from_lived > 0) and learns,
        positive_partial=(n_trans > 0) and (laws_known > 0),
        control_rejected=abstains,
        strength="scoped",
        organ_paths=_paths("packages/continuous_self/causal_self.py",
                           "packages/continuous_self/causal_fuel.py",
                           "data/selfhood/stakes.jsonl"),
        stimulus="live coverage() + held-out COHERENT journal (explore->knowledge rises x6) + "
                 "INCOHERENT journal (explore->alternating +/-0.2 x12, no consistent direction)",
        positive_detail=f"live: {n_trans} transitions, laws_known={laws_known}, "
                        f"promoted_from_lived={from_lived}, laws_lived_strict={strict_lived}; "
                        f"coherent held-out -> {len(coherent_laws)} law(s) induced",
        control_detail=f"incoherent journal -> {len(induce_laws(noise))} laws (must abstain -> 0)",
        notes="Beliefs (causal laws) are formed from lived evidence, held revisably, and the former "
              "ABSTAINS on incoherent evidence (the falsification). Scope (transparent): the strict "
              "confidence-inducer promotes 0 on the live journal; the 13 held laws rest on "
              "causal_fuel's lived-corroboration counter, all promoted_from_lived.",
    )


def assess_hot4(build_markers=None, read_vitals=None) -> BlindResult:
    if build_markers is None:
        from packages.continuous_self.somatic_marker import build_markers
    if read_vitals is None:
        from packages.continuous_self.stakes import read_vitals

    markers = build_markers()
    vals = sorted({round(m.valence, 3) for m in markers.values()})
    n_levels = len(vals)
    intermediate = [v for v in vals if -0.9 < v < 0.9 and abs(v) > 1e-6]   # non-extreme, non-zero
    smooth = n_levels >= 3 and len(intermediate) >= 1
    grounded = len(markers) > 0 and all(int(getattr(m, "events", 0)) > 0 for m in markers.values())
    hungers = read_vitals().hungers()
    graded_vitals = len({round(h, 3) for h in hungers.values()}) >= 2

    return _result(
        "HOT-4",
        positive_pass=smooth and grounded and graded_vitals,
        positive_partial=n_levels >= 3,
        control_rejected=grounded,      # a smooth-LOOKING space with no real history is caught
        organ_paths=_paths("packages/continuous_self/somatic_marker.py",
                           "packages/continuous_self/stakes.py"),
        stimulus="live somatic markers (per-concept valence) + live vitals hungers; control: is the "
                 "smooth space grounded in real per-concept events (events>0) or fabricated?",
        positive_detail=f"{len(markers)} markers span {n_levels} distinct valence levels in "
                        f"[{vals[0] if vals else 0},{vals[-1] if vals else 0}], "
                        f"{len(intermediate)} intermediate (smooth); graded vitals={graded_vitals}",
        control_detail=f"grounded (every valence level backed by >=1 real event)={grounded}",
        notes="A graded per-concept valence space corroborated by graded vitals; the grounding control "
              "catches a fabricated smooth space with no lived history. Functional valence, not feeling.",
    )


# ================================================================ AST
def assess_ast1(build_schema=None, awareness_report=None) -> BlindResult:
    from packages.continuous_self.self_state import SelfState, Observation, evolve
    if build_schema is None:
        from packages.continuous_self.attention_schema import build_schema
    if awareness_report is None:
        from packages.continuous_self.attention_schema import awareness_report

    st_user = SelfState()
    for _ in range(6):
        evolve(st_user, Observation(user_present=True, learning_active=True, concepts_delta=1))
    st_reflect = SelfState()
    for _ in range(6):
        evolve(st_reflect, Observation(uncertainty_signal=0.9, learning_active=False))
    sch_u, sch_r = build_schema(st_user), build_schema(st_reflect)
    rep_u, rep_r = awareness_report(sch_u), awareness_report(sch_r)
    models_limits = bool(sch_u.get("not_attending_to"))
    honest = bool(sch_u.get("epistemic_status"))
    drives_report = bool(rep_u) and (rep_u != rep_r)

    return _result(
        "AST-1",
        positive_pass=bool(sch_u.get("attending_to")) and models_limits and honest and drives_report,
        positive_partial=bool(sch_u.get("attending_to")) and models_limits,
        control_rejected=(rep_u != rep_r),
        organ_paths=_paths("packages/continuous_self/attention_schema.py",
                           "packages/continuous_self/self_state.py"),
        stimulus="two states with different attention foci (user_present vs high-uncertainty), 6 "
                 "evolve steps each; require the awareness report to TRACK the schema (differ)",
        positive_detail=f"attending_to='{sch_u.get('attending_to')}' vs '{sch_r.get('attending_to')}'; "
                        f"models_limits={models_limits}; epistemic_status={honest}; "
                        f"reports differ={rep_u != rep_r}",
        control_detail=f"different schemas -> different awareness-talk={rep_u != rep_r} "
                       f"(a constant report ignoring the schema is caught)",
        notes="A distinct model of the system's own attention that owns its limits and DRIVES "
              "awareness-talk; the report-tracks-schema control catches a canned awareness string.",
    )


# ================================================================ PP
def assess_pp1(change_energy=None) -> BlindResult:
    from packages.perception import attention as att
    if change_energy is None:
        change_energy = att.change_energy

    rng = np.random.default_rng(20260722)                # held-out seed (self-battery used 0)
    fa = (rng.random((56, 56, 3)) * 40 + 20).astype(np.float32)
    fb = fa.copy(); fb[10:46, 10:46, :] = 240.0
    sa, sb = att.frame_signature(fa), att.frame_signature(fb)
    err_pred = change_energy(sa, sa)
    err_surp = change_energy(sa, sb)
    st = att.new_state()
    att.decide(st, sa, now=0.0); att.commit(st, sa, now=0.0)
    gate_skips = att.decide(st, sa, now=1.0)["run"] is False
    # FALSIFICATION: the error signal must be CONTENTFUL (identity->0, difference->>0); a constant
    # change-energy that cannot tell predicted from surprise is caught.
    control_rejected = (change_energy(sa, sa) == 0.0) and (change_energy(sa, sb) > 0.0)

    return _result(
        "PP-1",
        positive_pass=(err_pred == 0.0) and (err_surp > err_pred) and gate_skips,
        positive_partial=gate_skips,
        control_rejected=control_rejected,
        organ_paths=_paths("packages/perception/attention.py"),
        stimulus="held-out 56x56 noise frame + central bright patch (seed 20260722); "
                 "prediction error identical vs changed; gate skip on the predicted frame",
        positive_detail=f"prediction error identical={err_pred} vs changed={round(err_surp,3)}; "
                        f"well-predicted frame -> skip_heavy_detector={gate_skips}",
        control_detail=f"contentful energy: identity={change_energy(sa,sa)} (==0), "
                       f"difference={round(change_energy(sa,sb),3)} (>0)",
        notes="Compute is allocated to prediction error, not raw input; the constant-energy control "
              "catches a gate that cannot separate a predicted frame from a surprising one.",
    )


# ================================================================ AE
def assess_ae1(choose=None) -> BlindResult:
    from packages.continuous_self.stakes import Vitals
    if choose is None:
        from packages.continuous_self.stakes import choose

    # two SYNTHETIC held-out deficit states (deterministic): knowledge-starved vs social-starved
    know_starved = Vitals(knowledge=0.05, social=0.95, coherence=0.9, energy=0.9)
    social_starved = Vitals(knowledge=0.95, social=0.05, coherence=0.9, energy=0.9)
    a_know = choose(know_starved).get("action")
    a_social = choose(social_starved).get("action")
    tracks = (a_know == "explore") and (a_social == "converse")
    j = REPO / "data" / "selfhood" / "stakes.jsonl"
    n_journal = len([l for l in j.read_text(encoding="utf-8").splitlines() if l.strip()]) if j.exists() else 0

    return _result(
        "AE-1",
        positive_pass=tracks and n_journal > 0,
        positive_partial=bool(a_know) and n_journal > 0,
        control_rejected=(a_know != a_social),
        organ_paths=_paths("packages/continuous_self/stakes.py", "data/selfhood/stakes.jsonl"),
        stimulus="choose() over two synthetic vitals: knowledge-starved (0.05) vs social-starved "
                 "(0.05); live stakes.jsonl journaled-decision count",
        positive_detail=f"knowledge-starved -> '{a_know}', social-starved -> '{a_social}' "
                        f"(tracks steepest deficit={tracks}); {n_journal} journaled decisions",
        control_detail=f"choice varies with deficit: '{a_know}' != '{a_social}' -> {a_know != a_social} "
                       f"(a constant-action chooser is caught)",
        notes="Outputs are selected to pursue the steepest internal deficit and journaled as a real "
              "record; the two-state control catches a chooser that ignores the deficit.",
    )


def assess_ae2(body_schema_cls=None, naive_baseline_error=None, joint_model_cls=None) -> BlindResult:
    from packages.embodiment.body_schema import (BodySchema, JointForwardModel,
                                                  naive_baseline_error as real_naive)
    BS = body_schema_cls or BodySchema
    NAIVE = naive_baseline_error or real_naive
    JF = joint_model_cls or JointForwardModel

    rng = np.random.default_rng(20260722)        # held-out seed (self-battery used 0)
    L1, L2, dt = 0.7, 1.1, 0.05                  # held-out arm geometry (self-battery used 1.0/0.8)

    def tip(jj):
        return np.array([L1 * np.cos(jj[0]) + L2 * np.cos(jj[0] + jj[1]),
                         L1 * np.sin(jj[0]) + L2 * np.sin(jj[0] + jj[1])])

    def sample(n):
        X, Yd, Ynj = [], [], []
        for _ in range(n):
            jt = rng.uniform(-np.pi, np.pi, 2); vel = rng.uniform(-1, 1, 2); a = rng.uniform(-1, 1, 2)
            nj = jt + dt * vel + 0.5 * dt * dt * a
            X.append((jt, vel, a)); Yd.append(tip(nj) - tip(jt)); Ynj.append(nj)
        return X, np.array(Yd), np.array(Ynj)

    Xtr, Ydtr, Ynjtr = sample(400)
    Xte, Ydte, Ynjte = sample(120)               # held-out postures, disjoint from training
    bs = BS().fit(Xtr, Ydtr)
    bs_err, naive = bs.error(Xte, Ydte), NAIVE(Ydte)
    jf = JF().fit(Xtr, Ynjtr)
    jpred = np.stack([jf.predict(*x) for x in Xte])
    jf_err = float(np.mean(np.linalg.norm(jpred - Ynjte, axis=1)))
    naive_j = float(np.mean(np.linalg.norm(Ynjte - np.array([x[0] for x in Xte]), axis=1)))
    beats = (bs_err < naive) and (jf_err < naive_j)

    # FALSIFICATION: DECORRELATE inputs from outputs (shuffle target deltas). A real forward model's
    # advantage must VANISH (>= naive); a cheat that 'beats' anything is caught.
    perm = rng.permutation(len(Ydtr))
    bs_sh = BS().fit(Xtr, Ydtr[perm])
    sh_err = bs_sh.error(Xte, Ydte)
    advantage_vanishes = sh_err >= naive * 0.95

    return _result(
        "AE-2",
        positive_pass=beats,
        positive_partial=(bs_err < naive),
        control_rejected=advantage_vanishes,
        organ_paths=_paths("packages/embodiment/body_schema.py"),
        stimulus="2-link arm L1=0.7 L2=1.1, seed 20260722; fit on 400 babbling, test on 120 held-out "
                 "postures; control: refit on SHUFFLED target deltas (decorrelated)",
        positive_detail=f"held-out BodySchema err {round(bs_err,4)} vs naive {round(naive,4)} "
                        f"(ratio {round(bs_err/naive,3)}); JointForwardModel err {round(jf_err,4)} vs "
                        f"naive {round(naive_j,4)} (ratio {round(jf_err/naive_j,4)})",
        control_detail=f"shuffled-target model err {round(sh_err,4)} vs naive {round(naive,4)} -> "
                       f"advantage vanishes={advantage_vanishes} (a cheat that beats anything is caught)",
        notes="A learned forward model of the agent's own output->input contingencies beats a "
              "pre-declared no-motion baseline on UNSEEN postures AND loses that edge when the "
              "input->output mapping is decorrelated — structure, not a lookup table.",
    )


# ── the roster: id -> assessor callable ────────────────────────────────────────────────────────────
ASSESSORS = {
    "RPT-1": assess_rpt1, "RPT-2": assess_rpt2,
    "GWT-1": assess_gwt1, "GWT-2": assess_gwt2, "GWT-3": assess_gwt3, "GWT-4": assess_gwt4,
    "HOT-1": assess_hot1, "HOT-2": assess_hot2, "HOT-3": assess_hot3, "HOT-4": assess_hot4,
    "AST-1": assess_ast1, "PP-1": assess_pp1, "AE-1": assess_ae1, "AE-2": assess_ae2,
}
