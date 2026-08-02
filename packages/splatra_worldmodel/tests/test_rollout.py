# -*- coding: utf-8 -*-
"""Multi-step ROLLOUT tests: does the validated one-step proposer actually SIMULATE?

Cheap unit tests exercise the rollout primitives (true-dynamics reproduction, frozen
persistence, physics projection, intrinsic divergence, codec variants) with no training. A
handful of integrated tests share ONE small cached scorecard and assert the honest invariants
of the rung: the linear map DIVERGES under rollout while JEPA stays BOUNDED, JEPA beats
persistence at short horizon, the breakdown is model-limited (not the dynamics' chaos),
physics-truth-in-the-loop keeps every rolled step physical, and a usable horizon is reported.

We do NOT hard-assert a specific stable-horizon number (that is the honest empirical output);
we assert the qualitative simulator invariants that must hold for the verdict to be valid."""
from __future__ import annotations

import numpy as np

from packages.splatra_worldmodel.baselines import PersistenceBaseline
from packages.splatra_worldmodel.contact_dynamics import (
    ContactDynamicsParams,
    simulate_contact_episode,
)
from packages.splatra_worldmodel.physics_truth import PhysicsTruthGate
from packages.splatra_worldmodel.rollout import (
    TrueDynamics,
    default_encode,
    intrinsic_divergence,
    project_to_physical,
    raw_velocity_encode,
    rollout_closed_loop,
)
from packages.splatra_worldmodel.rollout_proof import (
    RolloutProofConfig,
    RolloutScorecard,
    format_rollout_scorecard,
    run_rollout_proof,
)
from packages.splatra_worldmodel.turbovec_field import FieldState, TurbovecFieldCodec


# ============================ cheap primitives (no training) =============================
def _short_episode(seed=5000, steps=30):
    off = np.random.default_rng(seed)
    return simulate_contact_episode(ContactDynamicsParams.elastic(), steps, seed=seed,
                                    init_offset=off.uniform(-0.4, 0.4, 3),
                                    init_vel=off.uniform(-0.1, 0.1, 3))


def test_true_dynamics_reproduces_episode_exactly():
    # The chaos measurement rests on this: the true simulator, re-run from a recorded state_0
    # with the same actions and seed, reproduces the episode bit-for-bit (elastic noise=0).
    ep = _short_episode(seed=5000, steps=30)
    truth = TrueDynamics(ContactDynamicsParams.elastic(), seed=5000)
    repro = truth.rollout(ep.states[0].pos, ep.states[0].vel, ep.actions)
    for t in range(len(ep.states)):
        assert np.allclose(repro[t].pos, ep.states[t].pos, atol=1e-9)


def test_persistence_rollout_stays_frozen():
    # A persistence closed-loop rollout predicts no motion -> it must stay at state_0 forever,
    # so its rollout error at horizon H equals the true trajectory's travel from its start.
    ep = _short_episode(seed=5001, steps=20)
    codec = TurbovecFieldCodec.fit(ep.states)
    per = PersistenceBaseline()
    traj = rollout_closed_loop(per.predict_next_positions, default_encode(codec),
                               ep.states[0], ep.actions, dt=ContactDynamicsParams.elastic().dt)
    for st in traj:
        assert np.allclose(st.pos, ep.states[0].pos)


def test_project_to_physical_enforces_ground_and_passes_gate():
    gate = PhysicsTruthGate()
    ep = _short_episode(seed=5002, steps=6)
    prev = ep.states[1].pos
    bad = prev.copy()
    bad[:, 1] = gate.ground_plane - 0.5          # drive every particle far below the floor
    fixed = project_to_physical(gate, prev, np.zeros(3), bad)
    assert fixed[:, 1].min() >= gate.ground_plane - 1e-9
    cand = FieldState(fixed, np.zeros_like(fixed))
    assert gate.verify(FieldState(prev, np.zeros_like(prev)), np.zeros(3), cand).ok


def test_project_to_physical_caps_teleport():
    gate = PhysicsTruthGate()
    ep = _short_episode(seed=5003, steps=6)
    prev = ep.states[1].pos
    bad = prev.copy()
    bad[:, 0] += 5.0                              # a 5-unit jump -> teleport violation
    fixed = project_to_physical(gate, prev, np.zeros(3), bad)
    disp = np.linalg.norm(fixed - prev, axis=1)
    assert float(disp.max()) <= gate.max_disp + 1e-6


def test_intrinsic_divergence_is_bounded_and_grows():
    # The dynamics' OWN divergence under a tiny IC perturbation: finite, bounded well below the
    # body scale (the settled body is a small attractor), and larger at long horizon than short.
    p = ContactDynamicsParams.elastic()
    eps = [_short_episode(seed=5000 + j, steps=30) for j in range(2)]
    ics = [(e.states[0], e.actions, 5000 + j) for j, e in enumerate(eps)]
    chaos = intrinsic_divergence(p, ics, horizons=(1, 5, 10, 25), eps=1e-4, n_dirs=2, seed=0)
    vals = [chaos.divergence[h] for h in (1, 5, 10, 25)]
    assert all(np.isfinite(v) and v >= 0 for v in vals)
    diameter = np.linalg.norm(eps[0].states[0].pos - eps[0].states[0].pos.mean(0), axis=1).max() * 2
    assert chaos.saturation < diameter           # intrinsic chaos does not reach body scale
    assert chaos.divergence[25] > chaos.divergence[1]   # sensitive dependence (it grows)


def test_raw_velocity_encode_matches_dim_but_changes_values():
    ep = _short_episode(seed=5004, steps=8)
    codec = TurbovecFieldCodec.fit(ep.states)
    enc_d, enc_r = default_encode(codec), raw_velocity_encode(codec)
    ld, lr = enc_d(ep.states[3]), enc_r(ep.states[3])
    assert ld.shape == lr.shape                  # same light-vector dim (only fidelity changes)
    # velocity channels (indices 3,4,5 per particle) differ where 8-bit quantization bit
    v = ep.states[3].vel
    if float(np.abs(v).max()) > 1e-6:
        assert not np.allclose(ld, lr)


# ============================ integrated proof (one cached run) ==========================
_CACHE: dict[str, RolloutScorecard] = {}


def _config() -> RolloutProofConfig:
    c = RolloutProofConfig.fast()
    c.rollout_steps = 40         # cover horizons 1..25 with real (non-nan) data
    c.chaos_ic = 2
    return c


def _scard() -> RolloutScorecard:
    if "s" not in _CACHE:
        _CACHE["s"] = run_rollout_proof(_config())
    return _CACHE["s"]


def test_neuro_budget_under_25m():
    s = _scard()
    assert s.param_counts["trainable_total"] < 25_000_000
    assert s.param_counts["total_incl_ema"] < 25_000_000


def test_linear_diverges_while_jepa_stays_bounded():
    # THE simulator invariant: the global linear forward-map compounds error and DIVERGES
    # under rollout (rises above persistence, i.e. worse than doing nothing), while JEPA stays
    # bounded well below it. This is exactly what one-step validation could not show.
    s = _scard()
    assert s.linear.at(25) > 1.2 * s.persistence.at(25)   # linear diverges past 'do nothing'
    assert s.jepa.at(25) < 0.6 * s.linear.at(25)          # JEPA is bounded far below linear
    assert s.jepa.at(25) < s.persistence.at(25)           # JEPA still beats doing nothing


def test_jepa_beats_persistence_at_short_horizon():
    s = _scard()
    assert s.jepa.at(5) < 0.8 * s.persistence.at(5)


def test_rollout_breakdown_is_model_limited_not_chaos():
    # Honest separation: the intrinsic chaos divergence is tiny; JEPA's rollout error is orders
    # of magnitude larger at the same horizon -> the wall is the MODEL, not the dynamics' chaos.
    s = _scard()
    assert s.jepa.at(10) > 100.0 * s.chaos.divergence[10]


def test_physics_truth_in_the_loop_stays_valid():
    # The membrane as a rollout stabilizer: every gated rolled-out step passes the physics gate.
    s = _scard()
    assert s.jepa_gated is not None
    assert s.jepa_gated_violation_free is True


def test_velocity_codec_sweep_runs_and_is_same_ballpark():
    # Higher velocity fidelity (raw, unquantized) is measured; it is not a silver bullet -- it
    # stays in the same order of magnitude as the 8-bit codec (codec is not THE bottleneck).
    s = _scard()
    assert s.jepa_rawvel is not None
    for h in s.horizons:
        d, r = s.jepa.at(h), s.jepa_rawvel.at(h)
        if np.isfinite(d) and np.isfinite(r) and d > 1e-6:
            assert 0.25 < r / d < 4.0


def test_usable_horizon_and_verdict_reported():
    s = _scard()
    assert int(s.usable["beats_persistence_through"]) >= 10
    assert isinstance(s.verdict, str) and "usable horizon" in s.verdict


def test_scorecard_formats():
    s = _scard()
    text = format_rollout_scorecard(s)
    assert "ROLLOUT ERROR vs HORIZON" in text
    assert "CHAOS CEILING" in text
    assert "PHYSICS-TRUTH IN THE LOOP" in text
    assert "VERDICT" in text
