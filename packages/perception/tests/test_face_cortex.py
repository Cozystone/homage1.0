# -*- coding: utf-8 -*-
"""Face cortex: GEOMETRIC identity over LEARNED embeddings (no name table), honest gap on an
unknown face, honest 'core absent' when DeepFace isn't installed. The unrecognized-person gap
must lift the self's curiosity (so the mind MAY inquire on its own) — never a hard-coded
question."""
import numpy as np

from packages.continuous_self import self_state
from packages.perception import face_cortex


def _unit(v):
    v = np.asarray(v, float)
    return (v / np.linalg.norm(v)).tolist()


def _use_tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(face_cortex, "KNOWN_FACES_PATH", tmp_path / "known_faces.jsonl")


def test_teach_then_recognize_geometrically(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)
    owner = _unit([1.0, 0.2, 0.0, 0.0])
    face_cortex.teach_face("사장님", owner)

    # the same face (tiny noise) resolves to the taught name, above threshold
    seen = _unit([0.98, 0.25, 0.02, 0.0])
    res = face_cortex.resolve_identity(seen)
    assert res["identity"] == "사장님"
    assert res["familiarity"] >= face_cortex._MATCH_THRESHOLD

    # a clearly different face is an HONEST gap — identity None, never guessed as the owner
    stranger = _unit([0.0, 0.0, 1.0, 0.3])
    gap = face_cortex.resolve_identity(stranger)
    assert gap["identity"] is None


def test_no_known_faces_is_a_gap_not_a_guess(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)
    res = face_cortex.resolve_identity(_unit([1.0, 0.0, 0.0]))
    assert res["identity"] is None and res["familiarity"] == 0.0


def test_teaching_same_name_sharpens(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)
    face_cortex.teach_face("K", _unit([1.0, 0.0, 0.0, 0.0]))
    out = face_cortex.teach_face("K", _unit([0.9, 0.1, 0.0, 0.0]))
    assert out["taught"] and out["samples"] == 2
    assert len(face_cortex._load_known()) == 1     # merged, not duplicated


def test_perceive_without_core_is_honest(monkeypatch):
    monkeypatch.setattr(face_cortex, "_DF_CACHE", {"tried": True, "mod": None})
    p = face_cortex.perceive(np.zeros((8, 8, 3), np.uint8))
    assert p["core"] == "absent" and p["faces"] == [] and p["person_present"] is False
    assert "DeepFace" in p["note"]                 # says so plainly, never pretends to see


def test_unfamiliar_person_lifts_curiosity_not_a_question():
    """The gap raises curiosity through the SAME channel as any other unresolved signal — the
    mind's inquiry can turn there on its own. No question string is produced anywhere."""
    base = self_state._target_from(self_state.Observation(user_present=True))
    gap = self_state._target_from(self_state.Observation(user_present=True, person_unfamiliar=True))
    assert gap["curiosity"] > base["curiosity"]
