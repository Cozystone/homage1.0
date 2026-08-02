"""Test isolation for base_brain: redirect all pack/seed/semantic/surface/benchmark/
proof output paths to a per-test tmp dir.

Why: build_base_brain_pack_v0() and the sub-builders WRITE to the real data paths
(data/base_brain/...). Running the suite therefore CLOBBERED the live promoted pack
(1472 concepts) back to curated-only (58), silently reverting promotions. Each writer
module binds its own copy of the path constant at import, so we monkeypatch every
bound copy (patching models alone is not enough). Autouse => every base_brain test is
isolated from the real files.
"""

from __future__ import annotations

import pytest

from packages.base_brain import (
    benchmark,
    benchmark_runner,
    models,
    pack_builder,
    pack_loader,
    proof,
    seed_extension,
    semantic_pack,
    surface_pack,
)

# attr name -> path relative to the tmp base_brain root
_REL = {
    "SEED_PATH": "seed/seed_graph_v2.json",
    "SEMANTIC_PATH": "semantic_packs/general_semantic_v0.json",
    "SURFACE_PATH": "surface_packs/general_surface_v0.json",
    "PACK_PATH": "packs/atanor_base_brain_v0.json",
    "BENCHMARK_PATH": "benchmark/zero_user_general_v0.json",
    "PROOF_JSON_PATH": "proofs/base_brain_proof.json",
    "PROOF_MD_PATH": "proofs/base_brain_proof.md",
}

# module -> the path attrs it binds (from `from .models import <NAME>`)
_TARGETS = [
    (models, list(_REL)),
    (pack_builder, ["PACK_PATH"]),
    (pack_loader, ["PACK_PATH"]),
    (proof, ["PACK_PATH", "PROOF_JSON_PATH", "PROOF_MD_PATH"]),
    (seed_extension, ["SEED_PATH"]),
    (semantic_pack, ["SEMANTIC_PATH"]),
    (surface_pack, ["SURFACE_PATH"]),
    (benchmark, ["BENCHMARK_PATH"]),
    (benchmark_runner, ["BENCHMARK_PATH"]),
]


@pytest.fixture(autouse=True)
def _isolate_base_brain_paths(tmp_path, monkeypatch):
    root = tmp_path / "base_brain"
    for mod, attrs in _TARGETS:
        for attr in attrs:
            target = root / _REL[attr]
            target.parent.mkdir(parents=True, exist_ok=True)
            monkeypatch.setattr(mod, attr, target, raising=False)
    # ensure_base_dirs() mkdir's under BASE_BRAIN_ROOT (models global) — point it at tmp too
    monkeypatch.setattr(models, "BASE_BRAIN_ROOT", root, raising=False)
    yield
