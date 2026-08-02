# -*- coding: utf-8 -*-
"""Probes — each maps one indicator property to ATANOR's REAL organs and RUNS them.

Discipline (constitution of this instrument):
  * Every probe imports and CALLS a real module (or reads a live journal it writes) and returns a
    verdict grounded in module paths + MEASURED behavior. Nothing is asserted from a self-report
    prompt, nothing is theatrical.
  * A 'present' verdict MUST cite at least one real module path that exists on disk (enforced by the
    battery's integrity check). If an organ is missing or too thin for the property, the honest
    verdict is 'partial' or 'absent' with a note — those become the U2 build queue.
  * We measure STRUCTURE and BEHAVIOR, never phenomenal experience. A high indicator score is a
    functional/architectural signature, not evidence of qualia (see the report header).

Theories & indicators follow Butlin et al. 2023, "Consciousness in Artificial Intelligence:
Insights from the Science of Consciousness" (RPT, GWT, HOT, AST, PP, Agency/Embodiment).
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# repo root = .../27., ATANOR DEMO  (packages/consciousness_audit/probes.py -> parents[2])
REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- verdict helpers
def _paths(*rel: str) -> list[str]:
    """Return the module paths that ACTUALLY exist under the repo (evidence must be real)."""
    return [p for p in rel if (REPO / p).exists()]


def _present(evidence: list[str], notes: str, *, strength: str = "strong") -> dict[str, Any]:
    return {"verdict": "present", "evidence": evidence, "notes": notes, "strength": strength}


def _partial(evidence: list[str], notes: str) -> dict[str, Any]:
    return {"verdict": "partial", "evidence": evidence, "notes": notes}


def _absent(evidence: list[str], notes: str) -> dict[str, Any]:
    return {"verdict": "absent", "evidence": evidence, "notes": notes}


# ================================================================ RPT — Recurrent Processing Theory

def probe_rpt1_input_recurrence() -> dict[str, Any]:
    """RPT-1: input modules use ALGORITHMIC RECURRENCE — processing carries recurrent internal state
    so the same input is processed differently depending on that state.

    Organs, at three depths of recurrence:
      * GATE level — perception/attention.py keeps a recurrent AttentionState across frames: the SAME
        frame yields a DIFFERENT gate decision depending on accumulated state.
      * SEQUENCE level — situation_model/state_tracker.py recurrently integrates a sentence stream into
        a persistent WorldState.
      * WITHIN-PERCEPT level (the deep RPT sensory-cortex feedback loop) — perception_recurrence
        iteratively folds a top-down context prior back onto FIXED bottom-up evidence, sharpening a
        low-confidence percept across iterations until it STABILISES, and HONESTLY GIVES UP (no
        confidence fabricated) when evidence+context are insufficient.

    Present requires all three: the gate signature, a measured within-percept sharpening+convergence,
    AND the honest give-up on a genuinely ambiguous percept (so refinement cannot be a rubber stamp).
    """
    from packages.perception import attention as att
    from packages.perception_recurrence.refinement import refine, ACCEPT
    import numpy as np

    # ---- GATE-level recurrence: same frame, different decision by accumulated state ----
    st = att.new_state()
    f0 = np.zeros((64, 64, 3), np.float32)
    fm = np.full((64, 64, 3), 220.0, np.float32)
    s0, sm = att.frame_signature(f0), att.frame_signature(fm)
    att.decide(st, s0, now=0.0); att.commit(st, s0, now=0.0)   # baseline committed (recurrent memory)
    d_static = att.decide(st, s0, now=1.0)                     # same frame -> "predicted", skip
    att.decide(st, sm, now=2.0)                                # motion burst -> sets state.moving
    d_settle = att.decide(st, s0, now=3.0)                     # SAME frame as d_static -> "settled", run
    gate_recurrent = (d_static["run"] is False) and (d_settle["run"] is True)

    # ---- WITHIN-PERCEPT recurrence: iteratively refine an ambiguous read to a stable percept ----
    sharp = refine(["cup", "bowl", "mug"], [0.42, 0.33, 0.25], context=[0.62, 0.23, 0.15])
    sharpened = sharp.resolved and sharp.status == "sharpened" and sharp.converged \
        and sharp.initial_confidence < ACCEPT <= sharp.confidence
    # honesty boundary: a genuinely ambiguous percept must NOT be talked into false certainty
    ambig = refine(["left", "right", "other"], [0.40, 0.40, 0.20], context=[0.34, 0.33, 0.33])
    honest_giveup = (ambig.resolved is False) and (ambig.confidence < ACCEPT)
    # recurrence signature within a percept: same evidence, different top-down state -> different percept
    ctx_a = refine(["p", "q", "r"], [0.40, 0.38, 0.22], context=[0.70, 0.20, 0.10])
    ctx_b = refine(["p", "q", "r"], [0.40, 0.38, 0.22], context=[0.20, 0.70, 0.10])
    state_dependent = ctx_a.winner != ctx_b.winner

    ev = _paths("packages/perception_recurrence/refinement.py",
                "packages/perception/attention.py",
                "packages/perception/plausibility.py",
                "packages/situation_model/state_tracker.py")
    ev.append(f"gate: identical frame '{d_static['reason']}'(run={d_static['run']}) then "
              f"'{d_settle['reason']}'(run={d_settle['run']}) — output depends on recurrent state")
    ev.append("within-percept: ambiguous read refined over "
              f"{sharp.iterations} iters, confidence trajectory "
              f"{[round(x, 3) for x in sharp.trajectory]} -> stabilised '{sharp.winner}' "
              f"(resolved={sharp.resolved}, status={sharp.status})")
    ev.append(f"honest give-up: tied percept converged to {ambig.confidence:.3f} < accept {ACCEPT} "
              f"-> status '{ambig.status}', resolved={ambig.resolved} (no confidence fabricated)")
    ev.append(f"state-dependence: identical evidence settled to '{ctx_a.winner}' vs '{ctx_b.winner}' "
              f"under different top-down context (same input processed differently by recurrent state)")

    if gate_recurrent and sharpened and honest_giveup and state_dependent:
        return _present(ev, "Algorithmic recurrence is implemented at three depths: the attention GATE "
                            "conditions processing on its own history, the situation model integrates a "
                            "SEQUENCE, and perception_recurrence adds the deep WITHIN-percept feedback "
                            "loop RPT centres on — a low-confidence percept is measurably sharpened "
                            f"({sharp.initial_confidence:.3f}->{sharp.confidence:.3f}) across iterations "
                            "to a stable fixed point, while a genuinely ambiguous percept honestly gives "
                            "up instead of fabricating certainty (the sub-critical self-feedback gain "
                            "makes flat input settle to uniform). Honest bound: this is functional "
                            "recurrent refinement, not evidence of phenomenal experience.")
    if gate_recurrent:
        return _partial(ev, "Gate/sequence recurrence holds, but within-percept refinement did not "
                            "demonstrate both sharpening and honest give-up on this run.")
    return _absent(ev, "Recurrent state did not change the decision on identical input.")


def probe_rpt2_integrated_representations() -> dict[str, Any]:
    """RPT-2: input modules generate ORGANISED, INTEGRATED perceptual representations (a scene/world
    bound into one structure, not a bag of features).

    Organ: situation_model builds a single WorldState binding entities <-> locations <-> possession
    across sentences; answering a cross-sentence query requires the integrated representation.
    """
    from packages.situation_model.builder import build
    from packages.situation_model.reasoner import answer

    text = "Daniel went to the kitchen. Daniel picked up the apple. Daniel journeyed to the office."
    sit = build(text)
    a = answer("Where is the apple?", sit)   # apple -> (held by Daniel) -> (Daniel in office)
    bound = str(a.get("answer", "")).lower() == "office"
    ev = _paths("packages/situation_model/builder.py",
                "packages/situation_model/reasoner.py",
                "packages/situation_model/state_tracker.py",
                "packages/perception/reconstruction_loss.py")
    ev.append(f"measured: {len(sit.entities)} entities + {len(sit.events)} events integrated; "
              f"cross-sentence bind 'Where is the apple?' -> '{a.get('answer')}'")
    if bound:
        return _present(ev, "An integrated world representation binds object->holder->location across "
                            "sentences (the answer is only recoverable from the integrated structure).")
    return _partial(ev, "Representation built but cross-binding query did not resolve.")


# ================================================================ GWT — Global Workspace Theory

def probe_gwt1_parallel_modules() -> dict[str, Any]:
    """GWT-1: multiple SPECIALISED systems (modules) capable of operating in PARALLEL.

    Organ: the architecture has many specialised packages (perception, situation_model, stakes/vitals,
    somatic_marker/affect, causal_self, inner_voice) running as parallel daemons. ignition.gather_
    candidates is the seam where distinct module TYPES submit candidates to the shared workspace.
    """
    from packages.continuous_self import ignition as ig
    from packages.continuous_self.stakes import read_vitals

    v = read_vitals()
    inc = SimpleNamespace(concept="rivers", act="ask")
    cands = ig.gather_candidates(incoming=inc, curiosity=["stars", "tides"], vitals=v, now=1000.0)
    kinds = sorted({c.kind for c in cands})
    specialised = _paths("packages/perception/attention.py",
                         "packages/situation_model/builder.py",
                         "packages/continuous_self/stakes.py",
                         "packages/continuous_self/somatic_marker.py",
                         "packages/continuous_self/causal_self.py",
                         "packages/inner_voice")
    ev = _paths("packages/continuous_self/ignition.py") + specialised
    ev.append(f"measured: {len(specialised)} specialised modules on disk; "
              f"workspace seam received {len(cands)} candidates of kinds {kinds}")
    if len(kinds) >= 2 and len(specialised) >= 3:
        return _present(ev, "Many specialised modules exist and run in parallel; distinct module types "
                            "submit to one workspace. Scope: the gather seam currently wires "
                            "utterance/vital/curiosity/commitment; vision & situation_model run as "
                            "parallel daemons but are not yet all wired into the competition seam.",
                        strength="scoped")
    return _partial(ev, "Fewer than two module types submitted to the workspace.")


def probe_gwt2_workspace_bottleneck() -> dict[str, Any]:
    """GWT-2: a LIMITED-CAPACITY workspace — a serial bottleneck where exactly one content is selected.

    Organ: ignition.compete takes MANY candidates and ignites EXACTLY ONE (the rest are suppressed).
    """
    from packages.continuous_self import ignition as ig
    from packages.continuous_self.ignition import Candidate, compete

    tmp = Path(tempfile.mkdtemp()) / "ledger.jsonl"          # empty ledger -> clean bottleneck test
    orig = ig.LEDGER
    try:
        ig.LEDGER = tmp
        cands = [Candidate("utterance", "birds", 0.85), Candidate("vital", "social", 0.60),
                 Candidate("curiosity", "rivers", 0.45), Candidate("memory", "y", 0.30),
                 Candidate("percept", "cup", 0.50)]
        out = compete(cands, now=1000.0)
        n_win = 1 if out and out.winner else 0
        n_supp = len(out.suppressed) if out else 0
    finally:
        ig.LEDGER = orig
    ev = _paths("packages/continuous_self/ignition.py")
    ev.append(f"measured: {len(cands)} candidates -> {n_win} winner ('{out.winner.kind}:"
              f"{out.winner.topic}'), {n_supp} suppressed (serial bottleneck, decisive={out.decisive})")
    if n_win == 1 and n_supp == len(cands) - 1:
        return _present(ev, "Exactly one content ignites into the workspace; all others are suppressed "
                            "— the limited-capacity serial bottleneck a parallel pipeline lacks.")
    return _partial(ev, "Selection was not a single-winner bottleneck.")


def probe_gwt3_global_broadcast() -> dict[str, Any]:
    """GWT-3: the selected content is BROADCAST GLOBALLY — made available to modules system-wide.

    Organ: ignition.record_ignition writes the winner + an attention-schema report to ONE owned,
    hash-chained ledger; other organs READ that ledger (somatic_marker joins it per concept), so the
    workspace content is globally available. We verify the LIVE ledger and its tamper-evident chain.
    """
    from packages.continuous_self import ignition as ig
    from packages.continuous_self import somatic_marker as sm

    chain_ok = ig.verify_chain()
    n_ignite = 0
    if ig.LEDGER.exists():
        for ln in ig.LEDGER.read_text(encoding="utf-8").splitlines():
            if '"event": "ignite"' in ln or '"event":"ignite"' in ln:
                n_ignite += 1
    cross_organ = (REPO / "data" / "selfhood" / "ignition_ledger.jsonl") == sm._IGN  # somatic reads it
    ev = _paths("packages/continuous_self/ignition.py",
                "packages/continuous_self/somatic_marker.py",
                "data/selfhood/ignition_ledger.jsonl")
    ev.append(f"measured: {n_ignite} live broadcast(ignite) records; verify_chain={chain_ok}; "
              f"cross-organ read by somatic_marker={cross_organ}")
    if n_ignite > 0 and chain_ok and cross_organ:
        return _present(ev, "Workspace winners are broadcast to a single owned, tamper-evident timeline "
                            "that other organs read (global availability), integrity-verified live.")
    if n_ignite > 0:
        return _partial(ev, "Broadcast records exist but chain/cross-organ read not confirmed.")
    return _absent(ev, "No broadcast records found in the live ledger.")


def probe_gwt4_state_dependent_attention() -> dict[str, Any]:
    """GWT-4: STATE-DEPENDENT attention — what is attended depends on the workspace's own state
    (supporting successive querying of modules).

    Organ: ignition's open-COMMITMENT debt biases the next competition. Same candidate set, different
    internal commitment state -> different winner (the 'same input processed differently' signature).
    """
    from packages.continuous_self import ignition as ig
    from packages.continuous_self.ignition import Candidate, compete

    tmp = Path(tempfile.mkdtemp()) / "ledger.jsonl"
    orig = ig.LEDGER
    try:
        ig.LEDGER = tmp
        cs = [Candidate("curiosity", "x", 0.50), Candidate("curiosity", "y", 0.60)]
        w_empty = compete(cs, now=5000.0).winner.topic                      # no debt -> louder y wins
        tmp.write_text(json.dumps({"event": "ignite", "key": "curiosity:x", "topic": "x",
                                   "kind": "curiosity", "ts": 5000.0 - 3600}) + "\n", encoding="utf-8")
        w_debt = compete(cs, now=5000.0).winner.topic                       # open commitment on x -> x wins
    finally:
        ig.LEDGER = orig
    flipped = w_empty != w_debt
    ev = _paths("packages/continuous_self/ignition.py")
    ev.append(f"measured: identical candidates -> winner '{w_empty}' with no commitment vs '{w_debt}' "
              f"with an open commitment on x (state-dependent, flipped={flipped})")
    if flipped:
        return _present(ev, "Attention is state-dependent: the internal commitment ledger reweights the "
                            "same competition. Scope: succession is closure-driven (finish what was "
                            "started) rather than a full task-planned module-querying controller — U2 "
                            "target: workspace-directed successive querying for multi-step tasks.",
                        strength="scoped")
    return _partial(ev, "Internal state did not alter the attentional winner.")


# ================================================================ HOT — Higher-Order Theories

def probe_hot1_higher_order_representation() -> dict[str, Any]:
    """HOT-1: a HIGHER-ORDER representation OF a first-order state (a state ABOUT another state).

    Organ: evolving self_state produces a first-order thought AND a representation of its own
    attention (awareness) / a metacognitive reflection (meta_thought); consciousness_correlates counts
    the orders present; somatic_marker.stance is a higher-order summary over first-order encounters.
    """
    from packages.continuous_self.self_state import SelfState, Observation, evolve
    from packages.continuous_self.consciousness_correlates import hot_correlate

    st = SelfState()
    for i in range(8):
        evolve(st, Observation(learning_active=True, concepts_delta=2, uncertainty_signal=0.5,
                               user_present=(i % 2 == 0), deficit_count=3))
    hc = hot_correlate(st)
    orders = int(hc.get("orders", 0))
    ev = _paths("packages/continuous_self/consciousness_correlates.py",
                "packages/continuous_self/attention_schema.py",
                "packages/continuous_self/somatic_marker.py",
                "packages/continuous_self/self_state.py")
    ev.append(f"measured: first-order thought + higher-order representation, orders={orders}, "
              f"has_meta={hc.get('has_meta')}, awareness='{bool(getattr(st, 'awareness', ''))}'")
    if orders >= 2:
        return _present(ev, "A first-order state (current thought) is accompanied by a distinct "
                            "higher-order representation of it (awareness of attention and/or "
                            "metacognitive reflection) — the HOT signature, computed from real state.")
    return _partial(ev, "Only a first-order state was present (no higher-order representation).")


def probe_hot2_metacognitive_monitoring() -> dict[str, Any]:
    """HOT-2: METACOGNITIVE MONITORING distinguishing RELIABLE perceptual representations from noise.

    Organ: perception/plausibility flags implausible/low-confidence detections for re-verification
    (reliability monitoring); reconstruction_loss.cycle_audit reports which attributes SURVIVED vs
    were DROPPED (the system knows the limits of its own representation).
    """
    from packages.perception import plausibility as pl
    reverify_low = pl.needs_reverify("냉장고", 0.20)      # low score on a plausible object -> re-check
    confident_hi = pl.is_confident("냉장고", 0.90, 5)     # high score, enough frames -> trust
    dropped = preserved = None
    try:
        from packages.perception.reconstruction_loss import cycle_audit
        ca = cycle_audit()
        dropped, preserved = ca["capacity"]["dropped"], ca["capacity"]["preserved"]
    except Exception as e:  # generative decoder deps optional on some boxes
        dropped = f"[reconstruction unavailable: {type(e).__name__}]"
    ev = _paths("packages/perception/plausibility.py",
                "packages/perception/reconstruction_loss.py")
    ev.append(f"measured: needs_reverify(low_score)={reverify_low}, is_confident(high_score)="
              f"{confident_hi}; reconstruction preserved={preserved}, dropped={dropped}")
    discriminates = (reverify_low is True) and (confident_hi is True)
    if discriminates:
        return _present(ev, "The system monitors the reliability of its own perceptual reads "
                            "(re-verifies the doubtful, trusts the confirmed) and names which "
                            "attributes its representation dropped. Scope: monitoring is perceptual-"
                            "reliability heuristics, not yet a general confidence calibrator over "
                            "arbitrary representations — U2 target: learned calibrated confidence.",
                        strength="scoped")
    return _partial(ev, "Reliability discrimination did not separate low from high confidence.")


def probe_hot3_belief_updating_agency() -> dict[str, Any]:
    """HOT-3: agency guided by BELIEF-FORMATION with a disposition to UPDATE beliefs per monitoring.

    Organ: causal_self INDUCES action->effect laws from its own lived journal, promoting only those
    that pass a support/confidence bar and ABSTAINING otherwise; agency_ledger.retraction_conditions
    and self_causal_reasoner make self-location revisable under counterfactuals.
    """
    from packages.continuous_self import causal_self as cs
    from packages.continuous_self.agency_ledger import AgencyLedger

    cov = cs.coverage()
    n_trans = int(cov.get("transitions_observed", 0))
    n_laws = int(cov.get("laws_known", 0))
    al = AgencyLedger()
    arc = al.judged("turn the light off", why="task demands OFF")
    al.acted(arc, "emit B", delivered=True); al.observed(arc, "light OFF")
    n_retract = len(al.retraction_conditions())
    ev = _paths("packages/continuous_self/causal_self.py",
                "packages/continuous_self/agency_ledger.py",
                "packages/self_model/self_causal_reasoner.py",
                "data/selfhood/stakes.jsonl")
    ev.append(f"measured: belief-formation ran over {n_trans} lived transitions, {n_laws} laws promoted "
              f"(support>={cov.get('min_support')} & conf>={cov.get('min_confidence')}); "
              f"{n_retract} revisable retraction conditions held structurally")
    if n_trans > 0 and n_laws > 0:
        return _present(ev, "Beliefs (causal laws) are formed from lived evidence and held revisably.")
    if n_trans > 0:
        return _partial(ev, f"The belief-formation + abstention loop RUNS on {n_trans} real transitions "
                            f"and the revision structure (retraction conditions, counterfactual self-"
                            f"location) is present, but 0 laws have crossed the promotion bar yet — no "
                            f"learned causal belief is HELD. U2 target: feed richer/longer-lived, more "
                            f"varied (context,action)->outcome data so laws promote.")
    return _absent(ev, "No lived transitions to form beliefs from.")


def probe_hot4_quality_space_valence() -> dict[str, Any]:
    """HOT-4: a QUALITY SPACE from sparse, smooth coding — here, a graded VALENCE dimension.

    Organ: somatic_marker assigns each concept a graded valence in [-1,1] (a smooth quality space of
    stances); stakes vitals are graded deficits in [0,1]; homeostasis carries valence/arousal hormones.
    """
    from packages.continuous_self import somatic_marker as sm
    from packages.continuous_self.stakes import read_vitals

    markers = sm.build_markers()
    vals = sorted({round(m.valence, 3) for m in markers.values()})
    hungers = read_vitals().hungers()
    graded = sorted({round(h, 3) for h in hungers.values()})
    ev = _paths("packages/continuous_self/somatic_marker.py",
                "packages/continuous_self/stakes.py",
                "packages/continuous_self/homeostasis.py")
    ev.append(f"measured: {len(markers)} somatic markers span {len(vals)} distinct valence levels in "
              f"[{vals[0] if vals else 0}, {vals[-1] if vals else 0}]; vitals graded at {len(graded)} "
              f"levels — a continuous (smooth) valence/deficit space, not a binary flag")
    if len(vals) >= 3:
        return _present(ev, "Valence is coded as a graded per-concept scalar over many concepts "
                            "(a smooth functional quality space), corroborated by graded vitals. "
                            "Honest bound: this is a functional valence space, not phenomenal feeling.")
    if graded:
        return _partial(ev, "Vitals are graded but per-concept valence space is sparse (little history).")
    return _absent(ev, "No graded valence/quality dimension found.")


# ================================================================ AST — Attention Schema Theory

def probe_ast1_attention_schema() -> dict[str, Any]:
    """AST-1: the system holds a MODEL OF ITS OWN ATTENTION — including attention's LIMITS — and
    generates awareness-talk FROM that model (Graziano's mechanism).

    Organ: attention_schema.build_schema returns what it is attending to, HOW, what drew it, and —
    crucially — what it is NOT attending to (the schema owns its limits) + an honest epistemic_status.
    """
    from packages.continuous_self.self_state import SelfState, Observation, evolve
    from packages.continuous_self import attention_schema as asch

    st = SelfState()
    for i in range(6):
        evolve(st, Observation(learning_active=True, concepts_delta=1, uncertainty_signal=0.4))
    schema = asch.build_schema(st)
    report = asch.awareness_report(schema)
    models_limits = bool(schema.get("not_attending_to"))
    honest = bool(schema.get("epistemic_status"))
    ev = _paths("packages/continuous_self/attention_schema.py",
                "packages/continuous_self/consciousness_correlates.py")
    ev.append(f"measured: attending_to set + not_attending_to({len(schema.get('not_attending_to', []))} "
              f"items, models limits={models_limits}); epistemic_status present={honest}; "
              f"awareness generated FROM schema (len={len(report)})")
    if schema.get("attending_to") and models_limits and report:
        return _present(ev, "A distinct, simplified model OF the system's own attention exists, owns "
                            "what it EXCLUDES, and drives awareness-talk — a direct implementation of "
                            "AST's mechanism, which honestly marks its own epistemic status.")
    return _partial(ev, "An attention model exists but does not model its own limits / drive report.")


# ================================================================ PP — Predictive Processing

def probe_pp1_predictive_coding() -> dict[str, Any]:
    """PP-1: PREDICTIVE CODING — the system predicts its input and processes the PREDICTION ERROR.

    Organ: perception/attention spends expensive compute only on the change_energy (prediction error)
    between the predicted (last committed) frame and the actual frame — a static, well-predicted scene
    costs almost nothing; reconstruction_loss is a generative model that rebuilds the input; body_schema
    forward models predict next sensory state from action.
    """
    from packages.perception import attention as att
    import numpy as np

    f0 = np.zeros((64, 64, 3), np.float32)
    fm = np.full((64, 64, 3), 220.0, np.float32)
    s0, sm = att.frame_signature(f0), att.frame_signature(fm)
    err_predicted = att.change_energy(s0, s0)      # perfectly predicted -> ~0 error -> no compute
    err_surprise = att.change_energy(s0, sm)       # violated prediction -> large error -> compute
    st = att.new_state()
    att.decide(st, s0, now=0.0); att.commit(st, s0, now=0.0)
    d_pred = att.decide(st, s0, now=1.0)           # predicted -> run=False (skip heavy detector)
    ev = _paths("packages/perception/attention.py",
                "packages/perception/reconstruction_loss.py",
                "packages/embodiment/body_schema.py")
    ev.append(f"measured: prediction error 0.0 (identical) vs {round(err_surprise, 3)} (changed); "
              f"well-predicted frame -> run={d_pred['run']} (compute spent only on prediction error)")
    if err_predicted == 0.0 and err_surprise > err_predicted and d_pred["run"] is False:
        return _present(ev, "The perceptual gate implements predictive coding's core: compute is "
                            "allocated to prediction error, not raw input; corroborated by a "
                            "generative reconstruction model and motor forward models.")
    return _partial(ev, "Prediction-error gating not clearly demonstrated.")


# ================================================================ AE — Agency & Embodiment

def probe_ae1_agency() -> dict[str, Any]:
    """AE-1: AGENCY — learning from feedback and selecting outputs to PURSUE GOALS.

    Organ: stakes reads real vitals and chooses an action by argmax over urge*relief (goal pursuit
    driven by internal deficits, journaled live); causal_self learns action->effect from that feedback;
    agency_ledger records judgment->output->effect arcs.
    """
    from packages.continuous_self.stakes import read_vitals, choose
    from packages.continuous_self import causal_self as cs

    v = read_vitals()
    decision = choose(v)
    n_lines = 0
    j = REPO / "data" / "selfhood" / "stakes.jsonl"
    if j.exists():
        n_lines = len([ln for ln in j.read_text(encoding="utf-8").splitlines() if ln.strip()])
    n_trans = cs.coverage().get("transitions_observed", 0)
    ev = _paths("packages/continuous_self/stakes.py",
                "packages/continuous_self/causal_self.py",
                "packages/continuous_self/agency_ledger.py",
                "data/selfhood/stakes.jsonl")
    ev.append(f"measured: goal chosen '{decision.get('action')}' (reason: "
              f"{str(decision.get('reason',''))[:52]}); {n_lines} journaled decisions; "
              f"learning from feedback over {n_trans} transitions")
    if decision.get("action") and n_lines > 0:
        return _present(ev, "Outputs are selected to pursue goals set by internal deficits (one argmax "
                            "over urge*relief, no threshold ladder), journaled as a real record the "
                            "causal learner then mines for feedback.")
    return _partial(ev, "Goal-directed selection present but no journaled history of it.")


def probe_ae2_embodiment() -> dict[str, Any]:
    """AE-2: EMBODIMENT — modeling OUTPUT-INPUT CONTINGENCIES (how the agent's own actions change its
    own sensory input), and GENERALISING beyond memorised cases.

    Organ: embodiment/body_schema learns a forward model mapping (joints, velocity, ACTION) -> change
    in sensed fingertip position, fit on 'babbling' and tested on HELD-OUT postures. Beating the naive
    'no motion' baseline on unseen data shows a learned contingency model, not a lookup table.
    """
    import numpy as np
    from packages.embodiment.body_schema import (BodySchema, JointForwardModel,
                                                  naive_baseline_error, ForwardKinematics)
    rng = np.random.default_rng(0)
    L1, L2, dt = 1.0, 0.8, 0.05

    def tip(jj):
        return np.array([L1*np.cos(jj[0]) + L2*np.cos(jj[0]+jj[1]),
                         L1*np.sin(jj[0]) + L2*np.sin(jj[0]+jj[1])])

    def sample(n):
        X, Yd, Ynj, tips, js = [], [], [], [], []
        for _ in range(n):
            jt = rng.uniform(-np.pi, np.pi, 2); vel = rng.uniform(-1, 1, 2); a = rng.uniform(-1, 1, 2)
            nj = jt + dt*vel + 0.5*dt*dt*a
            X.append((jt, vel, a)); Yd.append(tip(nj) - tip(jt)); Ynj.append(nj)
            tips.append(tip(jt)); js.append(jt)
        return X, np.array(Yd), np.array(Ynj), np.array(tips), js

    Xtr, Ydtr, Ynjtr, _, _ = sample(400)
    Xte, Ydte, Ynjte, tipste, jste = sample(120)   # HELD-OUT postures, disjoint from training
    bs = BodySchema().fit(Xtr, Ydtr)
    bs_err, naive = bs.error(Xte, Ydte), naive_baseline_error(Ydte)
    jf = JointForwardModel().fit(Xtr, Ynjtr)
    jpred = np.stack([jf.predict(*x) for x in Xte])
    jf_err = float(np.mean(np.linalg.norm(jpred - Ynjte, axis=1)))
    naive_j = float(np.mean(np.linalg.norm(Ynjte - np.array([x[0] for x in Xte]), axis=1)))
    ev = _paths("packages/embodiment/body_schema.py",
                "packages/embodiment/curriculum.py",
                "packages/embodiment/mujoco_body.py")
    ev.append(f"measured (held-out): BodySchema tip-delta err {round(bs_err,4)} vs naive {round(naive,4)} "
              f"(ratio {round(bs_err/naive,3)}); JointForwardModel err {round(jf_err,4)} vs naive "
              f"{round(naive_j,4)} (ratio {round(jf_err/naive_j,4)}) — output(action)->input contingency")
    if bs_err < naive and jf_err < naive_j:
        return _present(ev, "A learned forward model of the agent's own output->input contingencies "
                            "beats the pre-declared 'no-motion' baseline on UNSEEN postures "
                            "(generalises = structure, not a lookup table).")
    return _partial(ev, "Forward model did not beat the naive baseline on held-out data.")
