from __future__ import annotations

from cgsr.corpus import corpus_metadata, stage1_corpus
from cgsr.induction import induce_constructions
from cgsr.pipeline import run_stage1_pipeline


def test_induction_returns_deduped_candidates() -> None:
    corpus = stage1_corpus()
    raw = induce_constructions(corpus, min_frequency=2, dedupe=False)
    deduped = induce_constructions(corpus, min_frequency=2, dedupe=True)

    assert raw
    assert deduped
    assert len(deduped) <= len(raw)
    assert corpus_metadata()["sentence_count"] == len(corpus)


def test_stage1_pipeline_runs_end_to_end() -> None:
    result = run_stage1_pipeline({"concept": "쿠버네티스", "predicate": "관리한다", "object": "컨테이너"})

    assert result["external_llm_used"] is False
    assert result["rhfc_used"] is False
    assert result["answer"] == "쿠버네티스는 컨테이너를 관리합니다."
