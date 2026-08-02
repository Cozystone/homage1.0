from __future__ import annotations

import json
from pathlib import Path

from packages.promotion_gate.proof import run_proof


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def test_promotion_gate_proof_uses_fixture_paths(tmp_path):
    candidate = tmp_path / "candidate"
    verified = tmp_path / "verified"
    for root in (candidate, verified):
        write_jsonl(root / "concepts.jsonl", [])
        write_jsonl(root / "relations.jsonl", [])
        write_jsonl(root / "evidence.jsonl", [])
        write_jsonl(root / "case_frames.jsonl", [])
    write_jsonl(
        candidate / "concepts.jsonl",
        [
            {
                "dedupe_key": "c1",
                "concept_id": "c1",
                "canonical_name": "Concept",
                "provenance": {"source_id": "s1", "license": "CC BY-SA 4.0", "usage_allowed": True},
                "verification": {"status": "verified"},
            }
        ],
    )

    result = run_proof(tmp_path / "out", candidate, verified)

    assert all(result["summary"].values())
    assert result["report"]["actual_promotion_enabled"] is False
    assert Path(result["outputs"]["json"]).exists()
