from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


RELATION_TYPES = [
    "is_a",
    "part_of",
    "has_property",
    "causes",
    "depends_on",
    "supports",
    "contradicts",
    "similar_to",
    "same_as",
    "derived_from",
    "created_by",
    "used_for",
    "located_in",
    "happened_at",
    "has_evidence",
    "has_source",
    "requires",
    "produces",
    "verifies",
    "weakens",
    "strengthens",
    "resolves",
    "conflicts_with",
    "belongs_to_layer",
]


BASE_CONCEPTS: list[dict[str, Any]] = [
    {
        "slug": "evidence",
        "label": "Evidence",
        "ko": "근거",
        "aliases_ko": ["증거", "판단 근거"],
        "aliases_en": ["proof", "supporting evidence"],
        "definition_ko": "주장이나 판단을 지지하거나 반박하는 확인 가능한 정보입니다.",
        "definition_en": "Verifiable information that supports or challenges a claim.",
        "type": "abstract_concept",
    },
    {
        "slug": "claim",
        "label": "Claim",
        "ko": "주장",
        "aliases_ko": ["명제", "답변 주장"],
        "aliases_en": ["assertion", "proposition"],
        "definition_ko": "검증될 수 있는 문장 단위의 의미 선언입니다.",
        "definition_en": "A sentence-level semantic assertion that can be checked.",
        "type": "abstract_concept",
    },
    {
        "slug": "source",
        "label": "Source",
        "ko": "출처",
        "aliases_ko": ["자료", "원천"],
        "aliases_en": ["reference", "origin"],
        "definition_ko": "근거가 유래한 문서, 웹 페이지, 파일, 기록의 위치입니다.",
        "definition_en": "The document, page, file, or record from which evidence originates.",
        "type": "abstract_concept",
    },
    {
        "slug": "graphrag",
        "label": "GraphRAG",
        "ko": "그래프 RAG",
        "aliases_ko": ["지식 그래프 검색", "그래프 기반 검색"],
        "aliases_en": ["graph retrieval augmented generation"],
        "definition_ko": "문서 조각뿐 아니라 개념 노드와 관계 경로를 함께 검색하는 구조입니다.",
        "definition_en": "Retrieval that uses both document chunks and concept-relation paths.",
        "type": "architecture_layer",
    },
    {
        "slug": "seed_graph",
        "label": "Seed Graph",
        "ko": "시드 그래프",
        "aliases_ko": ["기초 의미 좌표계", "초기 온톨로지"],
        "aliases_en": ["seed ontology", "semantic seed map"],
        "definition_ko": "개인 데이터가 부족할 때 추론 좌표계를 제공하는 공개 후보 온톨로지입니다.",
        "definition_en": "A public candidate ontology that provides coordinates before private data is sufficient.",
        "type": "architecture_layer",
    },
    {
        "slug": "local_brain",
        "label": "Local Brain",
        "ko": "로컬 브레인",
        "aliases_ko": ["개인 브레인", "사설 기억"],
        "aliases_en": ["private brain", "local memory"],
        "definition_ko": "사용자 문서와 상호작용으로 형성되는 사설 장기 기억입니다.",
        "definition_en": "Private long-term memory formed from user documents and interactions.",
        "type": "architecture_layer",
    },
    {
        "slug": "cloud_brain",
        "label": "Cloud Brain",
        "ko": "클라우드 브레인",
        "aliases_ko": ["공용 브레인", "공개 fragment 네트워크"],
        "aliases_en": ["public brain", "shared fragment network"],
        "definition_ko": "공개 fragment와 검증된 공용 지식 후보를 제공하는 보조 계층입니다.",
        "definition_en": "An assistive layer for public fragments and verified shared knowledge candidates.",
        "type": "architecture_layer",
    },
    {
        "slug": "payload_vault",
        "label": "Payload Vault",
        "ko": "페이로드 볼트",
        "aliases_ko": ["디스크 금고", "원문 금고"],
        "aliases_en": ["payload store", "disk vault"],
        "definition_ko": "원문과 메타데이터를 메모리가 아닌 디스크에 격리 저장하는 저장소입니다.",
        "definition_en": "A disk-bound store that isolates raw payloads and metadata outside active memory.",
        "type": "storage_layer",
    },
    {
        "slug": "ghost_shell",
        "label": "Ghost Shell",
        "ko": "고스트 셸",
        "aliases_ko": ["해시 위상 지도", "초경량 위상 레이어"],
        "aliases_en": ["hash topology", "ghost topology"],
        "definition_ko": "문장 원문 대신 해시와 관계만 메모리에 올리는 초경량 위상 지도입니다.",
        "definition_en": "A lightweight topology map that keeps hashes and relations in memory instead of raw text.",
        "type": "storage_layer",
    },
    {
        "slug": "ambiguity",
        "label": "Ambiguity",
        "ko": "중의성",
        "aliases_ko": ["의미 모호성", "다의성"],
        "aliases_en": ["polysemy", "unclear reference"],
        "definition_ko": "하나의 표현이 둘 이상의 개념 후보를 가리킬 수 있는 상태입니다.",
        "definition_en": "A state where one expression can refer to multiple concept candidates.",
        "type": "reasoning_state",
    },
    {
        "slug": "privacy_scope",
        "label": "Privacy Scope",
        "ko": "개인정보 범위",
        "aliases_ko": ["공개 범위", "사설 범위"],
        "aliases_en": ["privacy boundary", "visibility scope"],
        "definition_ko": "정보가 공개, 내부, 사설 중 어디에 속하는지 구분하는 경계입니다.",
        "definition_en": "The boundary that separates public, internal, and private information.",
        "type": "governance_concept",
    },
    {
        "slug": "conflict",
        "label": "Conflict",
        "ko": "충돌",
        "aliases_ko": ["모순", "불일치"],
        "aliases_en": ["contradiction", "inconsistency"],
        "definition_ko": "두 관계나 근거가 동시에 참이기 어려운 상태입니다.",
        "definition_en": "A state where two relations or evidence records are difficult to hold as true together.",
        "type": "reasoning_state",
    },
    {
        "slug": "verification",
        "label": "Verification",
        "ko": "검증",
        "aliases_ko": ["확인", "검사"],
        "aliases_en": ["validation", "checking"],
        "definition_ko": "근거, 출처, 관계 일관성을 이용해 주장의 신뢰도를 평가하는 과정입니다.",
        "definition_en": "The process of evaluating claim reliability through evidence, source, and relation consistency.",
        "type": "reasoning_process",
    },
    {
        "slug": "ontology",
        "label": "Ontology",
        "ko": "온톨로지",
        "aliases_ko": ["개념 체계", "의미 구조"],
        "aliases_en": ["concept system", "semantic schema"],
        "definition_ko": "개념과 관계를 명시적으로 연결한 의미 구조입니다.",
        "definition_en": "A semantic structure that explicitly links concepts and relations.",
        "type": "abstract_concept",
    },
    {
        "slug": "relation",
        "label": "Relation",
        "ko": "관계",
        "aliases_ko": ["엣지", "연결"],
        "aliases_en": ["edge", "link"],
        "definition_ko": "두 개념 사이의 의미 방향과 강도를 표현하는 연결입니다.",
        "definition_en": "A link that represents semantic direction and strength between concepts.",
        "type": "abstract_concept",
    },
    {
        "slug": "retrieval",
        "label": "Retrieval",
        "ko": "검색",
        "aliases_ko": ["회수", "탐색"],
        "aliases_en": ["lookup", "fetch"],
        "definition_ko": "질문과 관련된 개념, 관계, 근거를 찾는 과정입니다.",
        "definition_en": "The process of finding concepts, relations, and evidence relevant to a query.",
        "type": "reasoning_process",
    },
    {
        "slug": "trust",
        "label": "Trust",
        "ko": "신뢰",
        "aliases_ko": ["신뢰도", "검증 신뢰"],
        "aliases_en": ["confidence", "reliability"],
        "definition_ko": "출처, 반복성, 관계 일관성으로 추정되는 정보의 안정성입니다.",
        "definition_en": "Information stability estimated from source quality, repetition, and relation consistency.",
        "type": "governance_concept",
    },
    {
        "slug": "query",
        "label": "Query",
        "ko": "질문",
        "aliases_ko": ["사용자 질문", "입력 질의"],
        "aliases_en": ["user question", "input query"],
        "definition_ko": "사용자가 로컬 브레인에 던지는 요청 또는 탐색 시작점입니다.",
        "definition_en": "A user request that starts retrieval, grounding, or clarification.",
        "type": "reasoning_input",
    },
    {
        "slug": "answer",
        "label": "Answer",
        "ko": "답변",
        "aliases_ko": ["응답", "출력 문장", "답해야", "대답"],
        "aliases_en": ["response", "output utterance"],
        "definition_ko": "근거와 신뢰 상태를 반영해 사용자에게 표면화되는 문장입니다.",
        "definition_en": "The surfaced response that reflects grounding and trust state.",
        "type": "reasoning_output",
    },
    {
        "slug": "grounding",
        "label": "Grounding",
        "ko": "근거화",
        "aliases_ko": ["근거 연결", "증거 기반화", "근거가 필요", "근거 필요"],
        "aliases_en": ["evidence grounding", "groundedness"],
        "definition_ko": "답변이나 주장을 실제 근거, 출처, 관계 경로에 연결하는 과정입니다.",
        "definition_en": "The process of linking an answer or claim to evidence, sources, and relation paths.",
        "type": "reasoning_process",
    },
    {
        "slug": "no_evidence",
        "label": "No Evidence",
        "ko": "근거 없음",
        "aliases_ko": ["근거 부족", "로컬 근거 없음", "증거 없음", "근거가 없음", "근거가 없으면", "근거 없으면"],
        "aliases_en": ["missing evidence", "no local evidence", "unknown from local evidence"],
        "definition_ko": "질문에 답할 수 있는 검증 가능한 로컬 근거가 아직 없는 상태입니다.",
        "definition_en": "A state where verifiable local evidence for the query is not available yet.",
        "type": "reasoning_state",
    },
    {
        "slug": "seed_graph_duplicate",
        "label": "Seed Ontology",
        "ko": "시드 온톨로지",
        "aliases_ko": ["시드 그래프", "초기 의미 좌표계"],
        "aliases_en": ["seed graph", "semantic seed map"],
        "definition_ko": "시드 그래프와 같은 후보 개념이며 중복 병합 검사용입니다.",
        "definition_en": "A duplicate candidate for Seed Graph used to test canonical merging.",
        "type": "architecture_layer",
    },
    {
        "slug": "thin_candidate",
        "label": "Thin Candidate",
        "ko": "",
        "aliases_ko": [],
        "aliases_en": [],
        "definition_ko": "",
        "definition_en": "",
        "type": "unknown",
    },
]


BASE_EDGES: list[tuple[str, str, str]] = [
    ("evidence", "supports", "claim"),
    ("claim", "requires", "evidence"),
    ("evidence", "has_source", "source"),
    ("query", "used_for", "retrieval"),
    ("retrieval", "produces", "answer"),
    ("answer", "requires", "grounding"),
    ("grounding", "has_evidence", "evidence"),
    ("grounding", "has_source", "source"),
    ("no_evidence", "weakens", "trust"),
    ("no_evidence", "requires", "retrieval"),
    ("no_evidence", "requires", "grounding"),
    ("graphrag", "used_for", "retrieval"),
    ("graphrag", "has_evidence", "evidence"),
    ("seed_graph", "is_a", "ontology"),
    ("seed_graph", "used_for", "retrieval"),
    ("local_brain", "depends_on", "payload_vault"),
    ("local_brain", "belongs_to_layer", "privacy_scope"),
    ("cloud_brain", "depends_on", "ghost_shell"),
    ("cloud_brain", "has_property", "trust"),
    ("ghost_shell", "part_of", "cloud_brain"),
    ("payload_vault", "part_of", "local_brain"),
    ("ambiguity", "requires", "verification"),
    ("conflict", "requires", "verification"),
    ("verification", "verifies", "claim"),
    ("ontology", "has_property", "relation"),
    ("retrieval", "depends_on", "ontology"),
    ("trust", "strengthens", "verification"),
    ("privacy_scope", "weakens", "cloud_brain"),
    ("seed_graph_duplicate", "same_as", "seed_graph"),
    ("thin_candidate", "supports", "missing_target"),
]


BENCHMARKS: list[dict[str, Any]] = [
    {
        "id": "bench_0001",
        "query": "근거와 주장의 차이를 설명해줘",
        "expected_concepts": ["seed.core.evidence", "seed.core.claim"],
        "expected_relations": ["supports", "requires"],
        "expected_behavior": "explain conceptual difference with evidence relationship",
    },
    {
        "id": "bench_0002",
        "query": "Apple은 과일이야 회사야?",
        "expected_concepts": ["seed.core.ambiguity"],
        "expected_relations": ["requires"],
        "expected_behavior": "detect ambiguity and require disambiguation",
    },
    {
        "id": "bench_0003",
        "query": "출처가 없는 주장은 어떻게 처리해?",
        "expected_concepts": ["seed.core.claim", "seed.core.source", "seed.core.verification"],
        "expected_relations": ["has_source", "verifies"],
        "expected_behavior": "recognize missing source and lower trust",
    },
    {
        "id": "bench_0004",
        "query": "Local Brain과 Cloud Brain은 어떻게 분리돼?",
        "expected_concepts": ["seed.core.local_brain", "seed.core.cloud_brain", "seed.core.privacy_scope"],
        "expected_relations": ["belongs_to_layer", "depends_on"],
        "expected_behavior": "distinguish private local memory from public cloud fragments",
    },
    {
        "id": "bench_0005",
        "query": "Ghost Shell과 Payload Vault의 역할 비교",
        "expected_concepts": ["seed.core.ghost_shell", "seed.core.payload_vault"],
        "expected_relations": ["part_of"],
        "expected_behavior": "compare memory topology with disk payload vault",
    },
    {
        "id": "bench_0006",
        "query": "What does evidence support?",
        "expected_concepts": ["seed.core.evidence", "seed.core.claim"],
        "expected_relations": ["supports"],
        "expected_behavior": "resolve English alias and relation",
    },
    {
        "id": "bench_0007",
        "query": "모순되는 근거가 있으면?",
        "expected_concepts": ["seed.core.conflict", "seed.core.verification"],
        "expected_relations": ["requires"],
        "expected_behavior": "route to conflict detection and verification",
    },
    {
        "id": "bench_0008",
        "query": "내 개인 문서를 클라우드 브레인이 쓰나?",
        "expected_concepts": ["seed.core.privacy_scope", "seed.core.local_brain", "seed.core.cloud_brain"],
        "expected_relations": ["weakens", "belongs_to_layer"],
        "expected_behavior": "distinguish public seed/cloud from private local data",
    },
    {
        "id": "bench_0009",
        "query": "unknown-x47 개념이 뭐야?",
        "expected_concepts": [],
        "expected_relations": [],
        "expected_behavior": "detect missing knowledge rather than hallucinating",
    },
    {
        "id": "bench_0010",
        "query": "seed graph가 추론 구조에 왜 필요해?",
        "expected_concepts": ["seed.core.seed_graph", "seed.core.ontology", "seed.core.retrieval"],
        "expected_relations": ["is_a", "used_for"],
        "expected_behavior": "explain seed graph as semantic coordinate system",
    },
    {
        "id": "bench_0011",
        "query": "근거가 없으면 어떻게 답해야 해?",
        "expected_concepts": ["seed.core.no_evidence", "seed.core.grounding", "seed.core.answer"],
        "expected_relations": ["requires", "weakens"],
        "expected_behavior": "route unknown answers to no-evidence state instead of hallucination",
    },
    {
        "id": "bench_0012",
        "query": "답변은 왜 근거화가 필요해?",
        "expected_concepts": ["seed.core.answer", "seed.core.grounding", "seed.core.evidence"],
        "expected_relations": ["requires", "has_evidence"],
        "expected_behavior": "link answer quality to grounding and evidence",
    },
]


@dataclass(frozen=True)
class SeedPaths:
    root: Path
    runs: Path
    feedback: Path
    benchmarks: Path
    current: Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_root(root: str | Path | None = None) -> Path:
    configured = root or os.getenv("ATANOR_SEED_RESEARCH_ROOT")
    return Path(configured or "data/seed_research")


def paths(root: str | Path | None = None) -> SeedPaths:
    base = seed_root(root)
    return SeedPaths(
        root=base,
        runs=base / "runs",
        feedback=base / "feedback",
        benchmarks=base / "benchmarks",
        current=base / "current",
    )


def ensure_layout(root: str | Path | None = None) -> SeedPaths:
    p = paths(root)
    for directory in [p.root, p.runs, p.feedback, p.benchmarks, p.current]:
        directory.mkdir(parents=True, exist_ok=True)
    _write_json_if_missing(
        p.root / "relation_schema.json",
        {
            "schema": "atanor.seed-research.relation-schema.v1",
            "relation_types": [{"id": relation, "description": f"Seed graph semantic relation: {relation}"} for relation in RELATION_TYPES],
            "note": "These relation types are graph semantics, not answer templates.",
        },
    )
    benchmark_file = p.benchmarks / "seed_benchmark_questions.jsonl"
    ensure_standard_benchmarks(benchmark_file)
    (p.benchmarks / "seed_benchmark_results.jsonl").touch(exist_ok=True)
    (p.feedback / "feedback_log.jsonl").touch(exist_ok=True)
    (p.feedback / "patches").mkdir(parents=True, exist_ok=True)
    return p


def _write_json_if_missing(path: Path, data: Any) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_standard_benchmarks(path: Path) -> None:
    """Keep generated standard benchmark rows aligned without dropping custom rows."""

    standard_by_id = {row["id"]: row for row in BENCHMARKS}
    existing = read_jsonl(path) if path.exists() else []
    custom_rows = [row for row in existing if row.get("id") not in standard_by_id]
    merged = [*BENCHMARKS, *custom_rows]
    if existing != merged:
        write_jsonl(path, merged)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def next_run_id(root: str | Path | None = None) -> str:
    p = ensure_layout(root)
    existing = []
    for child in p.runs.glob("run_*"):
        if child.is_dir() and re.fullmatch(r"run_\d{4}", child.name):
            existing.append(int(child.name.split("_", 1)[1]))
    return f"run_{(max(existing) + 1) if existing else 1:04d}"


def concept_id(slug: str) -> str:
    slug = slug.replace("seed_graph_duplicate", "seed_graph")
    return f"seed.core.{slug}"


def edge_id(source: str, relation: str, target: str) -> str:
    return f"seed.edge.{source.removeprefix('seed.core.')}.{relation}.{target.removeprefix('seed.core.')}"


def canonical_key(candidate: dict[str, Any]) -> str:
    names = [candidate.get("label", ""), candidate.get("ko", "")]
    names.extend(candidate.get("aliases_ko") or [])
    names.extend(candidate.get("aliases_en") or [])
    normalized = {normalize_text(name) for name in names if str(name).strip()}
    duplicate_hints = {"seed ontology", "semantic seed map", "시드 온톨로지", "시드 그래프", "초기 의미 좌표계"}
    if normalized.intersection({normalize_text(item) for item in duplicate_hints}):
        return "seed_graph"
    return normalize_text(candidate.get("label") or candidate.get("slug") or "")


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def make_concept(candidate: dict[str, Any], run_id: str) -> dict[str, Any]:
    cid = concept_id(str(candidate["slug"]))
    trust_state = "seed_candidate"
    verification_state = "generated"
    return {
        "concept_id": cid,
        "label": candidate.get("label") or candidate["slug"],
        "labels": {"ko": candidate.get("ko", ""), "en": str(candidate.get("label") or "").lower()},
        "aliases": {"ko": list(candidate.get("aliases_ko") or []), "en": list(candidate.get("aliases_en") or [])},
        "definition": {"ko": candidate.get("definition_ko", ""), "en": candidate.get("definition_en", "")},
        "concept_type": candidate.get("type", "abstract_concept"),
        "source_scope": "seed",
        "privacy_scope": "public",
        "trust_state": trust_state,
        "verification_state": verification_state,
        "embedding_ref": None,
        "version": f"seed-{run_id.replace('_', '-')}",
        "created_by": "seed_research_loop",
    }


def resolve_duplicates(candidates: list[dict[str, Any]], run_id: str) -> tuple[list[dict[str, Any]], dict[str, str], int]:
    merged: dict[str, dict[str, Any]] = {}
    alias_map: dict[str, str] = {}
    duplicate_count = 0
    for candidate in candidates:
        key = canonical_key(candidate)
        target_slug = "seed_graph" if key == "seed_graph" else str(candidate["slug"])
        target_id = concept_id(target_slug)
        alias_map[concept_id(str(candidate["slug"]))] = target_id
        concept = make_concept({**candidate, "slug": target_slug}, run_id)
        if target_id in merged:
            duplicate_count += 1
            existing = merged[target_id]
            for locale in ["ko", "en"]:
                aliases = set(existing["aliases"].get(locale, []))
                aliases.update(concept["aliases"].get(locale, []))
                aliases.add(str(concept["labels"].get(locale, "")).strip())
                existing["aliases"][locale] = sorted(alias for alias in aliases if alias)
        else:
            merged[target_id] = concept
    return list(merged.values()), alias_map, duplicate_count


def concept_score(concept: dict[str, Any]) -> float:
    coverage = 0.0
    coverage += 0.2 if concept["labels"].get("ko") else 0
    coverage += 0.2 if concept["labels"].get("en") else 0
    coverage += 0.2 if concept["definition"].get("ko") else 0
    coverage += 0.2 if concept["definition"].get("en") else 0
    coverage += 0.1 if concept["aliases"].get("ko") else 0
    coverage += 0.1 if concept["aliases"].get("en") else 0
    return round(coverage, 3)


def generate_edges(alias_map: dict[str, str], concepts_by_id: dict[str, dict[str, Any]], run_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    edges: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for source_slug, relation, target_slug in BASE_EDGES:
        source = alias_map.get(concept_id(source_slug), concept_id(source_slug))
        target = alias_map.get(concept_id(target_slug), concept_id(target_slug))
        edge = {
            "edge_id": edge_id(source, relation, target),
            "source": source,
            "relation": relation,
            "target": target,
            "weight": 0.0,
            "confidence": 0.0,
            "source_scope": "seed",
            "trust_state": "seed_candidate",
            "verification_state": "generated",
            "version": f"seed-{run_id.replace('_', '-')}",
            "created_by": "seed_research_loop",
        }
        if relation not in RELATION_TYPES or source not in concepts_by_id or target not in concepts_by_id or source == target:
            rejected.append({**edge, "trust_state": "rejected", "reject_reason": "invalid_relation_or_endpoint"})
            continue
        degree_hint = 0.1 if relation in {"supports", "requires", "depends_on", "verifies", "has_source"} else 0.0
        edge["confidence"] = round(min(0.96, 0.62 + degree_hint + concept_score(concepts_by_id[source]) * 0.12), 3)
        edge["weight"] = round(edge["confidence"] * 0.75, 3)
        edge["trust_state"] = "seed_verified" if edge["confidence"] >= 0.68 else "seed_candidate"
        edge["verification_state"] = "checked"
        edges.append(edge)
    return edges, rejected


def distill(concepts: list[dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    accepted_concepts: list[dict[str, Any]] = []
    rejected_concepts: list[dict[str, Any]] = []
    for concept in concepts:
        score = concept_score(concept)
        concept["confidence"] = score
        if score < 0.55:
            rejected_concepts.append({**concept, "trust_state": "rejected", "reject_reason": "low_definition_or_alias_coverage"})
            continue
        concept["trust_state"] = "seed_verified" if score >= 0.85 else "seed_candidate"
        concept["verification_state"] = "distilled"
        accepted_concepts.append(concept)

    accepted_ids = {concept["concept_id"] for concept in accepted_concepts}
    accepted_edges: list[dict[str, Any]] = []
    rejected_edges: list[dict[str, Any]] = []
    for edge in edges:
        if edge["source"] not in accepted_ids or edge["target"] not in accepted_ids:
            rejected_edges.append({**edge, "trust_state": "rejected", "reject_reason": "endpoint_rejected"})
            continue
        if float(edge.get("confidence") or 0) < 0.55:
            rejected_edges.append({**edge, "trust_state": "rejected", "reject_reason": "low_confidence"})
            continue
        edge["verification_state"] = "distilled"
        accepted_edges.append(edge)
    return accepted_concepts, accepted_edges, rejected_concepts, rejected_edges


def aliases_for(concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for concept in concepts:
        for locale, aliases in concept.get("aliases", {}).items():
            for alias in aliases:
                rows.append({
                    "concept_id": concept["concept_id"],
                    "locale": locale,
                    "alias": alias,
                    "source_scope": "seed",
                    "version": concept["version"],
                })
    return rows


def graph_metrics(
    concepts: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    rejected_concepts: list[dict[str, Any]],
    rejected_edges: list[dict[str, Any]],
    duplicate_count: int,
    previous_metrics: dict[str, Any] | None,
    benchmarks: list[dict[str, Any]],
) -> dict[str, Any]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    relation_distribution: Counter[str] = Counter()
    conflict_edges = 0
    for edge in edges:
        adjacency[edge["source"]].add(edge["target"])
        adjacency[edge["target"]].add(edge["source"])
        relation_distribution[edge["relation"]] += 1
        if edge["relation"] in {"contradicts", "conflicts_with"}:
            conflict_edges += 1
    concept_ids = {concept["concept_id"] for concept in concepts}
    isolated = sorted(concept_id for concept_id in concept_ids if not adjacency.get(concept_id))
    components = connected_components(concept_ids, adjacency)
    alias_count = sum(len(concept.get("aliases", {}).get("ko", [])) + len(concept.get("aliases", {}).get("en", [])) for concept in concepts)
    confidence_values = [float(concept.get("confidence") or 0) for concept in concepts] + [float(edge.get("confidence") or 0) for edge in edges]
    ko_en_coverage = sum(1 for concept in concepts if concept["labels"].get("ko") and concept["labels"].get("en")) / max(1, len(concepts))
    definition_coverage = sum(1 for concept in concepts if concept["definition"].get("ko") and concept["definition"].get("en")) / max(1, len(concepts))
    benchmark_score, benchmark_results = evaluate_benchmarks(concepts, edges, benchmarks)
    previous_delta = {
        "concept_count": len(concepts) - int(previous_metrics.get("concept_count", 0)) if previous_metrics else len(concepts),
        "edge_count": len(edges) - int(previous_metrics.get("edge_count", 0)) if previous_metrics else len(edges),
        "benchmark_score": round(benchmark_score - float(previous_metrics.get("benchmark_score", 0.0)), 3) if previous_metrics else round(benchmark_score, 3),
    }
    return {
        "concept_count": len(concepts),
        "edge_count": len(edges),
        "alias_count": alias_count,
        "duplicate_merge_count": duplicate_count,
        "rejected_concept_count": len(rejected_concepts),
        "rejected_edge_count": len(rejected_edges),
        "isolated_node_count": len(isolated),
        "isolated_nodes": isolated,
        "average_degree": round((sum(len(neighbors) for neighbors in adjacency.values()) / max(1, len(concepts))), 3),
        "connected_component_count": len(components),
        "relation_type_distribution": dict(sorted(relation_distribution.items())),
        "ko_en_label_coverage": round(ko_en_coverage, 3),
        "concept_definition_coverage": round(definition_coverage, 3),
        "confidence_average": round(sum(confidence_values) / max(1, len(confidence_values)), 3),
        "low_confidence_edge_count": sum(1 for edge in edges if float(edge.get("confidence") or 0) < 0.68),
        "conflict_edge_count": conflict_edges,
        "benchmark_score": round(benchmark_score, 3),
        "benchmark_results": benchmark_results,
        "previous_run_delta": previous_delta,
    }


def connected_components(nodes: set[str], adjacency: dict[str, set[str]]) -> list[list[str]]:
    remaining = set(nodes)
    components: list[list[str]] = []
    while remaining:
        start = remaining.pop()
        queue: deque[str] = deque([start])
        component = [start]
        while queue:
            current = queue.popleft()
            for neighbor in adjacency.get(current, set()):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.append(neighbor)
                    queue.append(neighbor)
        components.append(sorted(component))
    return components


def evaluate_benchmarks(concepts: list[dict[str, Any]], edges: list[dict[str, Any]], benchmarks: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
    concept_ids = {concept["concept_id"] for concept in concepts}
    relations = {edge["relation"] for edge in edges}
    results: list[dict[str, Any]] = []
    scores: list[float] = []
    for item in benchmarks:
        expected_concepts = set(item.get("expected_concepts") or [])
        expected_relations = set(item.get("expected_relations") or [])
        concept_hits = len(expected_concepts.intersection(concept_ids))
        relation_hits = len(expected_relations.intersection(relations))
        concept_score_value = concept_hits / max(1, len(expected_concepts)) if expected_concepts else 1.0
        relation_score_value = relation_hits / max(1, len(expected_relations)) if expected_relations else 1.0
        score = round((concept_score_value * 0.68) + (relation_score_value * 0.32), 3)
        scores.append(score)
        results.append({
            "id": item["id"],
            "score": score,
            "concept_hits": concept_hits,
            "relation_hits": relation_hits,
            "expected_behavior": item.get("expected_behavior"),
        })
    return (sum(scores) / max(1, len(scores))), results


def graph_snapshot(concepts: list[dict[str, Any]], edges: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    return {
        "schema": "atanor.seed-research.graph-snapshot.v1",
        "run_id": run_id,
        "source_scope": "seed",
        "privacy_scope": "public",
        "concepts": concepts,
        "edges": edges,
        "created_at": utc_now_iso(),
    }


def viewer_export(concepts: list[dict[str, Any]], edges: list[dict[str, Any]], metrics: dict[str, Any], run_id: str) -> dict[str, Any]:
    nodes = []
    for index, concept in enumerate(concepts):
        angle = index * 2.399963229728653
        radius = 2.5 + (index % 5) * 0.42
        nodes.append({
            "id": concept["concept_id"],
            "label": concept["label"],
            "labels": concept["labels"],
            "aliases": concept["aliases"],
            "definition": concept["definition"],
            "type": concept["concept_type"],
            "trust_state": concept["trust_state"],
            "verification_state": concept["verification_state"],
            "source_scope": "seed",
            "privacy_scope": "public",
            "x": round(math.cos(angle) * radius, 4),
            "y": round(math.sin(angle) * radius, 4),
            "z": round(((index % 7) - 3) * 0.38, 4),
            "confidence": concept.get("confidence", 0.0),
        })
    return {
        "schema": "atanor.seed-research.viewer-export.v1",
        "mode": "seed_research_viewer",
        "read_only": True,
        "not_local_brain": True,
        "run_id": run_id,
        "badge": "Seed Research Viewer",
        "concept_count": len(concepts),
        "relation_count": len(edges),
        "metrics": metrics,
        "nodes": nodes,
        "edges": edges,
        "filters": {
            "relation_types": sorted({edge["relation"] for edge in edges}),
            "trust_states": sorted({concept["trust_state"] for concept in concepts} | {edge["trust_state"] for edge in edges}),
        },
        "exported_at": utc_now_iso(),
    }


def feedback_template(run_id: str) -> str:
    return f"""# Human Feedback for {run_id}

## Keep

*

## Remove

*

## Merge

*

## Rename

*

## Relation fixes

*

## Missing concepts

*

## Notes

*
"""


def previous_metrics(p: SeedPaths, run_id: str) -> dict[str, Any] | None:
    number = int(run_id.split("_", 1)[1])
    if number <= 1:
        return None
    previous = p.runs / f"run_{number - 1:04d}" / "seed_metrics.json"
    if previous.exists():
        return json.loads(previous.read_text(encoding="utf-8"))
    return None


def copy_current(run_dir: Path, p: SeedPaths) -> None:
    for name in ["seed_concepts.jsonl", "seed_edges.jsonl", "seed_aliases.jsonl", "viewer_export.json"]:
        shutil.copyfile(run_dir / name, p.current / name)
    manifest = {
        "schema": "atanor.seed-research.current-manifest.v1",
        "current_run_id": run_dir.name,
        "updated_at": utc_now_iso(),
        "source_scope": "seed",
        "privacy_scope": "public",
        "immutable_run_path": str(run_dir),
    }
    write_json(p.current / "seed_manifest.json", manifest)


def run_seed_iteration(root: str | Path | None = None) -> dict[str, Any]:
    p = ensure_layout(root)
    run_id = next_run_id(p.root)
    run_dir = p.runs / run_id
    run_dir.mkdir(parents=False, exist_ok=False)
    version = f"seed-{run_id.replace('_', '-')}"

    candidates = [dict(candidate, candidate_id=f"candidate.{candidate['slug']}", version=version, created_at=utc_now_iso()) for candidate in BASE_CONCEPTS]
    concepts, alias_map, duplicate_count = resolve_duplicates(candidates, run_id)
    concepts_by_id = {concept["concept_id"]: concept for concept in concepts}
    generated_edges, invalid_edges = generate_edges(alias_map, concepts_by_id, run_id)
    accepted_concepts, accepted_edges, rejected_concepts, rejected_edges = distill(concepts, generated_edges)
    rejected_edges.extend(invalid_edges)
    aliases = aliases_for(accepted_concepts)
    benchmarks = read_jsonl(p.benchmarks / "seed_benchmark_questions.jsonl")
    metrics = graph_metrics(accepted_concepts, accepted_edges, rejected_concepts, rejected_edges, duplicate_count, previous_metrics(p, run_id), benchmarks)
    snapshot = graph_snapshot(accepted_concepts, accepted_edges, run_id)
    viewer = viewer_export(accepted_concepts, accepted_edges, metrics, run_id)

    write_jsonl(run_dir / "seed_candidates.jsonl", candidates)
    write_jsonl(run_dir / "seed_concepts.jsonl", accepted_concepts)
    write_jsonl(run_dir / "seed_edges.jsonl", accepted_edges)
    write_jsonl(run_dir / "seed_aliases.jsonl", aliases)
    write_jsonl(run_dir / "rejected_concepts.jsonl", rejected_concepts)
    write_jsonl(run_dir / "rejected_edges.jsonl", rejected_edges)
    write_json(run_dir / "seed_metrics.json", metrics)
    write_json(run_dir / "graph_snapshot.json", snapshot)
    write_json(run_dir / "viewer_export.json", viewer)
    (run_dir / "human_feedback.md").write_text(feedback_template(run_id), encoding="utf-8", newline="\n")
    (run_dir / "seed_eval_report.md").write_text(evaluation_report(run_id, metrics), encoding="utf-8", newline="\n")
    copy_current(run_dir, p)
    append_jsonl(p.feedback / "feedback_log.jsonl", {
        "event": "seed_iteration_completed",
        "run_id": run_id,
        "concept_count": metrics["concept_count"],
        "edge_count": metrics["edge_count"],
        "benchmark_score": metrics["benchmark_score"],
        "created_at": utc_now_iso(),
    })
    return {"run_id": run_id, "run_dir": str(run_dir), "metrics": metrics, "viewer_export": str(run_dir / "viewer_export.json")}


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def evaluation_report(run_id: str, metrics: dict[str, Any]) -> str:
    relation_lines = "\n".join(f"- `{key}`: {value}" for key, value in metrics["relation_type_distribution"].items())
    return f"""# Seed Evaluation Report: {run_id}

## Summary

- Concept count: {metrics['concept_count']}
- Edge count: {metrics['edge_count']}
- Alias count: {metrics['alias_count']}
- Duplicate merges: {metrics['duplicate_merge_count']}
- Rejected concepts: {metrics['rejected_concept_count']}
- Rejected edges: {metrics['rejected_edge_count']}
- Benchmark score: {metrics['benchmark_score']}

## Structure

- Connected components: {metrics['connected_component_count']}
- Isolated nodes: {metrics['isolated_node_count']}
- Average degree: {metrics['average_degree']}
- Confidence average: {metrics['confidence_average']}
- Low confidence edges: {metrics['low_confidence_edge_count']}
- Conflict edges: {metrics['conflict_edge_count']}

## Coverage

- KO/EN label coverage: {metrics['ko_en_label_coverage']}
- Definition coverage: {metrics['concept_definition_coverage']}

## Relation Distribution

{relation_lines}

## Notes

This Seed Graph is a generated research artifact. It is not a rule-based answer
engine and is not written into the user's private Local Brain memory.
"""


def apply_feedback(run: str, root: str | Path | None = None) -> dict[str, Any]:
    p = ensure_layout(root)
    run_dir = p.runs / run
    feedback_file = run_dir / "human_feedback.md"
    if not feedback_file.exists():
        raise FileNotFoundError(f"human feedback file not found: {feedback_file}")
    feedback_text = feedback_file.read_text(encoding="utf-8")
    patch = {
        "schema": "atanor.seed-research.feedback-patch.v1",
        "run_id": run,
        "created_at": utc_now_iso(),
        "sections": parse_feedback(feedback_text),
        "next_iteration_hint": "Apply this patch as input context for the next immutable seed iteration.",
        "mutates_previous_run": False,
    }
    patch_path = p.feedback / "patches" / f"{run}_feedback_patch.json"
    write_json(patch_path, patch)
    append_jsonl(p.feedback / "feedback_log.jsonl", {
        "event": "feedback_patch_created",
        "run_id": run,
        "patch_path": str(patch_path),
        "created_at": utc_now_iso(),
    })
    return {"run_id": run, "patch_path": str(patch_path)}


def parse_feedback(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip().lower().replace(" ", "_")
            sections[current] = []
            continue
        if current and line.strip().startswith("*"):
            value = line.strip().lstrip("*").strip()
            if value:
                sections[current].append(value)
    return sections


def freeze_seed(run: str, version: str, root: str | Path | None = None, output_root: str | Path | None = None) -> dict[str, Any]:
    p = ensure_layout(root)
    run_dir = p.runs / run
    if not run_dir.exists():
        raise FileNotFoundError(f"seed run not found: {run}")
    output = Path(output_root or os.getenv("ATANOR_SEED_OUTPUT_ROOT") or "data/seed")
    output.mkdir(parents=True, exist_ok=True)
    for name in ["seed_concepts.jsonl", "seed_edges.jsonl", "seed_aliases.jsonl", "seed_eval_report.md", "viewer_export.json"]:
        shutil.copyfile(run_dir / name, output / name)
    manifest = {
        "schema": "atanor.seed.freeze-manifest.v1",
        "version": version,
        "source_run_id": run,
        "source_scope": "seed",
        "privacy_scope": "public",
        "read_only": True,
        "frozen_at": utc_now_iso(),
    }
    write_json(output / "seed_manifest.json", manifest)
    return {"run_id": run, "version": version, "output_dir": str(output)}


def current_viewer_export(root: str | Path | None = None) -> dict[str, Any]:
    p = ensure_layout(root)
    viewer_path = p.current / "viewer_export.json"
    if not viewer_path.exists():
        return {
            "schema": "atanor.seed-research.viewer-export.v1",
            "mode": "seed_research_viewer",
            "read_only": True,
            "not_local_brain": True,
            "run_id": None,
            "badge": "Seed Research Viewer",
            "concept_count": 0,
            "relation_count": 0,
            "metrics": {},
            "nodes": [],
            "edges": [],
            "filters": {"relation_types": [], "trust_states": []},
            "exported_at": utc_now_iso(),
        }
    return json.loads(viewer_path.read_text(encoding="utf-8"))


def main_run() -> None:
    parser = argparse.ArgumentParser(description="Run one ATANOR Seed Graph research iteration.")
    parser.add_argument("--root", default=None)
    args = parser.parse_args()
    print(json.dumps(run_seed_iteration(args.root), ensure_ascii=False, indent=2))


def main_feedback() -> None:
    parser = argparse.ArgumentParser(description="Create a feedback patch for a seed research run.")
    parser.add_argument("--run", required=True)
    parser.add_argument("--root", default=None)
    args = parser.parse_args()
    print(json.dumps(apply_feedback(args.run, args.root), ensure_ascii=False, indent=2))


def main_freeze() -> None:
    parser = argparse.ArgumentParser(description="Freeze a seed research run into data/seed.")
    parser.add_argument("--run", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--root", default=None)
    parser.add_argument("--output-root", default=None)
    args = parser.parse_args()
    print(json.dumps(freeze_seed(args.run, args.version, args.root, args.output_root), ensure_ascii=False, indent=2))
