# -*- coding: utf-8 -*-
"""Spatial Memory Replay Core: record a room's layout as distilled geometry (never a frame) and
rebuild it as a SPLATRA scene — objects placed WHERE they were seen."""
import packages.perception.spatial_memory as sm


def test_records_distilled_geometry_no_frame(tmp_path):
    sm._LEDGER = tmp_path / "spatial.jsonl"
    r = sm.record_snapshot([
        {"label": "물병", "x": 0.2, "y": 0.3, "depth": 0.4},
        {"label": "노트북", "x": 0.7, "y": 0.6},
    ], place="책상")
    assert r["recorded"] and r["n_objects"] == 2
    assert r["frames_stored"] == 0 and r["left_device"] is False   # BINDING: no frame ever stored
    assert len(sm._load()) == 1


def test_recall_latest_and_by_id(tmp_path):
    sm._LEDGER = tmp_path / "spatial.jsonl"
    a = sm.record_snapshot([{"label": "컵", "x": 0.5, "y": 0.5}])
    b = sm.record_snapshot([{"label": "책", "x": 0.1, "y": 0.9}])
    assert sm.recall_snapshot()["id"] == b["id"]                    # latest
    assert sm.recall_snapshot(a["id"])["objects"][0]["label"] == "컵"


def test_reconstruct_places_objects_where_seen(tmp_path):
    sm._LEDGER = tmp_path / "spatial.jsonl"
    sm.record_snapshot([{"label": "물병", "x": 0.0, "y": 0.0, "depth": 0.5}], place="방")
    scene = sm.reconstruct_scene(sm.recall_snapshot())
    assert scene["meta"]["replay"] is True and scene["meta"]["place"] == "방"
    o = scene["objects"][0]
    # bbox top-left (0,0) → scene left-TOP: x=-1, y=+1 (y flips: image-down → scene-up)
    assert o["pos"][0] == -1.0 and o["pos"][1] == 1.0
    assert o["role"] == "memory" and o["label"] == "물병"


def test_detect_recall_intent_phrase_level(tmp_path):
    sm._LEDGER = tmp_path / "spatial.jsonl"
    assert sm.detect_spatial_recall("아까 본 방 보여줘")["is_recall"] is True
    assert sm.detect_spatial_recall("그때 그 방 재현해줘")["is_recall"] is True
    assert sm.detect_spatial_recall("방탄소년단 보여줘")["is_recall"] is False
    assert sm.detect_spatial_recall("중력이 뭐야")["is_recall"] is False


def test_recall_matches_named_place(tmp_path):
    sm._LEDGER = tmp_path / "spatial.jsonl"
    sm.record_snapshot([{"label": "컵", "x": 0.5, "y": 0.5}], place="주방")
    sm.record_snapshot([{"label": "노트북", "x": 0.3, "y": 0.4}], place="책상")
    rc = sm.detect_spatial_recall("아까 본 책상 방 보여줘")
    assert rc["is_recall"] and rc["place"] == "책상"
    assert sm.recall_snapshot(place="책상")["objects"][0]["label"] == "노트북"
    assert sm.recall_snapshot(place="주방")["objects"][0]["label"] == "컵"


def test_empty_is_honest(tmp_path):
    sm._LEDGER = tmp_path / "spatial.jsonl"
    assert sm.recall_snapshot() is None
    assert sm.reconstruct_scene(None)["meta"]["empty"] is True
    assert sm.record_snapshot([])["recorded"] is False             # nothing seen → nothing recorded
