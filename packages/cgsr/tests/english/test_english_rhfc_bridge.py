from __future__ import annotations

from cgsr.english.construction_patterns import core_english_frames
from cgsr.english.rhfc_bridge import store_english_frames


def test_rhfc_recalls_stored_english_frame() -> None:
    frames = core_english_frames()
    store = store_english_frames(frames, shard_count=4)
    recall = store.recall(frames[0])
    assert recall["frame_id"] == frames[0].frame_id
    assert recall["score"] > 0.99


def test_english_rhfc_exact_recall_has_no_forgetting() -> None:
    store = store_english_frames(core_english_frames(), shard_count=4)
    metrics = store.exact_recall_accuracy()
    assert metrics["accuracy"] == 1.0
    assert metrics["forgetting_count"] == 0
