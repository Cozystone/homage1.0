# -*- coding: utf-8 -*-
"""Track E rigorous-physics lane — a MuJoCo articulated body (the Isaac-fidelity organ, no RTX).

Isaac Sim's renderer crashes on Blackwell; MuJoCo (DeepMind, Apache-2.0) gives the same rigorous
rigid-body / contact / articulation physics with NO RTX dependency (verified: a box drops and rests
on the floor via contact dynamics, CPU, no crash). This module runs the SAME developmental-self loop
as splatra_body.py but on a REAL articulated arm with REAL contact — so affordance (M2s) and
self/other (M3s) become physically true, not PBD-approximate.

Cognition stays ours (No-LLM): proprioception -> sensory cortex Percepts; contact with an object is a
grounded sensorimotor affordance candidate; the forward model is learned online. The Unitree G1 body
drops into the SAME code via MuJoCo Menagerie (unitree_g1, Apache-2.0) by swapping the MJCF — this arm
is the self-contained gate. mujoco is import-guarded so the package loads even where it isn't installed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

try:
    import mujoco as _mj
    HAVE_MUJOCO = True
except Exception:
    _mj = None
    HAVE_MUJOCO = False

# a 3-DoF arm that can reach a graspable box on the floor — real joints, real contact
_ARM_XML = """
<mujoco>
  <compiler angle="radian"/>
  <option gravity="0 0 -9.81" timestep="0.005"/>
  <default><joint limited="true" range="-1.4 1.4" damping="0.4"/></default>
  <worldbody>
    <geom name="floor" type="plane" size="5 5 0.1"/>
    <body name="base" pos="0 0 0.5">
      <joint name="j0" type="hinge" axis="0 0 1"/>
      <geom type="capsule" fromto="0 0 0 0.3 0 0" size="0.04"/>
      <body name="link1" pos="0.3 0 0">
        <joint name="j1" type="hinge" axis="0 1 0"/>
        <geom type="capsule" fromto="0 0 0 0.3 0 0" size="0.035"/>
        <body name="tip" pos="0.3 0 0">
          <joint name="j2" type="hinge" axis="0 1 0"/>
          <geom name="tipgeom" type="sphere" size="0.06"/>
          <site name="tipsite" pos="0 0 0"/>
        </body>
      </body>
    </body>
    <body name="target" pos="0.45 0 0.12">
      <freejoint/>
      <geom name="targetgeom" type="box" size="0.1 0.1 0.1" mass="0.3"/>
    </body>
  </worldbody>
  <actuator>
    <motor name="m0" joint="j0" ctrlrange="-1 1"/>
    <motor name="m1" joint="j1" ctrlrange="-1 1"/>
    <motor name="m2" joint="j2" ctrlrange="-1 1"/>
  </actuator>
</mujoco>
"""


@dataclass
class MjBodyState:
    joints: np.ndarray                 # arm joint angles (3,)
    joint_vel: np.ndarray              # arm joint velocities (3,)
    tip: np.ndarray                    # end-effector world position (3,)
    touching_object: bool              # rigorous MuJoCo contact between tip and the target

    def proprioception(self) -> np.ndarray:
        return np.concatenate([self.joints, self.joint_vel, self.tip])   # (9,)


class MujocoBody:
    """A rigorous-physics articulated body. Proprioception = joint state + tip; action = joint
    torques; contact = MuJoCo's own collision solver (not an approximation)."""

    def __init__(self, xml: str | None = None):
        if not HAVE_MUJOCO:
            raise RuntimeError("mujoco is not installed in this environment")
        self.model = _mj.MjModel.from_xml_string(xml or _ARM_XML)
        self.data = _mj.MjData(self.model)
        self._jadr = [self.model.joint(f"j{i}").qposadr[0] for i in range(3)]
        self._jvadr = [self.model.joint(f"j{i}").dofadr[0] for i in range(3)]
        self._tip_sid = self.model.site("tipsite").id
        self._tip_gid = self.model.geom("tipgeom").id
        self._tgt_gid = self.model.geom("targetgeom").id
        _mj.mj_forward(self.model, self.data)

    def _touching(self) -> bool:
        for i in range(self.data.ncon):
            c = self.data.contact[i]
            pair = {c.geom1, c.geom2}
            if self._tip_gid in pair and self._tgt_gid in pair:
                return True
        return False

    def snapshot(self) -> tuple[np.ndarray, np.ndarray]:
        return (self.data.qpos.copy(), self.data.qvel.copy())

    def restore(self, snap: tuple[np.ndarray, np.ndarray]) -> None:
        self.data.qpos[:], self.data.qvel[:] = snap[0], snap[1]
        self.data.qfrc_applied[:] = 0.0
        _mj.mj_forward(self.model, self.data)

    def state(self) -> MjBodyState:
        d = self.data
        j = np.array([d.qpos[a] for a in self._jadr])
        jv = np.array([d.qvel[a] for a in self._jvadr])
        tip = np.array(d.site_xpos[self._tip_sid])
        return MjBodyState(joints=j, joint_vel=jv, tip=tip.copy(), touching_object=self._touching())

    def step(self, action: np.ndarray, sub_steps: int = 4,
             external_torque: np.ndarray | None = None) -> MjBodyState:
        self.data.ctrl[:] = np.clip(np.asarray(action, dtype=np.float64).reshape(3), -1, 1)
        for _ in range(sub_steps):
            if external_torque is not None:                      # an unexpected shove — NOT an actuator
                for k, a in enumerate(self._jvadr):              # command, so it bypasses the ctrl clip
                    self.data.qfrc_applied[a] = float(np.asarray(external_torque).reshape(3)[k])
            _mj.mj_step(self.model, self.data)      # rigorous integration + contact solve
        self.data.qfrc_applied[:] = 0.0
        return self.state()


class JointSchema:
    """M1s forward model on joint state: predict next joint angles from (joints, action). Learned
    online (normalized LMS, No-LLM). Nonlinear dynamics mean it converges to a residual, not zero."""

    def __init__(self, lr: float = 0.3):
        self.W = np.zeros((3, 10))      # next_joints ~= [1, joints, joint_vel, action] @ W^T
        self.lr = lr

    def _feat(self, joints, joint_vel, action):
        # a 2nd-order system: next angle is dominated by joints + dt*vel; velocity is the key feature.
        return np.concatenate([[1.0], np.asarray(joints).reshape(3),
                               np.asarray(joint_vel).reshape(3), np.asarray(action).reshape(3)])

    def predict(self, joints, joint_vel, action) -> np.ndarray:
        return self.W @ self._feat(joints, joint_vel, action)

    def learn(self, joints, joint_vel, action, next_joints) -> float:
        x = self._feat(joints, joint_vel, action)
        pred = self.W @ x
        err = np.asarray(next_joints).reshape(3) - pred
        self.W = self.W + self.lr * np.outer(err, x) / (float(x @ x) + 1e-6)
        return float(np.linalg.norm(err))


@dataclass
class MjReport:
    steps: int
    baseline_error: float
    init_error: float
    perturbation_error: float
    surprise_ratio: float
    object_contacts: int
    affordances: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def run_mujoco_babbling(steps: int = 400, seed: int = 0, store: Any = None) -> MjReport:
    """The rigorous-physics M0s+M1s+M2s loop: joint babbling learns the body schema (error converges
    to a residual — real dynamics are nonlinear), contact with the object is grounded as an affordance
    (M2s), and an unexpected torque spike is surprising above the learned baseline (reaction)."""
    from packages.sensory_cortex import cortex as C

    body = MujocoBody()
    schema = JointSchema()
    rng = np.random.default_rng(seed)
    curve: list[float] = []
    contacts = 0
    percepts: list[Any] = []
    afford: set[str] = set()

    st = body.state()
    for t in range(steps):
        action = rng.normal(0, 0.15, 3)          # gentle babble -> small, learnable moves
        j, jv = st.joints.copy(), st.joint_vel.copy()
        st = body.step(action)
        curve.append(schema.learn(j, jv, action, st.joints))
        if st.touching_object:
            contacts += 1
            afford.add("can_push:target")
            percepts += C.from_touch([{"object": "target", "force": 1.0}])

    init = float(np.mean(curve[:20]))
    baseline = float(np.mean(curve[-30:]))
    # surprise: a torque the schema's action never accounted for (an external jolt on the joints)
    j, jv = st.joints.copy(), st.joint_vel.copy()
    action = rng.normal(0, 0.15, 3)
    pred = schema.predict(j, jv, action)
    st = body.step(action, external_torque=np.array([4.0, -4.0, 4.0]))   # unexpected external shove
    perturb = float(np.linalg.norm(st.joints - pred))
    ratio = perturb / max(baseline, 1e-6)

    grounded = 0
    if percepts:
        grounded = C.ground(C.integrate(percepts), store).get("stored", 0)

    return MjReport(steps=steps, baseline_error=baseline, init_error=init,
                    perturbation_error=perturb, surprise_ratio=ratio, object_contacts=contacts,
                    affordances=sorted(afford),
                    extra={"converged": baseline < init * 0.6, "grounded_percepts": grounded,
                           "physics": "mujoco-rigorous"})


def run_self_other_attribution(steps: int = 400, trials: int = 120, seed: int = 0) -> dict[str, Any]:
    """M3s self/other — the agency form of prepulse inhibition. A SELF-caused motion is PREDICTED by
    the body schema (low error -> 'self'); an EXTERNALLY-caused one (an uncommanded shove) is
    unpredicted (high error -> 'world'). The threshold is derived from the learned baseline, not tuned.
    Returns attribution accuracy — a measured self/other boundary, not an asserted one."""
    body = MujocoBody()
    schema = JointSchema()
    rng = np.random.default_rng(seed)
    st = body.state()
    curve = []
    for _ in range(steps):                                   # learn the body schema first
        a = rng.normal(0, 0.15, 3)
        j, jv = st.joints.copy(), st.joint_vel.copy()
        st = body.step(a)
        curve.append(schema.learn(j, jv, a, st.joints))
    baseline = float(np.mean(curve[-30:]))
    thresh = baseline * 4.0                                  # self if prediction holds within 4x noise

    # each trial is an INDEPENDENT probe from the SAME settled base state (snapshot/restore), so a
    # shove's after-effect can't contaminate the next self trial.
    for _ in range(30):
        st = body.step(np.zeros(3))                          # settle to rest
    base = body.snapshot()
    correct = 0
    for _ in range(trials):
        body.restore(base)
        s0 = body.state()
        is_self = bool(rng.integers(2))
        a = rng.normal(0, 0.15, 3)
        pred = schema.predict(s0.joints, s0.joint_vel, a)
        ext = None if is_self else rng.normal(0, 1, 3) * 4.0
        s1 = body.step(a, external_torque=ext)
        err = float(np.linalg.norm(s1.joints - pred))
        attributed_self = err < thresh
        correct += int(attributed_self == is_self)
    return {"trials": trials, "attribution_accuracy": round(correct / trials, 4),
            "baseline": round(baseline, 5), "threshold": round(thresh, 5),
            "note": "self=predicted (low error), world=unpredicted shove (high error) — agency PPI"}
