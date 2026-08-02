# -*- coding: utf-8 -*-
"""The System 1 intuition spark: perturbation surfaces cross-domain collisions
as QUESTIONS (never facts), and a calm space (no energy) produces no false leaps.
"""
import numpy as np


class _StubStore:
    """Records any attempt to touch it. The spark must NEVER write facts."""
    def __init__(self):
        self.writes = 0
    def facts_about(self, term, limit=40):
        return []                       # no existing edges -> nothing filtered out
    def add(self, *a, **k):
        self.writes += 1                # if the spark ever writes, this trips


def _inject_space(monkeypatch, n=50, seed=1):
    from packages.graph_scale import phase_space
    rng = np.random.default_rng(seed)
    terms = [f"개념{i:02d}자" for i in range(n)]     # legible Korean, 2-8 chars
    phases = rng.uniform(0, 2 * np.pi, size=(n, 8)).astype(np.float32)
    phase_space._SPACE["phases"] = phases
    phase_space._SPACE["terms"] = terms
    phase_space._SPACE["idx"] = {t: i for i, t in enumerate(terms)}
    monkeypatch.setattr(phase_space, "_load", lambda: True)


def test_energy_zero_is_calm_no_false_leaps(tmp_path, monkeypatch):
    """With no storm the geometry is unperturbed, so a FAR pair stays far and
    nothing can satisfy (clean<0.15 AND sparked>0.55). Zero sparks — the machine
    is not manufacturing analogies out of nothing."""
    from packages.graph_scale import intuition_spark as isp
    _inject_space(monkeypatch)
    monkeypatch.setattr(isp, "LEDGER", tmp_path / "sparks.jsonl")
    out = isp.spark(store=_StubStore(), energy=0.0, seed=3)
    assert out == []


def test_perturbation_sparks_are_questions_and_immune(tmp_path, monkeypatch):
    """Loosen the thresholds so a collision is guaranteed, then assert every
    spark (a) satisfies the far-then-collided invariant, (b) is a QUESTION with
    both concepts, (c) is unverified, and (d) the store received ZERO writes —
    model-collapse immunity is structural."""
    from packages.graph_scale import intuition_spark as isp
    _inject_space(monkeypatch)
    monkeypatch.setattr(isp, "LEDGER", tmp_path / "sparks.jsonl")
    monkeypatch.setattr(isp, "_CLEAN_MAX", 0.9)      # accept almost any clean res
    monkeypatch.setattr(isp, "_LAND_MIN", -1.0)      # ...and any landing res
    store = _StubStore()
    out = isp.spark(store=store, energy=1.0, seed=7, k_terms=40)
    assert out, "loosened thresholds must yield sparks"
    for row in out:
        assert row["clean_resonance"] < isp._CLEAN_MAX
        assert row["sparked_resonance"] > isp._LAND_MIN
        assert row["status"] == "unverified" and row["kind"] == "intuition_spark"
        assert row["a"] in row["question"] and row["b"] in row["question"]
        assert row["a"] != row["b"]
    assert store.writes == 0                          # never wrote a fact
    # ledgered as questions, and re-running does not duplicate a known pair
    again = isp.spark(store=store, energy=1.0, seed=7, k_terms=40)
    seen = {(r["a"], r["b"]) for r in out}
    assert all((r["a"], r["b"]) not in seen for r in again)


def test_energy_from_hormones_waxes_and_wanes():
    """Curiosity/arrival lift energy; stress and forced rest calm it."""
    from packages.graph_scale import intuition_spark as isp
    calm = isp.energy_from_hormones({})
    curious = isp.energy_from_hormones({"dopamine": 0.9, "noradrenaline": 0.8})
    stressed = isp.energy_from_hormones({"dopamine": 0.9, "noradrenaline": 0.8,
                                         "cortisol": 1.0, "repair": 1.0})
    assert abs(calm - 0.2) < 1e-6              # baseline muse
    assert curious > calm                       # arousal widens the leaps
    assert stressed < curious                   # stress/rest reins them in
    assert 0.0 <= stressed <= 1.2


def test_collide_forces_two_domains_and_stays_a_question(tmp_path, monkeypatch):
    """Naming two concepts returns the shared-ground bridges (resonate with BOTH)
    and ledgers the pair as a QUESTION, never a fact."""
    from packages.graph_scale import intuition_spark as isp
    _inject_space(monkeypatch, n=60)
    monkeypatch.setattr(isp, "LEDGER", tmp_path / "sparks.jsonl")
    a, b = "개념05자", "개념40자"
    r = isp.collide(_StubStore(), a, b)
    assert r["available"] and r["a"] == a and r["b"] == b
    assert a in r["question"] and b in r["question"]
    for br in r["bridges"]:
        assert br["term"] not in (a, b)         # a bridge is a third concept
    miss = isp.collide(_StubStore(), a, "존재하지않는개념")
    assert miss["available"] is False and "존재하지않는개념" in miss.get("missing", [])
