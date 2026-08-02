"""Forgetting is a demotion, not a deletion: archive on prune, restore on demand."""
from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timezone

_REPO = pathlib.Path(__file__).resolve().parents[3]
for p in (str(_REPO), str(_REPO / "packages")):
    if p not in sys.path:
        sys.path.insert(0, p)

from packages.cloud_brain.neuroplasticity import archive_pruned, restore_archived


NOW = datetime(2026, 7, 4, tzinfo=timezone.utc)


def _rows():
    return [
        {"dedupe_key": "rk_a", "relation": "OBJ_OF", "weight": 0.01},
        {"dedupe_key": "rk_b", "relation": "IS_A", "weight": 0.02},
    ]


def test_pruned_rows_land_in_archive_with_log(tmp_path):
    n = archive_pruned(tmp_path, _rows(), NOW)
    assert n == 2
    assert (tmp_path / "pruned_archive.jsonl").exists()
    log = (tmp_path / "forgetting_log.jsonl").read_text(encoding="utf-8")
    assert '"count": 2' in log and "plasticity_prune" in log


def test_restore_brings_back_requested_keys_with_safe_weight(tmp_path):
    archive_pruned(tmp_path, _rows(), NOW)
    restored = restore_archived(tmp_path, {"rk_b"})
    assert len(restored) == 1
    assert restored[0]["dedupe_key"] == "rk_b"
    assert restored[0]["weight"] >= 0.2          # above the prune floor
    assert "archived_at" not in restored[0]      # clean row again


def test_restore_unknown_key_returns_empty(tmp_path):
    archive_pruned(tmp_path, _rows(), NOW)
    assert restore_archived(tmp_path, {"rk_zzz"}) == []
    assert restore_archived(tmp_path / "nowhere", {"rk_a"}) == []
