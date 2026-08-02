# -*- coding: utf-8 -*-
"""3 R1 — . (env) :
no-wifi=LOCAL_BASE( ), +=LOCAL_EXPERT, +=SAGE. ."""
from __future__ import annotations

import packages.reasoning_vm.capability_tier as CT


def _fresh(monkeypatch, offline: bool, no_pack: bool):
    monkeypatch.setenv("ATANOR_FORCE_OFFLINE", "1" if offline else "0")
    monkeypatch.setenv("ATANOR_FORCE_NO_PACK", "1" if no_pack else "0")
    return CT.current_tier(refresh=True)


def test_local_base_when_offline_and_no_pack(monkeypatch):
    t = _fresh(monkeypatch, offline=True, no_pack=True)
    assert t["tier"] == CT.LOCAL_BASE and t["internet"] is False and t["pack"] is False
    assert "guesses" in t["persona"]


def test_local_expert_when_offline_with_pack(monkeypatch):
    t = _fresh(monkeypatch, offline=True, no_pack=False)
    if not t["pack"]:
        import pytest
        pytest.skip("PROPHETA pack not present on this machine")
    assert t["tier"] == CT.LOCAL_EXPERT
    assert "expert" in t["persona"]


def test_sage_when_online(monkeypatch):
    t = _fresh(monkeypatch, offline=False, no_pack=True)
    if not t["internet"]:
        import pytest
        pytest.skip("no live internet on this machine")
    assert t["tier"] == CT.SAGE and "sage" in t["persona"]


def test_hedge_matches_tier_and_confidence():
    assert CT.tier_hedge(CT.SAGE, confident=True) == ""
    assert "web" in CT.tier_hedge(CT.SAGE, confident=False)
    assert "knowledge base" in CT.tier_hedge(CT.LOCAL_EXPERT, confident=False)
    assert "offline" in CT.tier_hedge(CT.LOCAL_BASE, confident=False)


def test_annotate_attaches_tier_meta(monkeypatch):
    _fresh(monkeypatch, offline=True, no_pack=True)
    out = CT.annotate({"answer": "X"}, confidence=0.3)
    assert out["knowledge_tier"] == CT.LOCAL_BASE
    assert "offline" in out["tier_hedge"]
    out2 = CT.annotate({"answer": "Y"}, confidence=0.95)
    assert out2["tier_hedge"] == ""


def test_detection_never_raises(monkeypatch):

    for off in ("0", "1"):
        for np_ in ("0", "1"):
            monkeypatch.setenv("ATANOR_FORCE_OFFLINE", off)
            monkeypatch.setenv("ATANOR_FORCE_NO_PACK", np_)
            t = CT.current_tier(refresh=True)
            assert t["tier"] in {CT.LOCAL_BASE, CT.LOCAL_EXPERT, CT.SAGE}
