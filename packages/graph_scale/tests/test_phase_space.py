# -*- coding: utf-8 -*-
"""Phase space: gradient converges on a synthetic clustered graph and the
learned geometry beats random at held-out link prediction."""
from __future__ import annotations

import numpy as np

from packages.graph_scale import phase_space


class _FakeTerms:
    def __init__(self, names):
        self._names = names
        self._ids = {n: i for i, n in enumerate(names)}

    def lookup(self, name):
        return self._ids.get(name)

    def term(self, tid):
        return self._names[tid]


class _FakeStore:
    """Three is_a clusters (animals / cities / tools) with 20 members each —
    enough structure for the phase geometry to separate them."""

    def __init__(self):
        names = ["is_a"]
        edges = []
        rng = np.random.default_rng(0)
        for hub in ("animal", "city", "tool"):
            names.append(hub)
        for hub in ("animal", "city", "tool"):
            hub_id = names.index(hub)
            for i in range(20):
                m = f"{hub}_{i}"
                names.append(m)
                edges.append((names.index(m), 0, hub_id))
                # a few intra-cluster sibling edges for density
                if i > 0:
                    edges.append((names.index(m), 0, names.index(f"{hub}_{i - 1}")))
        self.terms = _FakeTerms(names)
        self._edges = edges
        rng.shuffle(self._edges)

    def open_columns(self):
        e = np.array(self._edges, dtype=np.int64)
        return {"s": e[:, 0], "p": e[:, 1], "o": e[:, 2]}


def test_training_converges_and_beats_random(tmp_path, monkeypatch):
    monkeypatch.setattr(phase_space, "SPACE_DIR", tmp_path)
    monkeypatch.setattr(phase_space, "PHASES_PATH", tmp_path / "phases.npy")
    monkeypatch.setattr(phase_space, "REL_PATH", tmp_path / "relations.npy")
    monkeypatch.setattr(phase_space, "TERMS_PATH", tmp_path / "terms.json")
    logs: list[str] = []
    r = phase_space.train_phase_space(_FakeStore(), epochs=40, min_degree=1,
                                      min_edges=50, batch=64, log=logs.append)
    assert "error" not in r, r
    # rank must beat the random baseline (~100.5 for 201 candidates). hits@10 is
    # structurally low HERE: all 20 cluster siblings share the hub's phase target,
    # so corrupted siblings are near-valid — the real 25M-row graph, with distinct
    # neighborhoods, measured hits@10 = 0.878.
    assert r["mean_rank"] < 90, r
    # convergence: last logged d_pos well below the 5.09 random expectation
    last = [l for l in logs if "d_pos" in l][-1]
    d_pos = float(last.split("d_pos=")[1].split()[0])
    assert d_pos < 3.0, last


def test_resonance_separates_clusters(tmp_path, monkeypatch):
    monkeypatch.setattr(phase_space, "SPACE_DIR", tmp_path)
    monkeypatch.setattr(phase_space, "PHASES_PATH", tmp_path / "phases.npy")
    monkeypatch.setattr(phase_space, "REL_PATH", tmp_path / "relations.npy")
    monkeypatch.setattr(phase_space, "TERMS_PATH", tmp_path / "terms.json")
    phase_space._SPACE["phases"] = None
    phase_space.train_phase_space(_FakeStore(), epochs=40, min_degree=1,
                                  min_edges=50, batch=64, log=lambda *_: None)
    same = phase_space.resonance("animal_3", "animal_7")
    cross = phase_space.resonance("animal_3", "tool_7")
    assert same is not None and cross is not None
    assert same > cross  # intra-cluster interference beats inter-cluster