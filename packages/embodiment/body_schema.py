# -*- coding: utf-8 -*-
"""Body schema (M1) — a forward model of the agent's OWN body, learned from motor babbling.

Track E, M1: "sensorimotor babbling -> self-body predictor (body schema); gate = fingertip
prediction-error convergence vs a pre-declared baseline, AND generalization to unseen postures."

This is the honest first rung of physical grounding, and it fits every doctrine: No-LLM (a small
learned forward map, no pretrained anything), grounded (real MuJoCo contact dynamics, not a
simulation of a simulation), and STRUCTURE over memorization — the gate is precisely that the model
GENERALIZES to postures it never trained on. A body schema that only fit the postures it saw would
be a lookup table, not a model of a body; the held-out test is what tells the two apart.

The model predicts the CHANGE in fingertip position from (joint state, joint velocity, action).
Fingertip position is a nonlinear function of joint angles (forward kinematics = sines and cosines),
so the feature map lifts the joints into sin/cos before a ridge-regularized linear read-out — the
nonlinearity lives in the fixed, interpretable feature map, the learning is the linear part. No
gradient descent, no black box: closed-form ridge, so the whole thing is inspectable.
"""
from __future__ import annotations

import numpy as np


def _features(joints: np.ndarray, joint_vel: np.ndarray, action: np.ndarray) -> np.ndarray:
    """Lift raw joint state into a kinematics-friendly feature vector. Fingertip motion is driven by
    the sines/cosines of joint angles (forward kinematics) times the commanded/actual motion, so the
    map is [1, sin(j), cos(j), vel, action, sin(j)*action, cos(j)*action] — the cross terms let a
    torque's effect on the tip depend on the arm's current pose, which is the whole point of a body
    schema (the same push moves the hand differently depending on how the arm is folded)."""
    j = np.asarray(joints, float).ravel()
    v = np.asarray(joint_vel, float).ravel()
    a = np.asarray(action, float).ravel()
    sj, cj = np.sin(j), np.cos(j)
    # tip_delta ~= Jacobian(joints) @ (joint motion). The Jacobian is sines/cosines of the angles,
    # and the DOMINANT joint motion over one step is the current joint VELOCITY (the arm keeps
    # moving), with the action a smaller correction. So the load-bearing features are pose x VELOCITY
    # (measured: omitting these left the model at 0.96x baseline — it could not see the main signal),
    # with pose x action for the commanded correction.
    cross_sv, cross_cv = np.outer(sj, v).ravel(), np.outer(cj, v).ravel()
    cross_sa, cross_ca = np.outer(sj, a).ravel(), np.outer(cj, a).ravel()
    return np.concatenate([[1.0], sj, cj, v, a, cross_sv, cross_cv, cross_sa, cross_ca])


class BodySchema:
    """Forward model: (joints, joint_vel, action) -> predicted next-fingertip DELTA. Closed-form
    ridge regression over the kinematic feature map — fit on babbling data, then frozen for the
    held-out generalization test."""

    def __init__(self, ridge: float = 1e-3):
        self.ridge = ridge
        self.W: np.ndarray | None = None          # (out_dim, feat_dim)
        self._feat_dim: int | None = None

    def fit(self, X_raw: list[tuple], Y_delta: np.ndarray) -> "BodySchema":
        """X_raw: list of (joints, joint_vel, action); Y_delta: (N, tip_dim) next-tip minus tip."""
        Phi = np.stack([_features(*x) for x in X_raw])       # (N, F)
        Y = np.asarray(Y_delta, float)
        F = Phi.shape[1]
        A = Phi.T @ Phi + self.ridge * np.eye(F)
        self.W = np.linalg.solve(A, Phi.T @ Y).T             # (tip_dim, F)
        self._feat_dim = F
        return self

    def predict_delta(self, joints, joint_vel, action) -> np.ndarray:
        if self.W is None:
            raise RuntimeError("BodySchema is not fitted")
        return self.W @ _features(joints, joint_vel, action)

    def error(self, X_raw: list[tuple], Y_delta: np.ndarray) -> float:
        """Mean L2 prediction error over a set — the metric the gate reads."""
        preds = np.stack([self.predict_delta(*x) for x in X_raw])
        return float(np.mean(np.linalg.norm(preds - np.asarray(Y_delta, float), axis=1)))


def naive_baseline_error(Y_delta: np.ndarray) -> float:
    """The pre-declared baseline a real body schema must beat: 'the hand does not move' (predict a
    zero delta). Its error is the mean magnitude of actual motion — any model worth the name
    predicts motion better than assuming stillness."""
    Y = np.asarray(Y_delta, float)
    return float(np.mean(np.linalg.norm(Y, axis=1)))


# ---------------------------------------------------------------- joint-space schema + kinematics

class ForwardKinematics:
    """Where the fingertip is, given the joint angles — LEARNED from the body's own observations,
    not hard-coded link lengths. For a planar arm the tip is linear in [cos t1, sin t1, cos(t1+t2),
    sin(t1+t2), ...], so a closed-form fit recovers the arm's geometry from experience. This is the
    kinematic half of the body schema: the agent learns the SHAPE of its own body."""

    def __init__(self, ridge: float = 1e-6):
        self.ridge = ridge
        self.W: np.ndarray | None = None

    def _phi(self, joints: np.ndarray) -> np.ndarray:
        j = np.asarray(joints, float).ravel()
        cum = np.cumsum(j)                          # t1, t1+t2, ... — link orientations in the plane
        return np.concatenate([[1.0], np.cos(cum), np.sin(cum), np.cos(j), np.sin(j)])

    def fit(self, joints_list: list[np.ndarray], tips: np.ndarray) -> "ForwardKinematics":
        Phi = np.stack([self._phi(j) for j in joints_list])
        A = Phi.T @ Phi + self.ridge * np.eye(Phi.shape[1])
        self.W = np.linalg.solve(A, Phi.T @ np.asarray(tips, float)).T
        return self

    def tip(self, joints: np.ndarray) -> np.ndarray:
        return self.W @ self._phi(joints)


class JointForwardModel:
    """Predict the NEXT joint state from (joints, joint_vel, action). Joint dynamics are smooth and
    nearly second-order (next ~= joints + dt*vel + small torque effect), so this is the LEARNABLE
    core of the body schema — far more predictable than the fingertip's Jacobian-warped motion.
    Closed-form ridge over a compact feature map."""

    def __init__(self, ridge: float = 1e-4):
        self.ridge = ridge
        self.W: np.ndarray | None = None

    def _phi(self, joints, joint_vel, action) -> np.ndarray:
        j = np.asarray(joints, float).ravel()
        v = np.asarray(joint_vel, float).ravel()
        a = np.asarray(action, float).ravel()
        return np.concatenate([[1.0], j, v, a, np.sin(j), np.cos(j)])

    def fit(self, X_raw: list[tuple], next_joints: np.ndarray) -> "JointForwardModel":
        Phi = np.stack([self._phi(*x) for x in X_raw])
        A = Phi.T @ Phi + self.ridge * np.eye(Phi.shape[1])
        self.W = np.linalg.solve(A, Phi.T @ np.asarray(next_joints, float)).T
        return self

    def predict(self, joints, joint_vel, action) -> np.ndarray:
        return self.W @ self._phi(joints, joint_vel, action)
