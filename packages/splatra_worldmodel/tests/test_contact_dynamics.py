# -*- coding: utf-8 -*-
"""The contact-rich / non-rigid / frictional regime: subclass, deterministic, gate-safe, and
-- the defining property -- GENUINELY NON-LINEAR (a global ridge linear map cannot fit it)."""
from __future__ import annotations

import numpy as np

from packages.embodiment.splatra_body import SplatraBody
from packages.splatra_worldmodel.contact_dynamics import (
    ContactDynamicsParams,
    ContactLatticeBody,
    contact_ground_y,
    simulate_contact_episode,
)


def _ridge_linear_heldout_vs_persistence(level: int, n_tr=8, n_ho=3, steps=16):
    """Fit a GLOBAL ridge linear forward-map delta ~ W[pos,vel,action,1] on train episodes,
    evaluate held-out per-particle L2, and return (linear_err, persistence_err). This is the
    honest witness of the regime's non-linearity: on the toy this ratio was ~0.13, here it is
    much larger (a global affine map leaves large irreducible error)."""
    p = ContactDynamicsParams.ladder(level)
    otr = np.random.default_rng(42)
    oho = np.random.default_rng(999)
    tr = [simulate_contact_episode(p, steps, 1000 + i, otr.uniform(-0.3, 0.3, 3),
                                   otr.uniform(-0.1, 0.1, 3)) for i in range(n_tr)]
    ho = [simulate_contact_episode(p, steps, 5000 + j, oho.uniform(-0.45, 0.45, 3),
                                   oho.uniform(-0.15, 0.15, 3)) for j in range(n_ho)]

    def ds(eps):
        X, Y, POS, POSN = [], [], [], []
        for ep in eps:
            for t in range(len(ep.actions)):
                X.append(np.concatenate([ep.states[t].pos.ravel(), ep.states[t].vel.ravel(),
                                         ep.actions[t], [1.0]]))
                Y.append((ep.states[t + 1].pos - ep.states[t].pos).ravel())
                POS.append(ep.states[t].pos); POSN.append(ep.states[t + 1].pos)
        return np.array(X), np.array(Y), np.array(POS), np.array(POSN)

    Xtr, Ytr, _, _ = ds(tr)
    Xho, _, POS, POSN = ds(ho)
    W = np.linalg.solve(Xtr.T @ Xtr + 1e-3 * np.eye(Xtr.shape[1]), Xtr.T @ Ytr)
    N = POS.shape[1]
    lin = float(np.mean([np.linalg.norm((Xho[i] @ W).reshape(N, 3) + POS[i] - POSN[i], axis=1).mean()
                         for i in range(len(POS))]))
    per = float(np.mean([np.linalg.norm(POS[i] - POSN[i], axis=1).mean() for i in range(len(POS))]))
    return lin, per


def test_is_a_subclass_not_an_edit():
    # We WRAP/subclass the proven kernel; we never edit embodiment/splatra_body.py.
    assert issubclass(ContactLatticeBody, SplatraBody)


def test_ground_plane_reused_from_splatra_body():
    from packages.embodiment.splatra_body import _GROUND_Y
    assert contact_ground_y() == float(_GROUND_Y)


def test_particle_count_matches_toy_light_dim():
    # Same particle count as the #74 toy (count=200 -> 196) so the light-vector dim is identical:
    # the comparison stays apples-to-apples (only the dynamics regime changes).
    ep = simulate_contact_episode(ContactDynamicsParams.elastic(), steps=4, seed=1)
    assert ep.states[0].n == 196


def test_determinism_noise_off():
    p = ContactDynamicsParams.elastic()  # noise=0.0 -> fully reproducible
    a = simulate_contact_episode(p, steps=12, seed=3, init_offset=np.zeros(3), init_vel=np.zeros(3))
    b = simulate_contact_episode(p, steps=12, seed=3, init_offset=np.zeros(3), init_vel=np.zeros(3))
    for sa, sb in zip(a.states, b.states):
        assert np.allclose(sa.pos, sb.pos)
        assert np.allclose(sa.vel, sb.vel)


def test_body_falls_and_contacts_ground():
    ep = simulate_contact_episode(ContactDynamicsParams.elastic(), steps=40, seed=7,
                                  init_offset=np.zeros(3), init_vel=np.zeros(3))
    top_start = ep.states[0].pos[:, 1].min()
    assert top_start > contact_ground_y() + 0.3      # starts above the floor
    assert any(ep.contacts), "expected contact frames (collisions or ground)"


def test_never_penetrates_ground():
    ep = simulate_contact_episode(ContactDynamicsParams.elastic(), steps=40, seed=11)
    for st in ep.states:
        assert st.pos[:, 1].min() >= contact_ground_y() - 1e-6


def test_is_contact_rich():
    # the whole point of this regime: pairwise/ground contact is active most of the time.
    ep = simulate_contact_episode(ContactDynamicsParams.elastic(), steps=40, seed=7,
                                  init_offset=np.zeros(3), init_vel=np.zeros(3))
    assert np.mean(ep.contacts) > 0.5


def test_motion_is_stable_and_bounded():
    # sub-stepped Euler stays finite and never teleports (per-step disp < the gate's bound).
    ep = simulate_contact_episode(ContactDynamicsParams.elastic(), steps=40, seed=7,
                                  init_offset=np.zeros(3), init_vel=np.zeros(3))
    P = np.array([s.pos for s in ep.states])
    assert np.isfinite(P).all()
    disp = np.linalg.norm(P[1:] - P[:-1], axis=2)
    assert float(disp.max()) < 1.5      # below PhysicsTruthGate.max_disp (no teleport)


def test_gate_passes_all_true_transitions():
    # observed contact dynamics is physical -> the physics-truth gate quarantines NOTHING true.
    from packages.splatra_worldmodel.physics_truth import PhysicsTruthGate
    from packages.splatra_worldmodel.turbovec_field import FieldState
    ep = simulate_contact_episode(ContactDynamicsParams.elastic(), steps=40, seed=7,
                                  init_offset=np.zeros(3), init_vel=np.zeros(3))
    gate = PhysicsTruthGate()
    for t in range(len(ep.actions)):
        prev = FieldState(ep.states[t].pos, np.zeros_like(ep.states[t].pos))
        cand = FieldState(ep.states[t + 1].pos, np.zeros_like(ep.states[t + 1].pos))
        assert gate.verify(prev, ep.actions[t], cand).ok, gate.verify(prev, ep.actions[t], cand).as_reason()


def test_dynamics_is_genuinely_nonlinear():
    # THE defining property of this rung: a GLOBAL linear forward-map cannot fit the elastic
    # regime -- it leaves large irreducible held-out error (unlike the near-linear toy, where a
    # linear map's held-out error was ~13% of persistence). Here it is a large fraction.
    lin, per = _ridge_linear_heldout_vs_persistence(level=3)
    assert lin / per > 0.25, (lin, per)   # measured ~0.39; toy was ~0.13


def test_complexity_ladder_orders_nonlinearity():
    # the ladder is monotone in "how badly a linear map fits": settle (L0) is near-linear,
    # elastic (L3) is strongly non-linear. This is the axis the crossover sweep walks.
    lin0, per0 = _ridge_linear_heldout_vs_persistence(level=0)
    lin3, per3 = _ridge_linear_heldout_vs_persistence(level=3)
    assert (lin0 / per0) < (lin3 / per3)
    assert (lin0 / per0) < 0.2      # L0 settle: a linear map fits it well (like the toy)
