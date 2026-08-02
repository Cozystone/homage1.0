"""Trust scaling: spot-audit sampling + CUSUM drift freeze on promotion surges."""
from __future__ import annotations

import pathlib
import random
import sys

_REPO = pathlib.Path(__file__).resolve().parents[3]
for p in (str(_REPO), str(_REPO / "packages"), str(_REPO / "packages" / "cgsr")):
    if p not in sys.path:
        sys.path.insert(0, p)

from packages.cloud_brain.consensus_ledger import ConsensusLedger
from packages.cloud_brain.trust_audit import clear_freeze, is_frozen, sample_for_review, update_drift
from packages.cgsr.cgsr.ingestion.decomposer import DecompositionResult


def _decomp(subject: str, obj: str, sentence: str, h: str) -> DecompositionResult:
    return DecompositionResult(
        concepts=[{"concept_id": "c_s", "canonical_name": subject},
                  {"concept_id": "c_o", "canonical_name": obj}],
        relations=[{"dedupe_key": f"rk_{h}", "relation": "IS_A",
                    "source_concept_id": "c_s", "target_concept_id": "c_o",
                    "language": "ko", "provenance": {"source_id": f"src_{h}"}}],
        evidence={"text": sentence, "source_hash": h},
    )


class _FakeStore:
    def __init__(self):
        self.rows = []

    def _append_unique(self, collection, row, agg):
        self.rows.append(row)
        return True


def test_steady_promotion_rate_never_trips(tmp_path):
    for i in range(30):
        r = update_drift(tmp_path, promoted_this_tick=2)
    assert r["frozen"] is False
    assert not is_frozen(tmp_path)


def test_surge_trips_freeze_and_operator_clears(tmp_path):
    for _ in range(20):
        update_drift(tmp_path, promoted_this_tick=2)   # baseline ~2/tick
    r = update_drift(tmp_path, promoted_this_tick=500)  # mass-injection signature
    assert r["frozen"] is True
    assert is_frozen(tmp_path)
    assert clear_freeze(tmp_path) is True
    assert not is_frozen(tmp_path)


def test_frozen_ledger_promotes_nothing_but_keeps_evidence(tmp_path):
    ledger = ConsensusLedger(tmp_path / "ledger", min_sources=2)
    ledger.record_decomposition(_decomp("커피", "음료", "커피는 음료이다.", "h1"))
    ledger.record_decomposition(_decomp("커피", "음료", "커피는 널리 마시는 음료이다.", "h2"))
    (tmp_path / "ledger" / "promotion_freeze.flag").write_text("{}", encoding="utf-8")
    store = _FakeStore()
    res = ledger.promote_into(store)
    assert res.promoted == 0 and store.rows == []
    assert res.still_quarantined == 1          # evidence retained, nothing lost
    clear_freeze(tmp_path / "ledger")
    res2 = ledger.promote_into(store)
    assert res2.promoted == 1                  # flows again after operator clears


def test_spot_audit_samples_promoted_claims(tmp_path):
    ledger = ConsensusLedger(tmp_path / "ledger", min_sources=1)
    ledger.record_decomposition(_decomp("커피", "음료", "커피는 음료이다.", "h1"))
    ledger.promote_into(_FakeStore())
    sample = sample_for_review(ledger, n=3, rng=random.Random(7))
    assert len(sample) == 1
    assert sample[0]["subject"] == "커피" and sample[0]["evidence_count"] == 1
