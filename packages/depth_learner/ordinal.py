# -*- coding: utf-8 -*-
"""Learn what is in front of what, from motion, with nobody supplying the answer.

Owner, 2026-07-29: GT는 학습되게 하면 좋겠다. 스스로 깊이감이라는걸 깨우칠 수 있게. 그래서 컴퓨터
화면을 볼때도 한 브라우저가 다른 브라우저 뒤에 있다 이런식으로 응용도 되게.

Those two sentences are one requirement, and seeing why decides the whole design. A browser window
is not four metres away. There is no metre anywhere on a screen, and a depth sense that only speaks
in metres has nothing to say about a desktop — yet "that window is behind this one" is unmistakably a
depth judgement, and a person makes it instantly. What survives from a street to a screen is not
distance, it is ORDER: who is in front of whom.

So the quantity is ordinal, and that is not a weakening. Monocular vision cannot recover metres in
the first place — halving every distance and halving the motion looks identical — so a rank is the
honest form of what a single moving eye can know, and the same output answers both questions.

WHERE THE TRAINING SIGNAL COMES FROM, GIVEN THAT NOTHING IS LABELLED. Move, and near things sweep
further across the image than far things. That is parallax, it needs no simulator, and it is exactly
what a walking body has. Track corners between two frames and every pair of them becomes a labelled
comparison — the one that moved more is nearer — with the label derived from the world rather than
supplied by anyone. The supervised CARLA net needed a simulator willing to report depth; this needs
only that the body moved.

TWO CORRECTIONS WITHOUT WHICH THE LABELS ARE WRONG, and they are not refinements:

  ROTATION CARRIES NO DEPTH, SO TURNING FRAMES ARE SKIPPED RATHER THAN CORRECTED. A turning camera
  moves every pixel alike whatever its distance, so a pair labelled during a turn is labelled by
  noise. Subtracting the best-fit affine flow was the obvious repair and it made the labels WORSE
  than doing nothing -- 0.534 against 0.674, chance being 0.5 -- because the flow a TRANSLATING
  camera produces is itself largely affine when depth varies smoothly across the frame, as it does
  down a road. The subtraction removed the signal along with the contaminant. Measured against CARLA
  ground truth:

      no correction, all frames          0.674
      subtract the affine flow           0.534   <- barely above chance
      skip frames dominated by rotation  0.747   (median 0.801)

  So the mechanism is a frame-level abstention: when the flow is mostly a uniform shift, this pair
  of frames is not one from which depth can be read, and no labels are emitted at all. Which is what
  a visual system does anyway -- saccadic suppression discards vision during rapid eye movement for
  the same reason, that the input carries nothing usable rather than that it is unpleasant.

  COMPARE NEARBY POINTS ONLY. Under forward motion, flow also falls to zero at the focus of
  expansion, so a near point straight ahead genuinely moves less than a far point off to the side.
  Comparing across the frame would teach the net that the centre of the image is distant. Two points
  close together share almost the same geometry, so their flow difference is dominated by their
  depth difference — which is the comparison actually wanted.

WHAT THIS BUYS ON A SCREEN. Nothing about the training is about roads. A window dragged across a
desktop is a body-free version of the same parallax: the moving window's contents shift, whatever it
covers does not, and the pair labels follow. Whether that transfers is measured in
`scripts/screen_depth_probe.py` against the one place a depth answer can be checked exactly — the
window manager's own Z-order, which is ground truth nobody had to annotate.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import torch

from .observe import _derotate, track


# --- turning motion into comparisons ---------------------------------------------------------------

def rotation_share(t: dict[str, Any]) -> float:
    """What fraction of the flow is ONE UNIFORM SHIFT — the thing that carries no depth information.

        |mean flow vector|^2 / mean(|flow|^2)

    Bounded in [0, 1] by Jensen, and it means the same thing in every regime, which the first
    version did not. That one divided by the MEDIAN flow, and on a screen where most of the picture
    is static the median is zero: the ratio came out at 1926 and the gate rejected every frame of
    every desktop trial, forty out of forty, reporting an abstention that was an arithmetic accident
    rather than a judgement about the scene.

    What the number says now:

        1.0   every point moved identically   -> a turn, or a whole scene sliding: no depth in it
        ~0.3  some points moved, others did not -> a surface passing in front of another
        ~0.2  flow spreads out from a centre  -> travelling forward, which is the good case

    One expression covers a camera turning and a window sliding, which matters beyond tidiness: a
    depth sense with a separate screen mode would be two senses wearing one name, and the rule
    against that is not stylistic — it is what makes the same faculty answer both questions."""
    fl = t.get("flow")
    if fl is None or len(fl) < 20:
        return 1.0
    d = t["dxy"]
    denom = float((d ** 2).sum(1).mean())
    if denom < 1e-9:
        return 1.0                      # nothing moved at all; there is no depth to read here
    return float((d.mean(0) ** 2).sum() / denom)


def rank_pairs(a_rgb: np.ndarray, b_rgb: np.ndarray, *, max_pairs: int = 400,
               neighbourhood: float = 0.22, min_ratio: float = 2.0,
               max_rotation: float = 0.6, derotate: bool = False) -> dict[str, Any]:
    """Every comparison the motion between two frames licenses. No labels are read from anywhere.

    Returns (i, j) index pairs into `xy` meaning "i is nearer than j", plus a confidence from how
    decisively the flows differed.

    `min_ratio` is the abstention. Two points whose flow differs by less than this are NOT emitted as
    a pair in either direction — the measurement did not settle the question, and a body that guesses
    when it cannot tell would be learning its own noise. Most candidate pairs are discarded, which is
    the intended behaviour rather than a yield problem."""
    t = track(a_rgb, b_rgb)
    xy = t.get("xy")
    if xy is None or len(xy) < 20:
        return {"xy": np.zeros((0, 2), np.float32), "pairs": np.zeros((0, 2), np.int32),
                "conf": np.zeros((0,), np.float32), "reason": "too few tracked points"}

    rot = rotation_share(t)
    if rot > max_rotation:
        # ABSTAIN. Near 1.0 every point moved alike, so there is no differential motion and
        # therefore nothing about depth to read -- whether the camera turned or the whole scene
        # slid. The default sits at 0.6 because that is where the gate stops meaning "no
        # information" and starts meaning "not the best kind of information": tightening it to 0.03
        # raises label accuracy on driving footage from 0.690 to 0.724 while discarding two thirds
        # of the frames, which is a quality preference and not the same judgement. Conflating the
        # two would have made a desktop unreadable -- a window sliding over another scores about
        # 0.30, well inside the range good driving frames occupy.
        return {"xy": xy, "pairs": np.zeros((0, 2), np.int32), "conf": np.zeros((0,), np.float32),
                "rotation_share": round(rot, 3), "reason": "camera was turning"}

    mag = _derotate(t["xy"], t["dxy"]) if derotate else t["flow"]
    h = max(a_rgb.shape[0], a_rgb.shape[1])
    radius = neighbourhood * h

    rng = np.random.default_rng(0)
    n = len(xy)
    ii = rng.integers(0, n, size=max_pairs * 12)
    jj = rng.integers(0, n, size=max_pairs * 12)
    keep = ii != jj
    ii, jj = ii[keep], jj[keep]

    d = np.sqrt(((xy[ii] - xy[jj]) ** 2).sum(1))
    near = d < radius                                   # only locally comparable points
    ii, jj = ii[near], jj[near]

    mi, mj = mag[ii], mag[jj]
    hi = np.maximum(mi, mj)
    lo = np.minimum(mi, mj) + 1e-6
    decisive = (hi / lo) >= min_ratio                   # abstain on the rest
    ii, jj = ii[decisive], jj[decisive]
    mi, mj = mag[ii], mag[jj]

    # order each pair so the first is the one that moved more == the nearer one
    swap = mj > mi
    a_idx = np.where(swap, jj, ii)
    b_idx = np.where(swap, ii, jj)
    conf = np.log(np.maximum(mag[a_idx], 1e-6) / np.maximum(mag[b_idx], 1e-6))

    if len(a_idx) > max_pairs:
        pick = rng.choice(len(a_idx), max_pairs, replace=False)
        a_idx, b_idx, conf = a_idx[pick], b_idx[pick], conf[pick]

    return {"xy": xy, "pairs": np.stack([a_idx, b_idx], 1).astype(np.int32),
            "conf": conf.astype(np.float32), "flow": mag, "rotation_share": round(rot, 3),
            "yield": round(float(len(a_idx)) / max(len(ii) + 1e-9, 1), 3)}


# --- learning from comparisons ---------------------------------------------------------------------

def ranking_loss(pred_log_depth: torch.Tensor, xy: np.ndarray, pairs: np.ndarray,
                 conf: np.ndarray, margin: float = 0.12) -> torch.Tensor:
    """Margin ranking on log depth, weighted by how decisive each comparison was.

    Log depth rather than depth, so the margin means a RATIO — being wrong about 2m versus 4m should
    cost what being wrong about 20m versus 40m costs, which is how a rank behaves and is not how a
    difference in metres behaves."""
    if len(pairs) == 0:
        return pred_log_depth.sum() * 0.0
    H, W = pred_log_depth.shape[-2:]
    xi = np.clip(np.round(xy[:, 0]).astype(np.int64), 0, W - 1)
    yi = np.clip(np.round(xy[:, 1]).astype(np.int64), 0, H - 1)
    flat = pred_log_depth.reshape(-1)
    idx = torch.from_numpy(yi * W + xi).to(flat.device)
    vals = flat[idx]
    a = vals[torch.from_numpy(pairs[:, 0].astype(np.int64)).to(flat.device)]
    b = vals[torch.from_numpy(pairs[:, 1].astype(np.int64)).to(flat.device)]
    w = torch.from_numpy(np.abs(conf)).to(flat.device).clamp(0, 3.0)
    # a is nearer, so log_depth(a) should be BELOW log_depth(b) by at least the margin
    viol = torch.relu(a - b + margin)
    return (viol * w).sum() / w.sum().clamp(min=1e-6)


def rank_accuracy(depth: np.ndarray, xy: np.ndarray, pairs: np.ndarray) -> float:
    """Fraction of comparisons the depth map gets in the right order. 0.5 is chance."""
    if len(pairs) == 0:
        return float("nan")
    H, W = depth.shape[:2]
    xi = np.clip(np.round(xy[:, 0]).astype(np.int64), 0, W - 1)
    yi = np.clip(np.round(xy[:, 1]).astype(np.int64), 0, H - 1)
    z = depth[yi, xi]
    return float(np.mean(z[pairs[:, 0]] < z[pairs[:, 1]]))


def pairs_from_truth(depth_true: np.ndarray, xy: np.ndarray, pairs: np.ndarray,
                     min_ratio: float = 1.15) -> tuple[np.ndarray, np.ndarray]:
    """The same comparisons, answered by ground truth instead of by motion — for CHECKING the
    motion-derived labels, never for training on them.

    Returns (kept_pairs, true_first_is_nearer). Pairs whose true depths are too close to call are
    dropped, so the check does not punish the learner for ties it could not have resolved."""
    H, W = depth_true.shape[:2]
    xi = np.clip(np.round(xy[:, 0]).astype(np.int64), 0, W - 1)
    yi = np.clip(np.round(xy[:, 1]).astype(np.int64), 0, H - 1)
    z = depth_true[yi, xi]
    za, zb = z[pairs[:, 0]], z[pairs[:, 1]]
    r = np.maximum(za, zb) / np.maximum(np.minimum(za, zb), 1e-6)
    keep = r >= min_ratio
    return pairs[keep], (za[keep] < zb[keep])
