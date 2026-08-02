# -*- coding: utf-8 -*-
"""Self-refinement stages 1+3 — contradiction sweep + hypothesis mint loop."""

from __future__ import annotations

import json

import packages.graph_scale.contradiction_sweep as cs
import packages.graph_scale.hypothesis_minter as hm
import packages.graph_scale.abstain_queue as abstain_queue
from packages.graph_scale.triple_store import TripleStore


def _seed_store(tmp_path):
    st = TripleStore(tmp_path / "kg")
    good = st.intern_source("curated_a", "")
    bad = st.intern_source("blog_x", "")

    for i in range(24):
        st.add(f"나라{i}", "수도", f"도시{i}", source=good)
    st.add("호주", "수도", "캔버라", source=good)
    st.add("호주", "수도", "시드니", source=bad)

    for i in range(24):
        st.add(f"나라{i}", "이웃", f"나라{(i + 1) % 24}")
        st.add(f"나라{i}", "이웃", f"나라{(i + 2) % 24}")
    st.flush()
    return st


def test_functionality_is_measured_not_listed(tmp_path):
    st = _seed_store(tmp_path)
    f = cs.measure_functionality(st)
    assert f["수도"]["functional"] is True
    assert f["이웃"]["functional"] is False  # multi-valued by the data itself


def test_lopsided_conflict_is_quarantined_not_deleted(tmp_path, monkeypatch):
    st = _seed_store(tmp_path)
    monkeypatch.setattr(cs, "LEDGER", tmp_path / "led.jsonl")
    out = cs.sweep(st, apply=True)
    assert out["conflicts"] == 1 and out["resolved"] == 1
    facts = st.facts_about("호주", limit=10)
    assert ("호주", "수도", "캔버라") in facts
    assert ("호주", "수도", "시드니") not in facts   # tombstoned...
    retr = (st.root / "retractions.jsonl").read_text(encoding="utf-8")
    assert "시드니" in retr and "contradiction_sweep" in retr  # ...auditable


def test_contradiction_sweep_defaults_to_observe_only(tmp_path, monkeypatch):
    st = _seed_store(tmp_path)
    monkeypatch.setattr(cs, "LEDGER", tmp_path / "led.jsonl")
    monkeypatch.setattr(abstain_queue, "record_abstain", lambda _term: True)

    out = cs.sweep(st)

    assert out["conflicts"] == 1
    assert out["resolved"] == 0
    assert ("호주", "수도", "시드니") in st.facts_about("호주", limit=10)
    assert not (st.root / "retractions.jsonl").exists()


def test_balanced_conflict_is_queued_not_judged(tmp_path, monkeypatch):
    st = TripleStore(tmp_path / "kg")
    src1, src2 = st.intern_source("blog_a", ""), st.intern_source("blog_b", "")
    for i in range(24):
        st.add(f"나라{i}", "수도", f"도시{i}", source=src1)
    st.add("분쟁국", "수도", "도시A", source=src1)
    st.add("분쟁국", "수도", "도시B", source=src2)  # blog vs blog — balanced
    st.flush()
    monkeypatch.setattr(cs, "LEDGER", tmp_path / "led.jsonl")
    pushed = []
    monkeypatch.setattr(cs, "abstain_queue", None, raising=False)
    out = cs.sweep(st, apply=True)
    assert out["resolved"] == 0 and out["queued_for_evidence"] == 1
    facts = st.facts_about("분쟁국", limit=10)
    assert len([f for f in facts if f[1] == "수도"]) == 2  # both kept — learn more


def test_hypothesis_loop_mints_questions_never_facts(tmp_path, monkeypatch):
    monkeypatch.setattr(hm, "LEDGER", tmp_path / "hyp.jsonl")
    st = TripleStore(tmp_path / "kg")
    st.add("문명", "is_a", "개념")
    st.flush()

    import packages.graph_scale.phase_space as ps
    monkeypatch.setattr(ps, "_load", lambda: True)
    monkeypatch.setattr(ps, "_SPACE", {"terms": ["문명", "기후", "바다"], "idx": {}})
    monkeypatch.setattr(ps, "neighbors",
                        lambda t, k=6: [("기후", 0.81)] if t == "문명" else [])

    minted = hm.mint(store=st, k_terms=3, seed=1)
    assert len(minted) == 1
    row = minted[0]
    assert row["status"] == "unverified"
    assert "어떤 관계" in row["question"]
    # the store was NOT touched — a hypothesis is a question, not knowledge
    assert hm._kg_edge_between(st, "문명", "기후") is None

    # settle: once gated evidence lands a real edge, the hypothesis confirms
    st.add("문명", "영향받음", "기후")
    st.flush()
    out = hm.settle(store=st)
    assert out["confirmed"] == 1
    rows = [json.loads(l) for l in (tmp_path / "hyp.jsonl").read_text(
        encoding="utf-8").splitlines()]
    assert rows[0]["status"] == "confirmed" and rows[0]["edge"] == "영향받음"
