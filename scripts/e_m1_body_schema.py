# -*- coding: utf-8 -*-
"""Track E M1 gate — the body schema, learned by babbling, judged by GENERALIZATION.

M0 proved the body can be driven to a goal (SAC Reacher, -3.69). M1 is the deeper claim: the agent
learns a MODEL of its own body from self-generated motion, and — the gate that separates a model
from a lookup table — that model predicts postures it never trained on.

The clearest, lowest-noise form of a body schema is proprioceptive-to-spatial: WHERE IS MY HAND
when my joints are at these angles? That is forward kinematics, and it is exactly "knowing your own
body." It is deterministic (no dynamics noise), so the memorization-vs-model question is put
sharply: fit the map on postures from one region, test it on a posture region NEVER seen. A lookup
table fails the reserved region; a real body schema — which has learned the arm's geometry — nails
it. (A dynamics forward-model is also fitted and reported as a secondary readout; the primary gate
is the kinematic generalization, because it is the honest, noise-free test of the claim.)

Protocol (thresholds pre-declared, never tuned to the result):
  1. BABBLE gentle random torques in the real MuJoCo Reacher; collect (joint angles -> fingertip)
     from self-motion, no reward.
  2. POSTURE SPLIT: reserve a band of shoulder angles the model NEVER trains on.
  3. LEARN the forward kinematics on the train region only.
  4. JUDGE:
       (a) LEARNED — train tip-error is far below the 'predict the average hand position' baseline
           (<= BEAT * baseline: it learned the mapping, not the mean);
       (b) GENERALIZES — held-out tip-error is close to train error (<= GEN * train): the geometry
           transfers to unseen postures, so it is a body model, not a memorized table.

Writes data/embodiment/m1_body_schema_result.json. Deterministic seed; every number reported.

  python scripts/e_m1_body_schema.py [babble_steps]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.embodiment.body_schema import (ForwardKinematics, JointForwardModel,
                                             naive_baseline_error)

OUT = REPO / "data" / "embodiment" / "m1_body_schema_result.json"

# pre-declared gate thresholds — fixed BEFORE the run, never tuned to the outcome
BEAT = 0.25     # train tip-error must be <= 25% of the 'predict the mean hand position' baseline
GEN = 1.8       # held-out error must be <= 1.8x train error (generalizes, does not memorize)
HELDOUT_BAND = (1.2, 2.6)   # starting shoulder angle (rad) reserved for the generalization test


def _reacher_state(obs: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Decode the real MuJoCo Reacher-v5 observation into (joint angles, joint velocities,
    fingertip position). obs = [cos(t1),cos(t2), sin(t1),sin(t2), tgt_x,tgt_y, t1_dot,t2_dot,
    tip_x-tgt_x, tip_y-tgt_y]. Fingertip = target + (tip-target vector)."""
    c1, c2, s1, s2 = obs[0], obs[1], obs[2], obs[3]
    joints = np.array([np.arctan2(s1, c1), np.arctan2(s2, c2)])
    jvel = obs[6:8].copy()
    tip = obs[4:6] + obs[8:10]
    return joints, jvel, tip


def _collect(steps: int, seed: int) -> dict:
    """Babble the REAL 2-DOF planar arm (gym Reacher-v5, the M0 body). Record, per transition, the
    input (joints, joint_vel, action), the NEXT joint angles, the current+next fingertip, and the
    starting shoulder angle for the posture split. Random gentle torques, no reward."""
    import gymnasium as gym
    env = gym.make("Reacher-v5")
    rng = np.random.default_rng(seed)
    obs, _ = env.reset(seed=seed)
    X, next_j, tip_now, tip_next, j0 = [], [], [], [], []
    for _ in range(steps):
        joints, jvel, tip = _reacher_state(np.asarray(obs, float))
        action = rng.normal(0, 0.30, env.action_space.shape[0])   # gentle motor babble (learnable)
        obs, _, term, trunc, _ = env.step(action)
        joints2, _, tip2 = _reacher_state(np.asarray(obs, float))
        X.append((joints, jvel, action)); next_j.append(joints2)
        tip_now.append(tip); tip_next.append(tip2); j0.append(float(joints[0]))
        if term or trunc:
            obs, _ = env.reset()
    env.close()
    return {"X": X, "next_j": np.stack(next_j), "tip_now": np.stack(tip_now),
            "tip_next": np.stack(tip_next), "j0": j0,
            "all_joints": [x[0] for x in X]}


def _fk_error(fk, idx, joints_all, tips) -> float:
    """Mean fingertip prediction error of the forward kinematics over a subset of postures."""
    return float(np.mean([np.linalg.norm(fk.tip(joints_all[i]) - tips[i]) for i in idx]))


def main() -> int:
    steps = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
    t0 = time.time()
    data = _collect(steps, seed=0)
    joints_all, tips = data["all_joints"], data["tip_now"]
    j0 = data["j0"]

    # posture split: reserve a band of shoulder angles the model never trains on
    lo, hi = HELDOUT_BAND
    held = [i for i, a in enumerate(j0) if lo <= ((a + np.pi) % (2 * np.pi) - np.pi) <= hi]
    train = [i for i in range(len(joints_all)) if i not in set(held)]
    if len(held) < 50 or len(train) < 200:
        print(f"insufficient split (train {len(train)}, held {len(held)}) — need more babble")
        return 1

    # PRIMARY gate: forward kinematics (the body's shape) learned on the TRAIN posture region only
    fk = ForwardKinematics().fit([joints_all[i] for i in train], tips[train])
    mean_tip = tips.mean(axis=0)
    baseline = float(np.mean([np.linalg.norm(tips[i] - mean_tip) for i in range(len(tips))]))
    train_err = _fk_error(fk, train, joints_all, tips)
    heldout_err = _fk_error(fk, held, joints_all, tips)

    learned_ok = train_err <= BEAT * baseline
    gen_ratio = heldout_err / max(train_err, 1e-9)
    generalize_ok = heldout_err <= GEN * train_err
    passed = learned_ok and generalize_ok

    # SECONDARY readout (not gated): the joint-DYNAMICS forward model, one-step
    jmodel = JointForwardModel().fit([data["X"][i] for i in train], data["next_j"][train])
    dyn_err = float(np.mean([np.linalg.norm(jmodel.predict(*data["X"][i]) - data["next_j"][i])
                             for i in held]))

    report = {
        "milestone": "M1_body_schema", "babble_steps": steps,
        "primary_gate": "forward-kinematics generalization to unseen postures",
        "n_train": len(train), "n_heldout": len(held), "heldout_band_rad": list(HELDOUT_BAND),
        "baseline_error_predict_mean_tip": round(baseline, 5),
        "train_error": round(train_err, 5), "heldout_error": round(heldout_err, 5),
        "learned_ratio_vs_baseline": round(train_err / max(baseline, 1e-9), 4),
        "generalization_ratio_heldout_over_train": round(gen_ratio, 4),
        "secondary_joint_dynamics_heldout_error": round(dyn_err, 5),
        "gate": {"BEAT": BEAT, "GEN": GEN},
        "learned_ok": learned_ok, "generalize_ok": generalize_ok,
        "verdict": "M1 PASS" if passed else "M1 FAIL", "wall_s": round(time.time() - t0, 1),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"baseline(predict-mean-tip) {baseline:.4f}  train {train_err:.4f} "
          f"({report['learned_ratio_vs_baseline']:.2f}x baseline)  "
          f"heldout {heldout_err:.4f} ({gen_ratio:.2f}x train)")
    print(f"learned {'OK' if learned_ok else 'FAIL'} (<= {BEAT} baseline)  "
          f"generalization {'OK' if generalize_ok else 'FAIL'} (<= {GEN}x train)")
    print(f"{report['verdict']} -> {OUT.relative_to(REPO)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
