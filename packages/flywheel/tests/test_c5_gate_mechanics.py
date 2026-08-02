# -*- coding: utf-8 -*-
"""Unit-level guards for the C5 flywheel gate (scripts/eval_c5_flywheel_gate.py).

The gate itself trains three routers and takes minutes, so it is run by hand / in the pillar
sweep. What MUST stay true cheaply is the machinery that makes its verdict meaningful:
the holdout really is sealed, the anti-wireheading seal is really checked, and scoring counts an
unpredictable label as a MISS (not a skip, which would reward an ignorant model)."""
import importlib.util
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "c5_gate", REPO / "scripts" / "eval_c5_flywheel_gate.py")
c5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c5)


def test_split_is_stable_and_partitions():
    """A turn must always land on the same side — otherwise the 'sealed' holdout leaks into
    training between runs and the gain is measured against data the model has seen."""
    qs = [f"question number {i}" for i in range(400)]
    first = [c5._split(q) for q in qs]
    second = [c5._split(q) for q in qs]
    assert first == second
    assert set(first) == {"train", "holdout"}
    held = sum(1 for s in first if s == "holdout")
    assert 0.15 < held / len(qs) < 0.45          # ~30% reserved, not degenerate


def test_seal_check_reports_oracle_state():
    """The anti-wireheading precondition must actually consult the frozen oracle."""
    ok, note = c5._seal_ok()
    assert isinstance(ok, bool) and isinstance(note, str) and note
    if ok:
        assert "intact" in note


def test_score_counts_unpredictable_label_as_miss(tmp_path):
    """An unseen lane must count against the model. If it were skipped, a router that knows only
    one label would score 1.0 by being ignorant of every other — the opposite of the gate's point."""
    from packages.learned_router.router import DIM

    classes = ["alpha"]
    W = np.zeros((1, DIM), dtype=np.float32)
    b = np.zeros(1, dtype=np.float32)
    mp, meta = tmp_path / "m.npz", tmp_path / "m.json"
    np.savez_compressed(mp, W=W, b=b)
    meta.write_text('{"classes": ["alpha"]}', encoding="utf-8")

    # half the holdout carries a label this model cannot emit
    pairs = [("q one", "alpha"), ("q two", "beta")]
    acc = c5._score(mp, meta, pairs)
    assert acc == 0.5, f"unseen label must be a miss, got {acc}"
    assert set(classes) == {"alpha"}
