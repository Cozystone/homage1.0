# -*- coding: utf-8 -*-
"""RIF M0 — the Ceiling Prober: mechanized ARCHITECTURAL credit assignment (oracle-gap analysis).

The one thing the flywheels could never do: tell WHETHER a plateau is a data/training wall (keep
learning) or a REPRESENTATION wall (the feature space cannot express the distinction at all — no
amount of learning within it will help; a new representational primitive must be invented).

The trick that mechanizes it: **train-on-eval separability**. Fit a deliberately-overfit,
high-capacity model ON the evaluation slice itself and score it on that same slice. If even
memorization-grade capacity cannot separate the classes through the current features, the classes
OVERLAP in feature space — an information-theoretic wall, not a training deficiency.

Verdict rule (per module):
    score ≈ oracle  and  oracle < goal   →  REPRESENTATION WALL  → fire the invention flywheel (M2+)
    score ≪ oracle                       →  TRAINING/DATA WALL   → fire the ordinary flywheel
    oracle ≈ goal   and  score ≈ goal    →  no wall — module is done

Everything is a measurement; nothing is a claim. First dataset: the SQuAD 2.0 reader
(data/graph_scale/rif_probe/{gate,ranker}_{X,y}.npy dumped by scripts/train_squad.py).
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
PROBE_DIR = REPO / "data" / "graph_scale" / "rif_probe"

# margins: measurement noise tolerance for "≈" in the verdict rule
_NEAR = 0.05          # score within 5 points of oracle counts as "at the ceiling"
_FAR = 0.15           # score more than 15 points under oracle counts as "far below"


@dataclass
class ProbeReport:
    module: str
    n: int
    dim: int
    class_balance: float          # fraction of positive labels
    majority_acc: float           # trivial baseline (predict majority class)
    current_acc: float | None     # honest CV accuracy of the deployed model class (5-fold)
    oracle_acc: float             # train-on-eval separability ceiling through current features
    goal_acc: float
    verdict: str                  # representation_wall | training_wall | done | inconclusive
    note: str
    elapsed_s: float


def _overfit_oracle(X: np.ndarray, y: np.ndarray) -> float:
    """Memorization-grade separability: 1-NN leave-one-out is the cleanest 'can ANY function of these
    features separate the classes' probe — duplicate/contradictory feature rows are the only failures."""
    from sklearn.neighbors import KNeighborsClassifier

    n = len(y)
    if n > 20_000:                                    # LOO on 20k is plenty; subsample for cost
        idx = np.random.RandomState(0).permutation(n)[:20_000]
        X, y = X[idx], y[idx]
        n = len(y)
    # leave-one-out via k=2 trick: nearest neighbour excluding self = 2nd neighbour of self-inclusive fit
    knn = KNeighborsClassifier(n_neighbors=2)
    knn.fit(X, y)
    _dist, ind = knn.kneighbors(X, n_neighbors=2)
    nn1 = np.where(ind[:, 0] == np.arange(n), ind[:, 1], ind[:, 0])   # first non-self neighbour
    return float((y[nn1] == y).mean())


def _honest_cv(X: np.ndarray, y: np.ndarray, spec: str = "gbm:0.1") -> float:
    """5-fold CV accuracy of the DEPLOYED model class — the honest 'current' for the verdict."""
    from sklearn.model_selection import cross_val_score

    import sys
    sys.path.insert(0, str(REPO))
    from packages.reasoning_vm import learned_discriminator as LD

    n = len(y)
    if n > 60_000:
        idx = np.random.RandomState(1).permutation(n)[:60_000]
        X, y = X[idx], y[idx]
    return float(cross_val_score(LD.make_clf(spec), X, y, cv=5, scoring="accuracy").mean())


def probe(module: str, X: np.ndarray, y: np.ndarray, goal_acc: float,
          model_spec: str = "gbm:0.1", run_cv: bool = True) -> ProbeReport:
    t0 = time.time()
    y = y.astype(int)
    bal = float(y.mean())
    maj = float(max(bal, 1 - bal))
    oracle = _overfit_oracle(X.astype(np.float32), y)
    cur = _honest_cv(X.astype(np.float32), y, model_spec) if run_cv else None

    goal = float(goal_acc)
    if cur is None:
        verdict, note = "inconclusive", "no current-model CV run"
    elif oracle < goal - _NEAR and cur >= oracle - _NEAR:
        verdict = "representation_wall"
        note = (f"even memorization through these features caps at {oracle:.3f} < goal {goal:.2f}; "
                f"the classes overlap in feature space — invent a new primitive (fire M2)")
    elif cur < oracle - _FAR:
        verdict = "training_wall"
        note = (f"features separate up to {oracle:.3f} but the deployed model realizes {cur:.3f} — "
                f"more data/negatives/model capacity, not new representation")
    elif cur >= goal - _NEAR:
        verdict = "done"
        note = "module at goal within tolerance"
    else:
        verdict = "inconclusive"
        note = f"cur {cur:.3f} within {_FAR} of oracle {oracle:.3f}; both below goal — mixed wall"
    return ProbeReport(module=module, n=int(len(y)), dim=int(X.shape[1]), class_balance=round(bal, 4),
                       majority_acc=round(maj, 4), current_acc=None if cur is None else round(cur, 4),
                       oracle_acc=round(oracle, 4), goal_acc=goal, verdict=verdict, note=note,
                       elapsed_s=round(time.time() - t0, 1))


def probe_squad_dumps(goal_gate: float = 0.80, goal_ranker: float = 0.90) -> list[ProbeReport]:
    """Probe the SQuAD reader's two learned modules from the dumped matrices. Goals are honest task
    targets: gate 0.80 (competitive answerability), ranker 0.90 (per-candidate binary accuracy needed
    for high top-1 pick among ~dozens of candidates)."""
    out = []
    for module, goal in (("squad_gate", goal_gate), ("squad_ranker", goal_ranker)):
        fx, fy = PROBE_DIR / f"{module.split('_')[1]}_X.npy", PROBE_DIR / f"{module.split('_')[1]}_y.npy"
        if not fx.exists():
            continue
        X, y = np.load(fx), np.load(fy)
        out.append(probe(module, X, y, goal))
    if out:
        PROBE_DIR.mkdir(parents=True, exist_ok=True)
        (PROBE_DIR / "probe_report.json").write_text(
            json.dumps([asdict(r) for r in out], indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for r in probe_squad_dumps():
        print(json.dumps(asdict(r), ensure_ascii=False, indent=2))
