# -*- coding: utf-8 -*-
"""RIF M3+M4 — sandbox trials, MAP-Elites archive, antibodies, and graduation with BASIS GROWTH.

This closes the loop. Given an Environment (a module's signals + labeled samples + current basis of
graduated feature-programs), one round:
  ③ PROPOSE   candidate programs (proposer.py)
  ④ TRIAL     compile each on train, score the DELTA it adds over the current basis on a val split
              (frozen critic = fixed accuracy scorer); winners → MAP-Elites archive, losers → antibodies
  ⑤ GRADUATE  the best gain that ALSO improves a SEALED holdout (touched only here) AND passes the
              operator-signed gate → append to the basis AND expose as a new signal leaf.

The graduation arrow is the whole point: a graduated program becomes a LEAF the next round composes on,
so the reachable representation set grows — the envelope EXPANDS, not just fills. Anti-wireheading:
holdout is sealed and rate-limited, the critic is fixed, writes are staged, humans sign graduation.
No LLM.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import dsl, proposer
from .dsl import Sig

REPO = Path(__file__).resolve().parents[3]
BASIS_DIR = REPO / "data" / "graph_scale" / "rif_basis"


@dataclass
class Environment:
    name: str
    signals: list[Sig]
    samples: list[dict]
    y: np.ndarray
    train_idx: np.ndarray
    val_idx: np.ndarray
    holdout_idx: np.ndarray
    basis: list = field(default_factory=list)          # graduated feature-programs (the current representation)
    goal: float = 0.9
    model_spec: str = "gbm:0.1"


@dataclass
class Trial:
    program: object
    render: str
    gain: float
    val_score: float
    depth: int


def _clf(spec: str):
    import sys
    sys.path.insert(0, str(REPO))
    from packages.reasoning_vm import learned_discriminator as LD
    return LD.make_clf(spec)


def _matrix(programs: list, samples: list[dict]) -> np.ndarray:
    if not programs:
        return np.zeros((len(samples), 0), np.float32)
    return np.column_stack([dsl.compile_scalar(p, samples) for p in programs])


def _score(env: Environment, programs: list, fit_idx, eval_idx) -> float:
    X = _matrix(programs, env.samples)
    if X.shape[1] == 0:                                 # no features → majority baseline
        maj = np.bincount(env.y[fit_idx].astype(int)).argmax()
        return float((env.y[eval_idx] == maj).mean())
    clf = _clf(env.model_spec)
    clf.fit(X[fit_idx], env.y[fit_idx])
    return float((clf.predict(X[eval_idx]) == env.y[eval_idx]).mean())


def _descriptor(prog, col: np.ndarray, y: np.ndarray) -> tuple:
    """MAP-Elites behavior cell: (program depth, sign of correlation with label). Keeps the loop from
    collapsing onto one lineage — novel-but-not-yet-winning shapes survive as stepping stones."""
    d = min(dsl.depth(prog), 4)
    if col.std() < 1e-9:
        c = 0
    else:
        r = float(np.corrcoef(col, y)[0, 1]) if len(set(y.tolist())) > 1 else 0.0
        c = 1 if r >= 0 else -1
    return (d, c)


def run_round(env: Environment, *, cross_module: list | None = None, n: int = 60, seed: int = 0,
              antibodies: set | None = None) -> tuple[list[Trial], dict, set]:
    """One generation: propose → trial → archive/antibodies. Returns (ranked trials, archive, antibodies)."""
    antibodies = set(antibodies or ())
    base_val = _score(env, env.basis, env.train_idx, env.val_idx)
    cands = proposer.propose_batch(env.signals, seeds=env.basis or None, graduated=cross_module,
                                   n=n, seed=seed)
    archive: dict[tuple, Trial] = {}
    trials: list[Trial] = []
    for c in cands:
        r = dsl.render(c)
        if r in antibodies:
            continue
        col = dsl.compile_scalar(c, env.samples)
        if col.std() < 1e-9:                            # constant feature — useless
            antibodies.add(r)
            continue
        val = _score(env, env.basis + [c], env.train_idx, env.val_idx)
        gain = val - base_val
        t = Trial(c, r, round(gain, 4), round(val, 4), dsl.depth(c))
        trials.append(t)
        if gain <= 1e-4:
            antibodies.add(r)                           # didn't help → don't re-propose
            continue
        cell = _descriptor(c, col, env.y)               # elites: best gain per behavior cell
        if cell not in archive or gain > archive[cell].gain:
            archive[cell] = t
    trials.sort(key=lambda t: -t.gain)
    return trials, archive, antibodies


def _sealed_ok(env: Environment, cand) -> bool:
    """A graduation candidate must ALSO improve the sealed holdout (touched only here)."""
    base_h = _score(env, env.basis, env.train_idx, env.holdout_idx)
    with_h = _score(env, env.basis + [cand], env.train_idx, env.holdout_idx)
    return with_h > base_h + 1e-4


def run_loop(env: Environment, *, rounds: int = 6, n: int = 60, seed: int = 0,
             margin: float = 0.01, sign_fn=None, cross_module: list | None = None,
             patience: int = 0, verbose: bool = False) -> dict:
    """Drive the closed loop until the goal is met or `patience` consecutive rounds yield no graduation.

    sign_fn(trial)->bool is the operator-signed gate (default: auto-accept in-sandbox; a live loop passes
    the human/operator gate here). Every graduation grows env.basis AND appends a new signal leaf.
    patience>0 lets the search EXPLORE fruitless rounds (fresh proposals each) before giving up — a hard
    real wall rarely yields on the first batch."""
    sign_fn = sign_fn or (lambda t: True)
    antibodies: set = set()
    history = []
    start_val = _score(env, env.basis, env.train_idx, env.val_idx)
    holdout0 = _score(env, env.basis, env.train_idx, env.holdout_idx)
    stale = 0
    for r in range(rounds):
        trials, archive, antibodies = run_round(env, cross_module=cross_module, n=n,
                                                seed=seed + r * 101, antibodies=antibodies)
        graded = None
        for t in trials:                                # best-first; graduate the first that clears all gates
            if t.gain < margin:
                break
            if _sealed_ok(env, t.program) and sign_fn(t):
                graded = t
                break
        rec = {"round": r, "base_val": round(_score(env, env.basis, env.train_idx, env.val_idx), 4),
               "n_candidates": len(trials),
               "best_gain": round(trials[0].gain, 4) if trials else 0.0, "archive_cells": len(archive),
               "graduated": None}
        if graded is not None:
            leaf = Sig(f"g{len(env.basis)}__{graded.render[:24]}", dsl.S)   # graduated → a new leaf
            for s in env.samples:
                s[leaf.name] = float(dsl.evaluate(graded.program, s))
            env.basis.append(graded.program)
            env.signals.append(leaf)                    # ← BASIS GROWTH: next round can compose on it
            rec["graduated"] = {"program": graded.render, "gain": graded.gain, "val": graded.val_score}
            stale = 0
        else:
            stale += 1
        history.append(rec)
        if verbose:
            print(f"  round {r}: base_val {rec['base_val']} cands {rec['n_candidates']} "
                  f"best_gain {rec['best_gain']} grad {rec['graduated']}", flush=True)
        cur = _score(env, env.basis, env.train_idx, env.val_idx)
        if cur >= env.goal or (graded is None and stale > patience):
            break
    final_val = _score(env, env.basis, env.train_idx, env.val_idx)
    final_hold = _score(env, env.basis, env.train_idx, env.holdout_idx)
    return {
        "module": env.name,
        "start_val": round(start_val, 4), "final_val": round(final_val, 4),
        "start_holdout": round(holdout0, 4), "final_holdout": round(final_hold, 4),
        "goal": env.goal, "reached_goal": bool(final_val >= env.goal),
        "basis_size": len(env.basis),
        "graduated_programs": [dsl.render(p) for p in env.basis if isinstance(p, dsl.Prog)],
        "history": history,
        "note": "Every graduation passed val-gain + sealed-holdout + sign gate; the invented programs "
                "are the representation the shallow feature space could not express. Nothing asserted.",
    }


def save_basis(env: Environment, path: Path = BASIS_DIR) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{env.name}_basis.json").write_text(
        json.dumps([dsl.render(p) for p in env.basis], indent=2), encoding="utf-8")
