"""Consensus ledger: relations enter the store only when independently re-confirmed."""
from __future__ import annotations

import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[3]
for p in (str(_REPO), str(_REPO / "packages"), str(_REPO / "packages" / "cgsr")):
    if p not in sys.path:
        sys.path.insert(0, p)

from packages.cgsr.cgsr.ingestion.decomposer import DecompositionResult
from packages.cloud_brain.consensus_ledger import ConsensusLedger, head_roundtrip_ok


def _decomp(subject: str, relation: str, obj: str, sentence: str, source_hash: str) -> DecompositionResult:
    return DecompositionResult(
        concepts=[
            {"concept_id": "c_s", "canonical_name": subject},
            {"concept_id": "c_o", "canonical_name": obj},
        ],
        relations=[
            {
                "dedupe_key": f"relation_key_{source_hash}_{subject}_{obj}",
                "relation": relation,
                "source_concept_id": "c_s",
                "target_concept_id": "c_o",
                "language": "ko",
            }
        ],
        evidence={"text": sentence, "source_hash": source_hash},
    )


def test_single_evidence_stays_quarantined(tmp_path):
    ledger = ConsensusLedger(tmp_path / "ledger", min_sources=2)
    r = ledger.record_decomposition(
        _decomp("엔비디아", "IS_A", "기업", "엔비디아는 미국의 반도체 기업이다.", "h1")
    )
    assert r.events_recorded == 1
    assert ledger.promotable() == []
    assert ledger.stats()["relations_quarantined"] == 1


def test_independent_reconfirmation_promotes(tmp_path):
    ledger = ConsensusLedger(tmp_path / "ledger", min_sources=2)
    ledger.record_decomposition(_decomp("엔비디아", "IS_A", "기업", "엔비디아는 미국의 반도체 기업이다.", "h1"))
    ledger.record_decomposition(_decomp("엔비디아", "IS_A", "기업", "엔비디아는 GPU를 만드는 기업이다.", "h2"))
    promotable = ledger.promotable()
    assert len(promotable) == 1
    assert len(promotable[0][1]["sources"]) == 2


def test_same_sentence_counts_once(tmp_path):
    ledger = ConsensusLedger(tmp_path / "ledger", min_sources=2)
    d = _decomp("엔비디아", "IS_A", "기업", "엔비디아는 미국의 반도체 기업이다.", "h1")
    ledger.record_decomposition(d)
    r2 = ledger.record_decomposition(d)  # identical sentence re-ingested
    assert r2.events_duplicate == 1
    assert ledger.promotable() == []  # 1 independent source, not 2


def test_roundtrip_rejects_mangled_head(tmp_path):
    ledger = ConsensusLedger(tmp_path / "ledger", min_sources=1)

    r = ledger.record_decomposition(
        _decomp("삼성", "IS_A", "기업", "엔비디아는 미국의 반도체 기업이다.", "h1")
    )
    assert r.events_rejected_roundtrip == 1
    assert r.events_recorded == 0


def test_roundtrip_rejects_date_unit_head():
    assert not head_roundtrip_ok("일", "홍길동(1992년 8월 28일 ~ )은 대한민국의 축구 선수이다.")
    assert head_roundtrip_ok("홍길동", "홍길동(1992년 8월 28일 ~ )은 대한민국의 축구 선수이다.")


def test_ledger_survives_restart(tmp_path):
    root = tmp_path / "ledger"
    ConsensusLedger(root, min_sources=2).record_decomposition(
        _decomp("엔비디아", "IS_A", "기업", "엔비디아는 미국의 반도체 기업이다.", "h1")
    )
    reloaded = ConsensusLedger(root, min_sources=2)  # counts rebuilt from JSONL
    reloaded.record_decomposition(_decomp("엔비디아", "IS_A", "기업", "엔비디아는 GPU 기업이다.", "h2"))
    assert len(reloaded.promotable()) == 1
