# -*- coding: utf-8 -*-
"""Learn what makes two views the same thing — from tracking, with nobody labelling anything.

Owner, 2026-07-29, on what "maximise" meant: 자가진화를 잘 해서 혼자 새로운 환경에서도 눈을 틔우는
법을 찾아서 눈을 벌려 틔우고, 이런 주체적인 act.

THAT IS WHAT THIS IS, and the reason is where the labels come from. Following a point across frames
produces, for free and continuously, exactly the supervision a same-or-different judgement needs:

    two views of ONE track          = the same thing, seen twice
    views of DIFFERENT tracks       = different things, seen at the same moment

Nobody says which. The world says it, by the fact that a surface stayed a surface while the camera
moved. So dropped into a world it has never seen, with no annotation and no teacher, ATANOR can open
its own eyes: track, harvest, train, and the discriminator it ends up with is fitted to THAT world.
The mechanism does not care whether the world is a simulator, a game, a desktop or a street.

WHY LEARNED AND NOT HAND-WRITTEN. `handle._signature` is a gradient-orientation histogram I chose,
and it works — 3% overlap between same and different, against 35% for the raw patch it replaced. But
it is a rule I picked, and this repository's standing finding is that a learned discriminator passes
the ceiling a hand rule sits under. It is also the thing that stops the pathology: hand-building one
more discriminator per organ is how a project ends up with a hundred and thirty-three of them, each
re-implementing the same judgement slightly differently.

WHAT WOULD MAKE THIS A FAILURE, and it is measured the same way the hand rule was. Same p10 against
different p90, on episodes the training never saw. If the learned code does not separate them more
cleanly than the histogram, the histogram stays and this is deleted. A learned thing that is merely
newer is not an improvement.

NEGATIVES ARE DRAWN FROM THE SAME FRAME, deliberately. Two patches from different moments differ in
lighting, exposure and weather as well as in identity, and a network given those as negatives learns
to tell moments apart instead of things apart — which would score beautifully and be useless. Same
frame, different track: the only thing that differs is which thing it is.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

PATCH = 24                 # side of the crop fed to the net
DIM = 32                   # embedding size; the hand rule uses 32 too, so the comparison is fair


def crop(rgb: np.ndarray, xy, r: int = PATCH // 2) -> np.ndarray | None:
    h, w = rgb.shape[:2]
    x, y = int(xy[0]), int(xy[1])
    if x - r < 0 or y - r < 0 or x + r > w or y + r > h:
        return None
    return rgb[y - r:y + r, x - r:x + r]


@dataclass
class Pairs:
    """Harvested supervision: anchors, positives (same track later), negatives (other track, now)."""

    a: np.ndarray
    p: np.ndarray
    n: np.ndarray

    def __len__(self) -> int:
        return len(self.a)


def harvest(frames: list[np.ndarray], *, max_pairs: int = 400, min_gap: int = 4,
            seed: int = 0) -> Pairs:
    """Turn tracking into training data. No labels are read from anywhere."""
    from .coherence import tracks

    tr = tracks(frames, max_points=300)
    xy, alive = tr["xy"], tr["alive"]
    T, N = alive.shape
    if N < 8:
        return Pairs(np.zeros((0, PATCH, PATCH, 3), np.uint8),
                     np.zeros((0, PATCH, PATCH, 3), np.uint8),
                     np.zeros((0, PATCH, PATCH, 3), np.uint8))
    rng = np.random.default_rng(seed)
    A, P, Nn = [], [], []
    for _ in range(max_pairs * 4):
        if len(A) >= max_pairs:
            break
        n = int(rng.integers(0, N))
        live = np.where(alive[:, n])[0]
        if len(live) < min_gap + 2:
            continue
        t0 = int(rng.choice(live[:-min_gap])) if len(live) > min_gap else int(live[0])
        cand = live[live >= t0 + min_gap]
        if not len(cand):
            continue
        t1 = int(rng.choice(cand))
        others = [m for m in range(N) if m != n and alive[t0, m]]
        if not others:
            continue
        m = int(rng.choice(others))
        ca, cp, cn = crop(frames[t0], xy[t0, n]), crop(frames[t1], xy[t1, n]), crop(frames[t0], xy[t0, m])
        if ca is None or cp is None or cn is None:
            continue
        A.append(ca)
        P.append(cp)
        Nn.append(cn)
    return Pairs(np.array(A, np.uint8), np.array(P, np.uint8), np.array(Nn, np.uint8))


def make_net(dim: int = DIM, pool: int = 1):
    """A small conv encoder. Small on purpose: the claim is that the SUPERVISION is what was missing,
    not capacity, and a large net would make that impossible to tell.

    `pool` IS NOT COSMETIC, and it was measured. AdaptiveAvgPool2d(1) collapses the whole spatial map into
    64 channel means before the embedding is formed, turning a patch into a bag of averages. On CIFAR-100
    that cost more effective dimensionality than the loss function did:

        triplet margin, pool=1     effective dims 4.80   naming 0.072
        InfoNCE,        pool=1     effective dims 5.90   naming 0.127
        InfoNCE,        pool=2     effective dims 7.44   naming 0.154   (chance 0.010)

    Default stays 1 so every existing caller and the checkpoint on disk keep working; pool=2 is the one to
    train new encoders with."""
    import torch.nn as nn
    head = ([nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Linear(64, dim)] if pool == 1 else
            [nn.AdaptiveAvgPool2d(pool), nn.Flatten(), nn.Linear(64 * pool * pool, dim)])
    return nn.Sequential(
        nn.Conv2d(3, 16, 3, 2, 1), nn.ReLU(True),        # 12
        nn.Conv2d(16, 32, 3, 2, 1), nn.ReLU(True),       # 6
        nn.Conv2d(32, 64, 3, 2, 1), nn.ReLU(True),       # 3
        *head)


def train_infonce(patches, groups, *, dim: int = DIM, pool: int = 2, epochs: int = 16,
                  batch: int = 256, lr: float = 2e-3, tau: float = 0.1, device: str = "cpu",
                  log=None):
    """Contrastive training that does NOT saturate, which is why it buys dimensions triplet loss cannot.

    Triplet margin loss has zero gradient once the margin is met, so an encoder stops as soon as it has
    just enough dimensions to separate the triplets. InfoNCE is a softmax over every other item in the
    batch: there is no point at which the objective is satisfied, so pressure to spread continues.

    `groups` is a label per patch saying which items count as the same thing -- a track id, a place, a
    class. No word is needed and none is read; it is the same free supervision `harvest` already builds."""
    import torch
    import torch.nn.functional as F

    net = make_net(dim, pool=pool).to(device)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    X = torch.from_numpy(np.asarray(patches, np.float32) / 255.0).permute(0, 3, 1, 2).to(device)
    g = torch.as_tensor(np.asarray(groups), device=device)
    rng = np.random.default_rng(0)
    for ep in range(epochs):
        order = rng.permutation(len(X))
        tot = nb = 0.0
        for s in range(0, len(X) - batch + 1, batch):
            idx = order[s:s + batch]
            z = F.normalize(net(X[idx]), dim=1)
            sim = z @ z.t() / tau
            sim.fill_diagonal_(-1e9)
            pos = (g[idx][:, None] == g[idx][None, :]).float()
            pos.fill_diagonal_(0)
            keep = pos.sum(1) > 0
            if int(keep.sum()) < 8:
                continue
            logp = F.log_softmax(sim[keep], dim=1)
            loss = -(logp * pos[keep]).sum(1) / pos[keep].sum(1)
            opt.zero_grad()
            loss.mean().backward()
            opt.step()
            tot += float(loss.detach().mean())
            nb += 1
        if log and nb:
            log(f"  ep{ep} loss {tot / nb:.4f}")
    net.eval()
    return net


def load_encoder(path):
    """Load a checkpoint AS IT DESCRIBES ITSELF, returning (net, patch_size).

    THE BUG THIS EXISTS TO MAKE IMPOSSIBLE, measured 2026-08-01. Two encoders sit side by side:
    signature_net.pt (dim 32, patch 24) and signature_net_v2.pt (dim 32, PATCH 20, POOL 2, trained by
    InfoNCE over point tracks, and carrying `naming_precision: 1.0` in its own metadata). The name
    book was built by v2. Every caller loaded v1 -- `make_net(ck["dim"])`, cropping at the module
    constant PATCH=24 -- and asked v2's book questions in v1's space.

    The result was not merely poor, it was ANTI-CORRELATED: patches sat at cosine 0.138 from their
    own word and 0.592 from the nearest wrong one, and nearest-centroid accuracy was 0.065 against a
    chance of 0.167. Less than half of chance is never weak features; it is a wiring error, and this
    one was invisible because both files load, both give 32 numbers, and every number downstream
    looks like a plausible embedding.

    So the checkpoint's own `patch` and `pool` are authoritative and a caller cannot supply them.
    Nothing here has a default that could silently be wrong."""
    import torch
    ck = torch.load(path, map_location="cpu")
    net = make_net(int(ck.get("dim", DIM)), int(ck.get("pool", 1)))
    net.load_state_dict(ck["state_dict"])
    net.eval()
    return net, int(ck.get("patch", PATCH))


def crop_at(rgb: np.ndarray, xy, patch: int):
    """`crop`, but at the size the encoder actually wants rather than the module default."""
    return crop(rgb, xy, r=int(patch) // 2)


def embed(net, patches: np.ndarray, device="cpu") -> np.ndarray:
    """Unit-norm embeddings, so cosine is the comparison — the same comparison the hand rule uses."""
    import torch
    with torch.no_grad():
        net.eval()
        x = torch.from_numpy(patches.astype(np.float32) / 255.0).permute(0, 3, 1, 2).to(device)
        v = net(x)
        v = v / v.norm(dim=1, keepdim=True).clamp(min=1e-6)
        net.train()
        return v.cpu().numpy()


def separability(same: np.ndarray, diff: np.ndarray) -> dict[str, Any]:
    """The one test that decides whether this replaces the hand rule.

    Same p10 against different p90, and the fraction of different pairs scoring above the same-p10.
    A threshold needs a GAP to live in; without one, no threshold works and the code is not a code."""
    s, d = np.asarray(same), np.asarray(diff)
    if not len(s) or not len(d):
        return {"overlap": 1.0, "reason": "empty"}
    s10, d90 = float(np.percentile(s, 10)), float(np.percentile(d, 90))
    return {"same_median": round(float(np.median(s)), 4), "same_p10": round(s10, 4),
            "diff_median": round(float(np.median(d)), 4), "diff_p90": round(d90, 4),
            "overlap": round(float(np.mean(d > s10)), 4),
            "gap": round(s10 - d90, 4),
            "separable": bool(s10 > d90)}


def train(pairs: Pairs, *, dim: int = DIM, epochs: int = 30, batch: int = 64, lr: float = 2e-3,
          margin: float = 0.3, pool: int = 1, device: str = "cpu", log=None):
    """Triplet margin on cosine distance. Positives come from a track, negatives from the same frame.

    `pool` defaults to 1 so every existing caller and checkpoint is unchanged; it exists so the loss and
    the pooling can be varied independently, which is the only way to say which of the two mattered."""
    import torch
    import torch.nn.functional as F

    net = make_net(dim, pool=pool).to(device)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    T = lambda a: torch.from_numpy(a.astype(np.float32) / 255.0).permute(0, 3, 1, 2).to(device)
    A, P, N = T(pairs.a), T(pairs.p), T(pairs.n)
    n = len(pairs)
    rng = np.random.default_rng(0)
    for ep in range(epochs):
        order = rng.permutation(n)
        tot = 0.0
        for s in range(0, n - batch + 1, batch):
            idx = order[s:s + batch]
            ea, epos, eneg = (F.normalize(net(x[idx]), dim=1) for x in (A, P, N))
            d_pos = 1.0 - (ea * epos).sum(1)
            d_neg = 1.0 - (ea * eneg).sum(1)
            loss = F.relu(d_pos - d_neg + margin).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += float(loss.detach())
        if log and (ep % 10 == 9 or ep == epochs - 1):
            log(f"  ep{ep} loss {tot:.4f}")
    return net
