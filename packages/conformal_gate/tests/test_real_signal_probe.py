# -*- coding: utf-8 -*-
"""GATE (d) — real-signal probe. Honest scope statement up front:

This runs the CONFORMAL GATE on nonconformity scores produced by REAL ATANOR signal code:
  * reasoning_vm.epistemic_memory.EpistemicGraph.answer  (recognition rung + graded confidence)
  * graph_scale.spreading_activation.spread              (activation mass + support-path count)
on a SMALL, in-memory knowledge graph. The WRONG class is genuine: inheritance EXCEPTIONS
that the graph does not know about, so it confidently returns an INHERITED answer that is
actually wrong — the real "confidently-wrong" failure mode of the recognition ladder.

It is NOT a measurement over the shipped 141M-edge store or the live answer path (that is
wiring-pending; see nonconformity.WIRING_STATUS and the report). It proves the WIRED signal
readers work end-to-end on real signal objects and that the certificate holds on real
(weak) ATANOR signals — paid for, as the thesis predicts, in abstention.
"""
from __future__ import annotations

import numpy as np
import pytest

from packages.conformal_gate import conformal as C
from packages.conformal_gate.nonconformity import (
    SignalVector, from_activated_subgraph, from_epistemic_answer, nonconformity,
)

ALPHAS = (0.05, 0.10, 0.20)


def _build_real_graph(seed: int):
    """A taxonomy where children inherit a parent trait, but a hidden fraction are EXCEPTIONS.
    Some exceptions are 'known' (override added -> raises the parent's override_risk, which the
    real EpistemicGraph uses to discount INHERITED confidence for the remaining siblings)."""
    from packages.reasoning_vm.epistemic_memory import EpistemicGraph
    rng = np.random.default_rng(seed)
    g = EpistemicGraph(spreading=False)
    truth: dict[tuple, str] = {}
    queries: list[tuple[str, str]] = []
    for pi in range(30):
        parent = f"cat{pi}"
        val = f"trait{pi}"
        g.add_fact(parent, "trait", val, sources=int(rng.integers(1, 6)))
        truth[(parent, "trait")] = val
        queries.append((parent, "trait"))
        n_child = int(rng.integers(30, 60))
        exc_rate = float(rng.uniform(0.15, 0.5))
        for ci in range(n_child):
            child = f"c{pi}_{ci}"
            g.add_isa(child, parent)
            if rng.random() < exc_rate:                       # a real exception
                exc_val = f"exc{pi}_{ci}"
                truth[(child, "trait")] = exc_val
                if rng.random() < 0.4:                         # 'known' exception -> override
                    g.add_override(child, "trait", exc_val, sources=1)
            else:
                truth[(child, "trait")] = val                  # correctly inherits
            queries.append((child, "trait"))
    return g, truth, queries


def _facts_about(g):
    idx: dict[str, list] = {}
    for (s, p), d in g.facts.items():
        idx.setdefault(s, []).append((s, p, d["o"]))
    for (s, p), d in g.overrides.items():
        idx.setdefault(s, []).append((s, p, d["o"]))
    for child, parents in g.isa.items():
        for par in parents:
            idx.setdefault(child, []).append((child, "is_a", par))
    return lambda t: idx.get(t, [])


def _probe(seed: int, use_spread: bool, jitter: bool = False):
    """Return (scores, labels) from REAL signal code. label 1=correct candidate, 0=wrong."""
    from packages.graph_scale.spreading_activation import spread
    g, truth, queries = _build_real_graph(seed)
    fa = _facts_about(g) if use_spread else None
    scores, labels = [], []
    for (s, p) in queries:
        res = g.answer(s, p)                          # REAL recognition-ladder answer
        if res["epistemic_type"] == "UNKNOWN" or res["answer"] is None:
            continue                                   # graph already abstained; not a candidate
        sv = from_epistemic_answer(res)
        if use_spread:
            sv = sv.merge(from_activated_subgraph(spread(s, fa)))
        scores.append(nonconformity(sv))
        labels.append(1 if res["answer"] == truth[(s, p)] else 0)
    s = np.array(scores, dtype=float)
    if jitter:                                         # randomized tie-break for the discrete ladder
        s = C.jitter_scores(s, np.random.default_rng(seed + 1), eps=1e-6)
    return s, np.array(labels, dtype=int)


def test_gate_d_real_signal_certificate_holds(capsys):
    # Averaged over independent graph builds (the certificate is on the calibration draw).
    seeds = range(4000, 4020)                          # 20 graphs
    per_alpha_fa = {a: [] for a in ALPHAS}
    per_alpha_abstain = {a: [] for a in ALPHAS}
    aucs = []
    wrong_counts = []
    for sd in seeds:
        s, y = _probe(sd, use_spread=False)            # epistemic-only for the averaged run (fast)
        # split each graph 50/50 into calibration / holdout
        rng = np.random.default_rng(sd)
        idx = rng.permutation(s.size)
        half = s.size // 2
        cal, ho = idx[:half], idx[half:]
        aucs.append(C.empirical_auc(s, y))
        wrong_counts.append(int((y == 0).sum()))
        for a in ALPHAS:
            q = C.calibrate(s[cal], y[cal], a)
            rep = C.evaluate(s[ho], y[ho], q, a)
            per_alpha_fa[a].append(rep.false_accept_given_wrong)
            per_alpha_abstain[a].append(rep.abstain_rate)

    mean_auc = float(np.mean(aucs))
    print(f"\n[gate d] REAL EpistemicGraph signal, {len(list(seeds))} graphs, "
          f"mean candidate-pool AUC = {mean_auc:.4f}, mean #wrong/graph = "
          f"{np.mean(wrong_counts):.0f}")
    print("  alpha | mean P(accept|wrong) [target<=a] | mean abstain-rate (price)")
    for a in ALPHAS:
        mfa = float(np.mean(per_alpha_fa[a]))
        mab = float(np.mean(per_alpha_abstain[a]))
        print(f"  {a:0.2f}  |         {mfa:0.4f}              |        {mab:0.4f}")
        # small per-graph wrong counts -> honest finite-sample slack on the mean
        assert mfa <= a + 0.03, f"real-signal alpha={a}: {mfa:.4f} > {a}+slack"
    # it is a genuinely WEAK signal (that is the point): AUC well below 1, above chance-ish
    assert 0.5 <= mean_auc <= 0.95
    print(capsys.readouterr().out)


def test_gate_d_randomized_tiebreak_restores_clean_coverage(capsys):
    """The discrete recognition-ladder confidence has heavy TIES; a deterministic threshold
    on a tie cluster over-accepts. Randomized tie-breaking (smoothed conformal, Vovk)
    restores clean coverage on the epistemic-ONLY signal -- mean P(accept|wrong) <= alpha."""
    seeds = range(4000, 4020)
    fa = {a: [] for a in ALPHAS}
    for sd in seeds:
        s, y = _probe(sd, use_spread=False, jitter=True)
        rng = np.random.default_rng(sd)
        idx = rng.permutation(s.size)
        half = s.size // 2
        cal, ho = idx[:half], idx[half:]
        for a in ALPHAS:
            q = C.calibrate(s[cal], y[cal], a)
            fa[a].append(C.evaluate(s[ho], y[ho], q, a).false_accept_given_wrong)
    print("\n[gate d/jitter] epistemic-only + randomized tie-break")
    print("  alpha | mean P(accept|wrong)")
    for a in ALPHAS:
        m = float(np.mean(fa[a]))
        print(f"  {a:0.2f}  |      {m:0.4f}")
        assert m <= a + 0.015, f"jittered alpha={a}: {m:.4f}"
    print(capsys.readouterr().out)


def test_gate_d_full_signal_single_draw_table(capsys):
    """One graph, FULL signal (epistemic rung + confidence + spread mass/paths), printed."""
    s, y = _probe(seed=777, use_spread=True)
    auc = C.empirical_auc(s, y)
    rng = np.random.default_rng(777)
    idx = rng.permutation(s.size)
    half = s.size // 2
    cal, ho = idx[:half], idx[half:]
    print(f"\n[gate d/full] one real graph, full signal; candidates={s.size}, "
          f"wrong={(y==0).sum()}, AUC={auc:.4f}")
    print("  alpha | held-out P(accept|wrong) | held-out abstain-rate | err-among-accepted")
    for a in ALPHAS:
        q = C.calibrate(s[cal], y[cal], a)
        rep = C.evaluate(s[ho], y[ho], q, a)
        print(f"  {a:0.2f}  |         {rep.false_accept_given_wrong:0.4f}          "
              f"|        {rep.abstain_rate:0.4f}        |      {rep.error_among_accepted:0.4f}")
    assert s.size > 100 and (y == 0).sum() > 20        # a real, non-trivial pool
    print(capsys.readouterr().out)
