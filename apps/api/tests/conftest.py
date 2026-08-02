from __future__ import annotations

import sys
import os
from pathlib import Path


os.environ.setdefault("ATANOR_DISABLE_DAEMON_SELF_HEAL", "1")
os.environ.setdefault("ATANOR_WEB_SEED_FEEDER_ON_TICK", "0")
# Tests run offline against the deterministic STATIC_RESULTS fixtures. In production these are
# quarantined (search returns nothing → honest abstention); opt in explicitly for the suite.
os.environ.setdefault("WEB_SEARCH_PROVIDER", "static")

REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPO_ROOT / "apps" / "api"
DATAGATE_ROOT = REPO_ROOT / "packages" / "datagate"
ONTOLOGY_ROOT = REPO_ROOT / "packages" / "ontology_forge"
RAG_ROOT = REPO_ROOT / "packages" / "rag_engine"
GUARD_ROOT = REPO_ROOT / "packages" / "guard"
MODEL_ROOT = REPO_ROOT / "packages" / "model"
TRAINER_ROOT = REPO_ROOT / "packages" / "trainer"
NEURO_ROOT = REPO_ROOT / "packages" / "neuro_efficiency"
KNOWLEDGE_ROOT = REPO_ROOT / "packages" / "knowledge_bakery"
COST_ROOT = REPO_ROOT / "packages" / "cost_model"
SEED_ROOT = REPO_ROOT / "packages" / "seed_research"

for path in (API_ROOT, DATAGATE_ROOT, ONTOLOGY_ROOT, RAG_ROOT, GUARD_ROOT, MODEL_ROOT, TRAINER_ROOT, NEURO_ROOT, KNOWLEDGE_ROOT, COST_ROOT, SEED_ROOT):
    path_string = str(path)
    if path_string not in sys.path:
        sys.path.insert(0, path_string)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_base_brain_paths(tmp_path, monkeypatch):
    """Redirect base_brain pack/proof output paths to a per-test tmp dir so API tests
    (e.g. POST /api/base-brain/build, which calls build_base_brain_pack_v0() and writes
    PACK_PATH) never CLOBBER the live promoted pack (1472 concepts) back to curated-58.
    Mirrors packages/base_brain/tests/conftest.py; each writer module binds its own copy
    of the constant, so every bound copy is patched."""
    try:
        from packages.base_brain import (
            benchmark, benchmark_runner, models, pack_builder, pack_loader,
            proof, seed_extension, semantic_pack, surface_pack,
        )
    except Exception:
        yield
        return
    rel = {
        "SEED_PATH": "seed/seed_graph_v2.json",
        "SEMANTIC_PATH": "semantic_packs/general_semantic_v0.json",
        "SURFACE_PATH": "surface_packs/general_surface_v0.json",
        "PACK_PATH": "packs/atanor_base_brain_v0.json",
        "BENCHMARK_PATH": "benchmark/zero_user_general_v0.json",
        "PROOF_JSON_PATH": "proofs/base_brain_proof.json",
        "PROOF_MD_PATH": "proofs/base_brain_proof.md",
    }
    targets = [
        (models, list(rel)),
        (pack_builder, ["PACK_PATH"]),
        (pack_loader, ["PACK_PATH"]),
        (proof, ["PACK_PATH", "PROOF_JSON_PATH", "PROOF_MD_PATH"]),
        (seed_extension, ["SEED_PATH"]),
        (semantic_pack, ["SEMANTIC_PATH"]),
        (surface_pack, ["SURFACE_PATH"]),
        (benchmark, ["BENCHMARK_PATH"]),
        (benchmark_runner, ["BENCHMARK_PATH"]),
    ]
    root = tmp_path / "base_brain"
    for mod, attrs in targets:
        for attr in attrs:
            target = root / rel[attr]
            target.parent.mkdir(parents=True, exist_ok=True)
            monkeypatch.setattr(mod, attr, target, raising=False)
    monkeypatch.setattr(models, "BASE_BRAIN_ROOT", root, raising=False)
    yield
