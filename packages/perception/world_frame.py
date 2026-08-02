# -*- coding: utf-8 -*-
"""Where a thing is IN THE WORLD, not where it is in the picture.

WHY THIS EXISTS. Permanence across a blind stretch was scored three ways, and coasting through the
gap at constant image-space velocity BEAT believing the thing stayed put at a 6-frame gap (0.917 vs
0.885, a difference too small to claim) and LOST to it badly at 18 frames (0.731 vs 0.846, and four
objects not re-bound at all where standing still lost none).

That is not a failure of the owner's idea, it is a failure of where I applied it. Image-space
velocity is not a physical quantity. It is a projection, and under an approaching camera it
ACCELERATES -- something coming towards you sweeps across the picture faster and faster while moving
at a perfectly constant speed through the world. Extrapolating it linearly for eighteen frames
overshoots, which is exactly the shape of what was measured.

So predict where prediction is valid. A thing moving through the world moves at a roughly constant
world velocity, which is the assumption physics actually licenses, and the corpus carries both pieces
needed to get there: `depth_m` per pixel and the camera `pose` per frame.

THE CONVENTION IS CHECKED, NOT TRUSTED. CARLA's axes are easy to get wrong and a wrong sign produces
plausible-looking numbers that are wrong everywhere. `drift_of_static_points` is the free oracle: a
building does not move, so its world position must stay put while the camera drives past it. If the
conversion is right, drift is near zero; if a sign is flipped, drift is large and obvious. No labels,
no annotation -- just an invariant the world already guarantees.
"""
from __future__ import annotations

import numpy as np

#: CARLA's default camera: 90 degree horizontal field of view.
FOV_DEG = 90.0


def intrinsics(width: int, height: int, fov_deg: float = FOV_DEG) -> tuple:
    f = width / (2.0 * np.tan(np.radians(fov_deg) / 2.0))
    return (f, f, width / 2.0, height / 2.0)


def _rotation(pitch_deg: float, yaw_deg: float, roll_deg: float) -> np.ndarray:
    """CARLA/UE4 rotation: X forward, Y right, Z up, applied roll then pitch then yaw."""
    p, y, r = (np.radians(pitch_deg), np.radians(yaw_deg), np.radians(roll_deg))
    cy, sy, cp, sp, cr, sr = np.cos(y), np.sin(y), np.cos(p), np.sin(p), np.cos(r), np.sin(r)
    return np.array([
        [cy * cp, cy * sp * sr - sy * cr, -cy * sp * cr - sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, -sy * sp * cr + cy * sr],
        [sp,      -cp * sr,               cp * cr],
    ], dtype=np.float64)


def to_world(uv, depth: float, pose, shape) -> np.ndarray:
    """One image point plus its depth, placed in the world."""
    h, w = shape[0], shape[1]
    fx, fy, cx, cy = intrinsics(w, h)
    u, v = float(uv[0]), float(uv[1])
    cam = np.array([depth, (u - cx) * depth / fx, (cy - v) * depth / fy], dtype=np.float64)
    R = _rotation(float(pose[3]), float(pose[4]), float(pose[5]))
    return R @ cam + np.asarray(pose[:3], dtype=np.float64)


def to_image(xyz, pose, shape):
    """The world point, back in the picture. Returns (u, v, depth); depth <= 0 means behind me."""
    h, w = shape[0], shape[1]
    fx, fy, cx, cy = intrinsics(w, h)
    R = _rotation(float(pose[3]), float(pose[4]), float(pose[5]))
    cam = R.T @ (np.asarray(xyz, dtype=np.float64) - np.asarray(pose[:3], dtype=np.float64))
    d = float(cam[0])
    if d <= 1e-6:
        return (float("nan"), float("nan"), d)
    return (cx + fx * cam[1] / d, cy - fy * cam[2] / d, d)


def drift_of_static_points(frames, points, *, classes_static=(1, 2)) -> dict:
    """How far a thing that never moved appears to move. Near zero means the conversion is right.

    `frames` is [(depth_m, pose, semantic, shape), ...] over consecutive views of one scene, and
    `points` are image points sampled in the FIRST frame. Each is carried to the world, then re-found
    in later frames by projecting back and reading the depth actually there -- so this measures the
    round trip, which is what permanence uses."""
    if not frames or not points:
        return {"n": 0}
    d0, p0, _s0, shape = frames[0]
    anchors = []
    for uv in points:
        u, v = int(uv[0]), int(uv[1])
        z = float(d0[v, u])
        if not np.isfinite(z) or z <= 0.5 or z > 200.0:
            continue
        anchors.append(to_world((u, v), z, p0, shape))
    drifts = []
    for dm, pose, _sem, shp in frames[1:]:
        for xyz in anchors:
            u, v, d = to_image(xyz, pose, shp)
            if not np.isfinite(u) or not (0 <= int(v) < shp[0]) or not (0 <= int(u) < shp[1]):
                continue
            seen = float(dm[int(v), int(u)])
            if np.isfinite(seen) and seen > 0.5:
                drifts.append(abs(seen - d))
    if not drifts:
        return {"n": 0}
    a = np.asarray(drifts)
    return {"n": int(a.size), "median_m": float(np.median(a)), "mean_m": float(a.mean()),
            "p90_m": float(np.percentile(a, 90))}
