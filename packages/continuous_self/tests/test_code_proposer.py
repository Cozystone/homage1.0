# -*- coding: utf-8 -*-
"""Code proposer — the machine WRITES code, but only ever to the staging dir (human-gated)."""
from __future__ import annotations

import ast
from pathlib import Path

from packages.continuous_self import code_proposer as cp


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "PROPOSALS_DIR", tmp_path / "proposals")
    monkeypatch.setattr(cp, "LEDGER", tmp_path / "proposals" / "proposals.jsonl")


def test_test_stub_reads_real_signature_and_parses(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    r = cp.propose_test_stub("packages/cgsr/cgsr/holographic_speaker.py", "hormone_tone")
    assert r["ok"] and r["kind"] == "test_stub"
    staged = Path(r["staged_file"]).read_text(encoding="utf-8")
    ast.parse(staged)                                   # the machine-authored code is valid Python
    assert "hormone_tone" in staged and "import" in staged


def test_unknown_function_is_declined(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    r = cp.propose_test_stub("packages/cgsr/cgsr/holographic_speaker.py", "no_such_fn_xyz")
    assert r["ok"] is False and r["reason"] == "function_not_found"


def test_viewer_component_is_self_contained(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    v = cp.propose_viewer_component("arena", "아레나", "/api/selfhood/live")
    assert v["ok"]
    html = Path(v["staged_file"]).read_text(encoding="utf-8")
    assert "/api/selfhood/live" in html and "<script>" in html
    assert "http://" not in html and "https://" not in html  # no external calls


def test_never_writes_to_the_live_tree(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    cp.propose_test_stub("packages/cgsr/cgsr/holographic_speaker.py", "hormone_tone")
    cp.propose_viewer_component("x", "X", "/api/x")
    # every staged artifact lives under the isolated proposals dir, never at its intended path
    for rec in cp.list_proposals():
        assert str(tmp_path) in rec["staged_file"]
        assert not (cp.REPO / rec["intended_path"]).exists()
        assert rec["applied"] is False
