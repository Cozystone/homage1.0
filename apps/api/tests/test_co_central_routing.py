# -*- coding: utf-8 -*-
"""End-to-end sealed gates for the CO KEYSTONE routing in dual_brain (flag ATANOR_CO_CENTRAL).

  (d) flag OFF (the default) is BYTE-IDENTICAL to before — the routing block does nothing, and no
      co_central trace is attached;
  (a) flag ON routes the finalized frame_realizer knowledge answer (a base_brain_* kind) through the
      response workspace — the main answer WINS the arbitration (won_by == 'main') and the surface is
      preserved (the no-drop gate keeps a curated-prose answer identical), so the answer is byte-identical
      to the flag-OFF answer: zero degradation, no specialist side-lane hijack;
  and a structured_triple_lookup / specialized answer is NOT routed (only the frame_realizer prose is).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

# A knowledge battery whose FINAL answers are deterministic (static base pack + curated store).
_BATTERY = [
    "What is GraphRAG?",
    "What is Kubernetes?",
    "What is encryption?",
    "Explain machine learning.",
    "What is a virtual machine?",
    "What is the capital of France?",
]


def _ask(client: TestClient, q: str) -> dict:
    r = client.post("/api/chat/atanor", json={"question": q, "language": "en", "brain_mode": "local"})
    assert r.status_code == 200, q
    return r.json()["result"]


def test_gate_d_flag_off_is_default_and_attaches_no_co_central_trace(monkeypatch):
    monkeypatch.delenv("ATANOR_CO_CENTRAL", raising=False)
    client = TestClient(app)
    res = _ask(client, "What is GraphRAG?")
    assert res["answer"].strip()
    assert "co_central" not in (res.get("compact_trace") or {})   # the block did nothing


def test_gate_a_flag_on_routes_frame_realizer_prose_through_the_workspace(monkeypatch):
    monkeypatch.setenv("ATANOR_CO_CENTRAL", "1")
    client = TestClient(app)
    res = _ask(client, "What is GraphRAG?")
    # GraphRAG surfaces as frame_realizer prose (base_brain_*), so it IS routed through the workspace
    assert res["answer_kind"].startswith("base_brain")
    cc = (res.get("compact_trace") or {}).get("co_central")
    assert cc is not None, "the frame_realizer knowledge answer must be routed through the workspace"
    assert cc["won_by"] == "main"                                  # the knowledge answer won the arbitration
    assert cc["engine"] == "ATANOR Main"
    # honesty: on curated prose the fluency pass is safely kept literal (no-drop), never a degradation
    assert cc["fluency_adopted"] is False
    assert cc["fluency_reason"] in ("literal_content_dropped", "no_faithful_surface", "no_fluency_gain",
                                    "not_multi_fact", "no_bones")


def test_gate_a_flag_on_is_byte_identical_to_flag_off_on_the_battery(monkeypatch):
    # capture flag-OFF answers
    monkeypatch.delenv("ATANOR_CO_CENTRAL", raising=False)
    client = TestClient(app)
    off = {q: _ask(client, q)["answer"] for q in _BATTERY}
    # flip the flag ON and re-ask — every answer must be identical (preserved-or-faithful, here preserved)
    monkeypatch.setenv("ATANOR_CO_CENTRAL", "1")
    on = {q: _ask(client, q)["answer"] for q in _BATTERY}
    diffs = {q: (off[q], on[q]) for q in _BATTERY if off[q] != on[q]}
    assert not diffs, diffs


def test_structured_and_specialized_answers_are_not_routed(monkeypatch):
    monkeypatch.setenv("ATANOR_CO_CENTRAL", "1")
    client = TestClient(app)
    # a curated structured-triple answer (not the frame_realizer prose) is left exactly as-is
    res = _ask(client, "What is Kubernetes?")
    assert res["answer_kind"] == "structured_triple_lookup"
    assert "co_central" not in (res.get("compact_trace") or {})   # not routed -> untouched
