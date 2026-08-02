# -*- coding: utf-8 -*-
"""Common-protocol step 1: freeze the decoder, the 10K skeleton bank and the graph snapshot, and
record their SHA-256 so every mission run is provably against the same artefacts. Writes
data/b5_missions/b5_freeze_manifest.json."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_ART = {
    "decoder": ROOT / "data" / "graph_scale" / "realizer.pt",
    "skeleton_bank_10k": ROOT / "data" / "construction_bank" / "formulaic_frames.jsonl",
    "graph_snapshot_base_brain": ROOT / "data" / "base_brain" / "proofs" / "base_brain_proof.json",
}


def _sha256(path: Path) -> dict:
    if not path.exists():
        return {"path": str(path.relative_to(ROOT)), "present": False, "sha256": None, "bytes": 0}
    h = hashlib.sha256()
    n = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return {"path": str(path.relative_to(ROOT)), "present": True, "sha256": h.hexdigest(), "bytes": n}


def build_manifest(artifacts: dict[str, Path] | None = None) -> dict:
    arts = artifacts or _ART
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "spec": "docs/ATANOR_b5_mission_spec_v1.md",
        "artifacts": {name: _sha256(p) for name, p in arts.items()},
    }
    out = ROOT / "data" / "b5_missions" / "b5_freeze_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    m = build_manifest()
    for name, rec in m["artifacts"].items():
        tag = rec["sha256"][:16] if rec["sha256"] else "MISSING"
        print(f"{name:26s} {tag}  {rec['bytes']:>12,} B  {rec['path']}")
