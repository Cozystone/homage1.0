"""Streaming maintenance must match in-memory plasticity semantics at O(1) row memory."""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

_REPO = pathlib.Path(__file__).resolve().parents[3]
for p in (str(_REPO), str(_REPO / "packages")):
    if p not in sys.path:
        sys.path.insert(0, p)

from packages.cloud_brain.neuroplasticity import plasticity_tick
from packages.cloud_brain.streaming_plasticity import streaming_plasticity_tick

NOW = datetime(2026, 7, 4, tzinfo=timezone.utc)
OLD = (NOW - timedelta(days=400)).isoformat().replace("+00:00", "Z")
FRESH = (NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z")


def _rows() -> list[dict]:
    rows = []
    for i in range(200):
        rows.append({"dedupe_key": f"isa_{i}", "relation": "IS_A", "weight": 0.8,
                     "updated_at": FRESH, "source_concept_id": f"s{i}", "target_concept_id": "t"})
    for i in range(150):
        rows.append({"dedupe_key": f"of_{i}", "relation": "OBJ_OF", "weight": 0.5,
                     "updated_at": OLD, "source_concept_id": f"s{i}", "target_concept_id": "t"})
    for i in range(50):
        rows.append({"dedupe_key": f"real_{i}", "relation": "발견하다", "weight": 0.7,
                     "updated_at": FRESH, "source_concept_id": f"r{i}", "target_concept_id": "핵분열"})
    return rows


def test_streaming_matches_in_memory_semantics(tmp_path):
    rows = _rows()
    rel_path = tmp_path / "relations.jsonl"
    rel_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                        encoding="utf-8")

    expected = plasticity_tick(rows, NOW, half_life_days=60, prune_floor=0.04)
    stats = streaming_plasticity_tick(rel_path, NOW, half_life_days=60, prune_floor=0.04,
                                      archive_root=tmp_path)

    assert stats["in"] == len(rows)
    assert stats["kept"] == expected["stats"]["kept"]
    assert stats["pruned"] == expected["stats"]["pruned"]
    # file rewritten with exactly the kept rows
    kept_on_disk = [json.loads(l) for l in rel_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(kept_on_disk) == stats["kept"]
    # fresh IS_A survives; ancient OBJ_OF is gone from hot store
    keys = {r["dedupe_key"] for r in kept_on_disk}
    assert "isa_0" in keys and "of_0" not in keys


def test_pruned_rows_are_archived_not_lost(tmp_path):
    rows = _rows()
    rel_path = tmp_path / "relations.jsonl"
    rel_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    stats = streaming_plasticity_tick(rel_path, NOW, half_life_days=60, prune_floor=0.04,
                                      archive_root=tmp_path)
    assert stats["archived"] == stats["pruned"] > 0
    archive = (tmp_path / "pruned_archive.jsonl").read_text(encoding="utf-8")
    assert "of_0" in archive        # demoted, recoverable
    assert (tmp_path / "forgetting_log.jsonl").exists()


def test_missing_file_is_a_noop(tmp_path):
    stats = streaming_plasticity_tick(tmp_path / "nope.jsonl", NOW)
    assert stats == {"in": 0, "kept": 0, "pruned": 0, "distinct_predicates": 0, "archived": 0}
