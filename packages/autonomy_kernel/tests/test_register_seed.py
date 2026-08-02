# -*- coding: utf-8 -*-
"""Register seed generator — license-safe bootstrap for the two starved registers (dialogue, english)."""
from __future__ import annotations

import random

from packages.autonomy_kernel.register_diet import classify_register
from packages.autonomy_kernel.register_seed import dialogue_seeds, english_seeds, generate


def test_dialogue_seeds_are_conversational_register():
    """Dialogue seeds are ENGLISH conversational lines now (doctrine 2026-07-18): script-wise they
    classify 'english' (classify_register is script-first), and register-wise the overwhelming
    majority must be the VOICE registers they exist to supply (measured on port: 119/120)."""
    from packages.autonomy_kernel.narrative_corpus import _VOICE_REGISTERS, register
    seeds = dialogue_seeds(120, random.Random(1))
    assert len(seeds) >= 40 and len(seeds) == len(set(seeds))       # distinct
    assert all(classify_register(s) == "english" for s in seeds)    # English by script
    hits = sum(1 for s in seeds if register(s) in _VOICE_REGISTERS)
    assert hits >= 0.85 * len(seeds)


def test_english_seeds_are_english_register():
    seeds = english_seeds(80, random.Random(2))
    assert len(seeds) >= 30 and len(seeds) == len(set(seeds))
    assert all(classify_register(s) == "english" for s in seeds)


def test_seeds_pass_the_corpus_quality_gate():
    # after the gate was widened for questions + casual endings, the seeds must actually be admissible
    from packages.autonomy_kernel.narrative_corpus import _quality
    g = generate(120, 80, random.Random(3))
    assert sum(1 for s in g["dialogue"] if _quality(s)) >= 0.4 * len(g["dialogue"])
    assert sum(1 for s in g["english"] if _quality(s)) >= 0.9 * len(g["english"])


def test_quality_gate_accepts_questions_and_casual_but_rejects_fragments():
    from packages.autonomy_kernel.narrative_corpus import _quality
    assert _quality("What did you do today?") is True       # a question passes
    assert _quality("I have been a bit tired lately.") is True
    assert _quality("How about a walk together this weekend?") is True
    assert _quality("Former journalist of the republic") is False   # fragment, no ending
    assert _quality("Coffee") is False                     # bare noun — still rejected
    assert _quality("오늘 뭐 했어?") is False               # Korean: refused at the door
