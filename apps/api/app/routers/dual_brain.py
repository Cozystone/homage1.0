from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.alpha_services import alpha_service
from packages.base_brain.zero_user_answer import answer_with_base_brain
from packages.cgsr.cgsr.conversation_surface import generate_conversation_surface
from packages.core_proof.three_core_answer_path import run_prompt_proof
from packages.voice_loop.runtime_availability import check_voice_runtime_availability
from packages.surface_brain.monitor import monitor_answer, repair_answer_for_mode
from packages.surface_brain.dual_projection import ingest_source_sentence_dual_projection
from packages.surface_brain.models import SourceSentence, honesty_flags
from packages.surface_brain.realization_planner import plan_speech, realize_answer
from packages.cloud_brain.graph_exchange import run_local_cloud_exchange
from packages.cloud_brain.semantic_store import SemanticCloudStore


router = APIRouter(tags=["dual-brain"])


class DualBrainIngestRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    source_id: str | None = None
    url: str | None = None
    title: str | None = None
    license: str = "unknown"
    usage_allowed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtanorChatRequest(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=1000)
    query: str | None = Field(default=None, min_length=1, max_length=1000)
    message: str | None = Field(default=None, min_length=1, max_length=1000)
    language: str | None = None
    audience_level: str = "beginner"
    tone: str = "clear"
    mode: str = "default"
    web_search: bool = False
    brain_mode: str = "unified"
    include_trace: bool = False

    def question_text(self) -> str:
        text = self.question or self.query or self.message or ""
        return re.sub(r"\s+", " ", text).strip()


def _flags() -> dict[str, Any]:
    return {
        **honesty_flags(),
        "final_answer_generation_claimed": True,
        "trace_hidden_by_default": True,
        "production_store_mutated": False,
        "candidate_promotion": False,
        "internal_trace_exposed": False,
    }


def _run_three_core_compact_trace(question: str) -> dict[str, Any]:
    """Run the symbolic three-core path as hidden trace, not as answer text."""
    try:
        record = run_prompt_proof(question)
    except Exception as exc:  # pragma: no cover - defensive trace isolation
        return {
            "used": False,
            "error": type(exc).__name__,
            "local_brain_write": False,
            "external_llm_used": False,
            "external_sllm_used": False,
            "trace_hidden_by_default": True,
        }
    sqc_atoms = record.get("sqc", {}).get("encoded_concepts") or []
    wave = record.get("wave_graph") or {}
    surface = record.get("surface") or {}
    return {
        "used": True,
        "sqc": {
            "used": bool(record.get("sqc", {}).get("used")),
            "atom_count": len(sqc_atoms),
            "memory_bytes": int(record.get("sqc", {}).get("memory_bytes") or 0),
            "compression_form": record.get("sqc", {}).get("compression_form"),
        },
        "fractal_seed_rail": {
            "used": bool(record.get("seed_rail", {}).get("used")),
            "activated_primitives": list(record.get("seed_rail", {}).get("activated_seed_primitives") or []),
            "rail_count": len(record.get("seed_rail", {}).get("reasoning_scaffold") or []),
        },
        "holographic_wave": {
            "used": bool(wave.get("used")),
            "candidate_paths": len(wave.get("candidate_paths") or []),
            "selected_path_id": (wave.get("selection_result") or {}).get("selected_path_id"),
            "selected_primitive": (wave.get("selection_result") or {}).get("selected_primitive"),
            "constructive_total": (wave.get("constructive_or_destructive_signal") or {}).get("constructive_total"),
            "destructive_total": (wave.get("constructive_or_destructive_signal") or {}).get("destructive_total"),
        },
        "surface_brain": {
            "used": bool(surface.get("used")),
            "candidate_count": len(surface.get("construction_candidates") or []),
            "selected_construction": list(surface.get("selected_construction") or []),
            "template_like": bool(surface.get("template_like")),
            "q_cortex_used": bool(surface.get("q_cortex_used")),
            "q_cortex_run_id": surface.get("q_cortex_run_id"),
        },
        "honesty": {
            "external_llm_used": bool(record.get("external_llm_used")),
            "external_sllm_used": bool(record.get("sllm_used")),
            "local_brain_write": bool(record.get("local_write")),
            "trace_hidden_by_default": True,
            "final_answer_source": "default_surface_or_base_brain_answer; three_core_is_hidden_trace",
        },
    }


def _attach_three_core_trace(
    response: dict[str, Any],
    *,
    request: AtanorChatRequest,
    three_core_trace: dict[str, Any],
) -> dict[str, Any]:
    result = response.get("result")
    if not isinstance(result, dict):
        return response
    compact_trace = result.setdefault("compact_trace", {})
    if isinstance(compact_trace, dict):
        compact_trace["three_core"] = three_core_trace
    else:
        result["compact_trace"] = {"three_core": three_core_trace}
    if request.include_trace or request.mode in {"trace", "research"}:
        trace = result.get("trace")
        if not isinstance(trace, dict):
            trace = {}
        trace["three_core"] = three_core_trace
        result["trace"] = trace
    else:
        result["trace"] = None
    if request.mode == "research":
        research_trace = result.get("research_trace")
        if not isinstance(research_trace, dict):
            research_trace = {}
        research_trace["three_core"] = three_core_trace
        result["research_trace"] = research_trace
    answer_engine = result.setdefault("answer_engine", {})
    if isinstance(answer_engine, dict):
        answer_engine["three_core_trace_attached"] = bool(three_core_trace.get("used"))
        answer_engine["three_core_answer_source"] = "hidden_trace_only"
    result["default_trace_visible"] = False
    result["trace_hidden_by_default"] = True
    return response


def _compact_conversation_text(question: str) -> str:
    return re.sub(r"[\s!.?,:;~\-_'\"()\[\]{}]+", "", question.strip().lower())


def _is_live_selfhood_conversation(question: str) -> bool:
    compact = _compact_conversation_text(question)
    if not compact:
        return True
    if compact in {
        "안녕",
        "안녕하세요",
        "하이",
        "헬로",
        "반가워",
        "고마워",
        "감사",
        "감사합니다",
        "hi",
        "hello",
        "hey",
        "yo",
        "thanks",
        "thankyou",
    }:
        return True
    lowered = question.strip().lower()
    return any(
        term in lowered
        for term in (
            "자기 모델",
            "자아 모델",
            "자의식",
            "내적 언어",
            "생각 중추",
            "유리 구",
            "구슬",
            "orb",
            "self model",
            "selfhood",
            "inner speech",
            "voice mode",
        )
    ) and len(question.strip()) <= 80


def _live_selfhood_speech_act(question: str, language: str) -> str:
    compact = _compact_conversation_text(question)
    if language == "ko":
        if compact in {"안녕", "안녕하세요", "하이", "헬로", "반가워"}:
            return "greeting"
        if compact in {"고마워", "감사", "감사합니다"}:
            return "thanks"
        if any(term in question for term in ("자기 모델", "자아 모델", "자의식", "내적 언어", "생각 중추")):
            return "self_model"
        if any(term in question for term in ("유리 구", "구슬")):
            return "orb"
        return "conversation"
    if compact in {"hi", "hello", "hey", "yo"}:
        return "greeting"
    if compact in {"thanks", "thankyou"}:
        return "thanks"
    if any(term in question.lower() for term in ("self model", "selfhood", "inner speech")):
        return "self_model"
    return "conversation"


def _voice_runtime_snapshot(text: str, language: str) -> dict[str, Any]:
    """Describe optional Fish TTS readiness without loading models or saving audio."""

    try:
        availability = check_voice_runtime_availability()
    except Exception as exc:  # pragma: no cover - optional runtime isolation
        return {
            "requested": True,
            "tts_engine": "fish_2",
            "available": False,
            "audio_stream_available": False,
            "visual_speaking_recommended": bool(text),
            "external_service": False,
            "generated_audio_persisted": False,
            "unavailable_reason": type(exc).__name__,
        }
    fish2 = availability.get("fish_2")
    available = bool(fish2 and fish2.available)
    return {
        "requested": True,
        "tts_engine": "fish_2",
        "available": available,
        "audio_stream_available": False,
        "visual_speaking_recommended": bool(text),
        "external_service": False,
        "generated_audio_persisted": False,
        "language": "ko-KR" if language == "ko" else "en-US",
        "unavailable_reason": None if available else ",".join(fish2.missing_modules if fish2 else ["fish_2_status_unavailable"]),
    }


def _live_selfhood_payload(
    request: AtanorChatRequest,
    *,
    question: str,
    language: str,
) -> dict[str, Any]:
    speech_act = _live_selfhood_speech_act(question, language)
    generated = generate_conversation_surface(question, language=language)
    compact_trace = {
        "local_coverage": "live_selfhood_conversation",
        "selfhood_loop": {
            "used": True,
            "internal_scratchpad_visible": False,
            "rule_based_answer_blocked": True,
            "requires_learned_generator": False,
            "speech_act": speech_act,
            "emotion_hint": "warm" if speech_act in {"greeting", "thanks"} else "calm",
        },
        "semantic_cloud_graph": {"attached_nodes": 0, "evidence_docs": 0},
        "surface_graph": {
            "construction_families": [],
            "discourse_moves": [],
            "conversation_surface": generated.diagnostics,
        },
        "q_cortex": {"used": False, "run_id": None, "real_quantum_hardware_used": False},
        "working_memory": {"temporary_context": False, "local_brain_write": False},
        "confidence": "medium" if generated.confidence >= 0.5 else "abstained",
    }
    if not generated.answer:
        payload = {
            "answer": None,
            "language": language,
            "confidence": 0.0,
            "answer_kind": "generation_abstained_no_rule_based_model",
            "speech_act": speech_act,
            "can_speak": False,
            "abstain_reason": generated.diagnostics.get("abstain_reason", "no_safe_token_walk"),
            "default_trace_visible": False,
            "trace": compact_trace if request.include_trace or request.mode in {"trace", "research"} else None,
            "compact_trace": compact_trace,
            "research_trace": {"selfhood_loop": compact_trace["selfhood_loop"]} if request.mode == "research" else None,
            "evidence_docs": [],
            "matched_nodes": [],
            "matched_edges": [],
            "surface_plan": {
                "plan_id": None,
                "intent": "live_selfhood_conversation",
                "construction_families": compact_trace["surface_graph"]["construction_families"],
                "q_cortex_used": False,
                "q_cortex_run_id": None,
            },
            "answer_engine": {
                "name": "ATANOR Live Selfhood Conversation Surface",
                "semantic_plane": "conversation_only",
                "surface_plane": "asm_v0_construction_conditioned_surface",
                "external_llm": False,
                "external_sllm": False,
                "local_brain_write": False,
                "production_store_mutated": False,
                "candidate_promotion": False,
                "trace_hidden_by_default": True,
                "internal_scratchpad_visible": False,
                "internal_trace_exposed": False,
                "rule_based_answer_used": False,
                "template_free_surface": True,
                "generation_basis": generated.diagnostics.get("generation_basis"),
                "diagnostics": generated.diagnostics,
            },
            **{**_flags(), "final_answer_generation_claimed": False},
        }
        return {"state": "abstained", "result": payload, **{**_flags(), "final_answer_generation_claimed": False}}
    voice_output = _voice_runtime_snapshot(generated.answer, language)
    payload = {
        "answer": generated.answer,
        "language": language,
        "confidence": generated.confidence,
        "answer_kind": "asm_v0_conversation_surface",
        "speech_act": speech_act,
        "can_speak": True,
        "voice_output": voice_output,
        "default_trace_visible": False,
        "trace": compact_trace if request.include_trace or request.mode in {"trace", "research"} else None,
        "compact_trace": compact_trace,
        "research_trace": {"selfhood_loop": compact_trace["selfhood_loop"]} if request.mode == "research" else None,
        "evidence_docs": [],
        "matched_nodes": [],
        "matched_edges": [],
        "surface_plan": {
            "plan_id": None,
            "intent": "live_selfhood_conversation",
            "construction_families": compact_trace["surface_graph"]["construction_families"],
            "q_cortex_used": False,
            "q_cortex_run_id": None,
        },
        "answer_engine": {
            "name": "ATANOR Live Selfhood Conversation Surface",
            "semantic_plane": "conversation_only",
            "surface_plane": "asm_v0_construction_conditioned_surface",
            "external_llm": False,
            "external_sllm": False,
            "local_brain_write": False,
            "production_store_mutated": False,
            "candidate_promotion": False,
            "trace_hidden_by_default": True,
            "internal_scratchpad_visible": False,
            "internal_trace_exposed": False,
            "rule_based_answer_used": False,
            "template_free_surface": True,
            "generation_basis": generated.diagnostics.get("generation_basis"),
            "diagnostics": generated.diagnostics,
        },
        **_flags(),
    }
    return {"state": "completed", "result": payload, **_flags()}


def _clean_graph_count_question(question: str) -> bool:
    lowered = question.lower()
    count_terms = (
        "총",
        "몇",
        "개수",
        "수",
        "표시",
        "렌더",
        "렌더링",
        "viewport",
        "rendered",
        "현재",
        "지금",
        "count",
        "how many",
        "number of",
    )
    graph_terms = (
        "노드",
        "node",
        "nodes",
        "관계",
        "관계선",
        "연결",
        "연결선",
        "엣지",
        "edge",
        "edges",
        "link",
        "links",
        "relation",
        "relations",
        "graph",
        "graph count",
        "시드",
        "seed",
        "base",
        "앵커",
    )
    memory_scope_terms = (
        "내 로컬 메모리",
        "로컬 메모리",
        "개인 메모리",
        "로컬 브레인",
        "클라우드 브레인",
        "local brain",
        "cloud brain",
        "local graph",
        "cloud graph",
        "저장된 기억",
        "저장된 노드",
        "화면",
        "표시",
        "렌더",
        "렌더링",
        "viewport",
        "rendered",
        "로컬",
        "클라우드",
        "local",
        "cloud",
        "메모리",
        "브레인",
        "brain",
        "그래프",
        "기본",
        "시드",
        "앵커",
        "seed",
        "base",
    )
    return (
        any(term in lowered or term in question for term in count_terms)
        and any(term in lowered or term in question for term in graph_terms)
        and any(term in lowered or term in question for term in memory_scope_terms)
    )


def _local_graph_count_snapshot() -> dict[str, Any]:
    try:
        from packages.brain_graph.aggregator import aggregate_brain_graph

        graph = aggregate_brain_graph(
            view="local",
            layers=["local_user", "local_base", "seed", "working_memory_local"],
            max_nodes=1200,
            max_edges=2400,
            mode="fast",
        )
    except Exception as exc:  # pragma: no cover - status must not fall through
        return {
            "available": False,
            "error": type(exc).__name__,
            "personal_local_memory_count": {"nodes": 0, "edges": 0},
            "local_viewport_materialized_count": {"nodes": None, "edges": None},
            "seed_anchor_count": None,
            "base_anchor_count": None,
            "rendered_edge_count": None,
            "logical_local_node_count": None,
        }
    stats = graph.get("stats") if isinstance(graph.get("stats"), dict) else {}
    layer_counts = stats.get("layer_counts") if isinstance(stats.get("layer_counts"), dict) else {}
    edge_layer_counts = stats.get("edge_layer_counts") if isinstance(stats.get("edge_layer_counts"), dict) else {}
    personal_nodes = int(layer_counts.get("local_user") or stats.get("local_user_nodes") or 0)
    personal_edges = int(edge_layer_counts.get("local_user") or 0)
    rendered_nodes = int(stats.get("rendered_nodes") or len(graph.get("nodes") or []))
    rendered_edges = int(stats.get("rendered_edges") or len(graph.get("edges") or []))
    return {
        "available": True,
        "personal_local_memory_count": {"nodes": personal_nodes, "edges": personal_edges},
        "local_viewport_materialized_count": {"nodes": rendered_nodes, "edges": rendered_edges},
        "seed_anchor_count": int(layer_counts.get("seed") or 0),
        "base_anchor_count": int(layer_counts.get("local_base") or 0),
        "working_memory_local_count": int(layer_counts.get("working_memory_local") or 0),
        "rendered_edge_count": rendered_edges,
        "logical_local_node_count": personal_nodes,
        "local_graph_pipeline": graph.get("honesty", {}).get("view_is_tab_aware", True),
    }


def _clean_graph_count_payload(
    request: AtanorChatRequest,
    *,
    question: str,
    language: str,
) -> dict[str, Any]:
    lowered = question.lower()
    wants_cloud = "cloud" in lowered or "클라우드" in question
    wants_local = "local" in lowered or "로컬" in question or not wants_cloud
    wants_viewport = any(term in lowered or term in question for term in ("화면", "표시", "렌더", "렌더링", "viewport", "rendered"))
    wants_seed_base = any(term in lowered or term in question for term in ("seed", "base", "시드", "기본", "앵커"))
    status_error: str | None = None
    local_snapshot = _local_graph_count_snapshot()
    try:
        cloud_status = SemanticCloudStore().status()
    except Exception as exc:  # pragma: no cover - status questions must stay safe
        status_error = type(exc).__name__
        cloud_status = {"concepts": 0, "relations": 0, "evidence": 0}
    personal_local = local_snapshot.get("personal_local_memory_count") if isinstance(local_snapshot.get("personal_local_memory_count"), dict) else {}
    local_nodes = int(personal_local.get("nodes") or 0)
    local_edges = int(personal_local.get("edges") or 0)
    viewport = local_snapshot.get("local_viewport_materialized_count") if isinstance(local_snapshot.get("local_viewport_materialized_count"), dict) else {}
    viewport_nodes = viewport.get("nodes")
    viewport_edges = viewport.get("edges")
    seed_anchor_count = local_snapshot.get("seed_anchor_count")
    base_anchor_count = local_snapshot.get("base_anchor_count")
    cloud_nodes = int(cloud_status.get("concepts") or 0)
    cloud_edges = int(cloud_status.get("relations") or 0)
    if wants_cloud and not wants_local:
        nodes = cloud_nodes
        edges = cloud_edges
        scope_ko = "클라우드 브레인 proof store"
        scope_en = "Cloud Brain proof store"
    elif wants_local and not wants_cloud:
        nodes = local_nodes
        edges = local_edges
        scope_ko = "로컬 브레인 개인 메모리 저장소"
        scope_en = "Local Brain private memory store"
    else:
        nodes = local_nodes + cloud_nodes
        edges = local_edges + cloud_edges
        scope_ko = "로컬 브레인과 클라우드 브레인 합산"
        scope_en = "Local Brain plus Cloud Brain"
    status_unavailable = status_error is not None and (wants_cloud or not wants_local)
    if status_unavailable and language == "ko":
        answer = "현재 그래프 상태를 읽을 수 없습니다. 일반 지식 답변으로 대체하지 않습니다."
    elif status_unavailable:
        answer = "ATANOR cannot read the graph status right now. It will not substitute an unrelated general-knowledge answer."
    elif language == "ko":
        if wants_local and not wants_cloud and (wants_viewport or wants_seed_base):
            if local_snapshot.get("available"):
                answer = (
                    f"개인 Local Brain 저장 메모리는 {local_nodes:,}개 노드 / {local_edges:,}개 연결선입니다. "
                    f"현재 화면에 물질화된 로컬 그래프 뷰포트는 {int(viewport_nodes or 0):,}개 노드 / {int(viewport_edges or 0):,}개 렌더링 연결선입니다. "
                    f"이 화면 값에는 기본 Seed/Base 앵커가 포함될 수 있으며, Seed 앵커 {int(seed_anchor_count or 0):,}개와 Base 앵커 {int(base_anchor_count or 0):,}개는 개인 저장 메모리로 계산하지 않습니다."
                )
            else:
                answer = "현재 로컬 그래프 뷰포트 상태를 읽을 수 없습니다. 일반 지식 답변으로 대체하지 않습니다."
        elif wants_local and not wants_cloud:
            answer = (
                f"개인 Local Brain 저장 메모리는 {local_nodes:,}개 노드 / {local_edges:,}개 연결선입니다. "
                f"현재 화면에 보이는 로컬 그래프 뷰포트는 별도 카테고리이며, 지금 확인된 표시 노드는 {int(viewport_nodes or 0):,}개, 표시 연결선은 {int(viewport_edges or 0):,}개입니다. "
                "Seed/Base 기본 그래프와 Working Memory 임시 노드는 개인 저장 메모리와 구분됩니다."
            )
        else:
            answer = (
                f"{scope_ko} 기준 현재 확인된 논리 노드는 {nodes:,}개, 연결선은 {edges:,}개입니다. "
                "개인 Local Brain 저장 메모리, 화면 뷰포트, Seed/Base 앵커, Cloud proof store는 서로 다른 count 카테고리입니다."
            )
    else:
        if wants_local and not wants_cloud and (wants_viewport or wants_seed_base):
            if local_snapshot.get("available"):
                answer = (
                    f"Personal Local Brain stored memory is {local_nodes:,} nodes / {local_edges:,} relations. "
                    f"The current local graph viewport has {int(viewport_nodes or 0):,} materialized nodes and {int(viewport_edges or 0):,} rendered edges. "
                    f"Seed anchors ({int(seed_anchor_count or 0):,}) and Base anchors ({int(base_anchor_count or 0):,}) are visible scaffolds, not personal stored memory."
                )
            else:
                answer = "ATANOR cannot read the local graph viewport status right now. It will not substitute an unrelated general-knowledge answer."
        elif wants_local and not wants_cloud:
            answer = (
                f"Personal Local Brain stored memory is {local_nodes:,} nodes / {local_edges:,} relations. "
                f"The visible local graph viewport is a separate category: {int(viewport_nodes or 0):,} displayed nodes and {int(viewport_edges or 0):,} displayed edges. "
                "Seed/Base scaffolds and temporary Working Memory nodes are not counted as personal stored memory."
            )
        else:
            answer = (
                f"For the {scope_en}, ATANOR currently sees {nodes:,} logical nodes and {edges:,} relations. "
                "Personal Local Brain memory, viewport rendering, Seed/Base anchors, and Cloud proof-store counts are separate categories."
            )
    compact_trace = {
        "local_coverage": "status_question",
        "graph_status": {
            "local_nodes": local_nodes,
            "local_edges": local_edges,
            "personal_local_memory_count": {"nodes": local_nodes, "edges": local_edges},
            "local_viewport_materialized_count": local_snapshot.get("local_viewport_materialized_count"),
            "seed_anchor_count": seed_anchor_count,
            "base_anchor_count": base_anchor_count,
            "rendered_edge_count": local_snapshot.get("rendered_edge_count"),
            "logical_local_node_count": local_snapshot.get("logical_local_node_count"),
            "count_categories": {
                "personal_local_memory_count": "user-owned Local Brain stored memories",
                "local_viewport_materialized_count": "nodes/edges currently visible or materialized in the local graph view",
                "seed_anchor_count": "default Seed anchors, not personal memory",
                "base_anchor_count": "Base Brain anchors, not personal memory",
                "rendered_edge_count": "edges currently rendered in the viewport",
                "logical_local_node_count": "full personal local logical graph count when available",
            },
            "cloud_nodes": cloud_nodes,
            "cloud_edges": cloud_edges,
            "selected_scope": "cloud" if wants_cloud and not wants_local else "local" if wants_local and not wants_cloud else "combined",
            "status_unavailable": status_unavailable,
            "status_error": status_error,
        },
        "semantic_cloud_graph": {"attached_nodes": 0, "evidence_docs": 0},
        "surface_graph": {"construction_families": ["direct_status_answer"], "discourse_moves": ["direct_answer"]},
        "q_cortex": {"used": False, "real_quantum_hardware_used": False},
        "working_memory": {"temporary_context": False, "local_brain_write": False},
        "confidence": "high",
    }
    payload = {
        "answer": answer,
        "language": language,
        "confidence": 0.52 if status_unavailable else 0.96,
        "default_trace_visible": False,
        "trace": compact_trace if request.include_trace or request.mode in {"trace", "research"} else None,
        "compact_trace": compact_trace,
        "research_trace": {"graph_status": compact_trace["graph_status"]} if request.mode == "research" else None,
        "evidence_docs": [],
        "surface_plan": {
            "plan_id": None,
            "intent": "graph_status_count",
            "construction_families": ["direct_status_answer"],
            "q_cortex_used": False,
            "q_cortex_run_id": None,
        },
        "answer_engine": {
            "name": "ATANOR Status Router",
            "semantic_plane": "Local/Cloud status counters",
            "surface_plane": "Direct status answer",
            "external_llm": False,
            "external_sllm": False,
            "local_brain_write": False,
            "trace_hidden_by_default": True,
        },
        **_flags(),
    }
    return {"state": "completed", "result": payload, **_flags()}


def _is_graph_count_question(question: str) -> bool:
    lowered = question.lower()
    count_terms = ("몇개", "몇 개", "개수", "총 개", "count", "how many", "number of")
    graph_terms = ("노드", "node", "관계", "relation", "edge", "그래프", "graph")
    return any(term in lowered for term in count_terms) and any(term in lowered for term in graph_terms)


def _should_try_base_brain_first(question: str) -> bool:
    lowered = question.lower()
    return any(
        term in lowered or term in question
        for term in (
            "local brain",
            "cloud brain",
            "q-cortex",
            "qcortex",
            "atanor",
            "아타노르",
            "로컬 브레인",
            "클라우드 브레인",
            "양자컴퓨터",
            "ram",
            "ssd",
            "컴퓨터 메모리",
            "휘발성 메모리",
            "주기억장치",
            "memory vs ssd",
            "volatile memory",
            "computer memory",
            "근거 중심",
            "과장 없이",
            "템플릿",
            "내부 경로",
            "숨기",
            "초등학생",
            "중학생",
            "전문가",
            "영어로",
            "한국어답게",
            "번역투",
        )
    )


def _graph_count_payload(request: AtanorChatRequest, question: str, language: str) -> dict[str, Any]:
    status = SemanticCloudStore().status()
    cloud_nodes = int(status.get("concepts") or 0)
    cloud_relations = int(status.get("relations") or 0)
    evidence = int(status.get("evidence") or 0)
    candidate_pairs = cloud_nodes * max(0, cloud_nodes - 1) // 2
    local_nodes = 0
    local_relations = 0
    if language == "ko":
        answer = (
            f"현재 확인된 기준으로 Local Brain 사용자 메모리는 {local_nodes:,}개 노드 / {local_relations:,}개 관계입니다. "
            f"Cloud Brain proof store에는 논리 노드 {cloud_nodes:,}개, 검증 저장 관계 {cloud_relations:,}개, 근거 {evidence:,}개가 있습니다. "
            f"참고로 가능한 노드쌍은 {candidate_pairs:,}개지만, ATANOR는 모든 쌍을 관계로 저장하지 않고 실제로 추출/검증된 관계만 저장합니다."
        )
    else:
        answer = (
            f"Current Local Brain user memory is {local_nodes:,} nodes / {local_relations:,} relations. "
            f"The Cloud Brain proof store has {cloud_nodes:,} logical nodes, {cloud_relations:,} verified stored relations, and {evidence:,} evidence records. "
            f"There are {candidate_pairs:,} possible node pairs, but ATANOR stores only extracted and verified relations, not every possible pair."
        )
    compact_trace = {
        "local_coverage": "status_query",
        "semantic_cloud_graph": {
            "attached_nodes": 0,
            "evidence_docs": 0,
            "cloud_logical_nodes": cloud_nodes,
            "cloud_stored_relations": cloud_relations,
            "candidate_pairs": candidate_pairs,
        },
        "surface_graph": {"construction_families": ["direct_status_answer"], "discourse_moves": ["answer"]},
        "q_cortex": {"used": False, "run_id": None, "real_quantum_hardware_used": False},
        "working_memory": {"temporary_context": False, "local_brain_write": False},
        "confidence": "high",
    }
    payload = {
        "answer": answer,
        "language": language,
        "confidence": 0.98,
        "answer_kind": "graph_status",
        "default_trace_visible": False,
        "trace": compact_trace if request.include_trace or request.mode in {"trace", "research"} else None,
        "compact_trace": compact_trace,
        "research_trace": {"semantic_cloud_status": status} if request.mode == "research" else None,
        "evidence_docs": [],
        "matched_nodes": [],
        "surface_plan": {
            "plan_id": None,
            "intent": "graph_status",
            "construction_families": ["direct_status_answer"],
            "q_cortex_used": False,
            "q_cortex_run_id": None,
        },
        "answer_engine": {
            "name": "ATANOR Status Router",
            "semantic_plane": "Semantic Cloud Proof Store",
            "surface_plane": "Direct Status Answer",
            "external_llm": False,
            "external_sllm": False,
            "local_brain_write": False,
            "trace_hidden_by_default": True,
        },
        **_flags(),
    }
    return {"state": "completed", "result": payload, **_flags()}


@router.post("/api/dual-brain/ingest")
def dual_brain_ingest(request: DualBrainIngestRequest) -> dict[str, Any]:
    source = SourceSentence.from_text(
        request.text,
        source_id=request.source_id,
        url=request.url,
        title=request.title,
        license=request.license,
        usage_allowed=request.usage_allowed,
        metadata=request.metadata,
    )
    return {**ingest_source_sentence_dual_projection(source), **_flags()}


def _semantic_context_from_rag(result: dict[str, Any]) -> dict[str, Any]:
    concepts = list(result.get("active_concepts") or [])
    for node in result.get("matched_nodes") or []:
        label = node.get("label") or node.get("primary_name") or node.get("id")
        if label and label not in concepts:
            concepts.append(label)
    relations = []
    for edge in result.get("matched_edges") or []:
        relations.append(
            {
                "source": edge.get("source") or edge.get("source_hash"),
                "relation": edge.get("relation") or edge.get("predicate"),
                "target": edge.get("target") or edge.get("target_hash"),
                "confidence": edge.get("confidence") or edge.get("weight") or 0.5,
            }
        )
    return {
        "concepts": concepts,
        "relations": relations,
        "evidence": list(result.get("evidence_docs") or []),
        "claims": list(result.get("claim_plan") or []),
        "confidence": float(result.get("confidence") or 0.0),
        "local_coverage": "high" if result.get("memory_activation") else "low" if not concepts else "medium",
        "retrieval_trace": result.get("retrieval_trace", {}),
    }


def _needs_base_brain_fallback(semantic_context: dict[str, Any]) -> bool:
    return not (semantic_context.get("relations") or semantic_context.get("evidence") or semantic_context.get("claims"))


def _is_recent_learning_question(question: str) -> bool:
    lower = question.lower()
    return any(token in question for token in ("최근 학습", "최근 배운", "학습한 개념", "새로 배운")) or (
        "recent" in lower and any(token in lower for token in ("learn", "concept", "memory"))
    )


def _safe_public_concept_label(row: dict[str, Any]) -> str:
    label = str(row.get("canonical_name") or row.get("label") or "").strip()
    if not label:
        labels = row.get("language_labels")
        if isinstance(labels, dict):
            label = str(labels.get("ko") or labels.get("en") or "").strip()
    if not label:
        return ""
    if re.fullmatch(r"[0-9a-f]{10,64}", label, flags=re.IGNORECASE):
        return ""
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f-]{20,}", label, flags=re.IGNORECASE):
        return ""
    if label.lower().startswith(("ghost:", "hash:", "cbn_", "payload-vault://")):
        return ""
    if len(label) < 2:
        return ""
    label = re.sub(r"\s+", " ", label).strip(" .,:;!?()[]{}\"'")
    lower = label.lower()
    if lower in {
        "it",
        "this",
        "that",
        "data",
        "the",
        "a",
        "an",
        "one",
        "several",
        "usually",
        "unknown",
        "there",
        "bibliography",
        "references",
        "contents",
        "text",
        "what",
        "guide",
        "library",
        "article",
        "page",
        "home",
        "about",
        "presidents",
        "president-elect",
        "external links",
        "see also",
        "award",
        "recognition",
        "portal",
        "charcoal",
        "ours",
        "man",
        "he",
        "another",
        "stub",
        "interactions",
    }:
        return ""
    if len(label) > 48:
        return ""
    if len(label.split()) > 5:
        return ""
    if any(
        marker in lower
        for marker in (
            " such as ",
            " one of ",
            " not the ",
            " usually ",
            " widely used ",
            " backed financially ",
            " with privacy concerns",
            " can be ",
            " may be ",
            " listed on ",
            " website",
            " online service",
            " public metadata record",
            " bibliography",
            " full-text collection",
            " full text collection",
            " non-profit professional",
            " non profit professional",
            " organized into ",
            " published in partnership",
            " no longer published",
            " co-sponsored by ",
            " co sponsored by ",
            " regarded as ",
            " credited with ",
            " administered by ",
            " no clinical evidence",
            " home to ",
            " estimated to ",
            " jump to ",
            " move to ",
            " edit ",
        )
    ):
        return ""
    if lower.startswith(("listed ", "there ", "this ", "that ", "from ", "according ", "part of ")):
        return ""
    if re.search(r"[,.]", label) and not re.search(r"\b(?:AI|API|SQL|RAG|GraphRAG|SQLite|HTTP|GPU|CPU)\b", label):
        return ""
    has_hangul = bool(re.search(r"[\uac00-\ud7a3]", label))
    has_acronym = bool(re.search(r"\b[A-Z]{2,}\b", label))
    has_title_word = bool(re.search(r"\b[A-Z][a-zA-Z0-9.+#-]{2,}\b", label))
    if not (has_hangul or has_acronym or has_title_word):
        return ""
    return label[:48]


def _augment_recent_learning_context(semantic_context: dict[str, Any]) -> dict[str, Any]:
    store = SemanticCloudStore()
    concepts = list(store.load_concepts().values())
    relations = store.load_relations()
    concepts.sort(
        key=lambda row: (
            str(row.get("updated_at") or row.get("created_at") or ""),
            int(row.get("seen_count") or 0),
        ),
        reverse=True,
    )
    labels: list[str] = []
    seen: set[str] = set()
    for row in concepts:
        label = _safe_public_concept_label(row)
        key = label.lower()
        if label and key not in seen:
            labels.append(label)
            seen.add(key)
        if len(labels) >= 8:
            break
    merged = dict(semantic_context)
    merged["semantic_store_counts"] = {
        "concepts": len(concepts),
        "relations": len(relations),
    }
    if labels:
        merged["concepts"] = labels + [item for item in list(semantic_context.get("concepts") or []) if str(item) not in labels]
        merged["local_coverage"] = semantic_context.get("local_coverage") or "semantic_cloud_growth"
        merged.setdefault("claims", []).append(
            {
                "claim": "Semantic proof store is growing from public web seed metadata.",
                "source_scope": "cloud_proof_store",
                "local_brain_write": False,
            }
        )
        return merged
    merged["local_coverage"] = semantic_context.get("local_coverage") or "semantic_cloud_growth"
    return merged


UNSAFE_DEFAULT_ANSWER_RE = re.compile(
    r"(?:[�占]|ì|ë|í|ð|筌|荑|濡|洹|蹂|留|좊|쾶|ㅽ|"
    r"\b[0-9a-f]{24,}\b|payload-vault://|source_hash|node_id|semantic_projection_id|"
    r"Local Brain|Cloud Brain|Working Memory|Q-Cortex)",
    re.IGNORECASE,
)


def _answer_is_unsafe(answer: str) -> bool:
    text = str(answer or "")
    if UNSAFE_DEFAULT_ANSWER_RE.search(text):
        return True
    if any(term in text for term in ("먼저 의도와 경계", "내부적으로 점검", "내부 점검", "숨겨진 사고", "내적 독백")):
        return True
    monitor = monitor_answer(text)
    return bool(set(monitor.get("issues") or []) & {"encoding_artifact", "internal_trace_leakage", "internal_identifier_leakage"})


def _public_evidence_docs(docs: list[dict[str, Any]], *, mode: str) -> list[dict[str, Any]]:
    if mode in {"trace", "research"}:
        return docs
    public_docs: list[dict[str, Any]] = []
    for doc in docs:
        text_blob = " ".join(
            str(doc.get(key) or "")
            for key in ("path", "url", "snippet", "text", "title", "chunk_id", "hash_key", "source_hash")
        )
        if "payload-vault://" in text_blob or re.search(r"\b[0-9a-f]{24,}\b", text_blob, flags=re.IGNORECASE):
            continue
        if UNSAFE_DEFAULT_ANSWER_RE.search(text_blob):
            continue
        public_docs.append(
            {
                "title": doc.get("title") or doc.get("doc_id") or "source",
                "url": doc.get("url") or doc.get("path"),
                "snippet": doc.get("snippet") or doc.get("text") or "",
                "score": doc.get("score"),
            }
        )
    return public_docs[:6]


def _compact_exchange_trace(exchange: dict[str, Any] | None) -> dict[str, Any]:
    if not exchange:
        return {
            "enabled": False,
            "states": [],
            "local": "not_run",
            "cloud": "not_run",
            "web_atlas": "not_run",
            "working_memory_nodes": 0,
            "auto_detached": False,
            "local_write": False,
            "cloud_promotion": "manual_required",
        }
    chunk = exchange.get("cloud_graph_chunk") if isinstance(exchange.get("cloud_graph_chunk"), dict) else {}
    evidence = exchange.get("evidence_bundle") if isinstance(exchange.get("evidence_bundle"), dict) else {}
    working_memory = exchange.get("working_memory") if isinstance(exchange.get("working_memory"), dict) else {}
    promotion = exchange.get("promotion") if isinstance(exchange.get("promotion"), dict) else {}
    return {
        "enabled": True,
        "states": list(exchange.get("states") or []),
        "local": "hit" if "local_hit" in (exchange.get("states") or []) else "miss",
        "cloud": "hit" if chunk else "miss",
        "cloud_chunk_id": chunk.get("chunk_id"),
        "cloud_nodes": len(chunk.get("semantic_nodes") or []),
        "cloud_relations": len(chunk.get("relations") or []),
        "web_atlas": evidence.get("extraction_status") if evidence else "not_requested",
        "working_memory_nodes": int(working_memory.get("temporary_context_count") or 0),
        "auto_detached": bool(working_memory.get("auto_detached")),
        "pinned": bool(working_memory.get("pinned")),
        "local_write": False,
        "cloud_promotion": promotion.get("cloud_promotion") or "manual_required",
        "candidate_pending": bool(promotion.get("candidate_pending")),
        "fake_counts": False,
        "pair_edges_sent": 0,
    }


def _augment_semantic_context_with_exchange(semantic_context: dict[str, Any], exchange: dict[str, Any] | None) -> dict[str, Any]:
    if not exchange or not isinstance(exchange.get("cloud_graph_chunk"), dict):
        return semantic_context
    chunk = exchange["cloud_graph_chunk"]
    labels = [
        str(node.get("label") or node.get("concept_id") or node.get("id"))
        for node in list(chunk.get("semantic_nodes") or [])
        if isinstance(node, dict)
    ]
    if not labels:
        return semantic_context
    merged = dict(semantic_context)
    existing = [str(item) for item in list(merged.get("concepts") or [])]
    merged["concepts"] = labels + [item for item in existing if item not in labels]
    merged["local_coverage"] = merged.get("local_coverage") or "cloud_chunk_attached"
    evidence = list(merged.get("evidence") or [])
    evidence.append(
        {
            "title": "Temporary Cloud graph chunk",
            "snippet": ", ".join(labels[:6]),
            "source_scope": "cloud",
            "temporary": True,
            "local_brain_write": False,
        }
    )
    merged["evidence"] = evidence
    return merged


def _base_brain_payload(
    request: AtanorChatRequest,
    *,
    question: str,
    language: str,
    rag_result: dict[str, Any],
    exchange: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    base = answer_with_base_brain(
        question,
        language=language,  # type: ignore[arg-type]
        audience_level=request.audience_level,  # type: ignore[arg-type]
        mode=request.mode,  # type: ignore[arg-type]
    )
    if int(base.get("semantic_context_count") or 0) <= 0 and not str(base.get("answer") or "").strip():
        return None
    compact_trace = {
        "local_coverage": "base_brain",
        "base_brain": {
            "semantic_context_count": int(base.get("semantic_context_count") or 0),
            "surface_candidate_count": int(base.get("surface_candidate_count") or 0),
            "local_user_brain_used": False,
        },
        "semantic_cloud_graph": {
            "attached_nodes": 0,
            "evidence_docs": 0,
        },
        "surface_graph": {
            "construction_families": list((base.get("compact_trace") or {}).get("selected_surface_candidates") or []),
            "discourse_moves": [],
        },
        "q_cortex": {
            "used": bool(base.get("q_cortex_used")),
            "run_id": (base.get("trace") or {}).get("q_cortex_run_id"),
            "real_quantum_hardware_used": False,
        },
        "working_memory": {
            "temporary_context": bool(exchange and (exchange.get("cloud_graph_chunk") or exchange.get("evidence_bundle"))),
            "local_brain_write": False,
        },
        "local_cloud_exchange": _compact_exchange_trace(exchange),
        "confidence": "medium" if base.get("answer") else "low",
    }
    payload = {
        "answer": base["answer"],
        "language": language,
        "confidence": 0.64,
        "default_trace_visible": False,
        "trace": compact_trace if request.include_trace or request.mode in {"trace", "research"} else None,
        "compact_trace": compact_trace,
        "research_trace": {
            "base_brain": base,
            "rag_retrieval_trace": rag_result.get("retrieval_trace", {}),
        } if request.mode == "research" else None,
        "evidence_docs": [],
        "surface_plan": {
            "plan_id": None,
            "intent": (base.get("trace") or {}).get("intent"),
            "construction_families": compact_trace["surface_graph"]["construction_families"],
            "q_cortex_used": base.get("q_cortex_used"),
            "q_cortex_run_id": (base.get("trace") or {}).get("q_cortex_run_id"),
        },
        "answer_engine": {
            "name": "ATANOR Base Brain + Surface Repair",
            "semantic_plane": "Seed Graph / Base Brain",
            "surface_plane": "Surface Brain",
            "external_llm": False,
            "external_sllm": False,
            "local_brain_write": False,
            "trace_hidden_by_default": True,
            "q_cortex_optional": True,
            "network_barrier": "sealed_for_generation",
        },
        **_flags(),
    }
    return {"state": "completed", "result": payload, **_flags()}


@router.post("/api/chat/atanor")
async def chat_atanor(request: AtanorChatRequest) -> dict[str, Any]:
    question = request.question_text()
    if not question:
        raise HTTPException(status_code=422, detail="question, query, or message is required")
    language = request.language or ("ko" if any("\uac00" <= char <= "\ud7a3" for char in question) else "en")
    three_core_trace = _run_three_core_compact_trace(question)
    if _is_live_selfhood_conversation(question):
        return _attach_three_core_trace(
            _live_selfhood_payload(request, question=question, language=language),
            request=request,
            three_core_trace=three_core_trace,
        )
    if _clean_graph_count_question(question) or _is_graph_count_question(question):
        return _attach_three_core_trace(
            _clean_graph_count_payload(request, question=question, language=language),
            request=request,
            three_core_trace=three_core_trace,
        )
    if _should_try_base_brain_first(question):
        early = _base_brain_payload(request, question=question, language=language, rag_result={})
        if early is not None:
            return _attach_three_core_trace(early, request=request, three_core_trace=three_core_trace)
    rag_status = await alpha_service.query_graphrag(
        question,
        request.web_search,
        None,
        brain_mode=request.brain_mode,
        locale=request.language,
        include_trace=True,
    )
    rag_result = rag_status.get("result") or {}
    semantic_context = _semantic_context_from_rag(rag_result)
    if _is_recent_learning_question(question):
        semantic_context = _augment_recent_learning_context(semantic_context)
    if _needs_base_brain_fallback(semantic_context):
        exchange = run_local_cloud_exchange(
            question,
            pin_context=request.mode in {"trace", "research"},
            allow_web=request.web_search,
            max_chunks=1,
            max_latency_ms=900,
        )
        fallback = _base_brain_payload(request, question=question, language=language, rag_result=rag_result, exchange=exchange)
        if fallback is not None:
            return _attach_three_core_trace(fallback, request=request, three_core_trace=three_core_trace)
        semantic_context = _augment_semantic_context_with_exchange(semantic_context, exchange)
    else:
        exchange = None
        if semantic_context.get("local_coverage") in {None, "low", "weak", "none"}:
            exchange = run_local_cloud_exchange(
                question,
                pin_context=request.mode in {"trace", "research"},
                allow_web=request.web_search,
                max_chunks=1,
                max_latency_ms=900,
            )
            semantic_context = _augment_semantic_context_with_exchange(semantic_context, exchange)
    plan = plan_speech(
        question,
        semantic_context,
        language=language,
        audience_level=request.audience_level,
        tone=request.tone,
        mode=request.mode,
    )
    realized = realize_answer(plan, semantic_context, query=question)
    if request.mode not in {"trace", "research"} and _answer_is_unsafe(str(realized.get("answer") or "")):
        fallback = _base_brain_payload(request, question=question, language=language, rag_result=rag_result)
        if fallback is not None:
            result = fallback["result"]
            result.setdefault("compact_trace", {})["safety_fallback"] = "base_brain_after_unsafe_surface_answer"
            return _attach_three_core_trace(fallback, request=request, three_core_trace=three_core_trace)
        repair_trace: dict[str, Any] = {}
        repaired = repair_answer_for_mode(str(realized.get("answer") or ""), mode="default", trace=repair_trace)
        realized["answer"] = repaired.get("repaired_answer") or (
            "현재 확인된 근거만으로는 단정하기 어렵습니다." if language == "ko" else "I do not have enough verified evidence to answer confidently yet."
        )
        realized["repair"] = {
            **(realized.get("repair") or {}),
            "safety_applied": True,
            "applied_rules": repaired.get("applied_rules", []),
            "moved_to_trace_count": len(repaired.get("moved_to_trace", [])),
        }
    compact_trace = {
        "local_coverage": semantic_context.get("local_coverage"),
        "semantic_cloud_graph": {
            "attached_nodes": len(semantic_context.get("concepts") or []),
            "evidence_docs": len(semantic_context.get("evidence") or []),
        },
        "surface_graph": {
            "construction_families": realized["trace_summary"].get("selected_construction_families", []),
            "discourse_moves": realized["trace_summary"].get("selected_discourse_moves", []),
        },
        "q_cortex": {
            "used": bool(plan.get("q_cortex_used")),
            "run_id": plan.get("q_cortex_run_id"),
            "real_quantum_hardware_used": False,
        },
        "working_memory": {
            "temporary_context": bool((rag_result.get("retrieval_trace") or {}).get("working_memory_overlay")),
            "local_brain_write": False,
        },
        "local_cloud_exchange": _compact_exchange_trace(exchange),
        "confidence": "high" if realized["confidence"] >= 0.75 else "medium" if realized["confidence"] >= 0.5 else "low",
    }
    payload = {
        "answer": realized["answer"],
        "language": realized["language"],
        "confidence": realized["confidence"],
        "default_trace_visible": False,
        "trace": compact_trace if request.include_trace or request.mode in {"trace", "research"} else None,
        "compact_trace": compact_trace,
        "research_trace": {
            "semantic_context": semantic_context,
            "surface_plan": plan,
            "realized_answer": realized,
            "rag_retrieval_trace": rag_result.get("retrieval_trace", {}),
        } if request.mode == "research" else None,
        "evidence_docs": _public_evidence_docs(list(semantic_context.get("evidence") or []), mode=request.mode),
        "surface_plan": {
            "plan_id": plan.get("plan_id"),
            "intent": plan.get("intent"),
            "construction_families": compact_trace["surface_graph"]["construction_families"],
            "q_cortex_used": plan.get("q_cortex_used"),
            "q_cortex_run_id": plan.get("q_cortex_run_id"),
        },
        "answer_engine": {
            "name": "ATANOR Surface Brain",
            "semantic_plane": "Semantic Cloud Graph",
            "surface_plane": "Surface Cloud Graph",
            "external_llm": False,
            "external_sllm": False,
            "local_brain_write": False,
            "trace_hidden_by_default": True,
            "q_cortex_optional": True,
            "network_barrier": "sealed_for_generation",
        },
        **_flags(),
    }
    return _attach_three_core_trace({"state": "completed", "result": payload, **_flags()}, request=request, three_core_trace=three_core_trace)
