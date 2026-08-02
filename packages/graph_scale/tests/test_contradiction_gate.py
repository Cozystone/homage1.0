# -*- coding: utf-8 -*-
"""The algebraic contradiction gate must bounce structurally impossible is_a edges (self-loop,
direct reversal, cycle) deterministically, while letting valid taxonomy edges through — all in
int space against the existing graph, writing nothing."""
import tempfile
from pathlib import Path

from packages.graph_scale.triple_store import TripleStore
from packages.graph_scale.contradiction_gate import check_edges, gate_candidates


def _store():
    st = TripleStore(Path(tempfile.mkdtemp()) / "kg")
    for s, o in [("진돗개", "개"), ("개", "포유류"), ("포유류", "동물"),
                 ("고양이", "포유류"), ("참새", "조류"), ("조류", "동물")]:
        st.add(s, "is_a", o)
    st.flush()
    return st


def test_rejects_cycle_reversal_selfloop_accepts_valid():
    st = _store()
    r = check_edges(st, [
        ("동물", "진돗개"),
        ("개", "진돗개"),
        ("진돗개", "진돗개"),   # self-loop
        ("진돗개", "동물"),     # VALID: transitive, no cycle
        ("호랑이", "포유류"),   # VALID: new subject
    ])
    reasons = {tuple(x["edge"]): x["reason"] for x in r["rejected"]}
    assert reasons[("동물", "진돗개")] == "cycle"
    assert reasons[("개", "진돗개")] == "direct_reversal"
    assert reasons[("진돗개", "진돗개")] == "self_loop"
    accepted = {tuple(e) for e in r["accepted"]}
    assert ("진돗개", "동물") in accepted
    assert ("호랑이", "포유류") in accepted
    assert r["rejected_count"] == 3 and r["accepted_count"] == 2


def test_gate_candidates_returns_clean_survivors_and_writes_nothing():
    st = _store()
    before = len(st)
    clean, rep = gate_candidates(st, [("동물", "개"), ("사자", "포유류")])
    assert ("사자", "포유류") in clean
    assert ("동물", "개") not in clean
    assert len(st) == before                    # gate is read-only
    assert rep["checked"] == 2
