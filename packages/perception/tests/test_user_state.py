# -*- coding: utf-8 -*-
"""User-state distiller: face perception → an Observation (state concepts + affective read).
Perception ONLY — it chooses no action; it never claims an unseen signal."""
from packages.perception.user_state import observe, observe_from_faces


def test_emotion_becomes_concepts_and_valence():
    o = observe(emotion="happy")
    assert "기쁨" in o.concepts and o.valence > 0.5 and o.energy > 0.5


def test_fatigue_signals_lower_energy():
    o = observe(emotion="neutral", eye_openness=0.3, yawning=True)
    assert "피곤" in o.concepts and "눈감김" in o.concepts and o.energy <= 0.25


def test_appearance_change_flag():
    o = observe(emotion="neutral", appearance_changed=True)
    assert "외형변화" in o.concepts


def test_partial_perception_claims_nothing_extra():
    o = observe()                                        # no signals at all
    assert o.concepts == [] and o.source == "face"


def test_from_faces_reads_first_known_person():
    perc = {"faces": [{"identity": "사장님", "familiarity": 0.9, "emotion": "happy"}]}
    o = observe_from_faces(perc)
    assert o is not None and "기쁨" in o.concepts


def test_from_faces_none_when_no_face():
    assert observe_from_faces({"faces": []}) is None


def test_from_faces_flags_appearance_drift_midband():
    # KNOWN person but mid-band familiarity → a soft 'something's different', not a verdict
    perc = {"faces": [{"identity": "사장님", "familiarity": 0.68, "emotion": "neutral"}]}
    o = observe_from_faces(perc)
    assert "외형변화" in o.concepts
    # a SHARP match (0.9) must NOT flag change
    perc2 = {"faces": [{"identity": "사장님", "familiarity": 0.92, "emotion": "neutral"}]}
    assert "외형변화" not in observe_from_faces(perc2).concepts
