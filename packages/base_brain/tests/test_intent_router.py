# -*- coding: utf-8 -*-
"""Learned intent router tests — the retirement of the hand-regex english-intent wheel.

Pin: the generated corpus is >= 600 samples across all five classes, the held-out accuracy clears the
0.9 target, the pinned realcity probes route correctly, and generation/split are deterministic (so the
held-out number is reproducible offline).
"""
from __future__ import annotations

import json

from packages.base_brain import intent_router as ir
from packages.base_brain.intent_router import CLASSES, IntentRouter, train_and_save


def test_corpus_is_large_and_covers_all_classes():
    rows = ir._gen()
    assert len(rows) >= 600, len(rows)
    labels = {y for _, y in rows}
    assert labels == set(CLASSES), labels
    # each class has a real presence (not a token handful)
    for c in CLASSES:
        assert sum(1 for _, y in rows if y == c) >= 20, c


def test_heldout_accuracy_clears_target():
    m = train_and_save()
    assert m["held_n"] >= 100, m["held_n"]
    assert m["held_accuracy"] >= 0.9, m
    for c, acc in m["held_per_class"].items():
        assert acc >= 0.75, (c, acc)          # no class collapses


def test_saved_weights_report_heldout():
    data = json.loads(ir._WEIGHTS_PATH.read_text(encoding="utf-8"))
    assert data["classes"] == CLASSES
    assert data["held_accuracy"] >= 0.9


def test_pinned_realcity_probes_route_correctly():
    r = IntentRouter.load()
    assert r.classify("hello how are you")[0] == "social"
    assert r.classify("what did I eat for breakfast yesterday?")[0] == "personal_unknowable"
    assert r.classify("what is happening here")[0] == "self_situation"
    assert r.classify("where are you right now?")[0] == "self_situation"
    assert r.classify("who are you?")[0] == "self_situation"
    assert r.classify("what are you doing?")[0] == "self_situation"
    assert r.classify("what is the capital of France?")[0] == "relational"
    # both knowledge classes route to the base_brain knowledge lane in realcity
    assert r.classify("what is photosynthesis?")[0] == "define"
    for q in ("what is the exact population of Mars in 2099?",
              "A cup is at the edge of the table and someone bumped it. What happens?",
              "The tunnel is blocked by rubble. Can the bus pass through the tunnel?"):
        assert r.classify(q)[0] in ("define", "relational"), q


def test_generation_and_split_are_deterministic():
    m1 = train_and_save()
    m2 = train_and_save()
    assert m1["held_accuracy"] == m2["held_accuracy"]
    assert m1["train_n"] == m2["train_n"] and m1["held_n"] == m2["held_n"]


def test_features_are_extracted_not_labels():
    """A regex probe lights a feature; it never sees the class label."""
    f = ir.extract_features("what is the capital of France?")
    assert f["rel_of"] == 1.0 and f["wh_lead"] == 1.0
    assert set(f.keys()) == set(ir.FEATURE_NAMES)
