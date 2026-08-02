# -*- coding: utf-8 -*-
"""Depth from motion, with no labels — the signal a body walking down a street actually has.

CARLA hands out metres. City Sample does not, and neither does a pavement in Seoul, so a depth sense
that only works where a simulator cooperates is not a depth sense. What a moving body always has is
its own motion: predict the depth of frame t and the camera motion from t to t+1, use them to warp t
into t+1, and score how wrong the warp looks. Geometry supplies the supervision. This is the standard
self-supervised formulation (SfMLearner / Monodepth2), and the reason it is the right one here is not
that it is standard — it is that it needs nothing but consecutive frames from a body that moved.

WHY THE WARP CONSTRAINS DEPTH AT ALL. Move a camera sideways and near things slide further across
the image than far things. That is parallax, and it means the correct depth is the one that makes
the warped frame line up. A depth map that is wrong in the near field puts the wrong pixels in the
wrong place and pays for it in photometric error. No labels are involved anywhere.

FOUR THINGS THAT MAKE OR BREAK IT, all of them known failure modes rather than refinements:

  SCALE IS UNRECOVERABLE. Monocular self-supervision cannot know metres: halving every depth and
  halving the translation produces an identical warp. So the objective fits depth only up to a
  global scale, and any metric claim from this alone would be fabricated. The CARLA-supervised
  initialisation is what carries the scale in; what this adds is structure, not units.

  STATIC PIXELS POISON IT. A car moving with the camera never shifts between frames, so the warp
  explains it best by placing it at infinity, and the net learns holes in the sky where traffic is.
  The auto-mask handles it: a pixel is used only if the warp made it BETTER than doing nothing.
  A pixel that already matched without moving is uninformative and is dropped.

  MINIMUM-OVER-FRAMES, NOT AVERAGE. Something visible in t and occluded in t+1 cannot be warped
  correctly to t+1 no matter what depth is predicted. Averaging over both neighbours pays that
  penalty everywhere; taking the minimum lets each pixel be explained by whichever neighbour can
  actually see it.

  SMOOTHNESS MUST BE EDGE-AWARE. A flat penalty on depth gradients erases the depth discontinuity at
  the edge of a building, which is precisely the structure worth having. Weighting it by the inverse
  image gradient lets depth jump where the picture jumps.

WHAT IS NOT SOLVED HERE. The camera intrinsics of the City Sample viewport are not known. A focal
length is assumed from the field of view, and an error there trades off against a global depth scale
-- which the objective cannot separate anyway. It means relative structure is what this can be
trusted for, and it is why the evaluation below reports ordering rather than metres.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import torch
import torch.nn.functional as F


# --- keeping depth in a range a body could be in --------------------------------------------------

D_MIN, D_MAX = 0.5, 100.0        # metres; matches the clip the CARLA-supervised training used


def bounded_log_depth(log_depth: torch.Tensor, d_min: float = D_MIN,
                      d_max: float = D_MAX) -> torch.Tensor:
    """Squash predicted log-depth into [d_min, d_max], smoothly.

    THIS IS NOT A SAFETY RAIL, IT IS THE FIX FOR A DEFECT THE OBJECTIVE HAS ON ITS OWN. Parallax
    falls as 1/Z, so the image difference between 30m and 1000m is a fraction of a pixel. In that
    regime the photometric loss is nearly flat, and `nearly` is the problem: whatever tiny gradient
    survives — interpolation error, mostly — pushes far depth toward infinity, where it can shave a
    little off the loss. Optimising a free depth map against the unbounded objective did exactly
    that, and the shape of it is worth recording because a training curve hides it completely:

        step  loss      d.max      error-vs-truth
           0  0.13416     20.6            4.64
          50  0.02009    504.8           10.55
         150  0.01845   3814.0           18.37
         399  0.01847  15038.3           19.05

    The loss falls by a factor of seven while the answer gets four times worse. The near field was
    recovered correctly (8.2m against a true 8.0m) the whole time; it is only the far field, where
    the data says nothing, that escapes.

    Smoothness on disparity is the usual regulariser and it is NOT sufficient here — measured, at
    weights from 1e-4 to 5e-2, the runaway was slowed and never stopped (d.max 1502, 1479, 1244, 828)
    and the largest weight was already spoiling the fit. Bounding the output is what works, and it is
    what the standard self-supervised formulation does; omitting it was my error, not a simplification.

    The form is chosen to leave the CARLA-trained head alone where it matters: the map is the
    identity to first order at the geometric centre of the range (unit slope there) and saturates
    only at the ends, so a supervised initialisation is not distorted on the way in."""
    lo, hi = float(np.log(d_min)), float(np.log(d_max))
    mid, span = (lo + hi) / 2.0, hi - lo
    return lo + span * torch.sigmoid((log_depth - mid) * (4.0 / span))


# --- geometry -------------------------------------------------------------------------------------

def intrinsics(h: int, w: int, fov_deg: float = 90.0, device: Any = None) -> torch.Tensor:
    """Pinhole K from a field of view. ASSUMED, not measured — see the module docstring."""
    f = 0.5 * w / np.tan(0.5 * np.radians(fov_deg))
    K = torch.tensor([[f, 0.0, w / 2.0], [0.0, f, h / 2.0], [0.0, 0.0, 1.0]], dtype=torch.float32)
    return K.to(device) if device is not None else K


def _pose_to_matrix(axisangle: torch.Tensor, translation: torch.Tensor) -> torch.Tensor:
    """(B,3) rotation vector + (B,3) translation -> (B,4,4), via Rodrigues."""
    B = axisangle.shape[0]
    theta = axisangle.norm(dim=1, keepdim=True).clamp(min=1e-7)
    k = axisangle / theta
    K = torch.zeros(B, 3, 3, device=axisangle.device, dtype=axisangle.dtype)
    K[:, 0, 1], K[:, 0, 2] = -k[:, 2], k[:, 1]
    K[:, 1, 0], K[:, 1, 2] = k[:, 2], -k[:, 0]
    K[:, 2, 0], K[:, 2, 1] = -k[:, 1], k[:, 0]
    I = torch.eye(3, device=axisangle.device, dtype=axisangle.dtype).expand(B, 3, 3)
    th = theta.view(B, 1, 1)
    R = I + torch.sin(th) * K + (1 - torch.cos(th)) * (K @ K)
    T = torch.zeros(B, 4, 4, device=axisangle.device, dtype=axisangle.dtype)
    T[:, :3, :3], T[:, :3, 3], T[:, 3, 3] = R, translation, 1.0
    return T


def warp(src: torch.Tensor, depth: torch.Tensor, pose: torch.Tensor, K: torch.Tensor) -> torch.Tensor:
    """Render `src` as it would look from the pose `depth` was predicted at.

    Back-project every pixel to a 3D point using its predicted depth, move it by the relative pose,
    project it back, and sample the source there. Where depth is right the result matches the target;
    where it is wrong the picture tears, and that tearing is the entire training signal."""
    B, _, H, W = depth.shape
    dev, dt = depth.device, depth.dtype
    ys, xs = torch.meshgrid(torch.arange(H, device=dev, dtype=dt),
                            torch.arange(W, device=dev, dtype=dt), indexing="ij")
    ones = torch.ones_like(xs)
    pix = torch.stack([xs, ys, ones], dim=0).view(1, 3, -1).expand(B, 3, H * W)

    cam = torch.inverse(K).unsqueeze(0) @ pix               # ray directions
    cam = cam * depth.view(B, 1, -1)                        # scaled to the predicted depth
    cam = torch.cat([cam, torch.ones(B, 1, H * W, device=dev, dtype=dt)], dim=1)

    proj = (K.unsqueeze(0) @ pose[:, :3, :]) @ cam
    z = proj[:, 2:3].clamp(min=1e-4)
    grid = (proj[:, :2] / z).view(B, 2, H, W).permute(0, 2, 3, 1)
    grid = torch.stack([2 * grid[..., 0] / (W - 1) - 1, 2 * grid[..., 1] / (H - 1) - 1], dim=-1)
    return F.grid_sample(src, grid, mode="bilinear", padding_mode="border", align_corners=True)


# --- the objective --------------------------------------------------------------------------------

def _ssim(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    """Structural similarity, 3x3. Included because raw L1 is dominated by brightness: two frames of
    the same wall under a passing shadow differ hugely in L1 and not at all in structure, and the
    objective should not be paying attention to the shadow."""
    C1, C2 = 0.01 ** 2, 0.03 ** 2
    pool = lambda x: F.avg_pool2d(F.pad(x, (1, 1, 1, 1), mode="reflect"), 3, 1)
    mu_a, mu_b = pool(a), pool(b)
    sa, sb = pool(a * a) - mu_a ** 2, pool(b * b) - mu_b ** 2
    sab = pool(a * b) - mu_a * mu_b
    n = (2 * mu_a * mu_b + C1) * (2 * sab + C2)
    d = (mu_a ** 2 + mu_b ** 2 + C1) * (sa + sb + C2)
    return ((1 - n / d) / 2).clamp(0, 1)


def photometric(pred: torch.Tensor, target: torch.Tensor, alpha: float = 0.85) -> torch.Tensor:
    """Per-pixel appearance error: mostly structure, a little absolute brightness."""
    return alpha * _ssim(pred, target).mean(1, keepdim=True) + \
        (1 - alpha) * (pred - target).abs().mean(1, keepdim=True)


def smoothness(disp: torch.Tensor, img: torch.Tensor) -> torch.Tensor:
    """Edge-aware: penalise depth gradients EXCEPT where the image has one."""
    d = disp / (disp.mean(dim=(2, 3), keepdim=True) + 1e-7)
    gx, gy = (d[..., :, :-1] - d[..., :, 1:]).abs(), (d[..., :-1, :] - d[..., 1:, :]).abs()
    ix = img.mean(1, True)[..., :, :-1] - img.mean(1, True)[..., :, 1:]
    iy = img.mean(1, True)[..., :-1, :] - img.mean(1, True)[..., 1:, :]
    return (gx * torch.exp(-ix.abs())).mean() + (gy * torch.exp(-iy.abs())).mean()


def selfsup_loss(tgt: torch.Tensor, neighbours: list[torch.Tensor], depth: torch.Tensor,
                 poses: list[torch.Tensor], K: torch.Tensor,
                 smooth_w: float = 1e-3) -> dict[str, torch.Tensor]:
    """The whole objective, with the auto-mask and the min-over-neighbours."""
    warped = [photometric(warp(src, depth, p, K), tgt) for src, p in zip(neighbours, poses)]
    identity = [photometric(src, tgt) for src in neighbours]

    reproj = torch.cat(warped, dim=1).min(dim=1, keepdim=True)[0]
    ident = torch.cat(identity, dim=1).min(dim=1, keepdim=True)[0]

    # AUTO-MASK. Keep a pixel only where warping helped. A pixel that matched just as well without
    # moving carries no parallax — it is either textureless, or moving with the camera — and letting
    # it vote teaches the net that the vehicle in front is infinitely far away.
    mask = (reproj < ident).float()
    photo = (reproj * mask).sum() / mask.sum().clamp(min=1.0)
    smooth = smoothness(1.0 / depth.clamp(min=1e-3), tgt)
    return {"loss": photo + smooth_w * smooth, "photo": photo, "smooth": smooth,
            "kept": mask.mean()}


# --- pose ------------------------------------------------------------------------------------------

class PoseNet(torch.nn.Module):
    """Where the camera went between two frames, from the two frames.

    Deliberately small. Its job is to stop being an excuse for the depth net — an inaccurate pose
    makes every depth look wrong — and not to be a good visual odometry system in its own right. It
    is thrown away after training; only the depth net is kept."""

    def __init__(self, width: int = 16):
        super().__init__()
        c = width
        self.enc = torch.nn.Sequential(
            torch.nn.Conv2d(6, c, 7, 2, 3), torch.nn.ReLU(True),
            torch.nn.Conv2d(c, c * 2, 5, 2, 2), torch.nn.ReLU(True),
            torch.nn.Conv2d(c * 2, c * 4, 3, 2, 1), torch.nn.ReLU(True),
            torch.nn.Conv2d(c * 4, c * 8, 3, 2, 1), torch.nn.ReLU(True),
            torch.nn.Conv2d(c * 8, c * 8, 3, 2, 1), torch.nn.ReLU(True),
        )
        self.head = torch.nn.Conv2d(c * 8, 6, 1)

    def forward(self, a: torch.Tensor, b: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.head(self.enc(torch.cat([a, b], dim=1))).mean(dim=(2, 3))
        # 0.01 scaling: the usual trick, and it matters. Unscaled, the first random poses fling the
        # camera across the scene, every warp samples off the edge of the image, and the gradient
        # that comes back is noise. Starting near identity means the first warps are small and the
        # signal is real from the first step.
        return h[:, :3] * 0.01, h[:, 3:] * 0.01


def relative_pose(net: PoseNet, tgt: torch.Tensor, src: torch.Tensor, invert: bool) -> torch.Tensor:
    """Pose taking a point in the TARGET frame to the SOURCE frame, which is the direction `warp`
    needs. For a past neighbour the network is run the other way round and the result inverted,
    rather than asking one small network to represent both directions."""
    if invert:
        ax, tr = net(src, tgt)
        return torch.inverse(_pose_to_matrix(ax, tr))
    ax, tr = net(tgt, src)
    return _pose_to_matrix(ax, tr)
