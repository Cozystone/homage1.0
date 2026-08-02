# -*- coding: utf-8 -*-
"""SEALED C5 gate — does ATANOR's self-improvement flywheel actually IMPROVE ATANOR, with no
human in the loop? The ①②③/C1-grade gate for the pillar.

WHAT IS BEING CLAIMED (bounded, per the FINAL PLAN charter)
 NOT "it gets smarter without limit" — that is the honest-null the charter forbids claiming.
 The bounded claim, and the only one measured here: **the rules teach their own replacement**
 ([[rules-are-training-wheels]]). The hand-written rule LANES act as weak supervision; the
 learned router distils them; and as ATANOR accumulates MORE OF ITS OWN logged experience, the
 distilled router should get better ON TURNS IT HAS NEVER SEEN. That is a real self-improvement
 gain — the system improving from its own operation, with zero human labels — and it is capped
 by the teacher, which is exactly why it is safe to state.

WHY THIS DESIGN
 · SEALED HOLDOUT. router_readiness() scores agreement on the same rows the router trained from,
 so it cannot separate learning from memorising. Here a stable hash reserves 30% of the log that
 training never touches, and every number is reported on that.
 · GROWING EXPERIENCE. Cycles train on 25% -> 50% -> 100% of the remaining log, simulating the
 flywheel accumulating turns. Gain = holdout accuracy at full experience minus at quarter.
 · NO HUMAN LABELS. The production distiller merges a human/battery gold set x10 (anti
 self-poisoning). This gate deliberately EXCLUDES it: the question is what the machine achieves
 from its OWN turns. Human labels would make a "no human in the loop" claim false.
 · ANTI-WIREHEADING PRECONDITION. The frozen oracle's seal must verify. That oracle is the fixed
 exam a candidate Critic must beat before it may replace the incumbent; if its seal is broken,
 the evaluator is editable, self-improvement becomes reward hacking, and the gate FAILS outright
 regardless of the accuracy numbers.
 · NEVER CLOBBERS THE LIVE ROUTER. Every cycle trains to a temp path (train(out_path=...)).

Gate declared before the run: seal intact AND gain > 0 AND full-experience holdout >= quarter.
Run: python scripts/eval_c5_flywheel_gate.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np  # noqa: E402


def _split(q: str) -> str:
    """Stable hash split — the same turn always lands on the same side, so the holdout is sealed
    across runs and cannot drift into training."""
    return "holdout" if int(hashlib.sha1(q.encode("utf-8")).hexdigest(), 16) % 100 < 30 else "train"


def _seal_ok() -> tuple[bool, str]:
    """The anti-wireheading precondition: the frozen oracle must still match its checksum."""
    try:
        from packages.evolution import frozen_oracle as fo

        oracle = fo.ensure_oracle()
        recomputed = fo._seal(oracle["pairs"])
        ok = bool(recomputed == oracle.get("seal"))
        n = sum(len(v) for v in oracle["pairs"].values())
        return ok, f"{'intact' if ok else 'BROKEN'} ({n} sealed judgments)"
    except Exception as exc:  # pragma: no cover
        return False, f"unavailable ({type(exc).__name__}: {exc})"


def _score(model_path: Path, meta_path: Path, pairs: list[tuple[str, str]]) -> float:
    """Accuracy of a trained router on the sealed holdout. The model is an .npz of (W, b) plus a
    meta json of class names — loaded directly so the LIVE router is never touched."""
    from packages.learned_router.router import _hash_features

    d = np.load(model_path)
    W, b = d["W"], d["b"]
    classes = json.loads(meta_path.read_text(encoding="utf-8"))["classes"]
    ok = 0
    for q, lane in pairs:
        # a lane this cycle never saw counts as a miss, not a skip — otherwise a narrow model
        # would score high simply by being ignorant of the labels it cannot produce
        p = W @ _hash_features(q) + b
        if classes[int(np.argmax(p))] == lane:
            ok += 1
    return ok / max(1, len(pairs))


def main() -> int:
    print("=== C5 sealed flywheel gate (self-improvement from ATANOR's own turns) ===\n")

    seal, seal_note = _seal_ok()
    print(f"[anti-wireheading] frozen oracle seal: {seal_note}")

    from packages.flywheel.self_improvement import _rows

    rows = _rows()
    pairs = [(str(r.get("q") or ""), str(r.get("lane") or "")) for r in rows
             if r.get("q") and r.get("lane")]
    # de-dup so a repeated question cannot sit on both sides of the split
    seen: set[str] = set()
    uniq: list[tuple[str, str]] = []
    for q, lane in pairs:
        if q not in seen:
            seen.add(q)
            uniq.append((q, lane))
    train_all = [p for p in uniq if _split(p[0]) == "train"]
    holdout = [p for p in uniq if _split(p[0]) == "holdout"]
    print(f"[data] {len(uniq)} unique logged turns -> train {len(train_all)} / SEALED holdout {len(holdout)}")
    if len(train_all) < 200 or len(holdout) < 80:
        print("\nnot enough logged experience yet to measure a flywheel gain")
        return 1

    from packages.learned_router.router import train

    results = []
    for frac in (0.25, 0.5, 1.0):
        cut = max(40, int(len(train_all) * frac))
        subset = train_all[:cut]
        if len({l for _q, l in subset}) < 2:
            continue
        with tempfile.TemporaryDirectory() as td:
            mp, meta = Path(td) / "cand.npz", Path(td) / "cand_meta.json"
            train(subset, out_path=mp, meta_path=meta)
            acc = _score(mp, meta, holdout)
        results.append((frac, cut, acc))
        print(f"[cycle] experience {int(frac*100):>3}% ({cut:>5} turns) -> SEALED holdout accuracy {acc:.4f}")

    if len(results) < 2:
        print("\ncould not run enough cycles")
        return 1
    first, last = results[0][2], results[-1][2]
    gain = last - first
    print(f"\n=== flywheel gain (full experience - quarter) = {gain:+.4f}")
    gate = seal and gain > 0 and last >= first
    print(f"=== C5 SEALED GATE (seal intact AND gain>0): {'PASS' if gate else 'not yet'}")
    print("\nSCOPE (honest): this measures IMITATION of the rule teacher from ATANOR's own logged\n"
          "turns with zero human labels — a bounded flywheel. It is capped by the rules' own\n"
          "quality and is NOT evidence of open-ended capability gain.")
    return 0 if gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
