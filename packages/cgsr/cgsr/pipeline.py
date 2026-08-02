"""End-to-end Stage 1 CGSR pipeline."""

from __future__ import annotations

from .canonicalize import dedupe_constructions
from .corpus import stage1_corpus
from .induction import induce_constructions
from .korean_realizer import realize_simple_clause
from .retrieval import retrieve_construction


def run_stage1_pipeline(semantic_skeleton: dict[str, str] | None = None) -> dict[str, object]:
    """Run induction, dedupe, and minimal Korean realization."""

    skeleton = semantic_skeleton or {"concept": "쿠버네티스", "predicate": "관리한다", "object": "컨테이너", "formality": "formal"}
    corpus = stage1_corpus()
    raw = induce_constructions(corpus, min_frequency=2, dedupe=False)
    deduped = dedupe_constructions(raw)
    retrieval = retrieve_construction(skeleton, deduped)
    answer = realize_simple_clause(skeleton)
    return {
        "corpus_sentences": len(corpus),
        "raw_constructions": len(raw),
        "deduped_constructions": len(deduped),
        "construction_retrieval": {
            "tier": retrieval.tier,
            "matched": retrieval.matched,
            "reason": retrieval.reason,
            "family_id": retrieval.construction.family_id if retrieval.construction else None,
        },
        "semantic_skeleton": skeleton,
        "answer": answer,
        "rhfc_used": False,
        "external_llm_used": False,
        "external_sllm_used": False,
    }
