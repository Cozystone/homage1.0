"""Guards the fold->node_store wiring: a materialized fold's geometry streams back with
negligible position error AND bounded working RAM regardless of node count N."""

from __future__ import annotations

import tracemalloc

import numpy as np

from packages.holographic_fold.folding import FoldedNode, FoldedState
from packages.holographic_fold.materialize import materialize_to_node_store, scene_node_count, scene_windows


def _folded(n: int, seed: int = 0) -> FoldedState:
    rng = np.random.default_rng(seed)
    nodes = tuple(
        FoldedNode(
            node_id=f"c{i}", source_type="concept",
            position=(float(rng.standard_normal()), float(rng.standard_normal()), float(rng.standard_normal())),
            radius=float(rng.uniform(0.1, 1)), coherence=float(rng.uniform(0, 1)),
            amplitude=float(rng.uniform(0, 1)), phase=float(rng.uniform(0, 6.28)),
            confidence=float(rng.uniform(0, 1)), frequency=float(rng.uniform(0.1, 5)),
        )
        for i in range(n)
    )
    return FoldedState(query="q", metadata={}, nodes=nodes)


def test_materialized_geometry_round_trips(tmp_path):
    fs = _folded(2000)
    orig = {nd.node_id: nd.position for nd in fs.nodes}
    materialize_to_node_store(fs, tmp_path / "m")
    assert scene_node_count(tmp_path / "m") == 2000
    errs = []
    seen = set()
    for sn in scene_windows(tmp_path / "m", window=512):
        seen.add(sn["id"])
        ox, oy, oz = orig[sn["id"]]
        px, py, pz = sn["position"]
        errs.append(((px - ox) ** 2 + (py - oy) ** 2 + (pz - oz) ** 2) ** 0.5)
    assert seen == set(orig)                       # every node streamed exactly once
    assert float(np.mean(errs)) / 6.0 < 0.02       # <2% of the ~6-unit coord range


def test_scene_stream_memory_bounded_across_N(tmp_path):
    materialize_to_node_store(_folded(10_000), tmp_path / "small")
    materialize_to_node_store(_folded(100_000), tmp_path / "large")

    def peak(root):
        tracemalloc.start()
        for _ in scene_windows(root, window=4096):
            pass
        _c, pk = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return pk

    p_small, p_large = peak(tmp_path / "small"), peak(tmp_path / "large")
    assert p_large <= p_small * 1.5     # 10x nodes must NOT grow the streaming window
    assert p_large < 5_000_000          # window-sized, not N-sized
