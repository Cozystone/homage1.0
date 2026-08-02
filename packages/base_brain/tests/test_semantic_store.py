"""Guards the semantic concept store: it must (1) return the SAME concepts as the
in-RAM O(N) scan (answer parity) and (2) keep query RAM bounded regardless of N — the
answer-quality side of " " (a weak PC serves a huge knowledge base)."""

from __future__ import annotations

import tracemalloc
import types

from packages.base_brain.pack_loader import get_semantic_context
from packages.base_brain.semantic_store import SemanticConceptStore


def _fake_pack(concepts):
    # get_semantic_context only reads pack.semantic_graph["concepts"]; with a concept
    # count != the real persisted store, the store fast-path is skipped -> true scan.
    return types.SimpleNamespace(semantic_graph={"concepts": concepts})


def _concepts():
    return [
        {"concept_id": "kubernetes", "canonical_name": "쿠버네티스", "labels": {"ko": "쿠버네티스"},
         "short_description": "컨테이너를 자동 배포·복구하는 오픈소스 운영 플랫폼이다.",
         "relations": [{"target": "container", "relation": "manages"}]},
        {"concept_id": "container", "canonical_name": "컨테이너", "labels": {"ko": "컨테이너"},
         "short_description": "애플리케이션과 실행 환경을 묶는 단위이다.", "relations": []},
        {"concept_id": "gpu", "canonical_name": "GPU", "labels": {"en": "GPU"},
         "short_description": "many parallel operations processor.", "relations": []},
        {"concept_id": "database", "canonical_name": "데이터베이스", "labels": {"ko": "데이터베이스"},
         "short_description": "구조화된 정보를 저장하는 저장소이다.", "relations": []},
        {"concept_id": "data", "canonical_name": "데이터", "labels": {"ko": "데이터"},
         "short_description": "사실이나 값의 모음이다.", "relations": []},
    ]


def test_lookup_parity_with_scan(tmp_path):
    concepts = _concepts()
    pack = _fake_pack(concepts)
    store = SemanticConceptStore.build(tmp_path / "s", concepts)
    for q in ["쿠버네티스", "쿠버네티스가 뭐야", "GPU", "데이터베이스", "컨테이너", "데이터"]:
        scan = [c["concept_id"] for c in get_semantic_context(q, pack, limit=8)]
        store_ids = [c["concept_id"] for c in store.lookup(q, limit=8)]
        assert scan[:1] == store_ids[:1], (q, scan, store_ids)   # same primary concept
        assert set(scan) == set(store_ids), (q, scan, store_ids)  # same concept set


def test_one_char_concept_survives_agglutination(tmp_path):
    """A 1-char Hangul concept () must be findable both bare AND when the query wears a
 josa tail (/). Korean is left-headed so the concept is the query PREFIX; the
 indexed store's >=2 substring floor used to emit no 1-char stem key -> store returned
 [] where the O(N) scan matched via _named_with_boundary (measured battery C3). This
 locks store<->scan parity so the store can be rebuilt for speed without regressing."""
    concepts = [
        {"concept_id": "water_ko", "canonical_name": "물", "labels": {"ko": "물"},
         "short_description": "수소와 산소로 이루어진 물질이다.", "relations": []},
        {"concept_id": "river_ko", "canonical_name": "강", "labels": {"ko": "강"},
         "short_description": "육지 위를 흐르는 큰 물줄기이다.", "relations": []},
        *_concepts(),
    ]
    pack = _fake_pack(concepts)
    store = SemanticConceptStore.build(tmp_path / "one", concepts)
    for q, expect in [("물", "water_ko"), ("물은", "water_ko"), ("물이", "water_ko"),
                      ("강", "river_ko"), ("강이", "river_ko")]:
        scan = [c["concept_id"] for c in get_semantic_context(q, pack, limit=8)]
        store_ids = [c["concept_id"] for c in store.lookup(q, limit=8)]
        assert store_ids[:1] == [expect], (q, "store", store_ids)
        assert scan[:1] == store_ids[:1], (q, "parity", scan, store_ids)
    # a bare noun that is NOT a concept must stay empty (honest, never fabricated)
    assert store.lookup("봄은", limit=8) == []


def _distinct(n):
    base = _concepts()
    cs = list(base)
    i = 0
    while len(cs) < n:
        cs.append({"concept_id": f"syn_{i}", "canonical_name": f"항목{i}", "labels": {"ko": f"항목{i}"},
                   "short_description": f"{i}번째 항목이다.", "relations": []})
        i += 1
    return cs


def test_query_memory_bounded_across_N(tmp_path):
    small = SemanticConceptStore.build(tmp_path / "small", _distinct(20_000))
    large = SemanticConceptStore.build(tmp_path / "large", _distinct(200_000))
    qs = ["쿠버네티스", "GPU", "데이터베이스", "항목1234"]

    def peak(store):
        tracemalloc.start()
        for q in qs * 3:
            store.lookup(q, limit=12)
        _c, pk = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return pk

    p_small, p_large = peak(small), peak(large)
    # 10x more concepts must NOT grow per-query peak RAM materially (bounded by candidates).
    assert p_large <= p_small * 1.5, (p_small, p_large)
