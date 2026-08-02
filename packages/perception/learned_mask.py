# -*- coding: utf-8 -*-
"""A learned sprite mask — the replacement for `abs(frame - bg) > 40`, as an organ rather than a script.

Per docs/ATANOR_eye_learned_vs_wired_2026-07-30.md, motion segmentation is a stage humans ACQUIRE --
infants group by common fate before they use shape -- so a threshold standing there is a training wheel,
and it is upstream of every other perception organ.

WHAT IT CAN DO THAT SUBTRACTION CANNOT AT ANY THRESHOLD. Subtraction only ever sees CHANGE, so a
stationary sprite sits in the rollout median and is removed by construction. That is the defect that
killed the pellet map: searching for static pellets inside background subtraction found 74 pixels and a
map covering 0.7% of the screen. A model that sees APPEARANCE learns "a sprite looks like this" from
moving examples and then finds one that is not moving. Measured at matched false-positive rate:

    FPR 20%     static pellets 82.6%   moving sprites 94.7%
    subtraction static pellets  0.0%   moving sprites  100% (by definition -- it IS the moving mask)
    random init static pellets  2.5%

TRAINED WITH NO HAND-DRAWN MASKS. Positives are pixels the incumbent rule calls moving; negatives are the
rest. The rule bootstraps the labels and the model generalises past it -- which is why the evaluation is
on pellets, a class the label source never saw and cannot see.

THE OPERATING POINT IS NOT MINE TO PICK. `threshold_for_fpr` sets it from the BACKGROUND's own score
distribution, so the caller asks for a false-positive rate and the data supplies the cut. Reporting a
detector at one hand-chosen point hid a factor of nine the first time this was measured.

THIS DOES NOT DELETE THE RULE. Per the standing condition, the incumbent is removed only once the
replacement also wins on the organs that CONSUME it -- blobs, tracking, and the body criterion -- and
that is measured in scripts/wire_learned_mask.py, not asserted here.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

PATCH = 7                # odd, so a pixel has a centre


def patches_at(frame: np.ndarray, ys, xs, patch: int = PATCH) -> np.ndarray:
    r = patch // 2
    H, W = frame.shape[:2]
    out = np.zeros((len(ys), patch, patch, 3), np.float32)
    for i, (y, x) in enumerate(zip(ys, xs)):
        y0, x0 = max(0, y - r), max(0, x - r)
        p = frame[y0:min(H, y + r + 1), x0:min(W, x + r + 1)]
        out[i, :p.shape[0], :p.shape[1]] = p
    return out / 255.0


def make_net(device: str = "cpu"):
    import torch.nn as nn
    return nn.Sequential(
        nn.Conv2d(3, 16, 3, 1, 1), nn.ReLU(True),
        nn.Conv2d(16, 32, 3, 2, 1), nn.ReLU(True),
        nn.AdaptiveAvgPool2d(1), nn.Flatten(),
        nn.Linear(32, 2)).to(device)


class LearnedMask:
    """Pixel -> P(sprite). Domain-blind: the only input is a colour patch."""

    def __init__(self, device: str = "cpu", net=None):
        self.device = device
        self.net = net if net is not None else make_net(device)
        self.threshold: float | None = None

    # ---------------------------------------------------------------- training
    def fit(self, X: np.ndarray, Y: np.ndarray, epochs: int = 4, lr: float = 2e-3,
            batch: int = 256, seed: int = 0) -> "LearnedMask":
        import torch
        opt = torch.optim.Adam(self.net.parameters(), lr=lr)
        lossf = torch.nn.CrossEntropyLoss()
        rng = np.random.default_rng(seed)
        Xt = torch.from_numpy(X).permute(0, 3, 1, 2)
        Yt = torch.from_numpy(Y)
        self.net.train()
        for _ep in range(epochs):
            idx = rng.permutation(len(X))
            for s in range(0, len(idx) - batch + 1, batch):
                j = idx[s:s + batch]
                loss = lossf(self.net(Xt[j].to(self.device)), Yt[j].to(self.device))
                opt.zero_grad()
                loss.backward()
                opt.step()
        return self

    # ---------------------------------------------------------------- inference
    def score(self, frame: np.ndarray, stride: int = 1, batch: int = 8192) -> np.ndarray:
        """P(sprite) per pixel. `stride` subsamples for speed and the result is upsampled back."""
        import torch
        H, W = frame.shape[:2]
        ys, xs = np.mgrid[0:H:stride, 0:W:stride]
        ys, xs = ys.ravel(), xs.ravel()
        self.net.eval()
        out = []
        with torch.no_grad():
            for s in range(0, len(ys), batch):
                P = patches_at(frame, ys[s:s + batch], xs[s:s + batch])
                t = torch.from_numpy(P).permute(0, 3, 1, 2).to(self.device)
                out.append(self.net(t).softmax(1)[:, 1].cpu().numpy())
        self.net.train()
        s_small = np.concatenate(out).reshape(len(range(0, H, stride)), len(range(0, W, stride)))
        if stride == 1:
            return s_small
        return np.repeat(np.repeat(s_small, stride, axis=0), stride, axis=1)[:H, :W]

    def threshold_for_fpr(self, frames, background_mask_of, fpr: float = 0.2,
                          stride: int = 2) -> float:
        """The cut that yields this false-positive rate ON BACKGROUND. The data picks it, not me."""
        vals = []
        for f in frames:
            s = self.score(f, stride=stride)
            bgm = background_mask_of(f)
            vals.append(s[bgm])
        v = np.concatenate(vals) if vals else np.zeros(1)
        self.threshold = float(np.percentile(v, 100 * (1 - fpr)))
        return self.threshold

    def mask(self, frame: np.ndarray, stride: int = 2) -> np.ndarray:
        if self.threshold is None:
            raise RuntimeError("threshold not set; call threshold_for_fpr first")
        return self.score(frame, stride=stride) > self.threshold

    # ---------------------------------------------------------------- persistence
    def save(self, path: Path) -> None:
        import torch
        torch.save({"state": self.net.state_dict(), "threshold": self.threshold}, path)

    @classmethod
    def load(cls, path: Path, device: str = "cpu") -> "LearnedMask":
        import torch
        d = torch.load(path, map_location=device)
        m = cls(device)
        m.net.load_state_dict(d["state"])
        m.threshold = d.get("threshold")
        return m
