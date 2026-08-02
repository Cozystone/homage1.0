# -*- coding: utf-8 -*-
"""M3 real-signal probe builder — an HONEST small graph where NS-2 / NS-5 CAN be informative.

Honest scope (stated up front, repeated in the report):
  * SMALL, in-memory graph built from REAL engine code (reasoning_vm.EpistemicGraph +
    graph_scale.spreading_activation.spread + vsa_reasoning.fhrr_core). NOT the 141M-edge store
    (a download is writing there; we never co-access it).
  * The point of the probe is to let the two new signals be MEASURED where a semantic-entropy /
    resonance-margin signal COULD matter — i.e. queries with MULTIPLE competing support paths.
    A signal that does not separate wrong-from-right here is reported as a null result, honestly.

The graph generalizes M1's inheritance-exception probe with genuine multi-path ambiguity. Every
entity's TRUE trait is fixed at construction; the LABEL is the REAL engine answer vs that truth.
Two independent, honestly-distinct error modes are planted:

  MODE-1  AMBIGUITY (multi-hub race).  The entity is_a its TRUE class hub with `mult_true`
     corroborating (duplicate) is_a edges AND a DISTRACTOR class hub with `mult_dist` edges.
     The engine answers the majority hub. When the distractor majority wins (mult_dist>mult_true)
     the answer is WRONG (a "spurious majority" — a real KG failure). Because the two hubs have
     COMPARABLE support, K diverse (edge-dropout) traversals DISAGREE -> high semantic entropy,
     and the VSA filler is a superposition of two atoms -> small clean-up margin. NS-2/NS-5 can
     see this. M1's epistemic confidence (a function of the hub's own source-count) is blind to it.

  MODE-2  INHERITANCE EXCEPTION (M1's mode).  The entity is_a ONE class hub, UNANIMOUSLY, but is
     a hidden exception: its true trait differs from the inherited value. The engine confidently
     returns the (wrong) inherited value. Every traversal AGREES -> entropy 0, margin large.
     NS-2/NS-5 are BLIND to this (the honest boundary). A fraction of exceptions are 'known'
     (an override is stored) -> they are answered correctly AND raise the hub's override_risk,
     which is the only partial hook M1's graded confidence has for the remaining hidden ones.

So NS-2/NS-5 are expected to help on MODE-1 and NOT on MODE-2 — the probe is built to reveal
exactly that split, not to guarantee a win.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from packages.conformal_gate.nonconformity import (
    SignalVector, from_activated_subgraph, from_epistemic_answer,
    from_resonance_margin, from_semantic_entropy,
)

# signal-field groups for the four measurement configs (masks over the full SignalVector)
BASELINE_FIELDS = ("epistemic_rung", "graded_confidence",
                   "activation_mass", "support_path_count", "top_delivered")
NS2_FIELDS = ("semantic_entropy",)
NS5_FIELDS = ("cleanup_resonance", "cleanup_margin")


@dataclass
class QueryRecord:
    entity: str
    label: int                 # 1 = engine answer correct, 0 = wrong (from REAL engine vs truth)
    mode: str                  # 'clean' | 'amb' | 'exc'
    full: SignalVector         # all signals populated
    entropy: float             # NS-2 diagnostic
    margin: Optional[float]    # NS-5 diagnostic


def _mask(sv: SignalVector, fields: tuple[str, ...]) -> SignalVector:
    """A copy of ``sv`` keeping only ``fields`` set (others -> None)."""
    return SignalVector(**{f: getattr(sv, f) for f in fields})


def config_signal(rec: QueryRecord, config: str) -> SignalVector:
    """The SignalVector a given measurement config sees for a record."""
    fields = {
        "baseline": BASELINE_FIELDS,
        "ns2": BASELINE_FIELDS + NS2_FIELDS,
        "ns5": BASELINE_FIELDS + NS5_FIELDS,
        "both": BASELINE_FIELDS + NS2_FIELDS + NS5_FIELDS,
    }[config]
    return _mask(rec.full, fields)


def build_probe(seed: int, *, n_classes: int = 8, n_entities: int = 500,
                p_clean: float = 0.50, p_amb: float = 0.32,
                K: int = 24, p_drop: float = 0.35, exc_scale: float = 1.0) -> list[QueryRecord]:
    """Build the probe and return one QueryRecord per entity (with REAL signals + true label).

    Modes: CLEAN (single hub, correct, entropy~0), AMB (balanced true+distractor race -> ~50%%
    wrong, high entropy/low margin -> NS-2/NS-5 VISIBLE), EXC (single-hub hidden inheritance
    exception -> wrong, entropy~0/margin high -> NS-2/NS-5 BLIND, M1's mode-2)."""
    from packages.reasoning_vm.epistemic_memory import EpistemicGraph
    from packages.graph_scale.spreading_activation import spread
    from packages.conformal_gate.semantic_entropy import semantic_entropy_full
    from packages.conformal_gate.resonance_verifier import (
        build_codebook, weighted_superposition, verify_binding,
    )

    rng = np.random.default_rng(seed)
    g = EpistemicGraph(spreading=False)

    # --- class hubs, each with a trait value and its own source count + exception rate ----
    hubs = [f"H{k}" for k in range(n_classes)]
    vals = [f"V{k}" for k in range(n_classes)]
    hub_val = dict(zip(hubs, vals))
    hub_exc_rate = {}
    for k in range(n_classes):
        g.add_fact(hubs[k], "trait", vals[k], sources=int(rng.integers(1, 6)))
        hub_exc_rate[hubs[k]] = float(rng.uniform(0.10, 0.45))

    # spread evidence index (WITH multiplicity — parallel corroborating paths a real KG has)
    spread_idx: dict[str, list] = {h: [(h, "trait", hub_val[h])] for h in hubs}

    def add_isa_mult(entity: str, hub: str, mult: int) -> None:
        g.add_isa(entity, hub)                       # EpistemicGraph dedups (structure only)
        for _ in range(mult):                        # spread sees `mult` corroborating edges
            spread_idx.setdefault(entity, []).append((entity, "is_a", hub))

    truth: dict[str, str] = {}
    plan: list[tuple] = []                           # (entity, mode) after graph is built

    for i in range(n_entities):
        e = f"e{i}"
        c = int(rng.integers(0, n_classes))          # true class
        true_hub = hubs[c]
        u = rng.random()
        # TOTAL support T is drawn from the SAME distribution for every mode, so activation-mass
        # and support-path-count carry NO spurious mode signal (an ambiguous entity is NOT just a
        # higher-mass node). The only structural difference an entity's mode makes is whether that
        # same T is CONCENTRATED on one hub or SPLIT across two -- which top_delivered (the M1
        # concentration proxy) CAN partly see, and which NS-2/NS-5 are built to see. This is the
        # fair, conservative test: mass is neutralized, the baseline keeps its legitimate hook.
        T = int(rng.integers(5, 8))                   # {5,6,7}, same for all modes
        if u < p_clean:
            # CLEAN: unanimous true hub. A fraction are hidden/known exceptions (MODE-2).
            add_isa_mult(e, true_hub, T)
            if rng.random() < hub_exc_rate[true_hub] * exc_scale:
                exc = f"x{i}"
                truth[e] = exc                        # true trait is the exception value
                if rng.random() < 0.4:                # 'known' exception -> override (correct) + raises risk
                    g.add_override(e, "trait", exc, sources=1)
                plan.append((e, "exc"))
            else:
                truth[e] = hub_val[true_hub]          # correctly inherits
                plan.append((e, "clean"))
        elif u < p_clean + p_amb:
            # MODE-1 AMBIGUITY: SAME total T split near-evenly between true + distractor hub, so
            # the race is a genuine coin flip -> ~50% wrong AND high entropy / small margin.
            d = int(rng.integers(0, n_classes))
            while d == c:
                d = int(rng.integers(0, n_classes))
            dist_hub = hubs[d]
            hi, lo = (T + 1) // 2, T // 2              # near-equal split of the SAME total T
            if rng.random() < 0.5:
                mult_true, mult_dist = hi, lo          # true (co-)majority -> engine tends correct
            else:
                mult_true, mult_dist = lo, hi          # distractor (co-)majority -> engine tends wrong
            true_first = (mult_true > mult_dist) or (mult_true == mult_dist and rng.random() < 0.5)
            if true_first:
                add_isa_mult(e, true_hub, mult_true); add_isa_mult(e, dist_hub, mult_dist)
            else:
                add_isa_mult(e, dist_hub, mult_dist); add_isa_mult(e, true_hub, mult_true)
            truth[e] = hub_val[true_hub]
            plan.append((e, "amb"))
        else:
            # pure-CLEAN remainder (unanimous true hub, correct) -- keeps proportions summing
            add_isa_mult(e, true_hub, T)
            truth[e] = hub_val[true_hub]
            plan.append((e, "clean"))

    fa = lambda t: spread_idx.get(t, [])
    codebook, cb_labels = build_codebook(hubs)

    records: list[QueryRecord] = []
    for e, mode in plan:
        res = g.answer(e, "trait")                    # REAL recognition-ladder answer
        if res["answer"] is None or res["epistemic_type"] == "UNKNOWN":
            continue                                  # engine already abstained -> not a candidate
        label = 1 if res["answer"] == truth[e] else 0

        # M1 baseline signals: epistemic rung/confidence + ONE canonical spread (p_drop=0)
        sv = from_epistemic_answer(res)
        canon = spread(e, fa)
        sv = sv.merge(from_activated_subgraph(canon))

        # NS-2: K diverse traversals over the SAME entity
        ent = semantic_entropy_full(e, fa, answer_values=hubs, K=K, seed=seed * 100003 + hash(e) % 100000,
                                    p_drop=p_drop)
        sv = sv.merge(from_semantic_entropy(ent))

        # NS-5: VSA verify of the entity's trait-hub filler (superposition of reached hubs)
        hub_items = [(h, canon.activation[h]) for h in hubs if h in canon.activation]
        if hub_items:
            filler = weighted_superposition(hub_items)
            vres = verify_binding(filler, codebook, cb_labels)
        else:
            vres = None
        sv = sv.merge(from_resonance_margin(vres))

        records.append(QueryRecord(entity=e, label=label, mode=mode, full=sv,
                                   entropy=ent.entropy,
                                   margin=(None if not vres else vres.get("margin"))))
    return records
