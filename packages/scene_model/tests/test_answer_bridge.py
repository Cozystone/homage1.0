# -*- coding: utf-8 -*-
"""scene_relational_answer: the same (dict-or-None) contract resolve_relational uses, plus the
wall-clock budget that keeps a huge-extension composition from adding latency to the live path."""
from __future__ import annotations

import time

import numpy as np
import pytest

from packages.scene_model import answer_bridge as B


class _Store:
    class _Terms:
        def __init__(self, labels): self._l = labels
        def term(self, i): return self._l[i]
        def lookup(self, t): return self._l.index(t) if t in self._l else None

    def __init__(self, triples):
        labels = []
        for row in triples:
            for x in row:
                if x not in labels:
                    labels.append(x)
        self._t = triples
        self.terms = self._Terms(labels)
        self._c = {k: np.array([labels.index(r[i]) for r in triples], dtype="<i4")
                   for i, k in enumerate(("s", "p", "o"))}

    def open_columns(self): return self._c
    def facts_about(self, subject, limit=60):
        return [t for t in self._t if t[0] == subject][:limit]


WORLD = [
    ("France", "is_a", "Country"), ("France", "capital", "Paris"),
    ("Japan", "is_a", "Country"), ("Japan", "capital", "Tokyo"),
    ("Nauru", "is_a", "Country"),
]


def test_answers_the_shape_the_relational_lane_cannot_represent():
    core = B.scene_relational_answer(
        "Which countries have no capital?", language="en", store=_Store(WORLD))
    assert core is not None
    assert core["answer_kind"] == "scene_algebra"
    assert "Nauru" in core["answer"]


def test_a_composed_but_unresolvable_scene_is_an_honest_abstention_not_none():
    """None here would fall through to the define lane and risk the head-noun-define defect;
    a dict (even an abstention) short-circuits it. Nauru is a real, grounded Country -- it simply
    carries no `capital` edge, so the scene composes cleanly but the readout is empty."""
    core = B.scene_relational_answer(
        "What is the capital of Nauru?", language="en", store=_Store(WORLD))
    assert core is not None
    assert core["answer_kind"] == "scene_algebra_abstain"
    assert "Nauru" in core["answer"]


def test_nothing_the_graph_can_name_returns_none_not_an_abstention():
    core = B.scene_relational_answer("hello, how are you?", language="en", store=_Store(WORLD))
    assert core is None


def test_an_unreadable_question_is_logged_as_curriculum(monkeypatch):
    """The reason compose() gives is the widening signal; discarding it was the gap this closes."""
    seen = []
    monkeypatch.setattr(B, "_log_unread",
                        lambda q, reason, detail="": seen.append((q, reason, detail)))
    B.scene_relational_answer("Which flurbles have no snorgle?", language="en", store=_Store(WORLD))
    assert seen and "flurbles" in seen[0][0]
    assert seen[0][1]                                    # a reason, not an empty string


def test_a_dropped_qualifier_is_logged_with_the_word_that_had_nowhere_to_go(monkeypatch):
    seen = []
    monkeypatch.setattr(B, "_log_unread",
                        lambda q, reason, detail="": seen.append((q, reason, detail)))
    store = _Store(WORLD + [
        ("atanor", "has_a", "deliberator"),
        ("deliberator", "is_a", "organ"),
        ("heart", "is_a", "organ"), ("heart", "has_a", "valve"),
        ("lung", "is_a", "organ"), ("lung", "has_a", "alveolus"),
    ])
    B.scene_relational_answer("Which atanor organs have no tests?", language="en", store=store)
    assert seen and "atanor" in seen[0][2]


def test_korean_is_refused_before_the_store_is_ever_touched():
    class _Boom:
        def __getattr__(self, name):
            raise AssertionError("store must not be touched for a Korean query")
    assert B.scene_relational_answer("이것은 질문입니다", language="ko", store=_Boom()) is None


def test_a_slow_composition_times_out_rather_than_blocking_the_answer_path(monkeypatch):
    """Measured on the real graph: a huge-extension pairing (`city`) cost 45-280s. The lane must
    never make an ordinary query slower than before it existed -- proved here with a budget short
    enough that the test itself stays fast, not by trusting the production default (8s)."""
    monkeypatch.setenv("ATANOR_SCENE_TIMEOUT_S", "0.2")

    def _slow(query, store):
        time.sleep(2.0)
        return {"answer": "too slow", "answer_kind": "scene_algebra"}

    monkeypatch.setattr(B, "_compose_and_evaluate", _slow)
    t0 = time.time()
    core = B.scene_relational_answer("anything", language="en", store=_Store(WORLD))
    elapsed = time.time() - t0
    assert core is None
    assert elapsed < 1.0, f"timeout budget was not honoured: waited {elapsed:.2f}s"


def test_a_dropped_qualifier_abstains_instead_of_answering_the_wrong_domain():
    """Real bug, real graph, 2026-07-28: "which atanor organs have no tests" answered, confidently,
    about human anatomy organs -- a same-named but unrelated type -- because `atanor` had nowhere
    to bind and was silently dropped. Fixed at the composer; this proves the fix reaches the
    answer contract: a dict, useful=False via answer_kind, not a confident wrong-domain answer."""
    store = _Store(WORLD + [
        ("atanor", "has_a", "deliberator"),
        ("deliberator", "is_a", "organ"),
        ("heart", "is_a", "organ"), ("heart", "has_a", "valve"),
        ("lung", "is_a", "organ"), ("lung", "has_a", "alveolus"),
    ])
    core = B.scene_relational_answer(
        "Which atanor organs have no tests?", language="en", store=store)
    assert core is not None
    assert core["answer_kind"] == "scene_algebra_abstain"
    assert "atanor" in core["answer"]


def test_a_fault_inside_composition_never_breaks_the_answer_path(monkeypatch):
    def _boom(query, store):
        raise RuntimeError("scene lane exploded")

    monkeypatch.setattr(B, "_compose_and_evaluate", _boom)
    core = B.scene_relational_answer("anything", language="en", store=_Store(WORLD))
    assert core is None
