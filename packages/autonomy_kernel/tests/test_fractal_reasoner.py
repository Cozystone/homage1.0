# -*- coding: utf-8 -*-
"""The fractal reasoner must (a) stay OFF for simple/high-confidence queries, (b) debate only in
grounded terms and collapse to an honest verdict, (c) report unstable/insufficient rather than
fabricate, (d) never write to the store."""
import tempfile
from pathlib import Path

from packages.graph_scale.triple_store import TripleStore
from packages.autonomy_kernel import fractal_reasoner as fr


class _F:  # minimal frame stub
    def __init__(self, act="", fact_intent="", subject="", verify_target=""):
        self.act, self.fact_intent, self.subject, self.verify_target = act, fact_intent, subject, verify_target


def _store():
    st = TripleStore(Path(tempfile.mkdtemp()) / "kg")
    for s, o in [("진돗개", "개"), ("개", "포유류"), ("포유류", "동물")]:
        st.add(s, "is_a", o)
    st.flush()
    return st


def test_gate_stays_closed_for_simple_or_confident():
    # high confidence → never engage, even if complex
    assert fr.should_engage(_F(fact_intent="cause"), answer_confidence=0.9) is False
    # low confidence but a SIMPLE fact lookup → the fast path handles it
    assert fr.should_engage(_F(fact_intent="verify"), answer_confidence=0.1) is False
    # low confidence AND complex → the special move unlocks
    assert fr.should_engage(_F(fact_intent="cause"), answer_confidence=0.2) is True


def test_deliberate_collapses_and_never_writes():
    st = _store()
    before = len(st)
    r = fr.deliberate("진돗개는 동물이야?", st, frame=_F(subject="진돗개", verify_target="동물"))
    assert r["collapsed"] is True
    assert r["verdict"] in ("supported", "contradicted", "unstable", "insufficient_evidence")
    assert len(st) == before          # read-only


def test_contradiction_surfaces_as_grounded_against_evidence():
    st = _store()

    r = fr.deliberate("동물이 진돗개야?", st, frame=_F(subject="동물", verify_target="진돗개"))
    assert r["against_count"] >= 1
    assert r["verdict"] in ("contradicted", "unstable")


def test_maybe_deliberate_off_by_default(monkeypatch):
    monkeypatch.delenv("ATANOR_FRACTAL", raising=False)
    assert fr.maybe_deliberate("x", _store(), frame=_F(fact_intent="cause"), answer_confidence=0.1) is None
    monkeypatch.setenv("ATANOR_FRACTAL", "1")
    out = fr.maybe_deliberate("x", _store(), frame=_F(fact_intent="cause", subject="진돗개"), answer_confidence=0.1)
    assert out is not None and out["collapsed"] is True


def test_moral_gate_exception_aborts_deliberation(monkeypatch):
    from packages.graph_scale import moral_invariants

    monkeypatch.setattr(
        moral_invariants,
        "verify_integrity",
        lambda: (_ for _ in ()).throw(RuntimeError("gate offline")),
    )
    r = fr.deliberate("x", _store(), frame=_F(subject="x"))
    assert r == {
        "verdict": "aborted",
        "reason": "moral_core_integrity_failed",
        "collapsed": True,
    }


def test_truthy_moral_verdict_cannot_authorize_deliberation(monkeypatch):
    from packages.graph_scale import moral_invariants

    monkeypatch.setattr(moral_invariants, "verify_integrity", lambda: {"ok": "true"})
    r = fr.deliberate("x", _store(), frame=_F(subject="x"))
    assert r["verdict"] == "aborted"
