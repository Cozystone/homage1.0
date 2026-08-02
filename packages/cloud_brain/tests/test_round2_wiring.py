"""Round-2 fixes: alias merging, voice consensus, belief gate, modifier predicate, verb frames."""
from __future__ import annotations

import json
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[3]
for p in (str(_REPO), str(_REPO / "packages"), str(_REPO / "packages" / "cgsr")):
    if p not in sys.path:
        sys.path.insert(0, p)

from packages.cloud_brain.alias_resolution import AliasResolver, normalize
from packages.cloud_brain.consensus_ledger import ConsensusLedger
from packages.cgsr.cgsr.discourse_planner import plan_and_realize
from packages.cgsr.cgsr.ingestion.decomposer import DecompositionResult


def _decomp(subject: str, obj: str, sentence: str, h: str, source_id: str) -> DecompositionResult:
    return DecompositionResult(
        concepts=[{"concept_id": "c_s", "canonical_name": subject},
                  {"concept_id": "c_o", "canonical_name": obj}],
        relations=[{"dedupe_key": f"rk_{h}", "relation": "IS_A",
                    "source_concept_id": "c_s", "target_concept_id": "c_o",
                    "language": "ko", "provenance": {"source_id": source_id}}],
        evidence={"text": sentence, "source_hash": h},
    )


# ---- ① alias resolution ----

def test_normalization_merges_case_and_spacing():
    assert normalize("Nvidia") == normalize("nvidia")
    assert normalize("삼성 전자") == normalize("삼성전자")
    assert normalize("삼성") != normalize("삼성전자")  # never substring-merge


def test_parenthetical_alias_learned_and_resolved(tmp_path):
    r = AliasResolver(tmp_path / "aliases.jsonl")
    n = r.learn_from_sentence("엔비디아 코퍼레이션(Nvidia Corporation)은 미국의 반도체 기업이다.")
    assert n == 1
    assert r.resolve("엔비디아 코퍼레이션") == r.resolve("Nvidia Corporation")
    # persisted: a fresh resolver over the same file knows the pair
    r2 = AliasResolver(tmp_path / "aliases.jsonl")
    assert r2.resolve("엔비디아 코퍼레이션") == r2.resolve("nvidia corporation")


def test_date_parenthetical_is_not_an_alias(tmp_path):
    r = AliasResolver(tmp_path / "aliases.jsonl")
    assert r.learn_from_sentence("홍길동(1992년 8월 28일 ~ )은 대한민국의 축구 선수이다.") == 0


def test_alias_merges_consensus_across_surface_forms(tmp_path):
    """The core payoff: the same fact under two surface forms reaches consensus."""
    ledger = ConsensusLedger(tmp_path / "ledger", min_sources=2)
    ledger.record_decomposition(_decomp(
        "엔비디아 코퍼레이션", "기업",
        "엔비디아 코퍼레이션(Nvidia Corporation)은 미국의 반도체 기업이다.", "h1", "wiki_ko"))
    ledger.record_decomposition(_decomp(
        "Nvidia Corporation", "기업",
        "Nvidia Corporation은 GPU를 설계하는 기업이다.", "h2", "news_en"))
    assert len(ledger.promotable()) == 1  # merged into ONE claim, 2 voices


# ---- voice-based consensus (Sybil cap in the ledger itself) ----

def test_same_source_two_sentences_is_one_voice(tmp_path):
    ledger = ConsensusLedger(tmp_path / "ledger", min_sources=2)
    ledger.record_decomposition(_decomp("커피", "음료", "커피는 음료이다.", "h1", "same_site"))
    ledger.record_decomposition(_decomp("커피", "음료", "커피는 널리 마시는 음료이다.", "h2", "same_site"))
    assert ledger.promotable() == []          # 2 sentences but ONE voice
    ledger.record_decomposition(_decomp("커피", "음료", "커피는 기호 음료이다.", "h3", "other_site"))
    assert len(ledger.promotable()) == 1      # a second independent voice arrives


# ---- truth-belief promotion gate ----

class _FakeStore:
    def __init__(self):
        self.rows = []

    def _append_unique(self, collection, row, agg):
        self.rows.append(row)
        return True


def test_low_belief_claim_is_held_not_promoted(tmp_path):
    ledger = ConsensusLedger(tmp_path / "ledger", min_sources=1)
    ledger.record_decomposition(_decomp("한국", "부산수도", "한국은 부산수도이다.", "h1", "spam"))
    key = ledger.promotable()[0][0]
    (tmp_path / "ledger" / "truth_scores.json").write_text(
        json.dumps({"claim_belief": {key: 0.1}}), encoding="utf-8")
    store = _FakeStore()
    res = ledger.promote_into(store)
    assert res.promoted == 0 and store.rows == []
    assert key not in ledger._promoted        # unmarked → can promote later
    (tmp_path / "ledger" / "truth_scores.json").write_text(
        json.dumps({"claim_belief": {key: 0.9}}), encoding="utf-8")
    assert ledger.promote_into(store).promoted == 1


# ---- verb-frame realization ----

def test_korean_verb_predicate_conjugates_instead_of_generic_frame():
    para = plan_and_realize("지식그래프", [("저장하다", "출처 근거"), ("IS_A", "저장소")])
    assert "저장합니다" in para.text
    assert "관계에 있습니다" not in para.text
