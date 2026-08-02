# -*- coding: utf-8 -*-
"""Stages 3+4 of the sense-disease repair: per-sense closure stays inside one
reading, and the registry is a versioned sense-keyed read layer."""
import numpy as np
import pytest

pytestmark = pytest.mark.usefixtures()


class _Terms:
    def __init__(self):
        self._t = {}; self._r = {}
    def add(self, t):
        if t not in self._t:
            self._t[t] = len(self._t); self._r[self._t[t]] = t
        return self._t[t]
    def lookup(self, t): return self._t.get(t)
    def term(self, i): return self._r.get(i)


class _Store:
    """Minimal store: facts_about + the column attrs the trust filter reads."""
    def __init__(self, tmp, triples):
        self.root = tmp
        self.terms = _Terms()
        rows = [(self.terms.add(s), self.terms.add(p), self.terms.add(o), src)
                for s, p, o, src in triples]
        for name, col in zip(("s", "p", "o", "src"),
                             zip(*rows) if rows else ([], [], [], [])):
            np.asarray(col, dtype="<i4").tofile(tmp / f"{name}.col")
        self._by_s = {}
        for s, p, o, _ in triples:
            self._by_s.setdefault(s, []).append((s, p, o))
    def facts_about(self, t, limit=100): return self._by_s.get(t, [])[:limit]
    def _sources(self): return ["legacy", "dbpedia:bulk"]
    def _tombstones(self): return set()


def _hub_store(tmp):

    # discriminative grandparent; plus one garbage-batch parent.
    t = []
    t += [("동전", "is_a", "화폐", 1), ("동전", "is_a", "현금", 1),
          ("동전", "is_a", "금속조각", 1), ("동전", "is_a", "원반", 1)]
    t += [("동전", "is_a", f"junk{i}", 0) for i in range(10)]   # hub-maker
    t += [("화폐", "is_a", "교환수단", 1), ("현금", "is_a", "교환수단", 1),
          ("금속조각", "is_a", "물체", 1), ("원반", "is_a", "물체", 1)]
    return _Store(tmp, t)


def test_per_sense_closure_scopes_to_cluster(tmp_path):
    from packages.graph_scale.sense_partition import per_sense_closure_candidates
    st = _hub_store(tmp_path)
    cands = per_sense_closure_candidates(st, "동전")
    by = {}
    for c in cands:
        by.setdefault(c["candidate"][2], set()).add(c["sense_id"])
    # both grandparents proposed, and each under ONE sense only
    assert "교환수단" in by and "물체" in by
    assert by["교환수단"] != by["물체"]
    # every candidate carries sense + provenance for the evidence gates
    assert all(c["via"] and c["sense_id"] for c in cands)


def test_registry_roundtrip(tmp_path, monkeypatch):
    from packages.graph_scale import sense_registry as sr
    monkeypatch.setattr(sr, "REG_DIR", tmp_path)
    monkeypatch.setattr(sr, "CURRENT", tmp_path / "current.json")
    sr._CACHE["data"] = None; sr._CACHE["key"] = None
    st = _hub_store(tmp_path)
    out = sr.build_registry(st, max_hubs=10, log=lambda *_: None)
    assert out["hubs_registered"] >= 1
    senses = sr.senses_of("동전")
    assert senses and all(s["sense_id"] for s in senses)

    money = sr.sense_scoped_parents("동전", {"화폐"})
    assert "화폐" in money and "금속조각" not in money
