"""Truth discovery: majority of independent sources beats a lone unreliable source."""
from __future__ import annotations

import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[3]
for p in (str(_REPO), str(_REPO / "packages"), str(_REPO / "packages" / "cgsr")):
    if p not in sys.path:
        sys.path.insert(0, p)

from packages.cloud_brain.consensus_ledger import ConsensusLedger
from packages.cloud_brain.truth_discovery import Claim, claims_from_ledger, run_truth_discovery, score_and_persist
from packages.cgsr.cgsr.ingestion.decomposer import DecompositionResult


def test_majority_beats_lone_liar_in_exclusion_group():

    # The liar also spreads an unsupported claim elsewhere, dragging its trust down.
    claims = [
        Claim(key="k_seoul", subject="한국", predicate="CAPITAL", obj="서울",
              sources={"wiki", "news_a", "encyclo"}),
        Claim(key="k_busan", subject="한국", predicate="CAPITAL", obj="부산",
              sources={"spam_blog"}),
        Claim(key="k_other", subject="달", predicate="IS_A", obj="치즈",
              sources={"spam_blog"}),
        Claim(key="k_good", subject="서울", predicate="IS_A", obj="도시",
              sources={"wiki", "news_a"}),
    ]
    scores = run_truth_discovery(claims)
    assert scores.claim_belief["k_seoul"] > scores.claim_belief["k_busan"]
    assert scores.source_trust["wiki"] > scores.source_trust["spam_blog"]
    assert scores.exclusion_groups == 1


def test_independent_claims_keep_high_belief_without_competition():
    claims = [
        Claim(key="k1", subject="물", predicate="IS_A", obj="액체", sources={"a", "b", "c"}),
    ]
    scores = run_truth_discovery(claims)
    assert scores.claim_belief["k1"] > 0.7


def _decomp(subject: str, obj: str, sentence: str, source_hash: str, source_id: str) -> DecompositionResult:
    return DecompositionResult(
        concepts=[{"concept_id": "c_s", "canonical_name": subject},
                  {"concept_id": "c_o", "canonical_name": obj}],
        relations=[{"dedupe_key": f"rk_{source_hash}", "relation": "IS_A",
                    "source_concept_id": "c_s", "target_concept_id": "c_o", "language": "ko",
                    "provenance": {"source_id": source_id}}],
        evidence={"text": sentence, "source_hash": source_hash},
    )


def test_claims_built_from_ledger_events_collapse_voices_per_source(tmp_path):
    ledger = ConsensusLedger(tmp_path / "ledger", min_sources=2)
    # same website contributes two sentences -> ONE voice (Sybil cap)
    ledger.record_decomposition(_decomp("커피", "음료", "커피는 널리 마시는 음료이다.", "h1", "site_x"))
    ledger.record_decomposition(_decomp("커피", "음료", "커피는 인기 있는 음료이다.", "h2", "site_x"))
    claims = claims_from_ledger(ledger)
    assert len(claims) == 1
    assert claims[0].sources == {"site_x"}

    scores = score_and_persist(ledger)
    assert (tmp_path / "ledger" / "truth_scores.json").exists()
    assert 0.0 < scores.claim_belief[claims[0].key] <= 1.0
