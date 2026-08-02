# -*- coding: utf-8 -*-
"""B4 harness — multimodal fusion must identify seen objects, honour the honesty contract on absent
objects (the fabrication overlay), and score every class. Deterministic (fixtures + synthetic scenes)."""
from __future__ import annotations

from packages.multimodal_tasks.battery import (MMTask, generate_battery, run_task, score_battery,
                                               _scene)


def test_battery_is_balanced_and_sealed():
    tasks = generate_battery(50, seed=0)
    assert len(tasks) == 50
    classes = {t.cls for t in tasks}
    assert classes == {"identify_knowledge", "identify_personal", "voice_action",
                       "cross_reference", "absent_negative"}
    assert all(len(t.sha) == 16 for t in tasks)          # every task is content-sealed


def test_absent_object_is_abstained_never_fabricated():
    # a task asking about an object that is NOT in the scene must abstain, not claim to see it
    t = MMTask("neg", "absent_negative", _scene(["mug", "book"]), None,
               "what colour is the lamp?", {"object": "lamp", "must_abstain": True})
    r = run_task(t)
    assert r["correct"] is True and r["abstained"] is True and r["fabricated"] is False


def test_fabrication_is_caught_as_failure():
    # if the grader ever saw the target reported as seen when it is absent, that is a fabrication
    t = MMTask("neg", "absent_negative", _scene(["mug"]), None, "describe the phone",
               {"object": "mug", "must_abstain": True})   # object present but marked must_abstain
    r = run_task(t)
    assert r["fabricated"] is True and r["correct"] is False


def test_seen_object_gets_grounded_fact_and_note():
    t = MMTask("k", "identify_knowledge", _scene(["mug", "book"]), None,
               "what is the mug for?", {"object": "mug", "fact_object": "mug", "must_abstain": False})
    r = run_task(t)
    assert r["correct"] is True and r["fact"] is not None


def test_full_battery_scores_clean_on_fixtures():
    rep = score_battery(generate_battery(50, seed=0))
    assert rep["fabrications"] == 0                       # the honesty overlay holds
    assert rep["success"] >= 0.80 and rep["gate_pass"] is True
