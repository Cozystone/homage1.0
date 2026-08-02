# -*- coding: utf-8 -*-
"""Learned router: stable features, trainable, sane predictions on core intents."""
from __future__ import annotations

import numpy as np

from packages.learned_router.router import _hash_features, predict, router_available


def test_features_are_deterministic_and_normalized():
    a = _hash_features("대한민국의 수도는?")
    b = _hash_features("대한민국의 수도는?")
    assert np.array_equal(a, b)
    assert abs(float(np.linalg.norm(a)) - 1.0) < 1e-5


def test_predict_without_model_is_no_opinion_or_valid():
    label, conf = predict("넌 누구니")
    if router_available():
        assert label != "" and 0.0 <= conf <= 1.0
    else:
        assert (label, conf) == ("", 0.0)


def test_router_discriminates_distinct_intents():
    """Scheme-agnostic: the router now DISTILLS the rule lanes (2026-07-10), so its label
    vocabulary is whatever the flywheel taught it (lanes), not a fixed intent list. So assert
    what actually matters — it DISCRIMINATES: clearly different question types must not all
    collapse to one label, and every prediction is a valid (label, confidence)."""
    if not router_available():
        return  # no model trained in this checkout — honest skip
    probes = ["넌 누구니", "3 더하기 4는?", "사랑이란?", "안녕", "시 하나 지어줘"]
    preds = [predict(q) for q in probes]
    for label, conf in preds:
        assert label != "" and 0.0 <= conf <= 1.0
    labels = {label for label, _c in preds}
    assert len(labels) >= 3  # distinct intents get distinct routes (not collapsed to one)
