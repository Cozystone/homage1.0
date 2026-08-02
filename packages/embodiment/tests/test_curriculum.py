# -*- coding: utf-8 -*-
"""Track E M5s — the developmental curriculum must graduate its stages (reach -> contact -> push) by
its own gates, ending with the self intentionally displacing an object. Skipped without mujoco."""
from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from packages.embodiment.curriculum import run_curriculum


def test_curriculum_graduates_all_stages():
    r = run_curriculum(seed=1)
    names = {s.name: s.graduated for s in r.stages}
    assert names["REACH"] is True                     # learned the body schema, learning plateaued
    assert names["CONTACT"] is True                   # reached and touched the object
    assert names["PUSH"] is True                      # intentionally displaced the object
    assert r.graduated_all is True
    assert r.box_displacement > 0.02                  # the object really moved


def test_learning_progress_is_tracked():
    r = run_curriculum(seed=2)
    assert len(r.learning_progress) > 0               # competence-based intrinsic motivation signal
    assert r.extra["intrinsic_motivation"] == "competence/learning-progress"
