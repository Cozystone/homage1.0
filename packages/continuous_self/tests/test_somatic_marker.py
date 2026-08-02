# -*- coding: utf-8 -*-
"""Somatic markers (plan S3) — first-person consequence-traces per concept. The tests assert the
one property that separates perspective from performance: a stance appears ONLY when the trace is
real (a concept with no history gets NO point of view — the no-fabrication floor extended to
selfhood), the marker's sign matches what actually happened, and the spoken colour never leaks into
the fact taught."""
from __future__ import annotations

import json
import time

import packages.continuous_self.somatic_marker as sm
from packages.continuous_self.somatic_marker import Marker


def _wire(tmp_path, monkeypatch, *, learned=None, receipts=None, mentor=None):
    lp = tmp_path / "learned.jsonl"
    rp = tmp_path / "receipts.jsonl"
    mp = tmp_path / "mentor.log"
    lp.write_text("\n".join(json.dumps(x) for x in (learned or [])), encoding="utf-8")
    rp.write_text("\n".join(json.dumps(x) for x in (receipts or [])), encoding="utf-8")
    mp.write_text("\n".join(json.dumps(x) for x in (mentor or [])), encoding="utf-8")
    monkeypatch.setattr(sm, "_LEARNED", lp)
    monkeypatch.setattr(sm, "_RECEIPTS", rp)
    monkeypatch.setattr(sm, "_MENTOR", mp)
    monkeypatch.setattr(sm, "_IGN", tmp_path / "none.jsonl")
    monkeypatch.setattr(sm, "_CACHE", None)              # bust the module cache


# ---------- the honest floor: no history, no perspective ----------

def test_unknown_concept_has_no_stance(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    assert sm.marker_for("aardvark") is None
    assert sm.stance("aardvark") == ""                   # a concept it never met gets no point of view


def test_stance_requires_real_history(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch,
          learned=[{"concept": "city", "understanding": "a large settlement"}])
    m = sm.marker_for("city")
    assert m is not None and m.has_history()
    assert sm.stance("city") != ""                        # a real trace earns a stance


# ---------- the marker's sign matches what actually happened ----------

def test_self_learned_concept_reads_positive(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch,
          learned=[{"concept": "island", "understanding": "land surrounded by water"}])
    m = sm.marker_for("island")
    assert m.valence > 0
    assert "understand" in sm.stance("island") or "familiar" in sm.stance("island")


def test_failed_concept_reads_negative_and_effortful(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch,
          receipts=[{"topic": "quantum tunneling", "ts": time.time()} for _ in range(2)])
    m = sm.marker_for("quantum")
    assert m.valence < 0 and m.effort >= 0.5
    assert "struggled" in sm.stance("quantum") or "wrong before" in sm.stance("quantum")


def test_gap_then_fill_is_a_recovery(tmp_path, monkeypatch):
    """A concept ATANOR named as a gap in itself and LATER filled reads as recently-understood —
    the exact 'I only recently came to grasp this' first-person fact."""
    now = time.time()
    _wire(tmp_path, monkeypatch, mentor=[{
        "ts": now, "gaps": {"foundational_gaps": ["river"]},
        "learned": [{"concept": "river", "understanding": "a flowing watercourse"}]}])
    m = sm.marker_for("river")
    assert m.has_history() and m.valence > 0              # the fill outweighs the gap
    assert "recently came to understand" in sm.stance("river")


# ---------- perspective colours speech but never the fact taught ----------

def test_stance_does_not_leak_into_taught_payload(tmp_path, monkeypatch):
    """The conversation engine prepends a stance to the SPOKEN text but the peer LEARNS the clean
    fact — a point of view must not become someone else's data."""
    _wire(tmp_path, monkeypatch,
          learned=[{"concept": "coffee", "understanding": "a brewed drink"}])
    # hermetic: the shared engine now graph-enriches thin (is_a-only) bones from the live store
    # (lever 2, 2026-07-24); stub that read so this unit test asserts the clean payload offline.
    monkeypatch.setattr("packages.brain_link.conversation._graph_facts", lambda *a, **k: [])
    from packages.brain_link.conversation import Agent, step, Turn
    a = Agent("pc", knowledge={"coffee": [["coffee", "is_a", "beverage"]]}, web=False)
    ask = Turn("edge", "what is coffee?", "ask", concept="coffee")
    out = step(a, ask)
    assert out.act == "answer_known"
    assert out.payload == "Coffee is a beverage."          # the taught fact is clean
    # the spoken text may carry the stance, but only because the trace is real
    if sm.stance("coffee"):
        assert out.text != out.payload


# ---------- rumination: return to what marked you ----------

def test_revisit_prioritizes_invested_concepts(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch,
          receipts=[{"topic": "entropy", "ts": time.time()} for _ in range(2)])   # hard-won scar
    order = sm.revisit_priority(["banana", "entropy", "table"])
    assert order[0] == "entropy"                           # the invested concept comes first
    # concepts with no trace keep their given relative order, after
    assert order[1:] == ["banana", "table"]


def test_revisit_is_identity_without_history(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    assert sm.revisit_priority(["a", "b", "c"]) == ["a", "b", "c"]   # no trace -> no reordering
