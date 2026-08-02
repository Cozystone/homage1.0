# -*- coding: utf-8 -*-
"""The CARLA depth corpus, split so the number at the end means something.

THE SPLIT IS THE INSTRUMENT, and getting it wrong is the easiest way to produce an impressive
meaningless score. Consecutive frames of one drive are near-duplicates: at 20 Hz a car moves a few
centimetres between ticks, so frame 100 and frame 101 are the same picture. A random frame-level
split therefore puts near-copies of every validation image into training, and a model that has
memorised nothing but the corpus still reports excellent depth. The failure is silent — the loss
curve looks healthy and the metric looks strong.

So the split is BY TOWN, and two validation sets are reported rather than one:

  held-out TOWN      towns the model has never seen. This is generalisation.
  held-out EPISODE   a different drive, different weather, in a town it HAS seen. Easier, and worth
                     reporting beside the first, because the gap between them is the size of the
                     town-memorisation effect. One number cannot show that; two can.

Frames are read through `packages.eye.EpisodeSource`, the same door a screen or a camera comes
through, so nothing learned here is learned from a path that only CARLA data can take.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

ROOT = Path(r"D:\carla\episodes")

# Held out before any training run and not chosen by looking at results. Town06 and Town07 are one
# episode each, which is small -- so the reading they give is noisy and is reported with its n.
#
# FROZEN AFTER THE FIRST RESULT, deliberately. Run 1 (6 training towns, 1,060 frames) read
# val_town absrel 0.385 / delta1 0.357 against a constant baseline of 0.476 / 0.368 -- better on
# absrel, AT OR BELOW baseline on delta1, i.e. no reliable generalisation to an unseen town. Meanwhile
# val_episode reached 0.174 / 0.753. That gap is exactly what a town-level split exists to expose,
# and an episode-level split would have reported the 0.174 as the headline.
#
# The obvious next move is more training towns, and the temptation that comes with it is to widen or
# reshuffle the held-out set at the same time. That would change the measuring stick and the
# intervention together, and no comparison would survive it. So Town06 and Town07 stay exactly as
# they are; new towns go to TRAINING only. If val_town then improves, the cause is diversity, which
# is the thing being tested.
VAL_TOWNS = ("Town06", "Town07")
VAL_EPISODE_FRACTION = 0.15          # of the TRAIN towns' episodes, held out whole


@dataclass(frozen=True)
class Split:
    train: tuple[str, ...]
    val_town: tuple[str, ...]        # unseen towns  -> generalisation
    val_episode: tuple[str, ...]     # unseen drives in seen towns -> memorisation gap
    towns: dict[str, str]

    def as_dict(self) -> dict:
        return {"train_episodes": len(self.train), "val_town_episodes": len(self.val_town),
                "val_episode_episodes": len(self.val_episode),
                "val_towns": sorted({self.towns[e] for e in self.val_town}),
                "train_towns": sorted({self.towns[e] for e in self.train})}


def build_split(root: Path = ROOT, seed: int = 7) -> Split:
    """Episode names grouped by town. Deterministic given the corpus and the seed."""
    towns: dict[str, str] = {}
    for meta in sorted(root.glob("ep*/meta.json")):
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            continue
        towns[meta.parent.name] = str(m.get("map", "?")).split("/")[-1].replace("_Opt", "")

    val_town = tuple(sorted(e for e, t in towns.items() if t in VAL_TOWNS))
    rest = sorted(e for e in towns if e not in val_town)

    rng = np.random.default_rng(seed)
    n_hold = max(1, int(round(len(rest) * VAL_EPISODE_FRACTION)))
    idx = rng.permutation(len(rest))[:n_hold]
    val_ep = tuple(sorted(rest[i] for i in idx))
    train = tuple(e for e in rest if e not in val_ep)
    return Split(train=train, val_town=val_town, val_episode=val_ep, towns=towns)


def frames(episodes: tuple[str, ...], root: Path = ROOT, stride: int = 1) -> list[Path]:
    """Frame paths, optionally strided.

    `stride` is not an optimisation: at 20 Hz, taking every frame gives the loss thousands of copies
    of the same view and the effective dataset is far smaller than its file count. Striding by ~10
    (half a second of driving) buys genuine variety per step."""
    out: list[Path] = []
    for ep in episodes:
        out.extend(sorted((root / ep).glob("*.npz"))[::stride])
    return out


def load(path: Path, size: tuple[int, int] = (320, 240)) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(rgb float32 CHW in [0,1], depth metres HW, valid mask HW).

    Sky is EXCLUDED from the valid mask. Its ground truth is exactly the 1000m far plane, which is
    not a distance to a surface -- it is "no surface". Training on it would ask the model to
    regress a sentinel, and because sky is a large fraction of a city frame it would dominate the
    loss and drag every real prediction toward infinity."""
    z = np.load(path)
    rgb = z["rgb"]
    dep = z["depth_m"].astype(np.float32)
    sem = z["semantic"]

    h, w = size[1], size[0]
    ys = (np.arange(h) * (rgb.shape[0] / h)).astype(np.int32)
    xs = (np.arange(w) * (rgb.shape[1] / w)).astype(np.int32)
    rgb = rgb[ys][:, xs]
    dep = dep[ys][:, xs]
    sem = sem[ys][:, xs]

    valid = (sem != 11) & (dep > 0.5) & (dep < 200.0)      # 11 = Sky; also drop the far tail
    return (rgb.transpose(2, 0, 1).astype(np.float32) / 255.0, dep, valid)


def batches(paths: list[Path], batch: int, *, size: tuple[int, int] = (320, 240),
            shuffle: bool = True, seed: int = 0) -> Iterator[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    order = np.arange(len(paths))
    if shuffle:
        np.random.default_rng(seed).shuffle(order)
    for i in range(0, len(order) - batch + 1, batch):
        chunk = [load(paths[j], size) for j in order[i:i + batch]]
        yield (np.stack([c[0] for c in chunk]),
               np.stack([c[1] for c in chunk]),
               np.stack([c[2] for c in chunk]))
