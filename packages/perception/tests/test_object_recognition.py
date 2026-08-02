# -*- coding: utf-8 -*-
"""Object re-recognition: is this the SAME object I saw before? Cosine over signature vectors,
conservative threshold, multi-view drift adaptation, recency tie-break — honest about uncertainty."""
import packages.perception.object_recognition as orc


def _sig(*v):
    return list(v)


def test_new_object_is_minted(tmp_path):
    orc._LEDGER = tmp_path / "obj.jsonl"
    r = orc.recognize_object(_sig(1.0, 0.0, 0.0), label="물병")
    assert r["matched"] is False and r["new"] is True
    assert r["label"] == "물병" and len(orc._load()) == 1


def test_same_signature_is_re_recognized(tmp_path):
    orc._LEDGER = tmp_path / "obj.jsonl"
    first = orc.recognize_object(_sig(1.0, 0.1, 0.0), label="물병")
    again = orc.recognize_object(_sig(0.98, 0.12, 0.02), label="물병")
    assert again["matched"] is True
    assert again["instance_id"] == first["instance_id"]
    assert again["times_seen"] == 2                          # the same instance, seen twice
    assert len(orc._load()) == 1                             # no duplicate instance minted


def test_different_object_not_confused(tmp_path):
    orc._LEDGER = tmp_path / "obj.jsonl"
    orc.recognize_object(_sig(1.0, 0.0, 0.0), label="물병")
    other = orc.recognize_object(_sig(0.0, 1.0, 0.0), label="물병")   # orthogonal → not the same
    assert other["matched"] is False and other.get("new") is True
    assert len(orc._load()) == 2


def test_same_label_only(tmp_path):
    orc._LEDGER = tmp_path / "obj.jsonl"
    orc.recognize_object(_sig(1.0, 0.0, 0.0), label="물병")
    # identical signature but a DIFFERENT label → a cup is never matched to a bottle
    r = orc.recognize_object(_sig(1.0, 0.0, 0.0), label="컵")
    assert r["matched"] is False and r.get("new") is True


def test_uncertain_band_is_not_claimed(tmp_path):
    orc._LEDGER = tmp_path / "obj.jsonl"
    orc.recognize_object(_sig(1.0, 0.0, 0.0), label="물병")
    # a look ~0.65–0.75 similar: similar enough to notice, not enough to claim identity
    r = orc.recognize_object(_sig(1.0, 0.9, 0.0), label="물병", update=False)
    assert r["matched"] is False and r.get("uncertain") is True
    assert 0.65 <= r["similarity"] < 0.75


def test_drift_adaptation_absorbs_new_views(tmp_path):
    orc._LEDGER = tmp_path / "obj.jsonl"
    first = orc.recognize_object(_sig(1.0, 0.0, 0.0), label="물병")
    orc.recognize_object(_sig(0.9, 0.3, 0.0), label="물병")           # a drifted view, still a match
    inst = orc._load()[0]
    assert inst["id"] == first["instance_id"] and len(inst["signatures"]) == 2  # view absorbed


def test_empty_signature_is_honest(tmp_path):
    orc._LEDGER = tmp_path / "obj.jsonl"
    r = orc.recognize_object([], label="물병")
    assert r["matched"] is False and r["reason"] == "no_signature"
    assert len(orc._load()) == 0                             # nothing seen → nothing minted
