from __future__ import annotations

import json
from typing import Any

from .benchmark import build_zero_user_benchmark_v0
from .models import PACK_PATH, BaseBrainPack, ensure_base_dirs, utc_now_iso
from .seed_extension import build_seed_graph_v2
from .semantic_pack import build_general_semantic_pack_v0
from .surface_pack import build_general_surface_pack_v0


def _validate_seed(seed_graph: dict[str, Any]) -> None:
    required = ["relation_primitives", "reasoning_primitives", "answer_intent_primitives", "discourse_anchors"]
    missing = [key for key in required if not seed_graph.get(key)]
    if missing:
        raise ValueError(f"seed_graph_missing_required_fields:{','.join(missing)}")


def _validate_semantic(semantic_graph: dict[str, Any]) -> None:
    concepts = semantic_graph.get("concepts") or []
    if len(concepts) < 30:
        raise ValueError("semantic_pack_requires_at_least_30_concepts")
    for concept in concepts:
        for key in ["concept_id", "canonical_name", "aliases", "short_description", "relations", "confidence"]:
            if key not in concept:
                raise ValueError(f"semantic_concept_missing_{key}")


def _validate_surface(surface_graph: dict[str, Any]) -> None:
    constructions = surface_graph.get("constructions") or []
    languages = {item.get("language") for item in constructions}
    if not {"ko", "en"}.issubset(languages):
        raise ValueError("surface_pack_requires_ko_and_en_constructions")
    for construction in constructions:
        for key in ["construction_id", "language", "function", "abstract_shape", "allowed_discourse_moves"]:
            if key not in construction:
                raise ValueError(f"surface_construction_missing_{key}")


def _lemma_links(semantic_graph: dict[str, Any], surface_graph: dict[str, Any]) -> list[dict[str, str]]:
    languages = {item.get("language") for item in surface_graph.get("constructions", [])}
    links: list[dict[str, str]] = []
    for concept in semantic_graph.get("concepts", []):
        labels = concept.get("labels") or {}
        for language in sorted(languages):
            label = labels.get(language)
            if label:
                links.append({"concept_id": concept["concept_id"], "language": str(language), "lemma": str(label)})
    return links


def build_base_brain_pack_v0(write: bool = True) -> dict[str, Any]:
    """Build the curated base pack. ``write`` defaults True (create/refresh the
    on-disk pack). Callers that only need the payload in memory — proof/introspection
    and the loader's in-memory rebuild — pass write=False so they never CLOBBER a
    promoted pack on disk (curated 58 would overwrite promoted 1472+)."""
    ensure_base_dirs()
    seed_graph = build_seed_graph_v2()
    semantic_graph = build_general_semantic_pack_v0()
    surface_graph = build_general_surface_pack_v0()
    benchmark = build_zero_user_benchmark_v0()
    _validate_seed(seed_graph)
    _validate_semantic(semantic_graph)
    _validate_surface(surface_graph)
    pack = BaseBrainPack(
        pack_id="atanor_base_brain_v0",
        version="0.1.2",
        metadata={
            "created_at": utc_now_iso(),
            "base_pack_code_version": "0.1.2",
            "claims": [
                "zero-user-data graph-native answer proof",
                "curated small base graph",
                "no external LLM/sLLM",
            ],
            "does_not_claim": [
                "GPT-level quality",
                "complete world knowledge",
                "full web-scale Semantic Cloud Graph",
                "trained neural decoder",
            ],
            "semantic_surface_links": _lemma_links(semantic_graph, surface_graph),
            "honesty": {
                "user_data_used": False,
                "external_llm_used": False,
                "external_sllm_used": False,
                "external_web_used": False,
            },
        },
        seed_graph=seed_graph,
        semantic_graph=semantic_graph,
        surface_graph=surface_graph,
        benchmark=benchmark,
    )
    payload = pack.to_dict()
    if write:
        PACK_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(build_base_brain_pack_v0(), ensure_ascii=False, indent=2))
