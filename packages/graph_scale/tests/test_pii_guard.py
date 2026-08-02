# -*- coding: utf-8 -*-
"""PII guard — detection, ingest gate, quarantine sweep, right-to-be-forgotten."""

from __future__ import annotations

import packages.graph_scale.pii_guard as pg
from packages.graph_scale.triple_store import TripleStore


def test_detect_structured_pii_and_mask_never_leaks_raw():
    hits = pg.detect("연락처는 010-1234-5678 이고 메일은 hong@example.com 이다")
    types = {h["type"] for h in hits}
    assert "phone_kr" in types and "email" in types
    # the raw value never appears; only a masked form
    for h in hits:
        assert "1234" not in h["masked"] or "*" in h["masked"]
    assert not any("hong@example.com" == h["masked"] for h in hits)


def test_krrn_checksum_cuts_false_positives():
    assert pg.has_pii("901231-1234567")
    assert not pg.has_pii("999999-9234567")        # month 99 -> implausible


def test_clean_text_has_no_pii():
    assert pg.detect("바다는 소금물이 넓게 고인 곳이다") == []


def test_gate_refuses_pii_candidate():
    ok = pg.gate("바다", "defined_as", "소금물이 고인 곳")
    assert ok["allowed"] is True
    bad = pg.gate("홍길동", "연락처", "010-9876-5432")
    assert bad["allowed"] is False and bad["pii"]


def test_scan_quarantines_pii_rows_reversibly(tmp_path, monkeypatch):
    monkeypatch.setattr(pg, "LEDGER", tmp_path / "pl.jsonl")
    st = TripleStore(tmp_path / "kg")
    st.add("바다", "defined_as", "소금물이 넓게 고인 곳")
    st.add("사용자", "연락처", "010-1234-5678")   # PII object
    st.add("hong@example.com", "is_a", "이메일")  # PII subject
    st.flush()
    out = pg.scan_and_quarantine(st, apply=True)
    assert out["quarantined"] == 2
    # clean fact survives; PII facts are tombstoned (reversible)
    assert st.facts_about("바다", limit=5) == [("바다", "defined_as", "소금물이 넓게 고인 곳")]
    assert st.facts_about("사용자", limit=5) == []


def test_pii_mutation_helpers_default_to_observe_only(tmp_path, monkeypatch):
    monkeypatch.setattr(pg, "LEDGER", tmp_path / "pl.jsonl")
    st = TripleStore(tmp_path / "kg")
    st.add("사용자", "연락처", "010-1234-5678")
    st.flush()

    scan = pg.scan_and_quarantine(st)
    forget = pg.forget(st, "사용자")

    assert scan["detected"] == 1
    assert scan["quarantined"] == 0
    assert scan["applied"] is False
    assert forget["rows_matched"] == 1
    assert forget["rows_removed"] == 0
    assert forget["applied"] is False
    assert st.facts_about("사용자", limit=5)
    assert not (st.root / "retractions.jsonl").exists()
    assert not pg.LEDGER.exists()


def test_forget_removes_all_mentions(tmp_path, monkeypatch):
    monkeypatch.setattr(pg, "LEDGER", tmp_path / "pl.jsonl")
    st = TripleStore(tmp_path / "kg")
    st.add("홍길동", "직업", "회사원")
    st.add("홍길동", "거주지", "서울")
    st.add("회사", "직원", "홍길동")     # mention as object
    st.add("바다", "defined_as", "소금물")  # unrelated, must survive
    st.flush()
    out = pg.forget(st, "홍길동", apply=True)
    assert out["rows_removed"] == 3
    assert st.facts_about("홍길동", limit=5) == []
    assert st.facts_about("바다", limit=5) == [("바다", "defined_as", "소금물")]
