# -*- coding: utf-8 -*-
"""Sensory cortex tests — the fact/non-fact split is the load-bearing behaviour, so it is pinned
hard: heard speech must NEVER reach the graph, perceptual facts must, with sourced provenance.
No GPU, no model download — structured inputs + an in-memory fake store."""
from __future__ import annotations

from packages.sensory_cortex import cortex as C


class FakeStore:
    """Minimal store mirroring the triple_store surface the cortex uses."""
    def __init__(self):
        self.rows: list[tuple[str, str, str, int]] = []
        self.sources: dict[int, tuple[str, str]] = {}
        self._next = 1

    def intern_source(self, kind, detail):
        sid = self._next
        self._next += 1
        self.sources[sid] = (kind, detail)
        return sid

    def add(self, s, p, o, source=None):
        self.rows.append((s, p, o, source))
        return True

    def flush(self):
        pass


def test_vision_detection_becomes_groundable_object_fact():
    ps = C.from_vision({"detections": [{"label": "mug", "score": 0.91}], "sources": ["frame1"]})
    assert len(ps) == 1
    p = ps[0]
    assert p.modality == C.VISION and p.kind == "object" and p.groundable
    assert ("mug", "perceived_via", "vision") in p.triples
    assert p.confidence == 0.91


def test_heard_speech_is_NOT_a_fact_and_never_grounded():
    ps = C.from_audio("the cup is on the table", is_speech=True)
    assert len(ps) == 1 and ps[0].kind == "speech"
    assert ps[0].groundable is False and ps[0].triples == []
    store = FakeStore()
    res = C.ground(ps, store)
    assert res["stored"] == 0                      # heard words never enter the knowledge graph
    assert store.rows == []
    assert res["speech"] == ["the cup is on the table"]


def test_sound_event_is_a_perceptual_fact():
    ps = C.from_audio("a dog bark", is_speech=False, confidence=0.6)
    assert ps[0].kind == "sound_event" and ps[0].groundable
    assert ("a dog bark", "perceived_via", "hearing") in ps[0].triples


def test_interoception_drives_are_non_facts():
    ps = C.from_interoception({"cortisol": 0.4, "dopamine": 0.0})
    assert len(ps) == 1                            # zero-level drive dropped
    assert ps[0].modality == C.INTEROCEPTION and ps[0].kind == "drive"
    assert ps[0].groundable is False


def test_ground_writes_only_facts_with_provenance():
    percepts = C.integrate(
        C.from_vision({"detections": [{"label": "ball", "score": 0.8}], "sources": ["f2"]}),
        C.from_audio("throw the ball", is_speech=True),           # non-fact
        C.from_touch([{"object": "floor", "force": 1.0}]),
    )
    store = FakeStore()
    res = C.ground(percepts, store)
    assert res["stored"] == 2                       # ball(vision) + floor(touch); speech excluded
    subjects = {r[0] for r in store.rows}
    assert subjects == {"ball", "self"}
    # every written row is tagged as a PERCEPT, not an asserted fact
    for _s, _p, _o, sid in store.rows:
        assert store.sources[sid][0] == C._PERCEPT_SOURCE


def test_understand_integrates_all_senses_and_splits_fact_from_nonfact():
    res = C.understand(
        vision={"detections": [{"label": "chair", "score": 0.7}]},
        audio="sit down please", audio_is_speech=True,
        hormones={"curiosity": 0.5},
        write=False,
    )
    assert res["facts"] == 1                         # chair only
    assert res["heard_speech"] == ["sit down please"]
    assert res["drives"] == ["curiosity=0.50"]
    assert res["by_modality"].get(C.VISION) == 1 and res["by_modality"].get(C.AUDIO) == 1


def test_empty_and_unknown_inputs_are_silent_not_fabricated():
    assert C.from_vision(None) == []
    assert C.from_audio("") == []
    assert C.understand()["percepts"] == 0
