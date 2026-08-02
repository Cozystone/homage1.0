# -*- coding: utf-8 -*-
"""Putting a NAME on something ATANOR already recognises — with a few anchors, and silence when unsure.

    from packages.perception import naming
    book = naming.anchor_from(net, {"car": car_patches, "road": road_patches})
    naming.name_of(net, book, patch)        # -> ("car", 0.71) or (None, margin) when it will not guess

WHAT WAS MISSING, and it was one specific thing. `learned_signature` learns what makes two views the SAME
thing, with no labels at all -- positives come from tracking, so nothing was ever told what a car is. That
gives IDENTITY: "this again". `object_recognition` answers "is this a known instance". Neither of them
gives a NAME, and that gap is what an external open-vocabulary detector was quietly filling.

It turns out the gap is small. Measured 2026-07-31 on CARLA patches, the 103 KB signature encoder already
separates material classes it was never taught -- road against building at cosine 0.041, road against
vegetation at -0.370 -- so the clusters exist and only lack words. Naming is then a handful of labelled
anchors per class: a fact about which cluster carries which word, which is a graph edge and not a model.

    103 KB, label-free training, 32-dim   vs   593 MB, 155M params, ~200 ms/frame

ABSTENTION IS THE WHOLE DESIGN, not a safety wrapper on it. The external detector reached precision 0.51 on
this corpus with recall 0.95 -- it sees nearly everything that is there and invents about as much again,
claiming traffic lights and poles in every frame of a street that had none. A namer that says nothing when
the nearest cluster is not clearly nearest can be wrong far less often, and being right less often about
things it declines to name is the trade this project has already decided to make everywhere else.

The margin is between the best and second-best cosine, not the best alone. A patch sitting equally close to
two clusters is not weak evidence for the closer one; it is evidence that the space cannot tell them apart
here, which is a different thing and deserves silence rather than a coin flip.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class NameBook:
    """Which cluster carries which word. Plain data, versionable, and revocable one name at a time.

    Deliberately not weights. A wrong name is removed by deleting a row, the way a wrong fact is retracted
    from a graph -- not by retraining something that has absorbed it."""

    centroids: dict[str, np.ndarray] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"names": {k: [round(float(x), 6) for x in v] for k, v in self.centroids.items()},
                "anchors_per_name": dict(self.counts)}

    def save(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.as_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "NameBook":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(centroids={k: np.asarray(v, np.float32) for k, v in d["names"].items()},
                   counts=dict(d.get("anchors_per_name", {})))

    def forget(self, name: str) -> None:
        """Retract one name. The reason this is data and not weights."""
        self.centroids.pop(name, None)
        self.counts.pop(name, None)


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def anchor_from(embeddings: dict[str, np.ndarray]) -> NameBook:
    """Build the book from already-embedded anchors: {name: (n, dim) array}."""
    book = NameBook()
    for name, e in embeddings.items():
        e = np.asarray(e, np.float32)
        if e.ndim == 1:
            e = e[None]
        if not len(e):
            continue
        book.centroids[name] = _unit(e.mean(0))
        book.counts[name] = int(len(e))
    return book


def name_of(book: NameBook, embedding: np.ndarray, min_cosine: float = 0.78,
            min_margin: float = 0.0):
    """(name, closeness) when the patch sits close to a known cluster; (None, closeness) when it does not.

    THE CONFIDENCE SIGNAL IS CLOSENESS, NOT MARGIN, and the first version had it backwards. Refusing on a
    small best-minus-second gap LOWERED precision at five of six anchor counts, which sent me to measure
    whether either quantity predicts correctness at all:

        margin (best - second)   AUC 0.338   <- ANTI-predictive: wrong answers have the LARGER margin
        best cosine alone        AUC 0.768   <- the real signal
        correct mean margin 0.116 vs wrong 0.203   |   correct mean cosine 0.815 vs wrong 0.678

    The reason margin inverts is visible in the space itself. `road` is isolated -- cosine 0.041 to
    buildings -- so anything landing near it wins by a wide gap, including flat grey patches that are not
    road. That is confident and wrong. Meanwhile the correct answers live in the crowded
    building/vegetation region, where cosine 0.841 leaves almost no gap at all. Margin measures how
    ISOLATED the winning cluster is, which has nothing to do with whether this patch belongs to it.

    `min_margin` is kept at 0 and left in the signature deliberately: someone will reach for it again, and
    the docstring should be the thing they find."""
    if not book.centroids:
        return None, 0.0
    v = _unit(np.asarray(embedding, np.float32))
    sims = sorted(((float(v @ c), n) for n, c in book.centroids.items()), reverse=True)
    best, name = sims[0]
    second = sims[1][0] if len(sims) > 1 else -1.0
    if best < min_cosine or (min_margin and best - second < min_margin):
        return None, best
    return name, best


def name_many(book: NameBook, embeddings: np.ndarray, **kw):
    return [name_of(book, e, **kw) for e in np.asarray(embeddings, np.float32)]


def coverage(results) -> dict:
    """How often it spoke, which is the number that stops abstention from being a free pass.

    A namer that abstains on everything has perfect precision and is useless, so coverage is reported
    beside accuracy always -- the same rule the conformal membrane already lives under."""
    named = [r for r in results if r[0] is not None]
    return {"n": len(results), "named": len(named),
            "coverage": (len(named) / len(results)) if results else 0.0}
