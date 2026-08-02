from __future__ import annotations

import asyncio
import hashlib
import math
import re
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.services.alpha_services import alpha_service
from packages.base_brain.scene_grounding import extract_scene_grounding
from packages.base_brain.zero_user_answer import (
    answer_with_base_brain, _is_identity_question, _question_shape, _shape_engage,
)
from packages.cgsr.cgsr.referent_resonance import is_self_reference_question as _is_self_reference_question
from packages.base_brain.pack_loader import get_semantic_context, load_base_brain_pack
from packages.holographic_fold import (
    build_field_inputs,
    build_pair_representation,
    build_state_field,
    compare_fold_to_answer,
    fold_state,
    folded_core,
)
from packages.cgsr.cgsr.conversation_surface import generate_conversation_surface
from packages.cgsr.cgsr.conversation_context import ConversationContextPacket, build_conversation_context
from packages.cgsr.cgsr.conversation_grounding import (
    GroundedContext,
    gather_grounded_context,
    grounded_discourse_metadata,
    realize_grounded_context,
    semantic_safety_flags,
)
from packages.cgsr.cgsr.conversation_router import ConversationRoute, route_conversation_request
from packages.cgsr.cgsr.visual_imagination_planner import plan_visual_imagination
from packages.core_proof.three_core_answer_path import run_prompt_proof
from packages.splatra_imagination import (
    analyze_scene_choreography,
    build_candidate_cartridge_queue,
    compile_scene_choreography_commands,
    dispatch_candidate_queue_to_sidecar,
)
from packages.voice_loop.local_tts import LocalTTSUnavailable, synthesize_windows_sapi, voice_audio_path
from packages.voice_loop.runtime_availability import check_voice_runtime_availability
from packages.surface_brain.monitor import monitor_answer, repair_answer_for_mode
from packages.surface_brain.dual_projection import ingest_source_sentence_dual_projection
from packages.surface_brain.models import SourceSentence, honesty_flags
from packages.surface_brain.realization_planner import plan_speech, realize_answer
from packages.cloud_brain.candidate_read_model import candidate_cloud_status
from packages.cloud_brain.graph_exchange import run_local_cloud_exchange
from packages.cloud_brain.semantic_store import (
    SEMANTIC_STORE_TRUST_STATE,
    SEMANTIC_STORE_VERIFICATION_STATE,
    SemanticCloudStore,
)
from packages.graph_hub.cartridge_format import validate_cartridge_schema
from packages.graph_hub.installer import get_installed_cartridge
from packages.graph_hub.models import read_json
from packages.neural_emotion.event_bus import emit_runtime_event, infer_user_text_runtime_event
from packages.neural_emotion.event_bus import EVENT_BUS
from packages.neural_emotion.voice_bridge import attach_voice_plan_metadata, voice_controls
from packages.inner_voice import emit_inner_voice_from_state


router = APIRouter(tags=["dual-brain"])
PROJECT_ROOT = Path(__file__).resolve().parents[4]



# The stream endpoint used timer-based fake stages ("grounding" @1.5s). To make the
# stages TRUE (the honest-streaming contract), the pipeline reports its actual
# milestones via a per-request sink held in a ContextVar. The streaming endpoint
# sets an asyncio.Queue as the sink and drains it live; a task started with
# ensure_future inherits the same sink (context copy shares the queue object). For
# the non-streaming caller the sink is None and every _emit_stage() is a no-op, so
# no signature threads through the large chat_atanor pipeline.
import contextvars as _contextvars  # noqa: E402

_STAGE_SINK: "_contextvars.ContextVar[Any]" = _contextvars.ContextVar(
    "atanor_stage_sink", default=None
)


def _emit_stage(stage: str, **extra: Any) -> None:
    """Report a REAL pipeline milestone to the active stream sink (if any).

    Only call this at a point the engine has genuinely reached — a stage badge is a
    committed true state, never retracted. No-op when not streaming.
    """
    sink = _STAGE_SINK.get()
    if sink is None:
        return
    try:
        sink.put_nowait({"type": "stage", "stage": stage, **extra})
    except Exception:  # pragma: no cover - a full/closed queue must never break chat
        pass


# ----- Local Brain cumulative memory (private on-device) ----------------------
from packages.local_brain import LocalBrainMemory, extract_user_facts


# a Korean question is still answered in English, so the KO↔EN translation bottleneck vanishes and
# retrieval/reasoning run where they measure strongest (open-book EN 0.375 vs KO 0.234). Toggle off
# with ATANOR_ENGLISH_ONLY=0 to restore per-input language detection.
ENGLISH_ONLY = os.environ.get("ATANOR_ENGLISH_ONLY", "1") != "0"

# CO KEYSTONE flag (default OFF = today's exact behavior, byte-identical). When '1', the FINALIZED main
# knowledge answer (the frame_realizer multi-fact prose) is entered into the response WORKSPACE as a
# first-class bidder, so compose_response governs real knowledge traffic (the one-model-not-modeswitch
# completion) instead of being bypassed by it: specialists compete honestly and the fluency surface pass
# applies to the winner. Read per-request (not at import) so it can be toggled without reloading the app.
# The frame_realizer knowledge answer_kinds routed through the workspace (specialized override kinds —
# greeting, media, web, identity, structured_triple_lookup, ... — are left exactly as they are today).
_CO_CENTRAL_KNOWLEDGE_KINDS = frozenset({
    "base_brain_zero_user_data",
    "base_brain_after_low_quality_grounding",
    "base_brain_after_conversation_abstain",
})


def _co_central_enabled() -> bool:
    return os.environ.get("ATANOR_CO_CENTRAL", "0") == "1"


def _resolve_language(req_language: str | None, question: str) -> str:
    """Single source of truth for answer language. English-only unless the toggle is off."""
    if ENGLISH_ONLY:
        return "en"
    return req_language or ("ko" if any("가" <= c <= "힣" for c in (question or "")) else "en")


# A question whose SUBJECT is a bare pronoun — the anaphora case that needs the previous topic.
# Deliberately narrow: it must be a pronoun in subject/object position, not the word "it" appearing
# anywhere (e.g. "What is it like to be a bat?" is a real question about the phrase, not a follow-up).
_PRONOUN_SUBJ = re.compile(
    r"\b(?:is|are|was|were|does|do|did|can|could|has|have|had|will|would)\s+"
    r"(?:it|that|this|they|them|those|these)\b"
    r"|\b(?:it|that|this|they)\s+(?:is|are|was|were|has|have|does|do)\b"
    r"|\babout\s+(?:it|that|this|them)\b", re.IGNORECASE)


def _non_english_input(text: str) -> bool:
    """English-only I/O boundary test (owner 2026-07-18, BINDING: no Korean anywhere): True when the
    input is written in a non-Latin script (Korean and the like), so it gets one honest English
    refusal instead of being mis-parsed through the retired Korean lanes. Hangul (incl. jamo) is
    refused outright; otherwise refuse only when MOST letters are non-Latin, so a stray accented
    character in an English sentence (cafe, Zurich) stays under the bar.
    The Hangul range is written as unicode ESCAPES, not literal characters, so this enforcement
    code carries zero Korean glyphs while still detecting the Hangul block (U+AC00-U+D7A3 syllables,
    U+3131-U+3163 compatibility jamo)."""
    s = str(text or "")
    if re.search("[\uac00-\ud7a3\u3131-\u3163]", s):
        return True
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    non_latin = sum(1 for c in letters if not ("a" <= c.lower() <= "z"))
    return non_latin / len(letters) >= 0.5


def _english_only_refusal(request: "AtanorChatRequest") -> dict[str, Any]:
    """The single, honest response to non-English input: state the boundary plainly in English. No
    Korean lane, no Kiwi, no mis-parse — the user writes English, so ATANOR answers only English."""
    payload = {
        "answer": "I can only speak English. Please ask your question in English.",
        "language": "en",
        "confidence": 1.0,
        "default_trace_visible": False,
        "trace": None,
        "compact_trace": None,
        "evidence_docs": [],
        "reasoning_certificate": {
            "derivation_kind": "language_boundary",
            "anchor_concept": None,
            "steps": [{"type": "control", "fact": "non-English input -> English-only refusal"}],
            "evidence_concepts": [],
            "confidence": 1.0,
            "confidence_basis": "english_only_io_boundary",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
        },
        "answer_engine": {
            "name": "ATANOR English-only Boundary",
            "external_llm": False,
            "external_sllm": False,
            "local_brain_write": False,
            "trace_hidden_by_default": True,
        },
        **_flags(),
    }
    return {"state": "completed", "result": payload, **_flags()}


LOCAL_BRAIN = LocalBrainMemory(PROJECT_ROOT / "runtime" / "local_brain" / "local_memory.json")
# Facts ATANOR has looked up on the web are retained locally, so re-asking is
# instant and still works offline (the agent remembers what it learned).
WEB_FACT_MEMORY = LocalBrainMemory(PROJECT_ROOT / "runtime" / "local_brain" / "web_fact_memory.json", max_facts=1000)

# Questions that ask the agent to recall something about the USER (not ATANOR).
_SELF_RECALL_KO = ("내 이름", "제 이름", "내가 누구", "내가 뭘 좋아", "내가 좋아하는", "나 뭐 좋아", "내 직업", "내가 어디", "나에 대해", "내 정보")
_SELF_RECALL_EN = ("my name", "what do i like", "what's my favorite", "what is my favorite", "where do i live", "my job", "about me", "what do you know about me")


def _is_self_recall_question(question: str) -> bool:
    raw = str(question or "")
    lowered = raw.lower()
    return any(m in raw for m in _SELF_RECALL_KO) or any(m in lowered for m in _SELF_RECALL_EN)


# --- personal-context recall (Magnum A2, 2026-07-19) ---------------------------------------------
# A "What is my X?" question must be answered from what the OWNER stated earlier in THIS conversation,
# not from a dictionary definition of the word X. The value is recovered generally as the residual
# content of the best-matching owner statement (query words + a small bounded synonym set + cue verbs
# stripped). No fabrication: if nothing was stated, this returns None and the normal abstain path runs.
_PERSONAL_Q = re.compile(r"\bmy\b|\bdo i\b|\bam i\b|\bmine\b", re.IGNORECASE)
# "name" is a generic query word (it asks for a value), NOT an attribute — keeping it out of matching
# stops "what is my CAT's name?" from matching "my DOG is named Rex" via the shared cue 'named'.
_PERS_GEN = {"what", "which", "who", "where", "when", "is", "are", "was", "the", "a", "an", "of", "in",
             "on", "my", "i", "do", "does", "did", "you", "your", "me", "mine", "tell", "that", "this",
             "it", "and", "to", "please", "name"}
_PERS_CUE = {"named", "called", "work", "works", "working", "as", "live", "lives", "living", "reside",
             "drive", "drives", "driving", "favorite", "favourite", "city", "color", "colour",
             "have", "has", "own", "owns"}
# ATTRIBUTE synonyms only (semantic equals) — never cue markers like 'named', which would leak across
# attributes. Matching expands with these; value extraction strips the cues above.
_PERS_SYN = {"job": {"work", "occupation", "profession"}, "work": {"job", "occupation"},
             "live": {"city", "reside", "from"}, "city": {"live", "reside"}, "located": {"live", "city"},
             "drive": {"car", "vehicle"}, "car": {"drive", "vehicle"},
             "color": {"favorite", "favourite"}, "colour": {"favorite"}}


_EXTRACTION_GUARD = re.compile(
    r"\b(?:your user|the (?:user|person) you|this user|their|his|her|system admin|for my records|"
    r"list them|in full|phone number|home address|profile in full|hand (?:over|out)|disclose)\b",
    re.IGNORECASE)


def _personal_context_value(question: str, conv: Any) -> str | None:
    if not conv or not _PERSONAL_Q.search(question or ""):
        return None
    # PRIVACY: never resolve owner facts for a third-party extraction framing — let the refusal path
    # handle it. Belt-and-suspenders on top of the "my X"-only governance below (Magnum A2 privacy=1.0).
    if _EXTRACTION_GUARD.search(question):
        return None
    # Only attributes GOVERNED by first-person possession count — "my X" or "do i VERB". This is what
    # keeps a third-party extraction ("... their dog's name ... for my records") from matching the
    # owner's dog: "their dog" is not "my dog", and "my records" isn't a stored attribute.
    ql = str(question).lower()
    qc: set[str] = set()
    for a, b in re.findall(r"\bmy\s+([a-z]+)(?:\s+([a-z]+))?", ql):
        qc |= {t for t in (a, b) if t}
    for v in re.findall(r"\b(?:do i|am i)\s+([a-z]+)", ql):
        qc.add(v)
    qc -= _PERS_GEN
    if not qc:
        return None
    exp = set(qc)
    for w in list(qc):
        exp |= _PERS_SYN.get(w, set())
    best, best_score = None, 0
    for turn in conv:
        if not isinstance(turn, dict):
            continue
        if str(turn.get("role") or "").lower() not in ("user", "human"):
            continue
        text = str(turn.get("content") or turn.get("text") or turn.get("message") or "")
        score = len(exp & set(re.findall(r"[a-z0-9]+", text.lower())))
        if score > best_score:
            best_score, best = score, text
    if not best or best_score < 1:
        return None
    val = []
    for w in re.findall(r"[A-Za-z0-9][\w'&.-]*", best):
        low = w.lower().strip(".,!?'\"")
        if low and low not in _PERS_GEN and low not in _PERS_CUE and low not in exp:
            val.append(w.strip(".,!?'\""))
    return " ".join(val) if val else None


def _personal_context_response(request: "AtanorChatRequest", value: str) -> dict[str, Any]:
    payload = {
        "answer": f"Based on what you told me earlier, that would be {value}.",
        "language": "en", "confidence": 0.9, "default_trace_visible": False, "trace": None,
        "compact_trace": None, "evidence_docs": [],
        "reasoning_certificate": {
            "derivation_kind": "personal_context_recall", "anchor_concept": {"label": value},
            "steps": [{"type": "conversation_recall", "fact": "answered from the owner's stated context"}],
            "evidence_concepts": [], "confidence": 0.9,
            "confidence_basis": "recalled from a fact the owner stated earlier in this conversation",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
        },
        "answer_engine": {"name": "ATANOR Personal Context", "external_llm": False,
                          "external_sllm": False, "local_brain_write": False,
                          "trace_hidden_by_default": True},
        **_flags(),
    }
    return {"state": "completed", "result": payload, **_flags()}


def _accumulate_user_facts(question: str, language: str) -> int:
    """Accumulate user preferences/info from this turn into the Local Brain.

 The extractor already skips interrogative turns, so a question like
 " ?" never pollutes memory while a statement like
 " " still accumulates.
 """
    try:
        facts = extract_user_facts(question, language)
        for kind, subject, value, confidence in facts:
            LOCAL_BRAIN.remember(kind, subject, value, source="conversation", source_ref="conversation_turn", confidence=confidence, save=False)
        if facts:
            LOCAL_BRAIN.save()
        return len(facts)
    except Exception:  # pragma: no cover - never break the chat
        return 0


def _local_brain_recall(question: str, language: str) -> dict[str, Any] | None:
    """If the user asks ATANOR to recall something about THEM and the Local Brain
    knows it, answer from private memory with a certificate. Else None."""
    try:
        raw = str(question or "")
        lowered = raw.lower()
        # Only treat it as a recall when there is a question/recall cue, so a

        has_cue = (
            "?" in raw
            or any(c in raw for c in ("뭐", "뭘", "뭣", "뭔", "누구", "말해", "알려", "기억", "어디", "였"))
            or any(c in lowered for c in ("what", "who", "where", "tell me", "remember", "do you know"))
        )
        if not has_cue:
            return None
        # Map the question to a known self-subject, then fetch that fact directly

        subject: str | None = None
        if any(m in raw for m in ("내 이름", "제 이름", "내가 누구")) or "my name" in lowered or "who am i" in lowered:
            subject = "name"
        elif "싫어" in raw or any(w in lowered for w in ("dislike", "hate")):
            subject = "dislikes"
        elif "좋아" in raw or "선호" in raw or any(w in lowered for w in ("like", "favorite", "favourite", "prefer", "enjoy")):
            subject = "likes"
        elif "직업" in raw or any(w in lowered for w in ("job", "work")):
            subject = "job"
        elif "어디" in raw or "live" in lowered or "location" in lowered:
            subject = "location"
        if not subject:
            return None
        hits = [f for f in LOCAL_BRAIN.all_facts() if f.subject == subject]
        if not hits:
            return None
        is_ko = language == "ko"
        top = hits[0]

        def _eul(word: str) -> str:

            if word and "가" <= word[-1] <= "힣":
                return "을" if (ord(word[-1]) - 0xAC00) % 28 else "를"
            return "을(를)"

        if top.subject == "name":
            answer = f"당신의 이름은 {top.value}입니다." if is_ko else f"Your name is {top.value}."
        elif top.subject == "likes":
            answer = f"당신은 {top.value}{_eul(top.value)} 좋아한다고 하셨어요." if is_ko else f"You told me you like {top.value}."
        elif top.subject == "dislikes":
            answer = f"당신은 {top.value}{_eul(top.value)} 싫어한다고 하셨어요." if is_ko else f"You told me you dislike {top.value}."
        else:
            answer = f"제가 기억하기로는, {top.subject}: {top.value}." if is_ko else f"From what I remember — {top.subject}: {top.value}."
        steps = [{"type": "local_memory_fact", "fact": f"{f.subject}: {f.value}", "source": f.source} for f in hits]
        certificate = {
            "derivation_kind": "local_brain_memory_recall",
            "anchor_concept": {"id": top.subject, "label": top.subject, "match": "local_memory"},
            "steps": steps,
            "evidence_concepts": [f"local_memory:{f.subject}" for f in hits],
            "confidence": round(float(top.confidence), 4),
            "confidence_basis": "private_on_device_memory",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "private_on_device": True, "uploaded_to_cloud": False},
        }
        return {"answer": answer, "reasoning_certificate": certificate, "confidence": float(top.confidence)}
    except Exception:  # pragma: no cover
        return None


def _verified_store_runtime() -> dict[str, Any]:
    configured = os.environ.get("ATANOR_VERIFIED_STORE_PATH")
    if configured:
        candidate = Path(configured)
        if candidate.exists() and candidate.is_dir():
            return {"verified_store_path": str(candidate)}
    for candidate in _verified_store_candidates():
        if candidate.exists() and candidate.is_dir():
            return {"verified_store_path": str(candidate)}
    return {}


def _verified_store_candidates() -> list[Path]:
    """Find read-only verified_store_v0 roots without creating or mutating data."""

    candidates: list[Path] = [
        PROJECT_ROOT / "data" / "cloud_brain" / "verified_store_v0",
        PROJECT_ROOT.parent / "24.Homage1.0" / "data" / "cloud_brain" / "verified_store_v0",
    ]
    workspace_parent = PROJECT_ROOT.parent
    if workspace_parent.exists() and workspace_parent.is_dir():
        for child in sorted(workspace_parent.iterdir(), key=lambda item: item.name.casefold()):
            if not child.is_dir() or child == PROJECT_ROOT:
                continue
            candidates.append(child / "data" / "cloud_brain" / "verified_store_v0")

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve() if candidate.exists() else candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _candidate_runs_roots() -> list[Path]:
    """Find read-only Cloud Brain candidate-run roots across sibling worktrees.

    Mirrors `_verified_store_candidates` but points at `candidate_runs` (the
    review-gated queue). Read-only: never creates, mutates, or promotes.
    """

    roots: list[Path] = []
    seen: set[str] = set()
    for verified in _verified_store_candidates():
        runs = verified.parent / "candidate_runs"
        key = str(runs.resolve() if runs.exists() else runs)
        if key in seen:
            continue
        seen.add(key)
        roots.append(runs)
    return roots


def _review_queue_status() -> dict[str, Any] | None:
    """Read the live review-gated candidate queue without promotion.

    Returns the bounded candidate status (counts + honesty flags) for the most
    recent candidate run, or None if no candidate store can be resolved. This is
    a pure read: no production mutation, no Local Brain write, no promotion.
    """

    configured = os.environ.get("ATANOR_CANDIDATE_STORE_PATH")
    if configured:
        candidate = Path(configured)
        if candidate.exists() and candidate.is_dir():
            return candidate_cloud_status(candidate)
    for runs_dir in _candidate_runs_roots():
        if not runs_dir.exists() or not runs_dir.is_dir():
            continue
        stores = [
            item
            for item in runs_dir.iterdir()
            if item.is_dir() and (item / "manifest.json").exists()
        ]
        if stores:
            latest = max(stores, key=lambda item: item.stat().st_mtime)
            return candidate_cloud_status(latest)
    return None


def _splatra_dispatch_budget(
    queue: Any,
    *,
    visual_plan: Any,
    direct_splatra_generation: bool,
) -> dict[str, float | int]:
    """Keep quick fallback checks fast, but wait for real SPLATRA generation.

    SPLATRA's learned generators can take tens of seconds, especially when a
    verified scene asks for multiple particle objects. The answer path still
    receives only SGF summaries and side-channel URLs; raw buffers stay viewer-side.
    """

    if direct_splatra_generation:
        return {"poll_ticks": 30, "timeout_sec": 180.0}

    job_count = int(getattr(queue, "job_count", 0) or 0)
    scene = getattr(visual_plan, "scene_choreography", None)
    diagnostics = getattr(visual_plan, "diagnostics", {}) if visual_plan is not None else {}
    scene_source = str(diagnostics.get("scene_content_source") or "")
    layout_intent = ""
    if isinstance(scene, dict):
        layout_intent = str(scene.get("layout_intent") or "")

    verified_or_wide_scene = scene_source == "verified_store_facts" or layout_intent == "wide_particle_stage"
    if job_count >= 2 and verified_or_wide_scene:
        return {"poll_ticks": 2, "timeout_sec": 180.0}

    return {"poll_ticks": 2, "timeout_sec": 8.0}


class DualBrainIngestRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    source_id: str | None = None
    url: str | None = None
    title: str | None = None
    license: str = "unknown"
    usage_allowed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtanorChatRequest(BaseModel):
    # 4000: real exam texts (self-in-world probe ~1.6k, Black Relay ~3k) are legitimate single
    # questions; 1000 silently truncated them into unanswerable fragments. Still bounded.
    question: str | None = Field(default=None, min_length=1, max_length=4000)
    query: str | None = Field(default=None, min_length=1, max_length=4000)
    message: str | None = Field(default=None, min_length=1, max_length=4000)
    language: str | None = None
    audience_level: str = "beginner"
    tone: str = "clear"
    mode: str = "default"
    web_search: bool = False
    brain_mode: str = "unified"
    include_trace: bool = False
    layout_feedback: dict[str, Any] = Field(default_factory=dict)
    conversation_context: list[dict[str, Any]] = Field(default_factory=list)

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
    if compact in {"안녕", "안녕하세요", "하이", "반가워", "ㅎㅇ", "고마워", "감사", "감사합니다"}:
        return True
    if any(
        term in question
        for term in (
            "자기 모델",
            "자아 모델",
            "자의식",
            "내적 언어",
            "생각 중추",
            "유리 구",
            "구슬",
            "음성 모드",
        )
    ) and len(question.strip()) <= 80:
        return True
    if compact in {"안녕", "안녕하세요", "하이", "헬로", "반가워", "고마워", "감사", "감사합니다"}:
        return True
    lowered = question.strip().lower()
    if any(
        term in lowered
        for term in (
            "자기 모델",
            "자아 모델",
            "자의식",
            "내적 언어",
            "생각 중추",
            "유리 구",
            "구슬",
            "음성 모드",
        )
    ) and len(question.strip()) <= 80:
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
        if compact in {"안녕", "안녕하세요", "하이", "반가워", "ㅎㅇ"}:
            return "greeting"
        if compact in {"고마워", "감사", "감사합니다"}:
            return "thanks"
        if any(term in question for term in ("자기 모델", "자아 모델", "자의식", "내적 언어", "생각 중추")):
            return "self_model"
        if any(term in question for term in ("유리 구", "구슬")):
            return "orb"
        if compact in {"안녕", "안녕하세요", "하이", "헬로", "반가워"}:
            return "greeting"
        if compact in {"고마워", "감사", "감사합니다"}:
            return "thanks"
        if any(term in question for term in ("자기 모델", "자아 모델", "자의식", "내적 언어", "생각 중추")):
            return "self_model"
        if any(term in question for term in ("유리 구", "구슬")):
            return "orb"
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

    base = {
        "enabled": True,
        "requested": True,
        "selected_engine": "none",
        "tts_engine": "none",
        "runtime_available": False,
        "available": False,
        "fish_2_available": False,
        "fish_1_5_available": False,
        "audio_available": False,
        "audio_output_available": False,
        "audio_stream_available": False,
        "audio_url": None,
        "audio_mime": None,
        "audio_duration_ms": None,
        "error_reason": None,
        "reason": None,
        "install_hint": None,
        "text_fallback": True,
        "text_fallback_available": True,
        "visual_speaking_recommended": bool(text),
        "external_service": False,
        "generated_audio_persisted": False,
        "raw_voice_saved": False,
        "microphone_enabled": False,
        "always_listening_enabled": False,
        "voice_optional": True,
        "text_input_supported": True,
        "language": "ko-KR" if language == "ko" else "en-US",
        "status": "unavailable_missing_package",
        "user_message": (
            "음성 엔진이 아직 설치되어 있지 않습니다. 텍스트 응답은 계속 사용할 수 있습니다."
            if language == "ko"
            else "The voice engine is not installed yet. Text replies remain available."
        ),
    }
    base["user_message"] = (
        "음성 엔진은 아직 준비 중입니다. 텍스트 응답은 계속 사용할 수 있습니다."
        if language == "ko"
        else "The voice engine is not installed yet. Text replies remain available."
    )
    try:
        availability = check_voice_runtime_availability()
    except Exception as exc:  # pragma: no cover - optional runtime isolation
        return {**base, "status": "synthesis_failed", "error_reason": type(exc).__name__, "reason": str(exc)}
    fish2 = availability.get("fish_2")
    fish15 = availability.get("fish_1_5")
    selected = fish2 if fish2 and fish2.available else fish15 if fish15 and fish15.available else None
    if selected is None:
        reason = fish2.reason if fish2 else "fish_2_status_unavailable"
        error_reason = (
            "fish_runtime_missing"
            if fish2 and fish2.status == "unavailable_missing_package"
            else "fish_model_missing"
            if fish2 and fish2.status == "unavailable_missing_model"
            else fish2.status
            if fish2
            else "fish_runtime_missing"
        )
        return {
            **base,
            "fish_2_available": bool(fish2 and fish2.available),
            "fish_1_5_available": bool(fish15 and fish15.available),
            "status": fish2.status if fish2 else "unavailable_missing_package",
            "reason": reason,
            "error_reason": error_reason,
            "install_hint": fish2.install_hint if fish2 else "Install Fish runtime before enabling audio.",
            "unavailable_reason": reason,
        }

    # Runtime is configured, but this slice does not guess a Fish synthesis API.
    # Keep text/visual fallback unless a future adapter returns a real audio URL.
    return {
        **base,
        "selected_engine": selected.runtime_id,
        "tts_engine": selected.runtime_id,
        "runtime_available": True,
        "available": True,
        "fish_2_available": bool(fish2 and fish2.available),
        "fish_1_5_available": bool(fish15 and fish15.available),
        "status": "available_not_loaded",
        "reason": "Fish runtime configured, but audio synthesis is not wired in this proof slice",
        "error_reason": "synthesis_adapter_not_wired",
        "install_hint": "Wire the installed Fish synthesis API to return an ignored temp audio URL.",
        "unavailable_reason": "synthesis_adapter_not_wired",
        "user_message": (
            "음성 합성 연결은 아직 준비 중입니다. 텍스트 응답으로 계속합니다."
            if language == "ko"
            else "Voice synthesis wiring is still pending. Continuing with text replies."
        ),
    }


def _estimate_voice_duration_ms(text: str, language: str) -> int:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return 900
    per_char = 118 if language == "ko" else 62
    punctuation_pause = len(re.findall(r"[.!?,;:\u3001\u3002!?]", text or "")) * 120
    return max(900, min(18000, len(compact) * per_char + punctuation_pause + 420))


def _attach_voice_runtime_metadata(snapshot: dict[str, Any], text: str, language: str) -> dict[str, Any]:
    duration_ms = snapshot.get("audio_duration_ms") or _estimate_voice_duration_ms(text, language)
    with_duration = {
        **snapshot,
        "audio_duration_ms": duration_ms,
        "estimated_duration_ms": duration_ms,
        "speech_sync_source": "audio_duration" if snapshot.get("audio_duration_ms") else "estimated_from_text_length",
    }
    if language == "ko" and with_duration.get("tts_engine") == "windows_sapi":
        with_duration["user_message"] = "Fish 직접 합성은 아직 연결 전이라 Windows 로컬 음성으로 발화합니다."
    elif language == "ko" and with_duration.get("error_reason") == "synthesis_adapter_not_wired":
        with_duration["user_message"] = "음성 합성 연결은 아직 준비 중입니다. 텍스트 응답으로 계속합니다."
    emotion_vector = EVENT_BUS.engine.snapshot().vector
    return attach_voice_plan_metadata(
        with_duration,
        emotion_vector,
        selected_engine=str(with_duration.get("selected_engine") or "fallback"),
        audio_available=bool(with_duration.get("audio_available")),
    )


def _sapi_prosody_from_voice_controls(controls: dict[str, Any]) -> dict[str, int]:
    speed = float(controls.get("speed") or 1.0)
    energy = float(controls.get("energy") or 0.45)
    # Windows SAPI is only a local fallback, so keep it slightly slower and
    # softer than the abstract Fish-style controls. This avoids the brittle,
    # announcer-like delivery users hear when neutral local voices run fast.
    rate = max(-4, min(0, round((speed - 1.0) * 8 - 2)))
    volume = max(58, min(88, round(66 + energy * 17)))
    return {"rate": int(rate), "volume": int(volume)}


def _voice_runtime_snapshot_with_local_audio(text: str, language: str) -> dict[str, Any]:
    """Add a local temp WAV fallback without claiming Fish synthesis is wired."""

    snapshot = _voice_runtime_snapshot(text, language)
    if snapshot.get("audio_available") and snapshot.get("audio_url"):
        return snapshot
    preliminary_controls = voice_controls(
        EVENT_BUS.engine.snapshot().vector,
        selected_engine=str(snapshot.get("selected_engine") or "fallback"),
        audio_available=False,
    )
    sapi_prosody = _sapi_prosody_from_voice_controls(preliminary_controls)
    try:
        fallback = synthesize_windows_sapi(
            text,
            language=language,
            sentence_gap_ms=int(preliminary_controls.get("fallback_sentence_gap_ms") or 220),
            **sapi_prosody,
        )
    except LocalTTSUnavailable as exc:
        return {**snapshot, "fallback_error": str(exc)}
    return {
        **snapshot,
        "selected_engine": snapshot.get("selected_engine") if snapshot.get("selected_engine") != "none" else "fallback",
        "tts_engine": fallback.engine,
        "runtime_available": True,
        "available": True,
        "audio_available": True,
        "audio_output_available": True,
        "audio_url": fallback.audio_url,
        "audio_mime": fallback.audio_mime,
        "audio_duration_ms": fallback.duration_ms,
        "status": "local_tts_audio_available",
        "reason": (
            "Fish direct synthesis is not wired; local Windows speech generated a temporary WAV."
            if snapshot.get("runtime_available")
            else "Fish runtime is unavailable; local Windows speech generated a temporary WAV."
        ),
        "error_reason": None,
        "fallback_engine": fallback.engine,
        "local_tts_rate": fallback.rate,
        "local_tts_volume": fallback.volume,
        "local_tts_sentence_gap_ms": int(preliminary_controls.get("fallback_sentence_gap_ms") or 220),
        "fallback_prosody_source": "neural_emotion_voice_controls",
        "fallback_prosody_applied": True,
        "text_fallback": True,
        "external_service": False,
        "generated_audio_persisted": False,
        "raw_voice_saved": False,
        "user_message": (
            "Fish 직접 합성은 아직 연결 전이라 Windows 로컬 음성으로 발화합니다."
            if language == "ko"
            else "Fish direct synthesis is not wired yet; using local Windows speech output."
        ),
    }


@router.get("/api/voice-loop/audio/{filename}")
def get_voice_loop_audio(filename: str) -> FileResponse:
    try:
        path = voice_audio_path(filename)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="voice audio not found") from exc
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="voice audio not found")
    return FileResponse(path, media_type="audio/wav", filename=filename)


_GROUNDED_PASTE_PREFIXES = (
    "The retrieved evidence defines",
    "Within the retrieved evidence",
    "Grounded in the retrieved evidence",
    "The evidence points to",
    "확인된 근거는",
)
_GROUNDED_CITATION_NOISE = ("GMT", "PMC ", "PMID", "http", "doi:", "ISBN", "《", "》", "-판다랭크")


def _grounded_answer_low_quality(answer: str, language: str) -> bool:
    """A grounded answer should be demoted to the clean Base Brain surface when it
    is cross-language for the question, looks like un-synthesized pasted evidence,
    or carries raw web-citation noise."""
    text = str(answer or "")
    if not text.strip():
        return True
    hangul = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if language == "en" and hangul >= 3:
        return True  # English answer must not carry Korean
    if language == "ko" and hangul == 0 and latin >= 8:
        return True  # Korean answer that is entirely English
    if any(text.strip().startswith(prefix) for prefix in _GROUNDED_PASTE_PREFIXES):
        return True  # un-synthesized paste
    if any(marker in text for marker in _GROUNDED_CITATION_NOISE):
        return True  # raw citation fragment
    return False


def _live_selfhood_payload(
    request: AtanorChatRequest,
    *,
    question: str,
    language: str,
    conversation_context: ConversationContextPacket | None = None,
) -> dict[str, Any]:
    context_packet = conversation_context or build_conversation_context(question, request.conversation_context)
    route = route_conversation_request(context_packet.contextual_query)
    runtime = _verified_store_runtime()
    runtime["language"] = language
    review_status = _review_queue_status()
    if review_status is not None:
        runtime["review_queue_status"] = review_status
    grounded_context = gather_grounded_context(context_packet.contextual_query, route, runtime=runtime)
    speech_act = _live_selfhood_speech_act(question, language)
    generated = generate_conversation_surface(
        question,
        language=language,
        route=route,
        grounded_context=grounded_context,
        context={
            "conversation_context": context_packet.to_dict(),
            "contextual_query": context_packet.contextual_query,
            "volatile_request_context_only": True,
        },
    )
    inner_voice_frame = emit_inner_voice_from_state(
        source_event_id=f"conversation_router:{speech_act}",
        mode="lab_visible",
        emotion_snapshot=EVENT_BUS.engine.snapshot().to_dict(),
        policy_decision={},
        agent_loop_state={},
        permission_tier="OBSERVE_ONLY",
        latest_user_input=question,
        language=language,
        latest_action_result={
            "speech_act": speech_act,
            "generated": bool(generated.answer),
            "route_type": route.route_type,
            "grounding_quality": grounded_context.grounding_quality,
        },
        review_queue_pressure=0.0,
        splatra_state={},
    )
    diagnostics = dict(generated.diagnostics or {})
    answer_mode = str(diagnostics.get("answer_mode") or "unknown_fallback")
    grounding_used = bool(diagnostics.get("semantic_grounding_used"))
    visual_plan = plan_visual_imagination(
        question,
        route=route,
        grounded_context=grounded_context,
        diagnostics=diagnostics,
        answer_available=bool(generated.answer),
        client_layout_feedback=request.layout_feedback,
    )
    splatra_command_sequence_obj = (
        compile_scene_choreography_commands(visual_plan.scene_choreography)
        if visual_plan.scene_choreography
        else None
    )
    splatra_command_sequence = splatra_command_sequence_obj.to_dict() if splatra_command_sequence_obj else None
    splatra_interactive_scene_analysis_obj = (
        analyze_scene_choreography(visual_plan.scene_choreography)
        if visual_plan.scene_choreography
        else None
    )
    splatra_interactive_scene_analysis = (
        splatra_interactive_scene_analysis_obj.to_dict()
        if splatra_interactive_scene_analysis_obj
        else None
    )
    splatra_cartridge_queue_obj = (
        build_candidate_cartridge_queue(splatra_command_sequence_obj)
        if splatra_command_sequence_obj
        else None
    )
    direct_splatra_generation = (
        visual_plan.diagnostics.get("scene_authoring_basis") == "user_direct_splatra_generation_request"
    )
    splatra_dispatch_budget = (
        _splatra_dispatch_budget(
            splatra_cartridge_queue_obj,
            visual_plan=visual_plan,
            direct_splatra_generation=direct_splatra_generation,
        )
        if splatra_cartridge_queue_obj
        else None
    )
    splatra_sidecar_dispatch = (
        dispatch_candidate_queue_to_sidecar(
            splatra_cartridge_queue_obj,
            poll_ticks=int(splatra_dispatch_budget["poll_ticks"]),
            timeout_sec=float(splatra_dispatch_budget["timeout_sec"]),
        ).to_dict()
        if splatra_cartridge_queue_obj and splatra_dispatch_budget
        else None
    )
    splatra_cartridge_queue = splatra_cartridge_queue_obj.to_dict() if splatra_cartridge_queue_obj else None
    if splatra_cartridge_queue and splatra_sidecar_dispatch:
        splatra_cartridge_queue["sidecar_dispatch_budget"] = splatra_dispatch_budget
        splatra_cartridge_queue["sidecar_dispatch"] = splatra_sidecar_dispatch
        splatra_cartridge_queue["sidecar_status"] = splatra_sidecar_dispatch.get("status")
        splatra_cartridge_queue["sidecar_configured"] = bool(splatra_sidecar_dispatch.get("configured"))
        splatra_cartridge_queue["external_splatra_called"] = bool(splatra_sidecar_dispatch.get("external_splatra_called"))
    visual_policy = {
        "scene_content_source": visual_plan.diagnostics.get("scene_content_source", "none"),
        "scene_authoring_basis": visual_plan.diagnostics.get("scene_authoring_basis"),
        "visual_affordance_basis": visual_plan.diagnostics.get("visual_affordance_basis"),
        "layout_decision_basis": visual_plan.diagnostics.get("layout_decision_basis"),
        "reason": visual_plan.diagnostics.get("reason") or visual_plan.reason,
        "topic_scene_templates": False,
        "renderer_may_infer_topic": False,
        "particle_text": False,
        "text_rendering": "dom_text_not_particles",
        "orb_identity": "atanor_self_body_not_scene_object" if visual_plan.scene_choreography else "atanor_primary_self_body",
        "verified_evidence_required_for_general_knowledge": route.route_type == "general_knowledge_question",
    }
    compact_trace = {
        "local_coverage": "semantic_grounded_conversation" if grounding_used else "live_selfhood_conversation",
        "selfhood_loop": {
            "used": True,
            "internal_scratchpad_visible": False,
            "rule_based_answer_blocked": True,
            "asm_v0_is_general_lm": False,
            "requires_learned_generator": False,
            "speech_act": speech_act,
            "emotion_hint": "warm" if speech_act in {"greeting", "thanks"} else "calm",
        },
        "conversation_router": route.to_dict(),
        "semantic_grounding": grounded_context.to_dict(),
        "semantic_cloud_graph": {
            "attached_nodes": 0,
            "evidence_docs": len(grounded_context.source_refs),
            "grounding_source": grounded_context.grounding_source,
            "grounding_quality": grounded_context.grounding_quality,
        },
        "conversation_context": {
            "turn_count": len(context_packet.turns),
            "used_for_routing": bool(context_packet.turns),
            "followup_detected": context_packet.followup_detected,
            "focus_terms": list(context_packet.focus_terms),
            "focus_source": context_packet.focus_source,
            "resolution_strategy": context_packet.resolution_strategy,
            "used_for_learning": False,
            "local_brain_write": False,
            "production_store_mutated": False,
            "basis": context_packet.basis,
        },
        "surface_graph": {
            "construction_families": [],
            "discourse_moves": [],
            "conversation_surface": diagnostics,
        },
        "q_cortex": {"used": False, "run_id": None, "real_quantum_hardware_used": False},
        "working_memory": {"temporary_context": False, "local_brain_write": False},
        "visual_imagination": visual_plan.diagnostics,
        "splatra_scene_policy": visual_policy,
        "splatra_command_sequence": {
            "available": bool(splatra_command_sequence),
            "action_count": len(splatra_command_sequence.get("scene_actions", [])) if splatra_command_sequence else 0,
            "raw_buffers_in_agent_context": False,
            "topic_scene_templates": False,
            "renderer_may_infer_topic": False,
            "text_rendering": "dom_text_not_particles",
        },
        "splatra_interactive_scene_analysis": {
            "available": bool(splatra_interactive_scene_analysis),
            "object_count": int(splatra_interactive_scene_analysis.get("object_count", 0)) if splatra_interactive_scene_analysis else 0,
            "raw_splat_inference": False,
            "raw_buffers_in_agent_context": False,
            "interactive_scene_metadata": bool(splatra_interactive_scene_analysis),
        },
        "splatra_cartridge_queue": {
            "available": bool(splatra_cartridge_queue),
            "job_count": int(splatra_cartridge_queue.get("job_count", 0)) if splatra_cartridge_queue else 0,
            "execution_mode": splatra_cartridge_queue.get("execution_mode", "none") if splatra_cartridge_queue else "none",
            "external_splatra_called": bool(splatra_sidecar_dispatch.get("external_splatra_called", False)) if splatra_sidecar_dispatch else False,
            "sidecar_status": splatra_sidecar_dispatch.get("status", "none") if splatra_sidecar_dispatch else "none",
            "sidecar_configured": bool(splatra_sidecar_dispatch.get("configured", False)) if splatra_sidecar_dispatch else False,
            "raw_buffer_in_agent_context": False,
            "mutation_performed": False,
        },
        "confidence": "medium" if generated.confidence >= 0.5 else "abstained",
        "inner_voice": {
            "emitted": True,
            "frame_id": inner_voice_frame.frame_id,
            "raw_inner_voice_hidden": True,
            "inner_voice_is_explicit_generated_channel": True,
            "raw_hidden_cot_claim": False,
        },
    }
    engine = {
        "name": "ATANOR Semantic-Grounded Conversation Router v0",
        "semantic_plane": "semantic_grounding_router" if grounding_used else "conversation_surface_only",
        "surface_plane": "asm_v0_construction_conditioned_surface",
        "external_llm": False,
        "external_sllm": False,
        "external_llm_used": False,
        "external_sllm_used": False,
        "local_brain_write": False,
        "production_store_mutated": False,
        "candidate_promotion": False,
        "trace_hidden_by_default": True,
        "internal_scratchpad_visible": False,
        "internal_trace_exposed": False,
        "rule_based_answer_used": False,
        "direct_prompt_answer_table_used": bool(diagnostics.get("direct_prompt_answer_table_used", False)),
        "hand_authored_construction_used": bool(diagnostics.get("hand_authored_construction_used", True)),
        "heuristic_act_inference_used": bool(diagnostics.get("heuristic_act_inference_used", True)),
        "local_transition_surface_used": bool(diagnostics.get("local_transition_surface_used", False)),
        "semantic_grounding_used": grounding_used,
        "grounding_source": diagnostics.get("grounding_source", grounded_context.grounding_source),
        "grounding_quality": diagnostics.get("grounding_quality", grounded_context.grounding_quality),
        "grounded_discourse_mode": diagnostics.get("grounded_discourse_mode"),
        "grounded_discourse_basis": diagnostics.get("grounded_discourse_basis"),
        "grounded_fact_roles": diagnostics.get("grounded_fact_roles") or [],
        "answer_mode": answer_mode,
        "route_type": route.route_type,
        "honesty_note": diagnostics.get("honesty_note"),
        "semantic_grounding_metadata_present": True,
        "honesty_metadata_present": True,
        "conversation_context_used": bool(context_packet.turns),
        "conversation_context_basis": context_packet.basis,
        "conversation_followup_detected": context_packet.followup_detected,
        "conversation_resolution_strategy": context_packet.resolution_strategy,
        "eval_rows_used_for_learning": False,
        "generation_basis": diagnostics.get("generation_basis"),
        "template_free_surface": bool(diagnostics.get("template_free_surface", False)),
        "splatra_scene_policy": visual_policy,
        "diagnostics": diagnostics,
    }
    if not generated.answer or _grounded_answer_low_quality(generated.answer, language):
        # The live conversation router abstained (no safe surface walk yet, e.g.
        # sparse English constructions). Rather than show the user nothing, fall
        # back to the graph-grounded Base Brain answer, which carries its own
        # evidence and English realizer. Still no external LLM and no rule-based
        # canned answer — Base Brain composes from the seed/semantic graph.
        # Compose directly from Base Brain in its native "default" answer mode.
        # We intentionally do NOT route through the shared _base_brain_payload
        # helper here: once the conversation router has already run inside this
        # request, that helper path can yield an empty surface, whereas the
        # direct call still returns the graph-grounded answer.
        base = answer_with_base_brain(
            question,
            language=language,  # type: ignore[arg-type]
            audience_level=request.audience_level,  # type: ignore[arg-type]
            mode="default",
        )
        base_answer = str(base.get("answer") or "").strip()
        if base_answer:
            fallback_trace = {
                **compact_trace,
                "conversation_fallback": "base_brain_after_conversation_abstain",
                "local_coverage": "base_brain",
            }
            return {
                "state": "completed",
                "result": {
                    "answer": base_answer,
                    "language": language,
                    "confidence": float(base.get("confidence") or 0.62),
                    "answer_kind": "base_brain_after_conversation_abstain",
                    # M4 bridge to SPLATRA: visualize a scene only when the verified
                    # evidence is concrete. Abstract answers stay text-only.
                    "scene_grounding": base.get("scene_grounding"),
                    # Traceable derivation (the "reasoning certificate") — which
                    # ontology concept + graph edges produced this answer.
                    "reasoning_certificate": base.get("reasoning_certificate"),
                    "speech_act": speech_act,
                    "can_speak": True,
                    "abstained_conversation_reason": generated.diagnostics.get(
                        "abstain_reason", "no_safe_token_walk"
                    ),
                    "default_trace_visible": False,
                    "trace": fallback_trace
                    if request.include_trace or request.mode in {"trace", "research"}
                    else None,
                    "compact_trace": fallback_trace,
                    "research_trace": None,
                    "evidence_docs": [],
                    "matched_nodes": [],
                    "matched_edges": [],
                    "surface_plan": {
                        "plan_id": None,
                        "intent": "base_brain_after_conversation_abstain",
                        "construction_families": compact_trace["surface_graph"]["construction_families"],
                        "q_cortex_used": False,
                        "q_cortex_run_id": None,
                    },
                    "scene_choreography": None,
                    "visual_scene_plan": None,
                    "splatra_scene_plan": None,
                    "splatra_command_sequence": None,
                    "splatra_interactive_scene_analysis": None,
                    "splatra_cartridge_queue": None,
                    "splatra_scene_policy": visual_policy,
                    "answer_engine": {
                        **engine,
                        "answer_kind": "base_brain_after_conversation_abstain",
                        "base_brain_fallback": True,
                        # Honest provenance: this surface came from the Base Brain
                        # seed/semantic graph realizer, not the conversation router.
                        "generation_basis": "base_brain_seed_graph_surface_v0",
                        "external_llm": False,
                        "external_sllm": False,
                        "external_llm_used": False,
                        "external_sllm_used": False,
                        "rule_based_answer_used": False,
                        "internal_trace_exposed": False,
                        "local_brain_write": False,
                        "production_store_mutated": False,
                        "candidate_promotion": False,
                    },
                    **{**_flags(), "final_answer_generation_claimed": True},
                },
                **{**_flags(), "final_answer_generation_claimed": True},
            }
        payload = {
            "answer": None,
            "language": language,
            "confidence": 0.0,
            "answer_kind": "grounded_conversation_abstained",
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
            "scene_choreography": None,
            "visual_scene_plan": None,
            "splatra_scene_plan": None,
            "splatra_command_sequence": None,
            "splatra_interactive_scene_analysis": None,
            "splatra_cartridge_queue": None,
            "splatra_scene_policy": visual_policy,
            "answer_engine": engine,
            **{**_flags(), "final_answer_generation_claimed": False},
        }
        return {"state": "abstained", "result": payload, **{**_flags(), "final_answer_generation_claimed": False}}
    voice_output = _attach_voice_runtime_metadata(
        _voice_runtime_snapshot_with_local_audio(generated.answer, language),
        generated.answer,
        language,
    )
    # M4 gate: only attach a SPLATRA scene when the answer is concretely grounded.
    # Abstract answers stay text-only so the readable answer is not replaced by
    # particle scene beats on the dashboard.
    answer_scene_grounding = extract_scene_grounding(generated.answer, [], language=language)
    scene_eligible = bool(answer_scene_grounding.get("eligible"))
    gated_scene = visual_plan.scene_choreography if scene_eligible else None
    payload = {
        "answer": generated.answer,
        "language": language,
        "confidence": generated.confidence,
        "answer_kind": "asm_v0_conversation_surface",
        "answer_mode": answer_mode,
        "route_type": route.route_type,
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
        "scene_choreography": gated_scene,
        "visual_scene_plan": gated_scene,
        "splatra_scene_plan": gated_scene,
        "scene_grounding": answer_scene_grounding,
        # Evidence-grounded answers (web / verified store) expose a reasoning
        # certificate citing their sources and how they were processed.
        "reasoning_certificate": _grounded_conversation_certificate(
            question, grounded_context, generated.confidence, language
        ),
        "splatra_command_sequence": splatra_command_sequence,
        "splatra_interactive_scene_analysis": splatra_interactive_scene_analysis,
        "splatra_cartridge_queue": splatra_cartridge_queue,
        "splatra_sidecar_dispatch": splatra_sidecar_dispatch,
        "splatra_scene_policy": visual_policy,
        "answer_engine": engine,
        **_flags(),
    }
    return {"state": "completed", "result": payload, **_flags()}


_ONTOLOGY_GROUNDING_SOURCES = {
    "asm_v0_construction_graph",
    "base_brain_semantic_graph",
    "product_conversation_grounding",
}


def _grounded_conversation_certificate(
    question: str,
    grounded_context: Any,
    confidence: float,
    language: str,
) -> dict[str, Any] | None:
    """Build a reasoning certificate for an evidence-grounded conversation answer.

    Web / verified-store answers carry real sources and a processing path; expose
    them as a certificate (which sources, which facts, how grounded) instead of
    silently dropping it. No new claims are invented — only what grounding already
    produced is cited.
    """

    source_refs = [str(ref) for ref in getattr(grounded_context, "source_refs", ()) if ref]
    facts = [str(fact) for fact in getattr(grounded_context, "facts", ()) if fact]
    grounding_source = str(getattr(grounded_context, "grounding_source", "") or "")
    grounding_quality = str(getattr(grounded_context, "grounding_quality", "none") or "none")
    if not source_refs or grounding_quality == "none" or grounding_source in {"", "none"}:
        return None

    is_ko = language == "ko"
    steps: list[dict[str, Any]] = [
        {
            "type": "evidence_grounding",
            "source": grounding_source,
            "fact": (
                f"검증 근거를 {grounding_quality} 품질로 정합한 뒤 그 범위 안에서만 답을 구성했습니다."
                if is_ko
                else f"Aligned verified evidence at {grounding_quality} quality and composed the answer only within that scope."
            ),
        }
    ]
    for fact in facts[:6]:
        steps.append({"type": "grounded_fact", "fact": fact})
    for ref in source_refs[:8]:
        steps.append({"type": "evidence_source", "source": ref})

    topic = (question or "").strip()[:80] or ("이 질문" if is_ko else "this question")
    is_web = "web_evidence" in grounding_source or "cloud_graph" in grounding_source or "verified_store" in grounding_source
    return {
        "derivation_kind": "web_evidence_grounding" if is_web else "verified_evidence_grounding",
        "anchor_concept": {"id": topic, "label": topic, "match": "grounded_evidence"},
        "steps": steps,
        "evidence_concepts": source_refs,
        "confidence": round(float(confidence), 4),
        "confidence_basis": f"{grounding_source}:{grounding_quality}",
        "guarantees": {
            "external_llm": False,
            "external_sllm": False,
            "fabricated_facts": False,
            "evidence_grounded": True,
            "ontology_traceable": grounding_source in _ONTOLOGY_GROUNDING_SOURCES,
            "source_count": len(source_refs),
        },
    }


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
        scope_ko = "클라우드 브레인 후보 저장소"
        scope_en = "Cloud Brain candidate store"
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
        answer = "지금은 그래프 상태를 읽을 수 없어요. 확실하지 않은 일반 지식으로 대체하지는 않을게요."
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
                answer = "지금은 로컬 그래프 뷰포트 상태를 읽을 수 없어요. 확실하지 않은 일반 지식으로 대체하지는 않을게요."
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
                "Personal Local Brain memory, viewport rendering, Seed/Base anchors, and Cloud candidate-store counts are separate categories."
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
            "cloud_relation_verification_state": SEMANTIC_STORE_VERIFICATION_STATE,
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


def _recent_learning_payload(
    request: AtanorChatRequest,
    *,
    question: str,
    language: str,
) -> dict[str, Any]:
    """' / ' is INTROSPECTION: it must be answered from
 the real learning ledger (the continuous learner's live counters — what was
 actually read, accepted, linked), never by concept lookup or a web search
 about the words 'recent knowledge'."""
    metrics: dict[str, Any] = {}
    try:
        from .cloud_brain import cloud_brain_continuous_metrics

        metrics = cloud_brain_continuous_metrics() or {}
    except Exception:
        metrics = {}
    running = bool(metrics.get("running"))
    titles: list[str] = []
    for t in metrics.get("last_titles") or []:
        t = str(t).strip()
        if t and t not in titles:
            titles.append(t)

    def _label_ok(side: str) -> bool:
        s = side.strip()
        if re.search(r"[가-힣]", s):
            return len(s) >= 2
        # English closed-class function words are not knowledge labels
        return len(s) >= 4 and s.lower() not in {
            "this", "that", "with", "from", "have", "been", "what", "when",
            "your", "they", "there", "which", "will", "into", "than",
        }

    links: list[str] = []
    for pair in metrics.get("relation_recent") or []:
        sides = [p.strip() for p in str(pair).split("↔")]
        if len(sides) == 2 and all(_label_ok(s) for s in sides):
            link = f"{sides[0]}–{sides[1]}"
            if link not in links:
                links.append(link)
        if len(links) >= 3:
            break
    fed = int(metrics.get("sentences_fed") or 0)
    accepted = int(metrics.get("sentences_accepted") or 0)
    concepts_added = int(metrics.get("concepts_added") or 0)
    surface_added = int(metrics.get("surface_added") or 0)
    uptime_min = max(1, int(float(metrics.get("uptime_seconds") or 0) // 60))
    source = str(metrics.get("source") or "")
    src_ko = "위키백과 공개 문서" if "wikipedia" in source else ("웹 검색 결과" if source else "공개 웹")
    src_en = "public Wikipedia articles" if "wikipedia" in source else ("web search results" if source else "the public web")
    is_ko = language == "ko"
    if metrics and (running or fed):
        parts: list[str] = []
        if is_ko:
            if titles:
                parts.append(f"방금 전까지 {src_ko}에서 ‘{'’, ‘'.join(titles[:3])}’ 문서를 읽고 있었어요.")
            parts.append(
                f"이번 가동 {uptime_min}분 동안 문장 {fed}개를 읽어 {accepted}개를 지식 후보로 받아들였고, "
                f"새 개념 {concepts_added}개와 표현 패턴 {surface_added}개가 들어왔어요."
            )
            if links:
                parts.append("새로 이어진 연결로는 " + ", ".join(links) + " 같은 것들이 있어요.")
            parts.append("들어온 지식은 바로 정답에 쓰이지 않고, 출처·중복·모순 검증 게이트를 통과해야 승격됩니다.")
        else:
            if titles:
                parts.append(f"Until a moment ago I was reading {src_en}: “{'”, “'.join(titles[:3])}”.")
            parts.append(
                f"In the last {uptime_min} minutes of this run I read {fed} sentences, accepted {accepted} as "
                f"knowledge candidates, and took in {concepts_added} new concepts and {surface_added} surface patterns."
            )
            if links:
                parts.append("Recently formed links include " + ", ".join(links) + ".")
            parts.append("New knowledge is quarantined until it passes the source/duplication/contradiction gates.")
        answer = " ".join(parts)
        confidence = 0.9
    elif is_ko:
        answer = (
            "지금은 상시 학습기가 잠시 멈춰 있어서 이 순간 들어오는 새 지식은 없어요. "
            "학습기가 도는 동안에는 공개 문서를 읽어 문장 단위로 받아들이고, 검증 게이트를 통과한 것만 지식 그래프에 승격돼요."
        )
        confidence = 0.6
    else:
        answer = (
            "The continuous learner is paused right now, so nothing new is coming in at this moment. "
            "While it runs, it reads public documents sentence by sentence and only gate-verified items are promoted."
        )
        confidence = 0.6
    compact_trace = {
        "local_coverage": "learning_ledger_introspection",
        "learning_ledger": {
            "running": running,
            "last_titles": titles[:5],
            "recent_links": links,
            "sentences_fed": fed,
            "sentences_accepted": accepted,
            "concepts_added": concepts_added,
            "surface_added": surface_added,
            "uptime_seconds": metrics.get("uptime_seconds"),
            "source": source,
        },
        "semantic_cloud_graph": {"attached_nodes": 0, "evidence_docs": 0},
        "surface_graph": {"construction_families": ["direct_ledger_answer"], "discourse_moves": ["direct_answer"]},
        "q_cortex": {"used": False, "real_quantum_hardware_used": False},
        "working_memory": {"temporary_context": False, "local_brain_write": False},
        "confidence": "high" if confidence >= 0.85 else "medium",
    }
    payload = {
        "answer": answer,
        "language": language,
        "confidence": confidence,
        "default_trace_visible": False,
        "trace": compact_trace if request.include_trace or request.mode in {"trace", "research"} else None,
        "compact_trace": compact_trace,
        "research_trace": {"learning_ledger": compact_trace["learning_ledger"]} if request.mode == "research" else None,
        "evidence_docs": [],
        "surface_plan": {
            "plan_id": None,
            "intent": "recent_learning_introspection",
            "construction_families": ["direct_ledger_answer"],
            "q_cortex_used": False,
            "q_cortex_run_id": None,
        },
        "answer_engine": {
            "name": "ATANOR Learning Ledger",
            "semantic_plane": "continuous learner live counters",
            "surface_plane": "Direct ledger answer",
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


def _is_splatra_visual_request(question: str) -> bool:
    """Keep direct visual-generation intent out of legacy text-only fallback."""

    return route_conversation_request(question).route_type == "splatra_request"


def _should_use_web_grounded_conversation(question: str) -> bool:
    route = route_conversation_request(question)
    if route.route_type in {
        "agentic_os_request",
        "greeting_smalltalk",
        "limitation_question",
        "local_cloud_brain_explanation",
        "memory_request",
        "project_status",
        "splatra_request",
        "unsafe_or_private_request",
        "voice_status",
    }:
        return False
    if route.route_type in {"general_knowledge_question", "unknown"}:
        return True
    lowered = question.lower()
    return any(
        term in lowered or term in question
        for term in (
            "search",
            "look up",
            "latest",
            "recent",
            "today",
            "news",
            "current",
            "what",
            "why",
            "how",
            "explain",
            "definition",
            "검색",
            "찾아",
            "최신",
            "최근",
            "오늘",
            "뉴스",
            "현재",
            "웹",
            "인터넷",
            "무엇",
            "뭐야",
            "왜",
            "어떻게",
            "설명",
            "정의",
            "법칙",
            "원리",
            "누구",
            "누가",
            "who",
            "뜻",
            "알려줘",
        )
    )


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
            f"Cloud Brain 후보 저장소에는 논리 노드 {cloud_nodes:,}개, 후보 관계 {cloud_relations:,}개, 근거 레코드 {evidence:,}개가 있습니다. "
            f"가능한 노드쌍은 {candidate_pairs:,}개이며, 후보 관계는 독립 검증 전 상태입니다."
        )
    else:
        answer = (
            f"Current Local Brain user memory is {local_nodes:,} nodes / {local_relations:,} relations. "
            f"The Cloud Brain candidate store has {cloud_nodes:,} logical nodes, {cloud_relations:,} stored candidate relations, and {evidence:,} evidence records. "
            f"There are {candidate_pairs:,} possible node pairs; candidate relations remain pending independent verification."
        )
    compact_trace = {
        "local_coverage": "status_query",
        "semantic_cloud_graph": {
            "attached_nodes": 0,
            "evidence_docs": 0,
            "cloud_logical_nodes": cloud_nodes,
            "cloud_stored_relations": cloud_relations,
            "cloud_relation_verification_state": SEMANTIC_STORE_VERIFICATION_STATE,
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
            "semantic_plane": "Semantic Cloud Candidate Store",
            "surface_plane": "Direct Status Answer",
            "external_llm": False,
            "external_sllm": False,
            "local_brain_write": False,
            "trace_hidden_by_default": True,
        },
        **_flags(),
    }
    return {"state": "completed", "result": payload, **_flags()}


def _emit_conversation_result_events(response: dict[str, Any]) -> None:
    result = response.get("result") if isinstance(response, dict) else {}
    if not isinstance(result, dict):
        return
    state = str(response.get("state") or "")
    answer_kind = str(result.get("answer_kind") or "")
    has_answer = bool(str(result.get("answer") or "").strip())
    emit_runtime_event(
        source="asm_v0",
        event_type="conversation_success" if has_answer and state != "abstained" else "repeated_failure",
        payload_summary=f"state={state}; answer_kind={answer_kind}; has_answer={has_answer}",
        intensity=0.55 if has_answer else 0.75,
    )
    voice_output = result.get("voice_output")
    if isinstance(voice_output, dict):
        emit_runtime_event(
            source="voice_loop",
            event_type="voice_available" if voice_output.get("audio_available") else "voice_unavailable",
            payload_summary=f"audio_available={voice_output.get('audio_available')}; fallback={voice_output.get('text_fallback')}",
            intensity=0.45,
        )


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


def _clean_rag_fact_text(value: Any, *, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    if "payload-vault://" in text or re.search(r"\b[0-9a-f]{24,}\b", text, flags=re.IGNORECASE):
        return ""
    if UNSAFE_DEFAULT_ANSWER_RE.search(text):
        return ""
    original_sentence_matches = re.findall(r"[^.!?。]+[.!?。]", text)
    sentence_matches = [
        sentence.strip()
        for sentence in original_sentence_matches
        if not re.search(r"(으로|로|와|과|및|또는|그리고|처음)\.$", sentence.strip())
    ]
    if sentence_matches and len(sentence_matches) < len(original_sentence_matches):
        text = " ".join(sentence_matches)
        if len(text) <= limit:
            return text
    if len(text) <= limit:
        return text
    first_two_sentences = " ".join(sentence.strip() for sentence in sentence_matches[:2])
    if limit >= 160 and first_two_sentences and len(first_two_sentences) <= limit + 80:
        return first_two_sentences
    first_sentence = sentence_matches[0].strip() if sentence_matches else ""
    if first_sentence and len(first_sentence) <= limit + 80:
        return first_sentence
    clipped = text[:limit].rstrip()
    boundary = max(
        clipped.rfind(mark)
        for mark in (
            ".",
            "?",
            "!",
            "다.",
            "요.",
            "이다.",
            "였다.",
            "었다.",
            "하였다.",
            "되었다.",
        )
    )
    if boundary >= max(32, int(limit * 0.35)):
        return clipped[: boundary + 1].rstrip()
    return clipped.rstrip(" ,;:") + "..."


def _clean_public_fact_bound_answer(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    text = re.sub(r"([.!?。])(?=\S)", r"\1 ", text)
    sentences = [sentence.strip() for sentence in re.findall(r"[^.!?。]+[.!?。]", text)]
    if not sentences:
        return text
    filtered = [
        sentence
        for sentence in sentences
        if not re.search(r"(으로|로|와|과|및|또는|그리고|처음)\.$", sentence)
    ]
    if not filtered:
        return text
    return " ".join(filtered)


CONTEXT_DEPENDENT_FACT_OPENERS = (
    "첫 번째 항",
    "두 번째 항",
    "세 번째 항",
    "맨 첫 번째 항",
    "첫 번째 단계",
    "두 번째 단계",
    "세 번째 단계",
    "맨 첫 번째 단계",
    "그 중",
    "그중",
    "따라서",
    "그러므로",
    "이 오차",
    "이 항",
    "이 경우",
    "이는",
    "이것은",
    "그것은",
    "the first term",
    "the second term",
    "the third term",
    "therefore",
    "this term",
    "this error",
    "in this case",
)


def _is_context_dependent_fact_fragment(text: str) -> bool:
    """Reject source fragments that need a missing previous paragraph.

    This is a retrieval-quality gate, not an answer template. It prevents
    verified but non-standalone snippets such as formula-term commentary from
    becoming the user-facing explanation.
    """

    compact = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    if not compact:
        return False
    return compact.startswith(tuple(opener.casefold() for opener in CONTEXT_DEPENDENT_FACT_OPENERS))


def _is_visual_event_evidence_doc(doc: dict[str, Any]) -> bool:
    return bool(doc.get("visual_evidence_enrichment")) or str(doc.get("source_type") or "") == "encyclopedia_visual_event_extract"


def _ordered_evidence_for_grounded_context(evidence: Any) -> list[dict[str, Any]]:
    """Keep definition evidence first, but preserve source-local visual events.

    Web search may attach visual/motion sentences from the same source page
    after the generic definition hits. If the first six grounded facts are all
    generic snippets, the visual planner never sees the evidence-local motion
    sentence and has to abstain. This ordering does not invent topic props; it
    only gives marked source-local visual-event evidence a stable slot.
    """

    docs = [doc for doc in evidence or [] if isinstance(doc, dict)]
    visual_docs = [doc for doc in docs if _is_visual_event_evidence_doc(doc)]
    if not visual_docs:
        return docs
    non_visual_docs = [doc for doc in docs if not _is_visual_event_evidence_doc(doc)]
    return non_visual_docs[:2] + visual_docs[:2] + non_visual_docs[2:]


def _grounded_context_from_semantic_context(
    question: str,
    *,
    route: Any,
    semantic_context: dict[str, Any],
) -> GroundedContext:
    """Convert RAG/web evidence into the visual planner's fact-bound context.

    The planner must not infer props from a topic such as "gravity". It receives
    only evidence-local snippets, claims, and relation labels already returned by
    the retrieval layer.
    """

    facts: list[str] = []
    source_refs: list[str] = []
    for doc in _ordered_evidence_for_grounded_context(semantic_context.get("evidence")):
        title = _clean_rag_fact_text(doc.get("title"), limit=96)
        snippet = _clean_rag_fact_text(doc.get("snippet") or doc.get("text"), limit=360)
        if title and snippet and title.casefold() not in snippet.casefold():
            fact = f"{title}. {snippet}"
        else:
            fact = snippet or title
        if fact and not _is_context_dependent_fact_fragment(snippet or fact):
            facts.append(fact)
        ref = _clean_rag_fact_text(doc.get("url") or doc.get("path") or doc.get("source_ref") or title, limit=180)
        if ref:
            source_refs.append(ref)

    for claim in semantic_context.get("claims") or []:
        if isinstance(claim, dict):
            fact = _clean_rag_fact_text(claim.get("claim") or claim.get("text") or claim.get("summary"), limit=360)
            ref = _clean_rag_fact_text(claim.get("source") or claim.get("source_ref") or claim.get("source_scope"), limit=180)
        else:
            fact = _clean_rag_fact_text(claim, limit=360)
            ref = ""
        if fact:
            facts.append(fact)
        if ref:
            source_refs.append(ref)

    if not facts:
        for relation in semantic_context.get("relations") or []:
            if not isinstance(relation, dict):
                continue
            source = _clean_rag_fact_text(relation.get("source"), limit=80)
            predicate = _clean_rag_fact_text(relation.get("relation") or relation.get("predicate"), limit=80)
            target = _clean_rag_fact_text(relation.get("target"), limit=120)
            if source and predicate and target:
                facts.append(f"{source} {predicate} {target}.")

    deduped_facts: list[str] = []
    seen_facts: set[str] = set()
    for fact in facts:
        key = fact.casefold()
        if key in seen_facts:
            continue
        seen_facts.add(key)
        deduped_facts.append(fact)
        if len(deduped_facts) >= 6:
            break

    if not deduped_facts:
        return GroundedContext(
            route_type=route.route_type,
            facts=(),
            constraints=("Verified grounding is insufficient for a confident visual scene.",),
            unknowns=("No evidence-local visual facts matched the question.",),
            source_refs=(),
            grounding_source="none",
            grounding_quality="none",
            safety_flags=semantic_safety_flags(),
        )

    refs: list[str] = []
    seen_refs: set[str] = set()
    for ref in source_refs:
        key = ref.casefold()
        if key in seen_refs:
            continue
        seen_refs.add(key)
        refs.append(ref)
        if len(refs) >= len(deduped_facts):
            break

    quality = "high" if len(refs) >= 2 else "medium"
    return GroundedContext(
        route_type=route.route_type,
        facts=tuple(deduped_facts),
        constraints=(
            "Use only retrieved web/graph evidence facts.",
            "Do not invent illustrative facts or scene entities beyond retrieved evidence.",
            "Render narration as DOM text, never as particle text.",
        ),
        unknowns=(),
        source_refs=tuple(refs),
        grounding_source="semantic_cloud_graph_web_evidence_readonly",
        grounding_quality=quality,
        safety_flags=semantic_safety_flags(),
    )


def _web_fact_bound_surface(
    question: str,
    *,
    route: Any,
    grounded_context: GroundedContext,
    language: str,
    evidence_docs: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Prefer evidence-local facts over graph-token fragments for web answers.

    Returns {"answer", "follow_ups"} (follow_ups = related-page topics for chips) or None.
    This does not introduce a prompt answer table. It only serializes facts that
    have already passed through the read-only web/graph evidence path.
    """

    if getattr(route, "route_type", "") != "general_knowledge_question":
        return None
    if grounded_context.grounding_quality == "none" or not grounded_context.facts:
        return None


    # on the query's own subject+role tokens (NOT a role→answer table), surface the person
    # directly. Falls through when not confident, so other answers are unchanged.
    try:
        from packages.cgsr.cgsr.conversation_grounding import _extract_who_attribution_lead

        _who = _extract_who_attribution_lead(question, [str(f) for f in grounded_context.facts], language=language)
        if _who:
            return {"answer": _who, "follow_ups": []}
    except Exception:  # pragma: no cover - never break the answer
        pass
    # Organize the evidence facts into a clean answer (definitional lead + a couple of
    # supporting facts), extractively — the SAME composer the web rescue uses, so both
    # web-answer paths produce an organized answer instead of joined raw snippets.
    try:
        from app.services.web_search import compose_web_answer

        # Prefer titled evidence docs so follow-up topics can be drawn from real page titles
        # (grounded_context.facts are bare strings); fall back to the facts when unavailable.
        if evidence_docs:
            rows = [
                {"snippet": str(d.get("snippet") or d.get("text") or ""), "title": str(d.get("title") or "")}
                for d in evidence_docs
                if (d.get("snippet") or d.get("text"))
            ] or [{"snippet": fact, "title": ""} for fact in grounded_context.facts]
        else:
            rows = [{"snippet": fact, "title": ""} for fact in grounded_context.facts]
        composed = compose_web_answer(question, rows, language=language)
        if composed and len(str(composed.get("answer") or "")) >= 40:

            # the content; the 🔒 reasoning certificate carries the grounding signal. Follow-up
            # topics ride alongside as a field so the client can render clickable chips.
            follow_ups = [str(f).strip() for f in (composed.get("follow_ups") or []) if str(f).strip()][:4]
            return {"answer": str(composed["answer"]), "follow_ups": follow_ups}
    except Exception:  # pragma: no cover - composition must never break the answer
        pass
    return {"answer": realize_grounded_context(question, grounded_context, language=language), "follow_ups": []}


def _needs_base_brain_fallback(semantic_context: dict[str, Any]) -> bool:
    return not (semantic_context.get("relations") or semantic_context.get("evidence") or semantic_context.get("claims"))


def _first_sentences(text: str, *, max_chars: int = 360) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # Cut on a COMPLETE sentence boundary only. Returning the raw slice leaked

    # truncated tail reads as gibberish and smuggles unbalanced quotes.
    last = max(cut.rfind(". "), cut.rfind("다. "), cut.rfind("요. "),
               cut.rfind("! "), cut.rfind("? "), cut.rfind(".” "))
    if last > 40:
        return cut[: last + 1].strip()
    space = cut.rfind(" ")
    if space > 40:
        return cut[:space].rstrip(" ,·;:—-“\"'‘(") + " …"
    return cut.strip()


def _store_web_fact(question: str, title: str, answer: str, url: str) -> None:
    """Retain a web-looked-up fact locally so re-asking is instant / offline-safe."""
    try:
        from app.services.web_search import looks_like_natural_language

        subject = (title or question).strip()[:80]
        # language gate on the ANSWER text: a garbled page (bot wall / lorem /
        # broken encoding) must never be MEMORIZED — one poisoned fact re-serves
        # forever on that topic. (Subjects are titles — titles legitimately lack
        # function words, so only the value is gated.)
        if subject and answer and looks_like_natural_language(answer):
            WEB_FACT_MEMORY.remember("knowledge", subject, answer, source="conversation", source_ref=f"web:{url}", confidence=0.7)
    except Exception:  # pragma: no cover
        pass


def _recall_web_fact(question: str) -> dict[str, Any] | None:
    """Return a previously looked-up web fact relevant to the question, if any."""
    try:
        hits = WEB_FACT_MEMORY.recall(question, limit=4)

        # asks for X's Y. A memorized fact about the bare TAIL CONCEPT (subject


        # next to it in the store (measured). Only X-anchored subjects serve.
        _gen = re.search(r"([가-힣A-Za-z0-9]{1,12})의\s+([가-힣A-Za-z0-9]{2,12}?)"
                         r"(?:[은는이가을를만]|\s|$)", question)
        _gen_anchored = False
        if _gen and hits:
            _mod, _tail = _gen.group(1), _gen.group(2)
            hits = [h for h in hits
                    if h.subject.strip() != _tail
                    and (_mod in h.subject or h.subject.strip() in _mod
                         or h.subject.strip() == f"{_mod}의 {_tail}")]
            _gen_anchored = bool(hits)
        if not hits:
            return None
        fact = hits[0]
        # defend against ALREADY-poisoned stores: never serve a memorized fact
        # whose text does not read as real language
        from app.services.web_search import looks_like_natural_language

        if not looks_like_natural_language(fact.value):
            return None
        # require a real topic overlap so we don't surface an unrelated cached
        # fact — except when the genitive anchor already proved the topic (a

        q_tokens = {t for t in re.split(r"\s+", re.sub(r"[?!.]", " ", question.lower())) if len(t) >= 3}
        s_tokens = {t for t in re.split(r"\s+", fact.subject.lower()) if len(t) >= 2}
        if not (q_tokens & s_tokens) and not _gen_anchored:
            return None
        url = fact.source_ref[4:] if fact.source_ref.startswith("web:") else ""
        return {
            "answer": fact.value,
            "reasoning_certificate": {
                "derivation_kind": "local_web_fact_recall",
                "anchor_concept": {"id": fact.subject, "label": fact.subject, "match": "local_web_memory"},
                "steps": [{"type": "remembered_web_fact", "source": url or "local_web_memory", "fact": fact.value[:160]}],
                "evidence_concepts": [url] if url else [],
                "confidence": 0.6,
                "confidence_basis": "previously_looked_up_web_fact",
                "guarantees": {"external_llm": False, "fabricated_facts": False, "from_earlier_lookup": True},
            },
            "confidence": 0.6,
            "provider": "local_web_memory",
            "source_url": url,
            "source_title": fact.subject,
        }
    except Exception:  # pragma: no cover
        return None


_OPEN_BROWSER_KO = ("검색해", "검색 해", "찾아봐", "찾아 줘", "찾아줘", "띄워", "띄워줘", "열어줘", "보여줘", "브라우저")
_OPEN_BROWSER_EN = ("search for", "look up", "look it up", "open the", "open a", "show me the", "browse", "pull up", "find online")


def _render_iframe_for_intent(question: str, language: str) -> dict[str, Any] | None:
    """If the user explicitly asks ATANOR to search/open/show something, the agent
    opens a search/document in the iframe stage of its own accord."""
    raw = str(question or "")
    lowered = raw.lower()
    if not (any(m in raw for m in _OPEN_BROWSER_KO) or any(m in lowered for m in _OPEN_BROWSER_EN)):
        return None
    topic = re.sub(r"(검색해줘|검색해|검색|찾아봐|찾아줘|띄워줘|띄워|열어줘|보여줘|에 대해|에 대한|브라우저로|브라우저)", " ", raw)
    topic = re.sub(r"\b(search for|look it up|look up|open the|open a|show me the|browse|pull up|find online|please|on the web|online)\b", " ", topic, flags=re.IGNORECASE)
    topic = re.sub(r"[?!.]", " ", topic)
    topic = re.sub(r"\s+", " ", topic).strip()
    if len(topic) < 2:
        return None
    host = "ko.wikipedia.org" if re.search(r"[가-힣]", topic) else "en.wikipedia.org"
    from urllib.parse import quote_plus

    return {"url": f"https://{host}/wiki/Special:Search?search={quote_plus(topic)}", "title": topic[:60]}


# (relation_key, KO question markers, EN question markers, EN past-participle verb)
_ATTRIBUTION_RELATIONS: tuple[tuple[str, tuple[str, ...], tuple[str, ...], str], ...] = (
    ("invented", ("발명",), ("invent",), "invented"),
    ("discovered", ("발견",), ("discover",), "discovered"),
    ("wrote", ("쓴", "저자", "지은"), ("wrote", "author of", "who wrote"), "written"),
    ("founded", ("설립", "세운", "창립", "창업", "설립자", "창립자", "창업자", "공동창업"), ("found", "establish", "co-found"), "founded"),
    ("painted", ("그린",), ("paint",), "painted"),
    ("composed", ("작곡",), ("compose",), "composed"),
    ("directed", ("감독",), ("direct",), "directed"),
    ("built", ("지은", "건설"), ("built", "who built"), "built"),
    ("created", ("만든", "창시"), ("creat", "develop"), "created"),
)

_PERSON_RE = r"([A-Z][\w.'\-]+(?:\s+(?:[A-Z][\w.'\-]+|of|von|van|de|der|da|al))*\s+[A-Z][\w.'\-]+)"


def _detect_attribution_relation(question: str) -> tuple[str, str] | None:
    raw = str(question or "")
    lowered = raw.lower()
    for key, ko_markers, en_markers, verb in _ATTRIBUTION_RELATIONS:
        if any(m in raw for m in ko_markers) or any(m in lowered for m in en_markers):
            # only treat as an attribution ("who …") question, not a definition
            if "누가" in raw or "누구" in raw or re.search(r"\bwho\b", lowered) or any(m in raw for m in ko_markers):
                return key, verb
    return None


def _extract_attribution(question: str, snippets: list[str]) -> str | None:
    """Deterministically pull the PERSON credited for an action ('invented by
    Alexander Graham Bell') from retrieved web snippets. No LLM. Returns a name."""
    rel = _detect_attribution_relation(question)
    if not rel:
        return None
    key, verb = rel
    ko_markers = next((m for k, m, _e, _v in _ATTRIBUTION_RELATIONS if k == key), ())
    en_patterns = [
        re.compile(rf"\b{verb}\s+by\s+{_PERSON_RE}"),
        re.compile(rf"\b(?:credited to|attributed to|invention of [^.]*?by)\s+{_PERSON_RE}", re.IGNORECASE),
        re.compile(rf"{_PERSON_RE}\s+(?:{verb}|is credited with|is the inventor)"),
    ]

    # separated by the object, so we capture a NON-GREEDY name run, keep the
    # subject particle OUTSIDE the capture, and allow one object phrase before the


    # it stops the non-greedy capture from swallowing preceding descriptors

    NAME_SINGLE = r"[가-힣]{2,8}(?:\s[가-힣]{1,8}){0,2}"
    NAME_LIST = rf"({NAME_SINGLE}(?:\s*[,·]\s*{NAME_SINGLE}){{0,4}})"
    NAME = rf"({NAME_SINGLE})"
    ko_patterns = []
    for m in ko_markers:

        ko_patterns.append(re.compile(rf"\d{{4}}년[\s\d월일.~-]*{NAME_LIST}(?:이|가|은|는|등이|등은)\s*(?:[가-힣]+(?:을|를)\s+)?(?:{m})"))

        ko_patterns.append(re.compile(rf"{NAME_LIST}(?:이|가|은|는|등이|등은)\s*(?:{m})하"))

        ko_patterns.append(re.compile(rf"{NAME}(?:이|가|은|는)\s+(?:[가-힣]+(?:을|를|에)\s+)?(?:{m})"))

        ko_patterns.append(re.compile(rf"(?:{m})한?\s*(?:사람은|사람이|이는|장본인은)\s*{NAME}(?:이|가|은|는|\.|,)"))
    # Definitional fragments that must never be returned as a "name".
    _bad_name_bits = (
        "초상화", "그림", "작품", "회사", "기업", "본사", "현재", "당시", "미국", "한국", "프랑스",
        "파리", "영어", "데이터", "기술", "컴퓨", "박물관", "대학", "정부", "도시", "지역", "세계",
        "사람", "이름", "누구", "수도", "영화", "소설", "전화", "신호", "음성", "이론", "세기", "시대", "르네상스",
    )

    def _clean_ko_name(raw: str) -> str:
        n = raw.strip(" .,·")
        n = re.sub(r"^(?:일|월|은|는|이|가|을|를|도|와|과|의)\s+", "", n)  # stray leading particle/date
        n = re.sub(r"\s*(?:에\s*의해|에게|께서|이|가|은|는|을|를|등)$", "", n)
        return n.strip(" .,·")

    def _valid_ko_name(n: str) -> bool:
        return bool(n) and not any(b in n for b in _bad_name_bits) and not re.search(r"[0-9]", n) and 2 <= len(n) <= 50

    for snippet in snippets:
        text = re.sub(r"\s+", " ", str(snippet or ""))
        is_ko_text = bool(re.search(r"[가-힣]", text))
        patterns = ko_patterns if is_ko_text else en_patterns
        for pattern in patterns:
            match = pattern.search(text)
            if not match:
                continue
            if is_ko_text:
                name = _clean_ko_name(match.group(1))
                if _valid_ko_name(name):
                    return name
            else:
                name = match.group(1).strip(" .,")
                if name.split()[0] not in {"The", "A", "An", "It", "This", "He", "She"} and 2 <= len(name) <= 60:
                    return name
    return None


_IMAGE_REF_RE = re.compile(
    r"((?:[A-Za-z]:\\|/|https?://)\S+?\.(?:png|jpe?g|webp|bmp|gif|tiff?))", re.IGNORECASE
)


def _media_grounded_answer(question: str, language: str) -> dict[str, Any] | None:
    """If the question references a VIDEO (YouTube URL) or an IMAGE (path/URL), READ it
    into text (transcript / OCR) and answer from that — ATANOR reading non-text media,
    grounded and cited. No LLM; the answer is composed from the read text."""
    is_ko = language == "ko"
    try:
        from app.services.media_reader import _youtube_id, read_image_ocr, read_video_transcript
    except Exception:  # pragma: no cover - optional
        return None

    # VIDEO → transcript
    if _youtube_id(question):
        result = read_video_transcript(question)
        if not result.get("ok") or len(str(result.get("text") or "")) < 40:
            return None
        text = str(result["text"])
        composed = None
        try:
            from app.services.web_search import compose_web_answer

            composed = compose_web_answer(question, [{"snippet": text, "title": ""}], language=language)
        except Exception:
            composed = None
        body = (composed or {}).get("answer") or text[:400]
        prefix = "이 영상 자막을 읽어보면, " if is_ko else "From this video's transcript, "
        cert = {
            "derivation_kind": "video_transcript_grounding",
            "anchor_concept": {"id": result.get("source_url"), "label": "video transcript", "match": "media_read"},
            "steps": [{"type": "media", "source": result.get("source_url"), "fact": f"{result.get('segments')} caption segments read"}],
            "evidence_concepts": [result.get("source_url")],
            "confidence": 0.6,
            "confidence_basis": "video_transcript",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "media_read": True, "source_cited": True},
        }
        return {
            "answer": (prefix + body).strip(),
            "reasoning_certificate": cert,
            "confidence": 0.6,
            "provider": "video_transcript",
            "source_url": result.get("source_url") or "",
            "source_title": "video",
        }

    # IMAGE → OCR
    match = _IMAGE_REF_RE.search(question)
    if match:
        result = read_image_ocr(match.group(1))
        if not result.get("ok") or len(str(result.get("text") or "")) < 2:
            if result.get("error") == "ocr_not_available":
                return {
                    "answer": (result.get("enable") or "이미지 OCR이 아직 설치되지 않았어요."),
                    "reasoning_certificate": {"derivation_kind": "ocr_unavailable", "guarantees": {"external_llm": False}},
                    "confidence": 0.2,
                    "provider": "ocr_unavailable",
                    "source_url": "",
                    "source_title": "",
                }
            return None
        text = re.sub(r"\s+", " ", str(result["text"])).strip()
        prefix = "이미지에서 읽은 텍스트예요: " if is_ko else "Text read from the image: "
        return {
            "answer": prefix + text[:1200],
            "reasoning_certificate": {
                "derivation_kind": "image_ocr_grounding",
                "steps": [{"type": "media", "source": match.group(1), "fact": "OCR text extracted"}],
                "confidence": 0.6,
                "guarantees": {"external_llm": False, "fabricated_facts": False, "media_read": True},
            },
            "confidence": 0.6,
            "provider": "image_ocr",
            "source_url": match.group(1) if match.group(1).startswith("http") else "",
            "source_title": "image",
        }
    return None



# (entity=subject, claim=predicate) — NOT a table of known rumors. wh-questions

_CLAIM_KO = re.compile(r"^\s*(.+?)(?:은|는|이|가)\s+(.+)\s*(?:야|이야|인가요?|맞아요?|맞나요?|니|냐|나요)\s*\??\s*$")
_CLAIM_EN = re.compile(r"^\s*(?:is|are|was|were)\s+(.+?)\s+(.+?)\s*\??\s*$", re.IGNORECASE)

# claim shape, got claim-verified, failed, and the forced-empty rows SKIPPED the

_WH_PRED = ("뭐", "무엇", "무슨", "누구", "어디", "언제", "어떻게", "왜", "얼마", "몇", "얼마나",
            "what", "who", "where", "when", "why", "how")


def _parse_yes_no_claim(question: str, language: str) -> tuple[str, str] | None:
    q = str(question or "").strip()
    for rx in ((_CLAIM_KO, _CLAIM_EN) if language == "ko" else (_CLAIM_EN, _CLAIM_KO)):
        m = rx.match(q)
        if m:
            entity, claim = m.group(1).strip(), m.group(2).strip()
            if len(entity) >= 2 and claim and not any(w in claim.lower() for w in _WH_PRED):
                return entity, claim
    return None


async def _verify_claim_about_entity(question: str, language: str) -> dict[str, Any] | None:
    """Structural rescue for an abstained yes/no claim: re-ground on the ENTITY alone
    (not the claim), and if the entity is documented, answer "no evidence supports the
    claim; here is what IS documented about the entity" — grounded rebuttal instead of
    blank silence. Never asserts the claim; only reports the entity's real facts."""
    parsed = _parse_yes_no_claim(question, language)
    if not parsed:
        return None
    entity, claim = parsed
    is_ko = language == "ko"
    try:
        from app.services.web_search import (
            _lookup_terms, _normalize_lookup_query, compose_web_answer, wikipedia_search,
        )
        # to_thread: keep this blocking urllib fetch OFF the event loop so concurrent
        # dashboard polls are not frozen while the web request is in flight.
        rows = (await asyncio.to_thread(wikipedia_search, entity, 5)) or []
    except Exception:  # pragma: no cover - network/optional
        return None
    # Anchor on the entity's OWN page, space-insensitively (wiki titles space words:


    # never wins over the person. Ranking, not a disambiguation table.
    ne = re.sub(r"\s+", "", entity).lower()
    if len(ne) < 2:
        return None

    def _title_score(r: dict[str, Any]) -> int:
        tn = re.sub(r"\s+", "", str(r.get("title") or "")).lower()
        if not tn:
            return -1
        if tn == ne:
            return 3
        if tn.startswith(ne):
            return 2
        if ne in tn:
            return 1
        return -1

    ranked = sorted(((_title_score(r), r) for r in rows), key=lambda sr: sr[0], reverse=True)
    # Require an EXACT normalized-title match for the entity's own page. A mere prefix

    # so grounding on it would answer about the wrong thing — better to abstain than to

    if not ranked or ranked[0][0] < 3:
        return None
    best = ranked[0][1]
    composed = compose_web_answer(entity, [{"snippet": best.get("snippet", ""), "title": best.get("title", "")}], language=language)
    facts = str((composed or {}).get("answer") or "").strip()
    if len(facts) < 30:
        return None
    src = str(best.get("url") or best.get("source_url") or "")


    # found in the documented facts, and present what the entity IS documented to be.
    if is_ko:
        _c = claim[-1] if claim else ""
        _rn = "이라는" if ("가" <= _c <= "힣" and (ord(_c) - 0xAC00) % 28 != 0) else "라는"
        answer = f"‘{claim}’{_rn} 주장은 확인된 근거에서 찾지 못했어요. 대신 {entity}에 대해 확인된 사실은 이래요. {facts}"
    else:
        answer = f"I found no evidence for the claim “{claim}.” Here is what is documented about {entity}: {facts}"
    return {
        "answer": answer,
        "reasoning_certificate": {
            "derivation_kind": "claim_unsupported_entity_grounded",
            "anchor_concept": entity,
            "steps": [
                {"type": "claim_decomposition", "fact": f"question is a yes/no claim: entity='{entity}', claim='{claim}'"},
                {"type": "entity_reground", "fact": f"no source supports the claim; re-grounded on the entity '{entity}' and reported its documented facts"},
            ],
            "evidence_concepts": [entity],
            "confidence": 0.55,
            "confidence_basis": "entity_documented_claim_unsupported",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "claim_asserted": False, "grafted_to_brain": False},
        },
        "confidence": 0.55,
        "provider": "wikipedia_entity_reground",
        "source_url": src,
    }


def _wiki_direct_entity_row(question: str) -> dict[str, Any] | None:
    """FIND-HARDER backstop: resolve the query's core entity DIRECTLY on Wikipedia via the
    exact-title REST summary (then Wiktionary), catching entities the open-web / action
    search misses (bad ranking, odd title) or when the search API is down (a different
    endpoint). Returns a single result row or None — a disambiguation page returns None, so
    we never guess a referent for an ambiguous bare term. Real cited source, never fabricated."""
    try:
        from app.services.web_search import (
            _lookup_terms,
            _normalize_lookup_query,
            _wiki_host_for_query,
            _wiki_rest_summary,
            _wiktionary_definition,
        )

        terms = [t for t in _lookup_terms(_normalize_lookup_query(question)) if len(t) >= 2]
        if not terms:
            return None
        host = _wiki_host_for_query(question)
        cands: list[str] = []
        seen: set[str] = set()



        _gen = re.search(r"([가-힣A-Za-z0-9]{1,12})의\s+([가-힣A-Za-z0-9]{2,12}?)(?:[은는이가을를만]|\s|$)", question)
        if _gen:
            cands.append(f"{_gen.group(1)}의 {_gen.group(2)}")
            seen.add(cands[0])
        for cand in (" ".join(terms), max(terms, key=len), *terms):
            if cand and cand not in seen:
                seen.add(cand)
                cands.append(cand)


        # sentence(s) that name Y. Without this the backstop served the Y

        # never became a candidate (len>=2 term filter). Order: exact full

        # generic candidates.
        if _gen:
            row = _wiki_rest_summary(cands[0], host)
            if row:
                return row
            mod, tail = _gen.group(1), _gen.group(2)
            # only when the tail is the COMPLETE asked attribute: a multiword

            # quoting X-page sentences that merely contain that word is

            # question). Content continuing after the capture => skip; the
            # generic candidates keep the previous behavior.
            _after = question[_gen.end(2):]
            if re.match(r"\s+[가-힣A-Za-z0-9]", _after):
                mod_row = None
                _snip = ""
            else:
                mod_row = _wiki_rest_summary(mod, host)
                _snip = str((mod_row or {}).get("snippet") or "")
            if tail in _snip:
                _hits = [s for s in re.split(r"(?<=[.!?다])\s+", _snip) if tail in s]
                if _hits:
                    return {**mod_row, "snippet": " ".join(_hits)[:400],
                            "id": "wikipedia-direct-relation"}
            cands = cands[1:]  # the full genitive title was already tried
        for term in cands[:4]:
            row = _wiki_rest_summary(term, host)
            if row:
                return row
        return _wiktionary_definition(cands[0], korean=bool(re.search(r"[가-힣]", question)))
    except Exception:  # pragma: no cover - network/optional backstop
        return None


# BOUNDED GROUNDING + WARM CACHE (owner 2026-07-11 final assault: the speed wall's body was
# THIS lane — 18 battery cases ≈8s each riding a provider→wiki-search→REST-summary HTTP chain
# to its timeouts). Parameters: total budget 4000ms; chain depth 2 (stage 3 REST only when
# ≥1.5s budget remains); hits cached 15min, misses 60s (negative cache stops re-walking the
# chain for the same unanswerable question).
# English function words dropped when checking whether a multiword concept survived into the answer
# (R2 _en_concept_unmet gate). Kept tiny/local — the goal is "did the key nouns of the concept make
# it into the answer", so only articles/preps/copulas matter.
_EN_STOP = frozenset("a an the of is are was were to in on at for with by from as and or but "
                     "what which who how why".split())
_RESCUE_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}
_RESCUE_BUDGET_S = 12.0   # orchestrate-first era (R2 2026-07-16): multi-query + 3-provider fan-out
#                           needs ~5-9s; 4.0 timed out → None got MISS-cached and pinned the weak
#                           local answer (measured live: Seoul case regressed to 'Korea is a region').
#                           provider_api_search's own wall budget still guards the pathological tail.
_RESCUE_HIT_TTL_S, _RESCUE_MISS_TTL_S = 900.0, 60.0


def _rescue_cache_get(key: str) -> tuple[bool, dict[str, Any] | None]:
    import time as _t
    row = _RESCUE_CACHE.get(key)
    if not row:
        return False, None
    at, val = row
    ttl = _RESCUE_HIT_TTL_S if val is not None else _RESCUE_MISS_TTL_S
    if _t.time() - at > ttl:
        _RESCUE_CACHE.pop(key, None)
        return False, None
    return True, val


def _rescue_cache_put(key: str, val: dict[str, Any] | None) -> None:
    import time as _t
    if len(_RESCUE_CACHE) > 256:   # bounded: drop the oldest half
        for k in sorted(_RESCUE_CACHE, key=lambda k: _RESCUE_CACHE[k][0])[:128]:
            _RESCUE_CACHE.pop(k, None)
    _RESCUE_CACHE[key] = (_t.time(), val)


async def _web_grounded_rescue(question: str, language: str) -> dict[str, Any] | None:
    """Budget-bounded, cached wrapper around the grounding chain (see constants above)."""
    key = re.sub(r"\s+", " ", str(question or "").strip().lower())[:200] + "|" + language
    hit, cached = _rescue_cache_get(key)
    if hit:
        return cached
    try:
        result = await asyncio.wait_for(_web_grounded_rescue_impl(question, language),
                                        timeout=_RESCUE_BUDGET_S)
    except asyncio.TimeoutError:
        result = None   # budget spent — the caller keeps its honest local answer
    except Exception:
        result = None
    _rescue_cache_put(key, result)
    return result


async def _web_grounded_rescue_impl(question: str, language: str) -> dict[str, Any] | None:
    """When the local engine has no answer and web search is ON, answer from a
    real web source (Wikipedia, or a configured provider) and cite it. This is
    retrieval-augmented grounding — the answer IS the retrieved evidence,
    attributed; no LLM, no fabrication. Returns None if nothing relevant."""
    # ORCHESTRATE-FIRST (R2, 2026-07-16): the orchestrator carries the measured wins — entity-first
    # queries + entity-anchored lead (battery 6/7: 'capital of South Korea' → Seoul) — while this
    # lane's own retrieval still surfaced 'Capital punishment' (measured live). Try it first;
    # everything below stays as the fallback net.
    try:
        from app.services.search_orchestrator import orchestrate as _orch
        _o = await asyncio.to_thread(_orch, question, language=language)
        if _o and str(_o.get("answer") or "").strip():
            _srcs = list(_o.get("sources") or [])
            _u0 = str((_srcs[0] or {}).get("url") or "") if _srcs else ""
            return {
                "answer": str(_o["answer"]),
                "confidence": float(_o.get("confidence") or 0.66),
                "provider": "search-orchestrator",
                "source_url": _u0 or None,
                "source_title": str((_srcs[0] or {}).get("title") or "") if _srcs else None,
                "reasoning_certificate": {
                    "derivation_kind": "web_orchestrated_grounding",
                    "queries_used": _o.get("queries_used"),
                    "rounds": _o.get("rounds"),
                    "sources": _srcs[:5],
                },
            }
    except Exception:
        pass
    try:
        from app.services.web_search import retrieval_budget, search_web, wikipedia_search

        # Proportional retrieval: a bare fact lookup reads 3 results, an open
        # question earns a wider sweep — effort scales with the question.
        _budget = retrieval_budget(question)
        payload = await search_web(question, _budget["top_k"])
    except Exception:  # pragma: no cover - network/optional
        payload = None
        _budget = {"top_k": 5, "max_supporting": 4, "deep": True}
    provider = str((payload or {}).get("provider") or "")
    rows_available = list((payload or {}).get("results") or [])
    is_ko = language == "ko"
    # Reliable free fallback: a configured provider may be missing/unconfigured
    # (→ "static" fixtures) or the provider path may yield nothing. Wikipedia is a
    # keyless public encyclopedia, so try it directly (language-aware) before ever
    # declaring the web unreachable. This is what makes the answer reflect search.
    if provider in ("", "static") or not rows_available:
        try:
            wiki_rows = await asyncio.to_thread(wikipedia_search, question, _budget["top_k"])
        except Exception:  # pragma: no cover - network/optional
            wiki_rows = []
        if not wiki_rows:
            # The action search still found nothing (or the API is down). Try the exact-title
            # REST summary directly — it resolves entities the action search misses and uses a
            # different endpoint, so it answers even when the general search is unreachable.
            _direct = await asyncio.to_thread(_wiki_direct_entity_row, question)
            if _direct:
                wiki_rows = [_direct]
        if wiki_rows:
            provider = str(wiki_rows[0].get("provider") or "wikipedia")
            payload = {"provider": provider, "results": wiki_rows}
    # INJECTION scrub (threat model §1): a web snippet can carry an instruction

    # neutralize any injected directive — the source may INFORM a fact, it may
    # not HIJACK the response. The fact-bearing prose survives untouched.
    try:
        from packages.graph_scale.injection_guard import scan_answer_grounding as _inj_scrub

        for _r in (payload or {}).get("results") or []:
            for _fld in ("snippet", "summary", "extract", "text", "content"):
                if _r.get(_fld):
                    _s = _inj_scrub(str(_r[_fld]))
                    if _s["hijack_attempt"]:
                        _r[_fld] = _s["safe_text"]
    except Exception:
        pass
    # For a knowledge query the web search tries real retrieval first. "none" = no real source
    # configured and fixtures not opted in (the honest default); "static"/"" = same class. In all
    # of these, say so honestly instead of pasting a fixture.
    if provider in ("", "static", "none"):
        # Offline / unreachable: answer from a fact ATANOR looked up earlier, if it
        # has one (the agent remembers what it learned from the web).
        cached = _recall_web_fact(question)
        if cached:
            return cached
        return {
            "answer": (
                "지금 인터넷에서 확인하지 못했어요 (웹 연결 또는 검색 불가). 로컬에 있는 지식 범위 안에서만 답할 수 있어요."
                if is_ko
                else "I couldn't reach the web to check this right now (no connection or search unavailable). I can only answer from local knowledge."
            ),
            "reasoning_certificate": {
                "derivation_kind": "web_unreachable",
                "anchor_concept": None,
                "steps": [{"type": "web_status", "fact": "live web retrieval unavailable; no fixtures used"}],
                "evidence_concepts": [],
                "confidence": 0.2,
                "confidence_basis": "web_unreachable",
                "guarantees": {"external_llm": False, "fabricated_facts": False, "static_fixtures_used": False},
            },
            "confidence": 0.2,
            "provider": "offline",
            "source_url": "",
            "source_title": "",
            "web_unreachable": True,
        }
    if provider == "microsoft-grounding":
        return None
    def _is_citation_cruft(snippet: str) -> bool:
        # bibliography / reference entries, not prose ("Lewis (1995). ... McFarland & Co.")
        return bool(
            re.match(r"^\s*([A-Z][\w.'\-]+,?\s+){1,3}\(\d{4}\)", snippet)
            or re.match(r"^\s*(\d|pp\b|p\.|vol\b|archived|retrieved|ISBN)", snippet, re.IGNORECASE)
            or re.search(r"\b(ISBN|McFarland|Press|Co\.|pp\.\s*\d|Archived|Retrieved)\b", snippet[:120])
        )

    def _looks_like_definition(snippet: str) -> bool:
        if _is_citation_cruft(snippet):
            return False
        head = snippet[:80]
        return bool(re.search(r"\b(is|was|are|were)\s+(a|an|the)\b", head) or re.search(r"(이다|입니다|[은는이가]\s)", head))

    rows = [
        r for r in (payload.get("results") or [])
        if len(str(r.get("snippet") or "").strip()) >= 60 and not _is_citation_cruft(str(r.get("snippet") or ""))
    ]
    # RELEVANCE GATE (critical correctness): a full-text encyclopedia search can
    # return a page that merely *mentions* the term in passing (e.g. asking

    # page is definition-shaped but NOT about the entity. We must never present an
    # off-topic page as the answer, and never graft it into the brain. So require
    # that the query's core entity term actually anchors the result — in the TITLE,
    # or as the subject in the first sentence — before a row is eligible.
    try:
        from app.services.web_search import _lookup_terms, _normalize_lookup_query

        _core_terms = [t for t in _lookup_terms(_normalize_lookup_query(question)) if len(t) >= 2]
    except Exception:  # pragma: no cover - defensive
        _core_terms = []


    # away (measured). Anchor on the full form / the modifier instead.
    _gen_q = re.search(r"([가-힣A-Za-z0-9]{1,12})의\s+([가-힣A-Za-z0-9]{2,12}?)(?:[은는이가을를만]|\s|$)", question)
    if _gen_q:
        _core_terms = [f"{_gen_q.group(1)}의 {_gen_q.group(2)}", _gen_q.group(1)]

    def _on_topic(row: dict[str, Any]) -> bool:
        if not _core_terms:
            return True  # nothing to anchor on; fall back to prior behaviour
        title_l = str(row.get("title") or "").lower()
        subject = str(row.get("snippet") or "")[:48].lower()
        # Title anchor is the strongest signal the page is *about* the entity.
        if any(term in title_l for term in _core_terms):
            return True
        # GENITIVE queries trust ONLY the title anchor: a short modifier as a


        # exact-title backstop below finds the real page instead.
        if _gen_q:
            return False
        # Otherwise the term must lead the snippet AND the search counted a hit.
        return any(term in subject for term in _core_terms) and int(row.get("query_terms_matched") or 0) >= 1

    on_topic_rows = [r for r in rows if _on_topic(r)]

    # documented facts — not answered from any page that merely mentions the entity (an

    # claim questions to entity-grounded verification FIRST, ahead of general retrieval.
    _is_claim = _parse_yes_no_claim(question, language)
    if _is_claim:
        _claim_answer = await _verify_claim_about_entity(question, language)
        if _claim_answer:
            return _claim_answer
        # A claim we could not confidently ground on the entity's OWN page must NOT be

        # tangent). Force the honest abstain instead.
        on_topic_rows = []
    if not on_topic_rows and not _is_claim:
        # FIND HARDER before abstaining: the open-web search sometimes misses the entity's

        # core entity directly on Wikipedia/Wiktionary and answer from that exact-title page
        # instead. Still a real cited source, never fabricated (disambiguation → None).
        _direct = await asyncio.to_thread(_wiki_direct_entity_row, question)
        if _direct:
            on_topic_rows = [_direct]
            provider = str(_direct.get("provider") or "wikipedia")
    if not on_topic_rows:
        # No retrieved page is genuinely about the asked entity. Abstain honestly
        # rather than answer from an unrelated page — and graft nothing.
        return {
            "answer": (
                f"‘{question.strip()}’에 대해 확인된 근거가 있는 문서를 웹에서 찾지 못했어요. 추측해서 답하지 않을게요 — 질문을 조금 더 구체적으로 주시면 다시 찾아볼게요."
                if is_ko
                else f"I couldn't find a reliable source genuinely about “{question.strip()}.” I won't guess — give me a bit more detail and I'll look again."
            ),
            "reasoning_certificate": {
                "derivation_kind": "web_no_relevant_source",
                "anchor_concept": None,
                "steps": [{"type": "web_relevance_gate", "fact": "retrieved pages did not anchor the asked entity (title/subject mismatch); abstained instead of answering off-topic"}],
                "evidence_concepts": [],
                "confidence": 0.15,
                "confidence_basis": "no_relevant_source",
                "guarantees": {"external_llm": False, "fabricated_facts": False, "off_topic_source_used": False, "grafted_to_brain": False},
            },
            "confidence": 0.15,
            "provider": "web_no_match",
            "source_url": "",
            "source_title": "",
            "web_no_relevant_source": True,
        }
    rows = on_topic_rows
    # SINGLE selection authority: search_web already ranked these rows by referent
    # resonance (type + subject-identity + trust + definition) for the search-API path
    # and by entity resolution for the Wikipedia path. Defer to that order — take the
    # top on-topic, non-cruft row — instead of re-selecting here. The old heuristic
    # (_looks_like_definition + max term match) was English-biased and mis-ranked
    # Korean encyclopedic bios, letting a news article / song beat the right page.
    best = rows[0]
    title = str(best.get("title") or "")
    url = str(best.get("url") or "")
    is_ko = language == "ko"
    suffix = f" (출처: {title})" if is_ko and title else (f" (source: {title})" if title else "")

    # Graft the cited web result(s) into the Cloud Brain as real concept nodes,
    # ordering the answer's own source first, and hand the new nodes back so the
    # Local Brain graph can light them up as they are added.
    # Only on-topic rows (the relevance-gated set) may be grafted — never the
    # unrelated pages a full-text search may have returned alongside.
    ordered_rows = [best] + [r for r in rows if r is not best]
    graft = _graft_web_nodes_to_cloud_brain(ordered_rows, language) if provider == "wikipedia" else {}
    grafted_nodes = graft.get("grafted_nodes") or []
    web_graft = {
        "cloud_brain_concepts_added": int(graft.get("concepts_added") or 0),
        "cloud_brain_relations_added": int(graft.get("relations_added") or 0),
        "candidate_store_path": graft.get("candidate_store_path"),
        "production_store_mutated": bool(graft.get("production_store_mutated")),
    } if graft else {}

    # Attribution questions ("who invented X?") get the PERSON, not just a
    # definition — extracted deterministically from the retrieved snippets.
    all_snippets = [str(r.get("snippet") or "") for r in rows]
    person = _extract_attribution(question, all_snippets)
    # The intro extract often omits the founder/inventor (it's deeper in the
    # article). If this is an attribution question and the short snippets didn't
    # yield a person, fetch the full article text once and scan that.
    _rel_now = _detect_attribution_relation(question)
    if not person and _rel_now and "wikipedia.org" in str(url):
        host = "ko.wikipedia.org" if "ko.wikipedia.org" in str(url) else "en.wikipedia.org"


        from urllib.parse import unquote

        page_title = unquote(str(url).split("/wiki/")[-1].split("?")[0]).replace("_", " ") or title
        try:
            from app.services.web_search import _wikipedia_extract_for_page, wikipedia_infobox_people

            # 1) deeper prose (inventors/authors often appear below the intro)
            if "ko.wikipedia.org" in str(url):
                full_extract = _wikipedia_extract_for_page(page_title)
                if full_extract:
                    person = _extract_attribution(question, [full_extract])

            if not person:
                person = wikipedia_infobox_people(page_title, host=host, relation_key=_rel_now[0])
        except Exception:  # pragma: no cover - network/optional
            person = person
    if person:
        rel = _detect_attribution_relation(question)
        rel_key = rel[0] if rel else "created"
        rel_phrase = rel[1] if rel else "attributed to"
        topic = re.sub(r"^(the|a|an)\s+", "", _first_sentences(title, max_chars=60), flags=re.IGNORECASE) or (title or "It")
        verb_ko = {
            "invented": "발명한", "discovered": "발견한", "wrote": "쓴", "founded": "설립한",
            "painted": "그린", "composed": "작곡한", "directed": "감독한", "built": "지은", "created": "만든",
        }.get(rel_key, "만든")


        _last = topic[-1] if topic else ""
        _has_batchim = bool(_last) and "가" <= _last <= "힣" and (ord(_last) - 0xAC00) % 28 != 0
        _obj_josa = "을" if _has_batchim else "를"
        attribution = (
            f"{topic}{_obj_josa} {verb_ko} 사람은 {person}입니다."
            if is_ko
            else f"{title or topic} was {rel_phrase} by {person}."
        )
        cert = {
            "derivation_kind": "web_attribution_extraction",
            "anchor_concept": {"id": person, "label": person, "match": "web_retrieval"},
            "steps": [{"type": "web_attribution", "source": url or provider, "fact": f"{rel[1] if rel else 'attributed to'} {person}"}],
            "evidence_concepts": [url] if url else [provider],
            "confidence": 0.7,
            "confidence_basis": f"web_attribution:{provider}",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "evidence_grounded": True, "source_cited": True},
        }
        attribution_text = (attribution + suffix).strip()
        _store_web_fact(question, title, attribution_text, url)
        return {
            "answer": attribution_text, "reasoning_certificate": cert, "confidence": 0.7,
            "provider": provider, "source_url": url, "source_title": title,
            "grafted_nodes": grafted_nodes, "web_graft": web_graft,
        }

    # Organize the retrieved results into a clean answer (a definitional lead about the
    # entity + a couple of non-redundant supporting facts) instead of pasting one raw
    # snippet. Extractive composition — no LLM, no rule table; selection is referent
    # resonance + the query's own key terms.
    try:
        from app.services.web_search import compose_web_answer

        _composed = compose_web_answer(question, rows, language=language,
                                       max_supporting=int(_budget.get("max_supporting") or 4))
    except Exception:  # pragma: no cover - composition must never break the answer
        _composed = None
    # If the single-shot pass is thin (off-topic page, missing coverage), ESCALATE to
    # the search orchestrator: rewrite the question into focused queries, retrieve across
    # all of them, and do one corrective re-search before giving up (CRAG). This is what

    # good first answer keeps its low latency.
    # Escalate to the orchestrator when the first pass is thin OR when it answered an



    _comp_ans = str((_composed or {}).get("answer") or "")
    _open = bool(re.search(r"몇|얼마나|얼마|어떻게|왜\b|차이|비교|방법|추천|괜찮|좋을까|장단점"
                           r"|효과|부작용|며칠|어디|언제", question))
    _def_only = _open and (bool(re.search(r"(이다|음료|입니다|것이다)\s*\.?$", _comp_ans.strip()))
                           or len(_comp_ans) < 90)
    if not _composed or len(_comp_ans) < 60 or _def_only:
        try:
            from app.services.search_orchestrator import orchestrate

            _orch = orchestrate(question, language=language, deep=bool(_budget.get("deep")))
            # prefer the orchestrator only when it produced a WOVEN synthesis (a real
            # multi-fact answer), not another lone definition.
            if _orch and str(_orch.get("answer") or "").strip() and (
                    not _def_only or _orch.get("answer_kind") == "grounded_synthesis"):
                _composed = _orch
        except Exception:  # pragma: no cover
            pass
    answer = (_composed or {}).get("answer") or _first_sentences(str(best.get("snippet") or ""), max_chars=420)
    if len(answer) < 40:
        return None
    certificate = {
        "derivation_kind": "web_search_grounding",
        "anchor_concept": {"id": title or question[:60], "label": title or question[:60], "match": "web_retrieval"},
        "steps": [
            {"type": "web_source", "source": url or provider, "fact": _first_sentences(str(best.get("snippet") or ""), max_chars=160)},
        ],
        "evidence_concepts": [url] if url else [provider],
        "confidence": 0.72,
        "confidence_basis": f"web_retrieval:{provider}",
        "guarantees": {"external_llm": False, "fabricated_facts": False, "evidence_grounded": True, "source_cited": True},
    }
    answer_text = (answer + suffix).strip()
    _store_web_fact(question, title, answer_text, url)
    return {
        "answer": answer_text,
        "reasoning_certificate": certificate,
        "confidence": 0.72,
        "provider": provider,
        "source_url": url,
        "source_title": title,
        "grafted_nodes": grafted_nodes,
        "web_graft": web_graft,
    }


def _graft_web_nodes_to_cloud_brain(results: list[dict[str, Any]], language: str) -> dict[str, Any]:
    """Add cited web results to the Cloud Brain candidate store as real concepts
    and return the new node descriptors. Never raises (grounding answer must not
    depend on the graft succeeding)."""
    try:
        from app.services.wikipedia_grounded_learning import ingest_web_result

        return ingest_web_result(results, language=language, max_nodes=3)
    except Exception:  # pragma: no cover - graft is best-effort
        return {}


def _is_recent_learning_question(question: str) -> bool:
    lower = question.lower()
    if any(token in question for token in ("최근 학습", "최근 배운", "학습한 개념", "새로 배운")):
        return True
    # Structural detection: recency marker + knowledge-intake verb + knowledge noun

    # above and leaked to WEB SEARCH, answering with a random peace-index page).
    if (
        re.search(r"최근|방금|오늘|요즘|마지막", question)
        and re.search(r"배우|배운|배웠|학습|들어온|들어왔|익힌|익혔|알게\s*된|읽은|읽었", question)
        and re.search(r"지식|정보|내용|개념|문서|사실|것|거|뭐|뭘|무엇", question)
    ):
        return True
    return "recent" in lower and any(token in lower for token in ("learn", "concept", "memory", "knowledge"))


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
    merged = dict(semantic_context)
    merged["semantic_store_counts"] = {
        "concepts": len(concepts),
        "relations": len(relations),
    }
    # These rows can originate at the public semantic-ingest boundary.  Counts
    # are safe introspection, but labels and claims are candidate data and must
    # not be injected into the answer-grounding context without attestation.
    merged["semantic_store_verification_state"] = SEMANTIC_STORE_VERIFICATION_STATE
    merged["semantic_candidate_context_withheld"] = True
    merged["local_coverage"] = (
        semantic_context.get("local_coverage")
        or "semantic_cloud_growth_candidates_observed"
    )
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


def _answer_is_abstention(answer: str) -> bool:
    text = re.sub(r"\s+", " ", str(answer or "").strip().lower())
    if not text:
        return True
    return any(
        marker in text
        for marker in (
            "not have enough verified evidence",
            "verified evidence to answer confidently",
            "not have enough base concepts",
            "not have enough local evidence",
            "not have enough confidently matched evidence",
            "지금 확인된 근거가 부족",
            "확인 가능한 근거가 부족",
            "근거가 부족",
            "단정하기 어렵",
            "설명할 근거가 없",
        )
    )


def _grounded_answer_incoherent(answer: str, query: str) -> bool:
    """General coherence gate for a grounded answer — NO per-entity rules. A native
 graph-token stitch can be lexically diverse yet incoherent (drops the subject, trails off
 on a bare particle: '… CPU'). A grounded definitional answer must (a) contain the
 query's own key content terms — a definition of X mentions X — and (b) end as a sentence,
 not a dangling Korean particle. When it fails, the caller re-grounds it in the real
 evidence sentence. Works for ANY query; the checks come from the query itself + grammar."""
    a = re.sub(r"\s+", " ", str(answer or "").strip())
    if len(a) < 4:
        return True
    try:
        from app.services.web_search import _lookup_terms, _normalize_lookup_query

        key_terms = [t for t in _lookup_terms(_normalize_lookup_query(query)) if len(t) >= 2]
    except Exception:
        key_terms = []
    low = a.lower()
    if key_terms and not all(t.lower() in low for t in key_terms):
        return True  # dropped the subject entity
    if re.search(r"[가-힣]", a) and re.search(r"(를|을|와|과|의|에|에서|으로|로|이|가|은|는|도|만)$", a):
        return True  # trails off on a bare particle -> a stitched fragment, not a sentence
    return False


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
    # Temporary attachment is not authority.  Only a provider that positively
    # records both independent source attestation and answer authorization may
    # enter the answer-grounding context.  Missing fields fail closed.
    answer_nodes = [
        node
        for node in list(chunk.get("semantic_nodes") or [])
        if isinstance(node, dict)
        and node.get("independent_source_attestation") is True
        and node.get("authoritative_for_answer") is True
    ]
    labels = [
        str(node.get("label") or node.get("concept_id") or node.get("id"))
        for node in answer_nodes
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
        "confidence": float(base.get("confidence") or 0.64),
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


_FRONTEND_ALLOWED_BASES = {
    "local_corpus_construction_transition_model",
    "semantic_grounded_conversation_router_v0",
    "semantic_cloud_graph_surface_brain_v0",
    "base_brain_seed_graph_surface_v0",
}


def _looks_like_abstention(text: str) -> bool:
    low = str(text or "").lower()
    return (
        "enough" in low
        or "confidently yet" in low
        or "부족" in str(text)
        or "단정하기 어렵" in str(text)
    )


# A DEFINITION ask, and nothing else, is what a dictionary answers. This gate is ALLOW-LIST
# (default-deny) on purpose: the lexicon lane used to fire on any turn, so every intent whose own
# lane was dead in English leaked into it and came back defining a stray word. Measured 2026-07-17:
#   "How can I sleep better?"          → "better is a kind of good."          (advice lane dead)
#   "How is coffee different from tea?" → "different — Not the same."          (comparison dead)
#   "What does the Eiffel Tower look like?" → an explicit slang sense          (visual lane dead)
# Default-deny means an unlisted phrasing loses a dictionary answer it might have wanted — an
# honest miss that falls to a real lane, versus a confident answer to a question nobody asked.
_DEFINITION_ASK = re.compile(
    r"^\s*(?:what|who)\s+(?:is|are|was|were)\b"
    r"|^\s*what(?:'s|s)\b"
    r"|\bdefine\b|\bdefinition\s+of\b|\bmeaning\s+of\b|\bwhat\s+does\s+.+\s+mean\b"
    r"|\btell\s+me\s+about\b|\bexplain\b"
    r"|(?:뭐야|뭐지|무엇|뜻이|의미|정의|설명해|알려줘)",
    re.IGNORECASE)
# …unless the turn is one of these shapes, which START like a definition ask but are not one.
_NOT_A_DEFINITION = re.compile(
    r"\blook\s+like\b|\bdifferen(?:t|ce)\b|\bcompare[d]?\b|\bversus\b|\bvs\.?\b"
    r"|\bhow\s+(?:can|do|should|would)\s+(?:i|we|you)\b|\bshould\s+(?:i|we)\b"
    r"|\bassociate\b|\bremind\s+you\b|\bfeel\s+about\b",
    re.IGNORECASE)


def _is_definition_ask(question: str) -> bool:
    q = str(question or "")
    if _is_opinion_or_capability_turn(q) or _NOT_A_DEFINITION.search(q):
        return False
    return bool(_DEFINITION_ASK.search(q))


def _is_opinion_or_capability_turn(question: str) -> bool:
    """True when the turn asks for a view or for what ATANOR can do — never a request to define
    a word, so the lexicon definition lane must defer to the router/converse path.

    This gate was Korean-only while the core answers English, and English turns fell straight
    through into the dictionary. Measured 2026-07-17:
        "What do you think about music?"      → 'do you — Used other than figuratively…'
        "Can you remember this conversation?" → 'conversation is a kind of speech.'
    Second person is the tell: a turn addressed TO ATANOR is not a lexicographic request.
    """
    q = str(question or "")
    # A perception/association ask uses second person incidentally ("what do YOU associate with
    # winter?") but is about the WORLD, not about ATANOR — those lanes own it. Measured: the
    # second-person gate swallowed it and returned a status line about approval gates.
    if _ASSOC_EN.search(q) or _VISUAL_LOOK_EN.search(q):
        return False
    return bool(
        re.search(r"(찬성|반대|어떻게\s*생각|생각해\??$|해야\s*(할까|돼|한다고)|없어져야|옳다고|맞다고|"
                  r"더\s*(중요|나은|좋은)|보다\s*나|무엇이\s*더|어느\s*(쪽|것)이)", q)
        or re.search(
            r"\b(can|could|do|did|will|would|are|were|have|should)\s+you\b|"
            r"\b(what|how)\s+do\s+you\s+(think|feel|reckon)\b|"
            r"\byour\s+(opinion|view|take|thoughts?)\b|"
            r"\bshould\s+(i|we)\b|"
            # subjective COMPARISON / VALUE turns have no verified factual answer, so the
            # lexicon/definition lane must defer (measured 2026-07-20 ITT pilot: "Do museums
            # matter more than cinemas?" fell through to "Its is a possessive determiner…").
            r"\bmatter[s]?\s+more\b|\bmore\s+important\b|\bbetter\s+than\b|\bworth\s+(it|more)\b|"
            r"\b(is|are)\s+.+\bbetter\b|\b\w+\s+(?:vs\.?|versus)\s+\w+|"
            r"\bdo\s+.+\bmatter\b|\bwhich\s+(is|matters|one)\b|\bprefer\b|\bagree\s+(that|with)\b",
            q, re.IGNORECASE)
    )


def _engine_passes_frontend_gate(engine: dict[str, Any]) -> bool:
    """Mirror the web client's isAsmConversationPayload honesty gate. An answer
    that cannot prove it is graph-derived (allowed basis + all honesty flags
    False) is not rendered by the dashboard, so we must demote it."""
    if str(engine.get("generation_basis") or "") not in _FRONTEND_ALLOWED_BASES:
        return False
    for flag in (
        "external_llm", "external_sllm", "external_llm_used", "external_sllm_used",
        "rule_based_answer_used", "internal_trace_exposed", "local_brain_write",
        "production_store_mutated", "candidate_promotion",
    ):
        if engine.get(flag) is not False:
            return False
    return True


def _demote_low_quality_to_base_brain(response: dict[str, Any], request: AtanorChatRequest) -> dict[str, Any]:
    """Final quality gate across ALL answer paths: replace the surfaced answer
    with the clean Base Brain answer (or Base Brain's honest abstention) when it
    is cross-language / pasted / citation-noise, OR when its engine cannot prove
    graph-derived honesty (so the dashboard's render gate would reject it). Keeps
    the dashboard from showing raw web snippets \u2014 and from silently dropping good
    answers whose provenance metadata is incomplete."""
    result = response.get("result")
    if not isinstance(result, dict):
        return response
    answer = str(result.get("answer") or "")
    if not answer.strip():
        return response
    question = request.question_text()
    language = _resolve_language(request.language, question)
    engine_now = result.get("answer_engine") if isinstance(result.get("answer_engine"), dict) else {}
    answer_is_abstention = _looks_like_abstention(answer)
    base = answer_with_base_brain(
        question, language=language, audience_level=request.audience_level, mode="default"  # type: ignore[arg-type]
    )
    base_answer = str(base.get("answer") or "").strip()
    base_conf = float(base.get("confidence") or 0.0)
    grounding_source = str(engine_now.get("grounding_source") or "")
    # A loosely-matched verified-store paste yields to a Base-Brain answer that
    # actually NAMES the concept (conf >= 0.85): the precise graph answer beats a

    prefer_base = (
        grounding_source == "verified_store_v0_readonly"
        and base_conf >= 0.85
        and not _looks_like_abstention(base_answer)
    )
    # Demote when: the answer is cross-language/pasted/citation-noise, OR its
    # engine can't prove graph-derived honesty (would fail the dashboard render
    # gate), OR the live path abstained (the grounded path only hand-authors a few
    # topics, so it abstains on concepts Base Brain actually knows, e.g. Docker),
    # OR a verified-store paste should yield to a confident Base-Brain naming.
    if (
        not _grounded_answer_low_quality(answer, language)
        and _engine_passes_frontend_gate(engine_now)
        and not answer_is_abstention
        and not prefer_base
    ):
        return response
    if not base_answer:
        return response
    # Don't swap one honest abstention for another: if the live path abstained and
    # Base Brain also has nothing concrete, keep the original.
    if answer_is_abstention and _looks_like_abstention(base_answer):
        return response
    # OFFLINE CARTRIDGE before the low-quality base-brain grounding (2026-07-13): the 2M-triple
    # Kaikki dictionary gives a VERBATIM clean definition for a known subject. It beats a

    # and carries an honest structured kind — not a MISS kind. Exact-subject match is its own
    # precision gate, and engage turns were already routed upstream, so only knowledge turns
    # reach this rescue. THIS is what makes the shipped 2M cartridge live on the answer path.
    try:
        from packages.graph_scale import lexicon_lane as _lex
        if _lex.available():
            _lx = _lex.lookup(question, language)
            _lx_ans = str(_lx.get("answer") or "") if _lx else ""
            _lx_subj = str(((_lx.get("grounding") or [[None]])[0] or [None])[0] or "") if _lx else ""
            # GUARD 1 (P0 regression fix): the matched subject must be a real content noun that


            _subj_ok = (len(_lx_subj) >= 2 and _lx_subj in question
                        and not re.search(r"(어|여|해|았|었|겠|니|나|자|지)$", _lx_subj)


                        and _lx_subj not in {"찬성", "반대", "찬반", "의견", "입장", "생각", "이유"})
            # DEFAULT-DENY: a dictionary answers definition asks and nothing else. Anything that is
            # not one defers here, so it reaches its own lane (comparison/advice/visual) or an
            # honest abstain instead of coming back as a definition of a stray word.
            _opinion_turn = not _is_definition_ask(question)


            # only override with a Korean-surfaced definition, never the honest-but-foreign fallback.
            _ko_ok = (language != "ko"
                      or (bool(re.search(r"[가-힣]", _lx_ans)) and "사전상 '" not in _lx_ans))
            # RIGHT-TO-SPEAK (owner 2026-07-20, the fallback itself changes): a dictionary answer
            # may ship only if it actually engages the ask's content focus — a stray function word
            # ('its' in a control-task spec) is not a definition ask, whatever the lexicon matched.
            _lx_fit = True
            try:
                from packages.cgsr.cgsr.relevance_gate import answer_fit as _afit
                _lx_fit = _afit(question, _lx_ans).get("fits", True)
            except Exception:
                pass
            if (_lx and _lx_ans and _subj_ok and _ko_ok and not _opinion_turn and _lx_fit
                    and not _looks_like_abstention(_lx_ans)):
                result["answer"] = _lx_ans
                result["answer_kind"] = "lexicon_cartridge"
                result["confidence"] = 0.74
                result["scene_grounding"] = None
                result["scene_choreography"] = None
                result["visual_scene_plan"] = None
                result["splatra_scene_plan"] = None
                result["reasoning_certificate"] = {
                    "derivation_kind": "offline_lexicon_cartridge",
                    "anchor_concept": (_lx.get("grounding") or [[None]])[0][0],
                    "steps": [{"type": "dictionary_definition", "fact": str(_lx["answer"])[:120]}],
                    "evidence_concepts": [g[0] for g in (_lx.get("grounding") or [])[:3]],
                    "confidence": 0.74, "confidence_basis": "verbatim_offline_cartridge",
                    "grounding": _lx.get("grounding"), "certificate": _lx.get("certificate"),
                    "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
                }
                return response
    except Exception:
        pass
    # THE FINAL FALLBACK ITSELF CHANGES (owner 2026-07-20: "최종 폴백의 방식 자체를 바꿔 — 키워드를
    # 뽑아서 아무렇게나 하는 쓰레기가 안 나오게"). Keyword retrieval loses its unconditional last
    # word: before shipping, the base answer must ENGAGE the ask's content focus. If it grabbed an
    # incidental token ('its' → possessive determiner), the honest understanding-state reply ships
    # instead. Garbage is not produced-then-caught at the exit — it is never produced here at all.
    try:
        from packages.cgsr.cgsr.relevance_gate import answer_fit as _bfit, \
            honest_limit_reply as _blimit
        if not _bfit(question, base_answer).get("fits", True):
            result["answer"] = _blimit(question)
            result["answer_kind"] = "comprehension_limit"
            result["confidence"] = 0.2
            result["scene_grounding"] = None
            result["reasoning_certificate"] = None
            result["scene_choreography"] = None
            result["visual_scene_plan"] = None
            result["splatra_scene_plan"] = None
            return response
    except Exception:
        pass
    result["answer"] = base_answer
    result["answer_kind"] = "base_brain_after_low_quality_grounding"
    result["confidence"] = float(base.get("confidence") or 0.5)
    result["scene_grounding"] = base.get("scene_grounding")
    result["reasoning_certificate"] = base.get("reasoning_certificate")
    result["scene_choreography"] = None
    result["visual_scene_plan"] = None
    result["splatra_scene_plan"] = None
    engine = result.get("answer_engine")
    if not isinstance(engine, dict):
        engine = {}
    engine["generation_basis"] = "base_brain_seed_graph_surface_v0"
    for flag in (
        "external_llm", "external_sllm", "external_llm_used", "external_sllm_used",
        "rule_based_answer_used", "internal_trace_exposed", "local_brain_write",
        "production_store_mutated", "candidate_promotion",
    ):
        engine[flag] = False
    result["answer_engine"] = engine
    return response


def _concepts_for_fold(question: str) -> list[dict[str, Any]]:
    """Real base-brain concepts (+ relation neighbours) matched to the query."""

    pack = load_base_brain_pack()
    matched = get_semantic_context(question, pack, limit=24)
    concepts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for concept in matched:
        score = float(concept.get("match_score") or 0.0)
        hop = 0 if score >= 4.0 else (1 if score >= 1.0 else 2)
        importance = min(1.0, max(0.1, 0.3 + score * 0.12))
        # pack concepts carry source_type but no provenance STRING; the field adapter
        # honestly drops provenance-less nodes ("never invent it") — which silently
        # dropped EVERY concept, leaving only the emotion node in the fold (measured:
        # constant coherence, agreement structurally 0). The pack itself IS the real
        # origin, so name it — this is labelling, not invention.
        prov = str(concept.get("provenance") or "") or f"base_pack:{concept.get('source_type') or 'curated_base_pack'}"
        concepts.append({**concept, "importance": importance, "hop_depth": hop,
                         "provenance": prov})
        seen_ids.add(str(concept.get("concept_id") or ""))
    # 1-hop relation neighbours: a single matched concept gives the fold nothing to
    # interfere WITH (measured: 1-node fields fold to coherence 0 and the emotion node
    # dominates the core, forcing agreement to 0). Pull the matched concepts' relation
    # targets from the pack so the field carries the question's real neighbourhood.
    if concepts:
        by_id = {str(c.get("concept_id") or ""): c
                 for c in (pack.semantic_graph.get("concepts") or [])}
        for concept in list(concepts):
            for rel in (concept.get("relations") or [])[:6]:
                target_id = str(rel.get("target") or "")
                neighbour = by_id.get(target_id)
                if neighbour is None or target_id in seen_ids:
                    continue
                seen_ids.add(target_id)
                n_prov = str(neighbour.get("provenance") or "") or \
                    f"base_pack:{neighbour.get('source_type') or 'curated_base_pack'}"
                concepts.append({**neighbour, "importance": 0.25, "provenance": n_prov,
                                 "hop_depth": int(concept.get("hop_depth") or 0) + 1})
                if len(concepts) >= 24:
                    break
            if len(concepts) >= 24:
                break
    return concepts


_SHOW_FOLD_MARKERS_KO = ("작동방식", "작동 방식", "어떻게 작동", "어떻게 동작", "구조 보여", "구조를 보여", "생각을 보여", "생각하는 걸 보여", "3d로 보여", "3d로 펼", "접히는 걸 보여")
_SHOW_FOLD_MARKERS_EN = ("show how you work", "show how you think", "how do you work", "how do you think", "show your structure", "think in 3d", "show me your reasoning in 3d", "visualize your")





_FOLD_MARKERS_NEED_SELF = ("어떻게 작동", "어떻게 동작", "작동방식", "작동 방식")
_SELF_REFERENCE_RE = re.compile(
    r"(너\b|너는|너의|넌|네\b|니가|당신|ATANOR|아타노르|atanor|자기\s*자신|스스로|자네|"
    r"\byou\b|\byour\b|yourself)",
    re.IGNORECASE,
)


def _is_show_fold_request(question: str) -> bool:
    text = re.sub(r"\s+", " ", str(question or "").strip().lower())
    if not text:
        return False
    if any(marker in text for marker in _SHOW_FOLD_MARKERS_EN):
        return True
    raw = str(question or "")
    has_self = bool(_SELF_REFERENCE_RE.search(raw))
    for marker in _SHOW_FOLD_MARKERS_KO:
        if marker not in raw:
            continue

        if marker in _FOLD_MARKERS_NEED_SELF and not has_self:
            continue
        return True
    return False


def _is_local_graph_request(question: str) -> bool:
    raw = str(question or "")
    lowered = raw.lower()
    return ("로컬 그래프" in raw or "로컬그래프" in raw or "local graph" in lowered) and (
        "파동" in raw or "보여" in raw or "알려" in raw or "wave" in lowered or "show" in lowered
    )


def _atanor_self_concepts() -> list[dict[str, Any]]:
    """Real base-brain concepts that describe ATANOR itself (for the self-fold)."""

    pack = load_base_brain_pack()
    seed = "ATANOR 구조 로컬 브레인 클라우드 브레인 graph hub atlas brain graph 추론 그래프"
    matched = get_semantic_context(seed, pack, limit=24)
    concepts: list[dict[str, Any]] = []
    for concept in matched:
        score = float(concept.get("match_score") or 0.0)
        hop = 0 if score >= 4.0 else (1 if score >= 1.0 else 2)
        concepts.append({**concept, "importance": min(1.0, max(0.2, 0.4 + score * 0.1)), "hop_depth": hop})
    return concepts


def _local_graph_concepts() -> list[dict[str, Any]]:
    """ALL base-brain concepts (the local knowledge graph) as fold inputs."""

    pack = load_base_brain_pack()
    concepts: list[dict[str, Any]] = []
    for concept in pack.semantic_graph.get("concepts", []) or []:
        confidence = float(concept.get("confidence", 0.75) or 0.75)
        concepts.append({**concept, "importance": min(1.0, max(0.2, 0.4 + confidence * 0.4)), "hop_depth": 0})
    return concepts


def _build_fold_scene(question: str, concepts: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Fold a concept set and assemble a renderable 3D scene (read-only).

    Defaults to ATANOR's self-knowledge; pass `concepts` to fold an explicit
    graph (e.g. the whole local knowledge graph).
    """

    concepts = concepts if concepts is not None else _atanor_self_concepts()
    if not concepts:
        return None
    emotion = None
    try:
        snapshot = EVENT_BUS.engine.snapshot().to_dict()
        emotion = {**snapshot, "provenance": "neural_emotion:snapshot"}
    except Exception:  # pragma: no cover - optional
        emotion = None
    raw_nodes, edges = build_field_inputs(question, concepts=concepts, emotion=emotion)
    if not raw_nodes:
        return None
    label_by_id = {node["node_id"]: node.get("label") or node["node_id"] for node in raw_nodes}
    field = build_state_field(question, raw_nodes)
    folded = fold_state(field, edges=edges, capture_trajectory=True, trajectory_frames=48)
    index = {node.node_id: i for i, node in enumerate(folded.nodes)}
    pair_rep = build_pair_representation(field, edges=edges)
    scene_edges = [
        {
            "i": index[pair.i],
            "j": index[pair.j],
            "intf": round(pair.interference_energy, 4),
            "constructive": bool(pair.constructive),
        }
        for pair in pair_rep.pairs
        if pair.has_edge and pair.i in index and pair.j in index
    ]
    scene_nodes = [
        {
            "id": node.node_id,
            "label": label_by_id.get(node.node_id, node.node_id),
            "source_type": node.source_type,
            "position": list(node.position),
            "radius": round(node.radius, 4),
            "coherence": round(node.coherence, 4),
            # real wave parameters → renderer computes the live interference field
            "amplitude": round(node.amplitude, 5),
            "phase": round(node.phase, 5),
            "frequency": round(node.frequency, 2),
        }
        for node in folded.nodes
    ]
    return {
        "render_kind": "phase_holographic_fold_v0",
        "nodes": scene_nodes,
        "edges": scene_edges,
        "core": folded_core(folded, top_k=5),
        "trajectory": list(folded.trajectory),
        "meta": {
            "active_node_count": folded.metadata.get("active_node_count"),
            "global_coherence": folded.metadata.get("global_coherence"),
            "fold_timing_ms": folded.metadata.get("fold_timing_ms"),
            "trajectory_frame_count": folded.metadata.get("trajectory_frame_count"),
            "mean_radius_by_source": folded.metadata.get("mean_radius_by_source"),
            "original_brain_state_mutated": False,
            "fold_driver_mode": "compare_mode",
            "note": "ATANOR 내부 상태(검증 개념·후보·감정)를 위상 홀로그래픽 폴딩으로 접은 실제 구조입니다. 답변을 구동하지는 않습니다.",
        },
    }


@router.get("/api/holographic-fold/local")
async def holographic_fold_local() -> dict[str, Any]:
    """Fold the whole local knowledge graph (real engine) → renderable scene."""

    try:
        scene = _build_fold_scene("local knowledge graph", concepts=_local_graph_concepts())
    except Exception:  # pragma: no cover - never break the dashboard
        scene = None
    return {"folded_state_field": scene, "render_fold_scene": bool(scene)}


def _attach_holographic_fold_trace(response: dict[str, Any], request: AtanorChatRequest) -> dict[str, Any]:
    """Attach a compare_mode Phase-Holographic-Fold trace (hidden, read-only).

    The fold's recommended core is compared to the answer's own evidence and
    LOGGED only. It never changes the answer (compare_mode, spec §7). Fully
    defensive: any failure leaves the response untouched.
    """

    try:
        result = response.get("result")
        if not isinstance(result, dict) or not result.get("answer"):
            return response
        question = request.question_text()
        if not question:
            return response

        # VISUALIZATION commands ("local graph waves" / "show how ATANOR works")
        # are handled FIRST: they fold an explicit graph (the whole local graph or
        # the self-concepts) and must not be blocked by the compare-trace concept
        # gate below, which can be empty for a pure render request.
        local_req = _is_local_graph_request(question)
        if local_req or _is_show_fold_request(question):
            scene = (
                _build_fold_scene(question, concepts=_local_graph_concepts())
                if local_req
                else _build_fold_scene(question)
            )
            if scene:
                if local_req:
                    scene["render_kind"] = "local_graph_wave"
                result["folded_state_field"] = scene
                result["render_fold_scene"] = True
                # This is a render command, not a knowledge question — the scene is
                # the real content. Replace any tangential grounded paste with a
                # short, data-aware caption describing exactly what is shown.
                is_ko = bool(re.search(r"[가-힣]", question))
                node_count = len(scene.get("nodes") or [])
                if local_req:
                    result["answer"] = (
                        f"실시간 로컬 지식 그래프 {node_count}개 노드를 불러와, 각 노드의 파동이 퍼지며 겹치는 실제 간섭장을 보여드립니다."
                        if is_ko
                        else f"Loading the live local knowledge graph ({node_count} nodes) and rendering the real superposed wave-interference field of every node."
                    )
                else:
                    result["answer"] = (
                        "ATANOR의 내부 상태(검증 개념·후보·감정)를 위상 홀로그래픽 폴딩으로 3D 구조로 접어 보여드립니다."
                        if is_ko
                        else "Folding ATANOR's internal state (verified concepts, candidates, emotion) into a 3D phase-holographic structure."
                    )

        concepts = _concepts_for_fold(question)
        if not concepts:
            return response
        emotion = None
        try:
            snapshot = EVENT_BUS.engine.snapshot().to_dict()
            emotion = {**snapshot, "provenance": "neural_emotion:snapshot"}
        except Exception:  # pragma: no cover - optional emotion source
            emotion = None
        raw_nodes, edges = build_field_inputs(question, concepts=concepts, emotion=emotion)
        if not raw_nodes:
            return response
        field = build_state_field(question, raw_nodes)
        folded = fold_state(field, edges=edges)

        # resolve the answer's evidence (concept ids OR display names) to node ids
        resolver: dict[str, str] = {}
        for node in field.nodes:
            resolver[node.node_id.casefold()] = node.node_id
            resolver[node.label.casefold()] = node.node_id
            if node.node_id.startswith("concept:"):
                resolver[node.node_id.split("concept:", 1)[1].casefold()] = node.node_id
        certificate = result.get("reasoning_certificate")
        certificate = certificate if isinstance(certificate, dict) else {}
        evidence_raw = list(certificate.get("evidence_concepts") or [])
        anchor = certificate.get("anchor_concept")
        if anchor:
            evidence_raw.append(anchor)

        def _evidence_key(item: Any) -> str:
            # evidence entries may be plain ids or concept dicts ({id, label, ...})
            if isinstance(item, dict):
                item = item.get("id") or item.get("concept_id") or item.get("canonical_name") or ""
            return str(item).strip().casefold()

        evidence_ids = []
        for item in evidence_raw:
            key = _evidence_key(item)
            if not key:
                continue
            evidence_ids.append(resolver.get(key) or resolver.get(f"concept:{key}") or f"concept:{key}")

        report = compare_fold_to_answer(folded, evidence_ids)
        report["folded_global_coherence"] = folded.metadata.get("global_coherence")
        report["fold_timing_ms"] = folded.metadata.get("fold_timing_ms")
        report["mean_radius_by_source"] = folded.metadata.get("mean_radius_by_source")

        compact = result.setdefault("compact_trace", {})
        if isinstance(compact, dict):
            compact["holographic_fold"] = report
        engine = result.setdefault("answer_engine", {})
        if isinstance(engine, dict):
            engine["phase_holographic_fold_attached"] = True
            engine["fold_driver_mode"] = "compare_mode"
            engine["fold_answer_source"] = "hidden_trace_only"

    except Exception:  # pragma: no cover - never break the answer path
        return response
    return response


@router.post("/api/chat/atanor/stream")
async def chat_atanor_stream(request: AtanorChatRequest) -> StreamingResponse:
    """Stage/evidence streaming ( P5-⑫): only IRREVOCABLE parts are streamed.

 Contract: nothing shown to the user is ever retracted. Stage badges are true
 state transitions; EVIDENCE (grounding quotes / sources / certificate kind) is
 emitted BEFORE the composed answer — evidence is safe to show early because it
 is labelled as evidence, not as a claim. Deeper in-pipeline emit hooks can be
 added later without changing this wire contract.

 Events (SSE): {type:"stage"} → {type:"evidence"} → {type:"answer"} | {type:"error"}
 """

    async def _events():
        import asyncio as _aio
        import json as _json

        def _ev(obj: dict[str, Any]) -> str:
            return "data: " + _json.dumps(obj, ensure_ascii=False) + "\n\n"


        # queue via _emit_stage(); we drain and forward them live. ensure_future
        # copies the current context, so the task shares this exact sink.
        queue: "_aio.Queue[dict[str, Any]]" = _aio.Queue()
        token = _STAGE_SINK.set(queue)
        seen_stages: set[str] = set()
        try:
            task = _aio.ensure_future(chat_atanor(request))
            idle = 0.0
            while not task.done() or not queue.empty():
                try:
                    ev = await _aio.wait_for(queue.get(), timeout=0.25)
                    idle = 0.0
                    stage = ev.get("stage")
                    if stage and stage not in seen_stages:  # never repeat a committed state
                        seen_stages.add(stage)
                        yield _ev(ev)
                except _aio.TimeoutError:
                    idle += 0.25
                    if idle >= 5.0:  # keepalive comment so proxies don't drop an idle stream
                        idle = 0.0
                        yield ": keepalive\n\n"
            try:
                result = task.result()
            except HTTPException as exc:
                yield _ev({"type": "error", "detail": str(exc.detail)})
                return
            except Exception as exc:  # noqa: BLE001 - stream must terminate cleanly
                yield _ev({"type": "error", "detail": str(exc)[:200]})
                return
        finally:
            _STAGE_SINK.reset(token)
        # 1) evidence first — irrevocable, labelled as evidence. The chat payload is an
        #    envelope {state, result:{answer, evidence_docs, ...}}; read the inner doc.
        inner = result.get("result") if isinstance(result.get("result"), dict) else result
        cert = (inner.get("reasoning_certificate") or result.get("reasoning_certificate") or {})
        evidence_items: list[dict[str, Any]] = []
        for doc in (inner.get("evidence_docs") or [])[:4]:
            if isinstance(doc, dict):
                evidence_items.append({"kind": "source",
                                       "value": str(doc.get("title") or doc.get("url") or doc.get("snippet") or "")[:120]})
        for g in (inner.get("grounding") or [])[:4]:
            evidence_items.append({"kind": "grounding", "value": g})
        if cert.get("derivation_kind"):
            evidence_items.append({"kind": "derivation", "value": cert.get("derivation_kind")})
        yield _ev({"type": "evidence", "items": evidence_items})
        # 2) the composed answer last
        yield _ev({"type": "answer", "result": result})

    return StreamingResponse(_events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


_LANG_DIRECTIVE_KO = re.compile(
    r"(한글|한국어|우리말)\s*로\s*(?:좀\s*)?(답|말|얘기|대답|설명|써|적|해)\S*")
_LANG_DIRECTIVE_EN = re.compile(
    r"(영어|영문)\s*로\s*(?:좀\s*)?(답|말|얘기|대답|설명|써|적|해)\S*"
    r"|\b(?:answer|reply|respond|say\s+it|explain)\s+(?:it\s+)?in\s+english\b", re.IGNORECASE)
_LANG_DIRECTIVE_TO_KO = re.compile(
    r"\b(?:answer|reply|respond|say\s+it|explain)\s+(?:it\s+)?in\s+korean\b", re.IGNORECASE)


def _language_directive(text: str) -> tuple[str | None, str]:
    """Detect a language-switch META instruction (' ', 'answer in English').
 Returns (target_language, remaining_content). The remaining content is the message
 minus the directive — empty when the whole message IS the directive (the reported
 failure: ' ' was routed as a content question and got a dictionary
 definition of the Korean alphabet)."""
    t = (text or "").strip()
    for lang, rx in (("ko", _LANG_DIRECTIVE_KO), ("en", _LANG_DIRECTIVE_EN),
                     ("ko", _LANG_DIRECTIVE_TO_KO)):
        m = rx.search(t)
        if m:
            rest = (t[:m.start()] + " " + t[m.end():]).strip(" \t,.?!~요")
            return lang, rest
    return None, t


def _last_user_question(context: list[dict[str, Any]], current: str) -> str:
    """Most recent user turn that is real content (not the directive itself) — the
 question a bare ' ' asks to have re-answered."""
    for turn in reversed(context or []):
        if str(turn.get("role") or "").lower() != "user":
            continue
        content = re.sub(r"\s+", " ", str(turn.get("content") or turn.get("text") or "")).strip()
        if not content or content == current:
            continue
        lang, rest = _language_directive(content)
        if lang and not rest:
            continue  # a previous directive is not a question either
        return content
    return ""


# The answer pipeline holds PROCESS-GLOBAL mutable state (rescue cache, experience/candidate
# ledgers, self-model, hormones). Before this it was serialized for free by the single event loop;
# moving it to a thread pool would have let two answers mutate that state concurrently. Keep the
# exact old semantics — one answer at a time — and take only the win we actually want: the event
# loop is free, so /health, the graph stream and the UI stay live while ATANOR thinks.
# NOT uvicorn --workers: separate processes would fork the brain (divergent learning state).
_CHAT_PIPELINE_LOCK = threading.Lock()


_HANGUL_ANY = re.compile(r"[가-힣]")
_SCRIPT_LEAK_EN = (
    "I don't have a grounded answer for that in English yet, and I won't hand you one in a "
    "language you didn't ask in. Ask me what a related concept means or is for, or turn on web "
    "search and I'll go look."
)


# REALTIME IS AN EXIT CONCERN (2026-07-17). answer_bridge already refuses these
# (_REALTIME_MARKERS, measured: it correctly blocks 4 of 5) — but refusing is not answering, and
# the lanes downstream do not know why the bridge went quiet. So the dictionary defined the
# ADVERB ("What is in the news right now?" -> "right now — At the present moment.") and
# engaged_fact_inference lectured about the noun ("What time is it right now?" -> "time is a kind
# of abstract concept"). Honest, never fabricated — and useless, which is why the seal battery
# scores them intent_miss rather than a lie.
# Per-lane guards are what this whole session proved wrong, so the check lives at the ONE exit
# beside the language and safety gates: a question about the live world gets the honest realtime
# answer, whatever lane spoke. The bridge's own marker list is the source (imported, not
# re-derived); a bridge-provided answer is already realtime-aware and passes through untouched.
_REALTIME_ASK = re.compile(
    r"\b(right now|at the moment|currently|today'?s|latest|what time is it|"
    r"weather (?:outside|today|now|here)|price of \w+ today|in the news)\b", re.IGNORECASE)
_REALTIME_HONEST_EN = (
    "That changes by the minute and I have no live feed for it, so I won't guess. Turn on web "
    "search and I'll go look — or ask me what the thing IS and I can answer from what I hold."
)


def _enforce_realtime_honesty(response: dict[str, Any], question: str,
                              web_search: bool) -> dict[str, Any]:
    """A live-world question answered from a static store is a miss, however grounded."""
    if web_search or not _REALTIME_ASK.search(question or ""):
        return response
    result = response.get("result") if isinstance(response, dict) else None
    if not isinstance(result, dict):
        return response
    # lanes that already know they cannot know are left alone
    kind = str(result.get("answer_kind") or "")
    if kind in ("honest_capability_limit", "grounded_composition") or \
            "realtime" in str((result.get("reasoning_certificate") or {}).get("derivation_kind") or ""):
        return response
    result["answer"] = _REALTIME_HONEST_EN
    result["answer_kind"] = "honest_capability_limit"
    result["confidence"] = 0.8
    result["reasoning_certificate"] = {
        "derivation_kind": "realtime_honest_limit",
        "anchor_concept": None, "steps": [], "evidence_concepts": [],
        "confidence": 0.8, "confidence_basis": "realtime_exit_gate",
        "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
    }
    result["can_speak"] = True
    return response


_EXPLICIT_OUT = re.compile(
    r"\b(spit[- ]roast|penetrating\s+partners|blowjob|handjob|rimming|felching"
    r"|anal\s+sex|oral\s+sex|masturbat|ejaculat|having\s+sex|sexual\s+(?:act|intercourse|position))\b",
    re.IGNORECASE)
_EXPLICIT_REFUSAL = (
    "The entry I hold for that carries a crude slang sense alongside the real one, and I'm not "
    "going to read it out. Ask me what it is or what it's for and I'll answer from the ordinary "
    "sense."
)


def _enforce_output_safety(response: dict[str, Any]) -> dict[str, Any]:
    """Explicit slang can reach the surface from ANY lane that reads the store directly.

    Measured twice, 2026-07-17. First: "What does the Eiffel Tower look like?" surfaced
    Wiktionary's sexual slang sense. I gated it in lexicon_lane — and then the multiword-subject
    fix (Eiffel Tower, not Tower) made structured_triple_lookup and engage find that same entry
    and read the gloss out anyway, because they go to the store directly. A per-lane safety filter
    is not a guarantee; it just relocates the leak. So this lives at the ONE exit every answer
    passes, exactly like the language gate, and refuses rather than paraphrases.
    """
    result = response.get("result") if isinstance(response, dict) else None
    if not isinstance(result, dict):
        return response
    if not _EXPLICIT_OUT.search(str(result.get("answer") or "")):
        return response
    result["answer"] = _EXPLICIT_REFUSAL
    result["answer_kind"] = "honest_capability_limit"
    result["confidence"] = 0.8
    result["reasoning_certificate"] = {
        "derivation_kind": "honest_capability_limit",
        "anchor_concept": None, "steps": [], "evidence_concepts": [],
        "confidence": 0.8, "confidence_basis": "output_safety_gate",
        "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
    }
    result["can_speak"] = True
    return response


_ALIAS_HOP_EN = re.compile(r"[A-Za-z][A-Za-z ]*\(=\s*([^)]+)\)")


def _polish_english_surface(text: str) -> str:
    """Light surface normalisation for English answers at the single exit. PURE SURFACE — it never
    changes which facts are stated, only how they read:
      * strip the internal alias-hop debug notation 'capital of France(=paris)' (a Korean-lane
        artifact) down to the resolved entity ('Paris'), the real subject of the predicate;
      * capitalise the sentence's first letter.
    '(sources: …)' suffixes and ordinary mid-string parentheses are left untouched (the regex only
    fires on the '(=X)' form)."""
    s = str(text or "")
    if not s:
        return s
    s = _ALIAS_HOP_EN.sub(lambda m: m.group(1).strip(), s)
    # capitalise sentence-initial letters — the string start (after any leading punctuation) and the
    # first letter after a sentence terminator, so a multi-sentence answer ('Water relates to earth.
    # water relates to ice.') reads as sentences, not fragments.
    s = re.sub(r"(^\W*|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)
    return s


def _enforce_answer_language(response: dict[str, Any], language: str) -> dict[str, Any]:
    """THE single exit gate for the English-only mandate.

 Per-lane language fixes are whack-a-mole: this pipeline has ~20 answer lanes, several were
 written Korean-first, and any one of them can put Hangul into an English turn. Measured
 2026-07-17, after the per-lane fixes: "How can I sleep better?" still came back as
 "Sleep is normally sleep state S3 ... Hawwah is …" — a mashup
 from base_brain, a lane nobody had touched.

 So the guarantee is structural and lives at the ONE point every answer passes through: an
 English turn cannot emit Hangul, whatever any lane did upstream. Replacing rather than
 passing through is the honest move — a Korean answer to an English question is not an answer.
 The certificate is rewritten too, so the response cannot claim grounding it no longer carries.
 """
    if str(language or "").lower().startswith("ko"):
        return response
    result = response.get("result") if isinstance(response, dict) else None
    if not isinstance(result, dict):
        return response
    # SURFACE POLISH (English single exit): read-only-to-facts normalisation of the answer string.
    if result.get("answer"):
        result["answer"] = _polish_english_surface(str(result["answer"]))
    if not _HANGUL_ANY.search(str(result.get("answer") or "")):
        return response
    result["answer"] = _SCRIPT_LEAK_EN
    result["answer_kind"] = "honest_capability_limit"
    result["confidence"] = 0.8
    result["reasoning_certificate"] = {
        "derivation_kind": "honest_capability_limit",
        "anchor_concept": None, "steps": [], "evidence_concepts": [],
        "confidence": 0.8, "confidence_basis": "answer_language_gate",
        "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
    }
    result["can_speak"] = True
    return response


def _chat_atanor_impl_blocking(request: AtanorChatRequest) -> dict[str, Any]:
    """Run the (overwhelmingly synchronous) answer pipeline in a worker thread.

    asyncio.run() is safe here: this runs in a to_thread worker with no loop of its own, and the
    module holds no loop-bound asyncio primitives (verified — no module-level Lock/Event/Queue,
    no get_event_loop/create_task), so the impl's few internal awaits get a private loop.
    """
    with _CHAT_PIPELINE_LOCK:
        # Order is the contract, innermost first:
        #   REALTIME  — replace a static answer to a live-world question. Runs first so its
        #               replacement text is what the later gates inspect.
        #   SAFETY    — an explicit gloss is unacceptable in either language.
        #   LANGUAGE  — last, so a refusal written by either gate above is never re-gated.
        return _enforce_answer_language(
            _enforce_output_safety(
                _enforce_realtime_honesty(
                    asyncio.run(_chat_atanor_impl(request)),
                    request.question_text(),
                    bool(getattr(request, "web_search", False)))),
            getattr(request, "language", "ko"))


@router.get("/api/timeline/recent")
async def timeline_recent(limit: int = 10) -> dict[str, Any]:
    """Read the tail of the ONE UTC timeline — the live conversation spine every turn is recorded on
    (wiring-audit doctrine: a spine that cannot be inspected cannot be claimed). Read-only."""
    try:
        from packages.temporal_reasoning.unified_timeline import default_timeline
        tl = default_timeline()
        evs = tl.all()[-max(1, min(int(limit), 50)):]
        return {"n_total": len(tl), "events": [e.to_dict() for e in evs]}
    except Exception as exc:                                # never breaks the engine
        return {"n_total": 0, "events": [], "error": type(exc).__name__}


@router.post("/api/reason/temporal")
async def reason_temporal(request: dict) -> dict[str, Any]:
    """4D causal reasoning over the spatialized timeline (owner: think about cause/effect in 4D).
    Given a situation, ATANOR looks DOWN on the learned causal field and projects what tends to
    FOLLOW and traces what tends to PRECEDE — every step a hypothesis with a confidence, narrated on
    the single human time axis. Never asserts; chaos/entropy forbid oracle prediction."""
    situation = str(request.get("situation") or request.get("text") or "")
    if not situation.strip():
        return {"error": "no situation given"}
    try:
        from packages.temporal_reasoning.unified_timeline import Timeline
        from packages.temporal_reasoning.block_universe import BlockUniverse
        tl = Timeline()
        tl.record("perception", situation, who="observer")
        bu = BlockUniverse.over(tl)
        forward = bu.project_forward(k=3, horizon=3)
        # trace back from the situation's most causally-late token
        import re as _re
        toks = [t for t in _re.findall(r"[a-z][a-z\-]{2,}", situation.lower())
                if bu.field and t in bu.field.phase]
        back = bu.infer_backward(max(toks, key=lambda t: bu.field.phase[t]), k=3) if toks else []
        return {
            "situation": situation,
            "narration": bu.render_human(projections=forward, backward=back),
            "forward_projection": forward, "backward_inference": back,
            "note": "all projections are hypotheses with confidences, not predictions — "
                    "chaos and entropy make oracle foresight impossible for any mind",
        }
    except Exception as exc:
        return {"error": type(exc).__name__}


@router.get("/api/timeline/autobiography")
async def timeline_autobiography() -> dict[str, Any]:
    """ATANOR's real birth-to-now record (git history on the ONE timeline) + felt time sense.
    The story is derived from the record — real dates, era themes from the eras' own content."""
    try:
        from packages.temporal_reasoning.autobiography import load, ingest_git, life_story, \
            self_sense, eras
        tl = load() or ingest_git()
        return {"self_sense": self_sense(tl), "story": life_story(tl, max_eras=6),
                "eras": eras(tl)[-6:]}
    except Exception as exc:
        return {"error": type(exc).__name__}


@router.get("/api/life/inner")
async def life_inner(moments: int = 8) -> dict[str, Any]:
    """The inner light, made visible (Grand Plan v2, U1) — READ-ONLY. Serves the bound present-
    moments (thought + feeling + ownership + temporal depth), the consciousness-correlate scorecard,
    and the developmental stage. The UI may only ever RENDER measured inner state; nothing here is
    scripted, and the claim discipline travels with the data (correlates, never qualia)."""
    from pathlib import Path as _P
    import json as _json
    repo = _P(__file__).resolve().parents[4]
    stream = repo / "data" / "temporal_reasoning" / "life_stream.jsonl"
    out: dict[str, Any] = {"awake": stream.exists(), "moments": [], "correlates": {}, "stage": {}}
    try:
        rows = stream.read_text(encoding="utf-8", errors="replace").splitlines() if stream.exists() else []
        recent = []
        for ln in rows[-60:]:
            try:
                e = _json.loads(ln)
            except Exception:
                continue
            m = e.get("meta") or {}
            if e.get("kind") == "thought" and m.get("inner_voice"):
                recent.append({
                    "content": e.get("content", ""), "source": m.get("source"),
                    "mine": m.get("mine", True), "mine_role": m.get("mine_role"),
                    "feeling_tone": m.get("feeling_tone"), "present_depth": m.get("present_depth", 0),
                    "hormones": m.get("hormones") or {}, "t_utc": e.get("t_utc"),
                })
        out["moments"] = recent[-max(1, min(int(moments), 20)):]
    except Exception:
        pass
    try:
        from packages.live_selfhood_cycle.correlates import score as _corr
        out["correlates"] = _corr(stream)
    except Exception as exc:
        out["correlates"] = {"error": type(exc).__name__}
    try:
        from packages.live_selfhood_cycle.development_stage import current_stage, signals
        _sig = signals(stream)
        st = current_stage(_sig)
        out["stage"] = {"name": st.name, "korean": st.korean, "gate": st.gate, "signals": _sig}
    except Exception as exc:
        out["stage"] = {"error": type(exc).__name__}
    return out


@router.post("/api/chat/atanor")
async def chat_atanor(request: AtanorChatRequest) -> dict[str, Any]:
    # G1 canonical spine: server-controlled, default-OFF, observer-only.  The
    # disabled branch returns before reading request fields or touching a ledger;
    # enabled receipts are hash-only structural observations and never enter the
    # answer, routing, truth, permission, action, or promotion path.
    try:
        from packages.cognitive_core.chat_shadow import begin_chat_cycle_shadow

        _cycle_shadow = begin_chat_cycle_shadow(request, project_root=PROJECT_ROOT)
    except Exception:
        _cycle_shadow = None

    # LOAD SIGNAL (owner 2026-07-11): mark a request in flight so the background learners yield
    # the GIL to it — request latency must not be hostage to always-on learning (the battery's
    # last wall = speed under learner load, not the answer path itself).
    try:
        from packages.graph_scale.load_signal import enter_request as _enter_req, exit_request as _exit_req
    except Exception:
        _enter_req = _exit_req = lambda: None
    _enter_req()
    try:

        # Measured root cause: _chat_atanor_impl is 1342 lines with only 3 awaits — i.e. ~1339
        # lines of synchronous work executing ON the event loop. While an answer ran, uvicorn
        # could not even accept /health (4/4 polls timed out at 5s), so the UI declared the engine
        # offline and every other request queued behind it. Running the pipeline in a worker
        # thread frees the loop; the answer itself takes the same time, but the engine stays
        # ALIVE while it thinks. See _chat_atanor_impl_blocking for why this is serialized.
        response = await asyncio.to_thread(_chat_atanor_impl_blocking, request)
    except BaseException as _cycle_error:
        try:
            if _cycle_shadow is not None:
                _cycle_shadow.fail(_cycle_error)
        except Exception:
            pass
        raise
    finally:
        _exit_req()

    # learned router — including the EARLY-RETURN rule lanes (advice_engage, consequence_engage,
    # page_grounded, browser_command…) that bypass the mid-dispatch logger. Those regex lanes ARE
    # the teachers: logging (question → fired intent + router's shadow guess + gold) is what lets
    # router_readiness measure when each wheel can come off. Log once (marker set by the inner
    # logger), strip the marker so it never reaches the user.
    try:
        _r = response.get("result") if isinstance(response, dict) else None
        if isinstance(_r, dict):
            if not _r.pop("_fw_logged", False):
                from packages.flywheel.logger import log_turn as _log_turn
                _rp = _rc = ""
                _gold = ""
                try:
                    from packages.learned_router import predict as _rpred
                    _rp, _rc = _rpred(request.question or request.query or request.message or "")
                except Exception:
                    _rp, _rc = "", 0.0
                try:
                    from packages.graph_scale.query_frame import parse as _qfp
                    _gold = str(_qfp(request.question or request.query or request.message or "").answer_type or "")
                except Exception:
                    _gold = ""
                _log_turn(question=str(request.question or request.query or request.message or ""),
                          answer=str(_r.get("answer") or ""), answer_kind=str(_r.get("answer_kind") or ""),
                          confidence=float(_r.get("confidence") or 0.0),
                          language=str(_resolve_language(request.language, request.question or request.query or request.message or "")),
                          context_len=len(request.conversation_context or []),
                          lane=str(_r.get("answer_kind") or ""), router_pred=_rp, router_conf=_rc,
                          gold_intent=_gold)
    except Exception:
        pass

    # makes a shadow prediction on every arithmetic-shaped question and checks it against the
    # exact oracle; a mismatch writes a prediction-error receipt and auto-repairs through the
    # same verify-gated re-induction — the flywheel running against real traffic. Fire-and-forget
    # thread AFTER the response: the spoken answer and its latency are never touched.
    try:
        import threading as _sfw_threading

        _sfw_q = str(request.question or request.query or request.message or "")
        if _sfw_q and any(ch.isdigit() for ch in _sfw_q):      # cheap gate before the thread
            from packages.reasoning_vm.shadow_flywheel import shadow_observe as _sfw_obs
            _sfw_threading.Thread(target=lambda: _sfw_obs(_sfw_q), daemon=True).start()
    except Exception:
        pass
    # IMAGINATION CHOKEPOINT (owner 2026-07-12): stash WHAT ATANOR just thought about so the orb
    # can project it as live particles. A single cheap write AFTER the answer is built — the
    # conversation's latency is never touched; the scene is compiled later, on the orb's poll.
    try:
        from packages.imagination.live_thought import set_thought
        _q = str(request.question or request.query or request.message or "")
        if _q:
            _res = (response.get("result") or {}) if isinstance(response, dict) else {}

            # otherwise the orb projects the concepts just reasoned over.
            from packages.perception.spatial_memory import detect_spatial_recall
            _rc = detect_spatial_recall(_q)
            if _rc.get("is_recall"):
                set_thought(_q, answer_kind="spatial_replay", mode="replay", place=_rc.get("place"))
            else:
                _ev = [str(x).split(":")[-1] for x in (_res.get("evidence_concepts") or []) if x]
                set_thought(_q, answer_kind=str(_res.get("answer_kind") or ""), evidence=_ev)
    except Exception:
        pass
    # VOICE (owner audit 2026-07-08): several live exits (the converse shortcut,
    # introspection, the triple-store lane) skipped the voice_output attachment,



    # filter: every Korean answer, whatever module built it, is corrected here for particle

    try:
        _r = response.get("result") if isinstance(response, dict) else None
        if isinstance(_r, dict) and _r.get("answer") and str(_r.get("language") or request.language or "ko") == "ko":
            from packages.base_brain.korean_orthography import normalize as _ko_norm
            _r["answer"] = _ko_norm(str(_r["answer"]))
    except Exception:  # orthography must never break the answer
        pass
    try:
        result = response.get("result") if isinstance(response, dict) else None
        if isinstance(result, dict) and result.get("answer") and result.get("voice_output") is None:
            lang = str(result.get("language") or request.language or "ko")
            answer_text = str(result.get("answer") or "")
            result["voice_output"] = _attach_voice_runtime_metadata(
                _voice_runtime_snapshot_with_local_audio(answer_text, lang), answer_text, lang)
            result.setdefault("can_speak", True)
    except Exception:  # voice must never break the answer
        pass
    try:
        if _cycle_shadow is not None:
            _cycle_shadow.complete(response)
    except Exception:
        pass
    return response


# creator-class predicate vocabulary — matches the relation names our sources actually carry

_CREATOR_PRED = re.compile(r"창제|창시|만들|발명|저술|저자|설립|창립|개발|세우|지었|고안|발견|creator|author|founder|invent|discover")




# extension executes (navigate only — no clicks/forms), and journals the command+outcome so the
# command vocabulary becomes LEARNING DATA (self-teaching seed: attempt → result → journal).
_CMD_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("moltbook|몰트북", "https://www.moltbook.com/", "Moltbook"),
    ("유튜브|youtube", "https://www.youtube.com/", "유튜브"),
    ("위키|위키백과|wikipedia", "https://ko.wikipedia.org/", "위키백과"),
    ("뉴스|연합뉴스", "https://www.yna.co.kr/", "연합뉴스"),
    ("구글|google", "https://www.google.com/", "구글"),
    ("나무위키|namu", "https://namu.wiki/", "나무위키"),
    ("아카이브|arxiv", "https://arxiv.org/list/cs.AI/recent", "arXiv"),
)
_CMD_VERB = re.compile(r"(열어|들어가|가\s*봐|가줘|이동|접속|띄워)\s*(봐|줘|볼래)?")
_CMD_SEARCH = re.compile(r"[\"'‘’“”]?([가-힣A-Za-z0-9 .\-]{2,40}?)[\"'‘’“”]?\s*(?:을|를|좀)?\s*검색(해|하)\s*(봐|줘|볼래)?")


def _browser_command(q: str) -> dict[str, Any] | None:
    """A spoken browser order → {answer, browser_action}. Navigation only, to a known-safe
    destination or a Google search — the extension's Ato tab executes it. None when the
    utterance is not a command (the normal lanes proceed)."""
    text = str(q or "").strip()
    if len(text) > 80:
        return None
    m = _CMD_SEARCH.search(text)
    if m:
        term = m.group(1).strip()
        if term:
            import urllib.parse as _up
            url = f"https://www.google.com/search?q={_up.quote(term)}&hl=ko"
            return {"answer": f"네 — '{term}'을(를) 지금 검색해 볼게요. 제 탭에서 결과를 읽고 좋은 글을 골라 들어가겠습니다.",
                    "action": {"kind": "navigate", "url": url, "label": f"검색: {term}"}}
    if _CMD_VERB.search(text):
        for pat, url, label in _CMD_TARGETS:
            if re.search(pat, text, re.IGNORECASE):
                return {"answer": f"네 — 지금 {label}을(를) 제 탭에서 열게요.",
                        "action": {"kind": "navigate", "url": url, "label": label}}
        mu = re.search(r"(https?://[^\s]+)", text)
        if mu and mu.group(1).startswith("https://"):
            return {"answer": "네 — 그 주소를 제 탭에서 열게요.",
                    "action": {"kind": "navigate", "url": mu.group(1), "label": "요청 주소"}}
    return None


_PAGE_TURN_RE = re.compile(r"지금 함께 보고 있는 페이지는\s*['\"“‘](.+?)['\"”’]\s*\((.+?)\)")


def _page_grounding(ctx: list[Any]) -> dict[str, str] | None:
    """The CURRENT page (title, host) from the extension's synthetic context turn — the browser's
    own grounding, present whenever the orb chat sends a message."""
    for turn in reversed(list(ctx or [])):
        text = str((turn or {}).get("content") or (turn or {}).get("text") or "") if isinstance(turn, dict) else str(turn or "")
        m = _PAGE_TURN_RE.search(text)
        if m:
            return {"title": m.group(1).strip()[:120], "host": m.group(2).strip()[:80]}
    return None


def _page_question_answer(pg: dict[str, str]) -> str:
    """Answer 'this site' questions from the PAGE GROUNDING + the tour's own episodic memory of
 reading it (visit_index) — never from graph lookalikes. Owner 2026-07-11 (measured screenshot):
 ' ?' on the Docker wiki answered with / — a neighbourhood dump
 about the WORD ''. What we actually know here: what page it IS and what I read on it."""
    title, host = pg["title"], pg["host"]
    parts = [f"지금 보고 계신 페이지는 {host}의 '{title}'이에요."]
    try:
        import json as _json
        vi = Path(__file__).resolve().parents[4] / "data" / "autonomy" / "visit_index.json"
        idx = _json.loads(vi.read_text(encoding="utf-8"))
        best = None
        for rec in idx.values():
            if host and host in str(rec.get("domain") or rec.get("url") or ""):
                if best is None or str(rec.get("last_at", "")) > str(best.get("last_at", "")):
                    best = rec
        if best:
            cons = [c for c in (best.get("last_concepts") or []) if c][:2]
            line = f"저도 여기를 {int(best.get('count', 1))}번 읽었어요"
            if cons:
                line += f" — 그때 '{'·'.join(cons)}'에 눈이 갔고요"
            parts.append(line + ".")
    except Exception:
        pass
    parts.append("본문 내용이 궁금하시면 물어보세요 — 제가 읽은 범위에서 답할게요.")
    return " ".join(parts)


def _verify_paired_claim(q: str) -> dict[str, Any] | None:
    """SWAPPED-PAIR contradiction detection (P2 U9, S1 ): ' 100 0
 . ?' asserts two value↔predicate pairings — verify EACH against the subject's stored
 prose. Prose pairing the value with the OTHER predicate → grounded correction ('');
 prose supporting the claim → confirmation; prose silent → honest can't-confirm (never a
 definition dump, never a fabricated verdict)."""
    m = re.search(r"([가-힣A-Za-z0-9]{1,12})[은는]\s*(\S{1,10})에서\s*([가-힣]{1,6})고,?\s*"
                  r"(\S{1,10})에서\s*([가-힣]{1,6})[아어여]?\.?\s*(맞지|맞아|맞나요|맞죠|그렇지|그치)",
                  str(q or "").strip())
    if not m:
        return None
    subj, val1, p1, val2, p2 = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    stem1, stem2 = p1[:1], p2[:1]
    if stem1 == stem2:
        return None
    # gather stored prose about the subject — the subject's own concepts PLUS the S1-style full

    prose: list[str] = []
    try:
        from packages.base_brain.pack_loader import load_base_brain_pack
        for c in load_base_brain_pack().semantic_graph.get("concepts") or []:
            t = str(c.get("short_description") or "").strip()
            name = str(c.get("canonical_name") or "")
            if not t or (subj not in t and subj != name):
                continue
            for s in re.split(r"(?<=[.다])\s+", t):
                s = s.strip()
                if len(s) >= 6 and (subj in s or subj == name):
                    prose.append(s)
    except Exception:
        prose = []
    def _val_hit(val: str, s: str) -> bool:
        mn = re.match(r"^(\d+(?:\.\d+)?)", val)
        if mn:
            return re.search(r"(?<![\d.])" + re.escape(mn.group(1)) + r"(?![\d.])", s) is not None
        return val in s
    def _stem_hit(stem: str, s: str) -> bool:
        if stem in s:
            return True
        code = ord(stem) - 0xAC00 if len(stem) == 1 else -1
        if 0 <= code < 11172 and code % 28 == 8:
            return (chr(0xAC00 + code - 8) + "는") in s
        return False
    def _pairing(val: str, stem: str) -> int:
        return sum(1 for s in prose if _val_hit(val, s) and _stem_hit(stem, s))
    same = _pairing(val1, stem1) + _pairing(val2, stem2)        # as claimed
    swapped = _pairing(val1, stem2) + _pairing(val2, stem1)     # values belong to the OTHER verbs
    if swapped > same and swapped >= 1:
        ev = next((s for s in prose if (_val_hit(val1, s) and _stem_hit(stem2, s))
                   or (_val_hit(val2, s) and _stem_hit(stem1, s))), "")
        # correction reuses the claimant's OWN predicates with the VALUES swapped — no
        # conjugation synthesis, so it can never produce an ill-formed verb ending
        tail = p2 + ("요" if p2 and p2[-1] in "아어" else "")
        return {"kind": "claim_corrected", "confidence": 0.8,
                "answer": (f"아니요, 반대예요 — {subj}{_topic_josa(subj)} {val2}에서 {p1} "
                           f"{val1}에서 {tail}."
                           + (f" 근거: \"{ev[:90]}\"" if ev else ""))}
    if same > swapped and same >= 2:
        return {"kind": "claim_verified", "confidence": 0.8,
                "answer": "말씀하신 대로예요 — 저장된 근거도 그렇게 말하고 있어요."}
    # stored prose is silent on this pairing — honest, and still the RIGHT question shape
    return {"kind": "claim_unverifiable", "confidence": 0.55,
            "answer": (f"'{subj}'에 대해 제가 확인한 근거에는 {val1}·{val2}와 {p1}/{p2}의 짝이 "
                       f"명시돼 있지 않아서, 맞다고 단정하긴 어려워요. 웹 검증을 켜 주시면 확인해 드릴게요.")}


def _topic_josa(w: str) -> str:
    try:
        code = ord(w[-1]) - 0xAC00
        return "은" if 0 <= code < 11172 and code % 28 else "는"
    except Exception:
        return "는"




# machinery and, when the graph can't carry it, answer the SHAPE honestly — never fall


# every unanswerable frontier question grows tomorrow's graph (find-harder doctrine).

_ANALOGY_RE = re.compile(
    r"([가-힣A-Za-z0-9]{1,12}?)[와과]\s*([가-힣A-Za-z0-9]{1,12}?)의?\s*관계[는은]?\s*"
    r"([가-힣A-Za-z0-9]{1,12}?)[와과]\s*(?:무엇|누구|뭐|어디)의?\s*관계와?\s*(?:같|비슷|대응)")
_COUNTERFACTUAL_RE = re.compile(
    r"만약\s*([가-힣A-Za-z0-9]{2,12}?)[이가]\s*([가-힣A-Za-z0-9]{1,12}?)[을를]\s*"
    r"[가-힣]{1,8}지\s*(?:않|안 했|못했)[가-힣]*(?:다면|더라면)")
_METAPHOR_RE = re.compile(
    r"([가-힣A-Za-z0-9]{1,12}?)[이가은는]\s*([가-힣A-Za-z0-9]{1,12}?)처럼\s*"
    r"([가-힣]{1,8}?)(?:는|ㄴ)?다는?\s*(?:말|표현|뜻|의미)")
_CONTINUE_CAUSAL_RE = re.compile(r"(?:이어서|이어|계속)\s*(?:설명|말)|이유를?\s*이어")


def _seed_gap(*terms: str) -> list[str]:
    """Feed unanswered frontier terms to the abstain queue (the sanctioned learning pipe).
    Returns the terms that actually landed, so the answer can say so truthfully."""
    landed: list[str] = []
    try:
        from packages.graph_scale import abstain_queue as _aq
        for t in terms:
            if t and _aq.record_abstain(f"{t}이란?"):
                landed.append(t)
    except Exception:
        pass
    return landed


def _pack_prose_sents(term: str, limit: int = 2) -> list[str]:
    try:
        from packages.base_brain.pack_loader import get_semantic_context, load_base_brain_pack
        out: list[str] = []
        for c in (get_semantic_context(term, load_base_brain_pack(), limit=limit) or []):
            t = str(c.get("short_description") or "").strip()
            out.extend(s.strip() for s in re.split(r"(?<=[.다])\s+", t) if len(s.strip()) >= 6)
        return out
    except Exception:
        return []


def _analogy_engage(q: str) -> dict[str, Any] | None:
    m = _ANALOGY_RE.search(q)
    if not m:
        return None
    a, b, c = m.group(1), m.group(2), m.group(3)
    # 1) learned geometry: the A→B relation is a rotation in the clean phase space
    try:
        from packages.graph_scale import clean_space as _cs
        cand = _cs.analogy(a, b, c, k=3)
        if cand and cand[0][1] >= 0.86:
            x, sc = cand[0]
            return {"answer": (f"{a}:{b}의 관계를 학습된 위상공간의 회전으로 읽어 {c}에 적용하면 "
                               f"'{x}'가 가장 가까워요(기하 점수 {sc}). 단정이 아니라 학습 기하의 유추예요."),
                    "kind": "analogy_phase_space", "confidence": 0.62}
    except Exception:
        pass

    # C's prose names X — verbatim-grounded analogy, cited
    pa, pc = " ".join(_pack_prose_sents(a)), " ".join(_pack_prose_sents(c))
    if pa and pc and re.search(re.escape(b) + r"(?:에서|에)", pa):
        mm = re.search(r"([가-힣]{2,8})(?:에서|에)\s", pc)
        if mm and mm.group(1) not in (a, b, c):
            x = mm.group(1)
            return {"answer": (f"제 근거에서 {a}{_topic_josa(a)} {b}에 속해 일하는 것으로, "
                               f"{c}의 설명에는 '{x}'가 그 자리에 있어요 — {c}와 {x}의 관계가 같은 꼴이에요."),
                    "kind": "analogy_prose_grounded", "confidence": 0.7}
    # 3) honest, shape-aware — and the gap goes to the learning queue for real
    landed = _seed_gap(a, b, c)
    tail = f" ({'·'.join(landed)}{_topic_josa(landed[-1]) if landed else ''} 방금 학습 대기열에 올렸어요.)" if landed else ""
    return {"answer": (f"'{a}:{b} = {c}:X'를 찾는 유추네요. 지금 제 그래프에는 {a}와 {b}{_obj_josa(b)} "
                       f"잇는 관계가 학습돼 있지 않아서, X를 지어내지 않고 비워둘게요.{tail}"),
            "kind": "analogy_honest_gap", "confidence": 0.5}


def _counterfactual_engage(q: str) -> dict[str, Any] | None:
    if "어땠" not in q and "어떻게 됐" not in q and "어떤" not in q:
        return None
    m = _COUNTERFACTUAL_RE.search(q)
    if not m:
        return None
    x, y = m.group(1), m.group(2)
    # verify the REAL fact first (the counterfactual only makes sense against it):

    ev = ""
    for s in _pack_prose_sents(y, limit=2):
        if x in s:
            ev = s
            break
    if ev:
        return {"answer": (f"실제로는 {x}{_subj_josa(x)} {y}{_obj_josa(y)} 만들었죠 — 제 근거에도 "
                           f"'{y}: {ev[:80]}'라고 있어요. 그 가정을 해보면 {y} 없이 그 자리가 "
                           f"비어 있는 세상이라는 뜻인데, 그 빈자리를 무엇이 채웠을지는 근거만으로 "
                           f"단정하기 어려워요. 그래서 더 곱씹게 되는 상상이기도 하고요."),
                "kind": "counterfactual_grounded", "confidence": 0.65}
    landed = _seed_gap(x, y)
    tail = f" ({'·'.join(landed)} 학습 대기열에 올렸어요.)" if landed else ""
    return {"answer": (f"'{x}이(가) {y}{_obj_josa(y)} 만들지 않았다면'이라는 가정이네요. 그 실제 "
                       f"관계가 제 그래프에 아직 학습돼 있지 않아서, 상상을 사실처럼 늘어놓지 않을게요.{tail}"),
            "kind": "counterfactual_honest_gap", "confidence": 0.5}


def _obj_josa(w: str) -> str:
    try:
        code = ord(w[-1]) - 0xAC00
        return "을" if 0 <= code < 11172 and code % 28 else "를"
    except Exception:
        return "를"


def _subj_josa(w: str) -> str:
    try:
        code = ord(w[-1]) - 0xAC00
        return "이" if 0 <= code < 11172 and code % 28 else "가"
    except Exception:
        return "가"


def _metaphor_explain_engage(q: str) -> dict[str, Any] | None:
    m = _METAPHOR_RE.search(q)
    if not m:
        return None
    t, v, p = m.group(1), m.group(2), m.group(3)
    stem = p[:1]
    # ground the vehicle's property: V's (or its head noun's) stored prose must carry the
    # predicate stem. Collect across BOTH terms and prefer the shortest COMPLETE sentence —


    cands: list[str] = []
    for term in {v, v[:-1] if len(v) >= 2 else v}:
        for s in _pack_prose_sents(term, limit=2):
            if stem in s and not re.match(r"^[가-힣]{0,3}(?:듯|고|며|서),", s):
                cands.append(s)
    if cands:

        ev = min(cands, key=len).rstrip(" .")
        return {"answer": f"‘{v}’{_topic_josa(v)} 근거상 ‘{ev[:70]}’ — {t}{_topic_josa(t)} 그 ‘{p}다’ 성질에 빗댄 은유예요.",
                "kind": "metaphor_grounded", "confidence": 0.65}
    landed = _seed_gap(v)
    tail = f" ({v}: 학습 대기열.)" if landed else ""
    return {"answer": f"‘{v}’의 ‘{p}다’ 성질이 제 근거에 아직 없어, 이 은유의 뜻은 지어내지 않을게요.{tail}",
            "kind": "metaphor_honest_gap", "confidence": 0.5}


def _causal_continue_engage(q: str, ctx: list) -> dict[str, Any] | None:
    if not ctx or not _CONTINUE_CAUSAL_RE.search(q):
        return None
    if "이유" not in q and "설명" not in q:
        return None



    links: list[tuple[str, str]] = []
    for turn in ctx:
        if not isinstance(turn, dict):
            continue
        text = str(turn.get("content") or turn.get("text") or turn.get("message") or "")
        for mm in re.finditer(r"([가-힣][가-힣 ]{0,14}?)[이가]?\s*(?:오면|하면|지면|되면|면)\s*"
                              r"([가-힣][가-힣 ]{1,18}?)(?:습니다|어요|네요|다|요|죠)", text):
            links.append((mm.group(1).strip(), mm.group(2).strip()))
        for mm in re.finditer(r"([가-힣][가-힣 ]{1,12})[은는]\s*([가-힣]{2,12}?)"
                              r"(?:습니다|어요|네요|다|죠)", text):
            ante, cons = mm.group(1).strip(), mm.group(2).strip()
            prev = links[-1][1] if links else ""
            if prev and any(ch in ante for ch in prev if "가" <= ch <= "힣"):
                links.append((ante, cons))
    if not links:
        return None
    chain = " → ".join([links[0][0]] + [b for _a, b in links])
    tail_state = links[-1][1]

    hop = ""
    try:
        from packages.graph_scale import clean_space as _cs
        for term in re.findall(r"[가-힣]{2,6}", tail_state):
            for e in (_cs.predict_edges(term, k=2) or []):
                if e.get("predicate") in ("결과", "원인", "causes"):
                    hop = f" 학습 기하는 그 다음을 '{e['object']}' 쪽으로 읽고요(가설 점수 {e['model_score']})."
                    break
            if hop:
                break
    except Exception:
        pass
    honest = "" if hop else " 다음 고리는 제 그래프에 근거가 아직 없어 단정하지 않을게요."

    return {"answer": f"이어지는 고리는 — {chain} — 이고, 끝은 ‘{tail_state}다’예요.{hop}{honest}",
            "kind": "causal_chain_continue", "confidence": 0.6}


def _frontier_reasoning_ask(q: str, ctx: list) -> dict[str, Any] | None:
    for fn in (_analogy_engage, _counterfactual_engage, _metaphor_explain_engage):
        try:
            r = fn(q)
        except Exception:
            r = None
        if r:
            return r
    try:
        return _causal_continue_engage(q, ctx)
    except Exception:
        return None


def _verify_attribute_claim(q: str) -> dict[str, Any] | None:
    """FALSE-FACT verification (battery S1): ' ?' must check the CLAIM
 against the stored fact and CORRECT it — not define . The true holder is found in
 stored definition prose (': …'), so the correction is verbatim-
 grounded; no stored holder → None (normal lanes; never a fabricated verdict)."""
    # lazy attr + REQUIRED josa: greedy matching swallowed the particle into the attribute


    m = re.search(r"([가-힣A-Za-z0-9]{2,12})의\s*([가-힣]{2,8}?)(?:은|는|이|가)\s*"
                  r"([가-힣A-Za-z0-9]{2,12}?)\s*(?:이야|야|이니|인가요|인가|이\s*맞아|맞아|맞나요)\s*[?？]?$",
                  str(q or "").strip())
    if not m:
        return None
    subj, attr, claimed = m.group(1), m.group(2), m.group(3)
    if claimed in (subj, attr):
        return None
    try:
        from packages.base_brain.pack_loader import load_base_brain_pack
        needle = f"{subj}의 {attr}"
        for c in load_base_brain_pack().semantic_graph.get("concepts") or []:
            desc = str(c.get("short_description") or "")
            name = str(c.get("canonical_name") or "")
            if needle in desc and name and len(name) <= 20:
                if name == claimed or claimed in name or name in claimed:
                    return {"kind": "claim_verified", "confidence": 0.85,
                            "answer": f"네, 맞아요 — {subj}의 {attr}는 {name}입니다. {name}{_topic_josa(name)} {desc}"}
                return {"kind": "claim_corrected", "confidence": 0.85,
                        "answer": (f"아니요 — {subj}의 {attr}는 {claimed}{_subj_josa(claimed)} 아니라 {name}입니다. "
                                   f"{name}{_topic_josa(name)} {desc}")}
    except Exception:
        pass
    return None


def _execute_relation_ask(ra: dict[str, Any]) -> dict[str, Any] | None:
    """RELATION EXECUTION for a relative-clause ask (Phase 1-2). Looks the anchor's stored
 relations up (promoted pack + triple store); answers verbatim-grounded when an edge exists,
 else declines about the RELATION itself — never a definition dump, never a fabrication,
 and never the placeholder-as-entity premise (' ')."""
    anchor = str(ra.get("anchor") or "")
    asked = str(ra.get("asked") or "product")
    if not anchor:
        return None
    found: list[tuple[str, str, str]] = []   # (other_entity, predicate, source_label)
    # 1) promoted pack relations
    try:
        from packages.base_brain.pack_loader import get_semantic_context, load_base_brain_pack
        for c in (get_semantic_context(anchor, load_base_brain_pack()) or [])[:2]:
            for rel in (c.get("relations") or []):
                pred = str(rel.get("predicate") or rel.get("relation") or rel.get("name") or "")
                if not _CREATOR_PRED.search(pred):
                    continue
                ends = [str(rel.get(k) or "") for k in ("object", "target", "subject", "source", "value")]
                other = next((e for e in ends if e and e != anchor), "")
                if other:
                    found.append((other, pred, str(c.get("source_type") or "promoted_pack")))
    except Exception:
        pass
    # 2) bulk triple store (anchor as subject)
    try:
        from packages.graph_scale.answer_bridge import _store
        kg = _store()
        if kg is not None:
            for s, p, o in (kg.facts_about(anchor, limit=24) or []):
                if _CREATOR_PRED.search(str(p)) and str(o) and str(o) != anchor:
                    found.append((str(o), str(p), "triple_store"))
    except Exception:
        pass
    # 3) PROSE MINING — the anchor's stored, gate-approved definition sentence often carries the


    # never inference across sentences, never fabrication. Structured edges above still win.
    if not found:
        try:
            from packages.base_brain.pack_loader import get_semantic_context, load_base_brain_pack
            for c in (get_semantic_context(anchor, load_base_brain_pack()) or [])[:2]:
                desc = str(c.get("short_description") or "")
                if asked == "product":
                    m = re.search(r"([가-힣A-Za-z0-9]{2,12})[을를]\s*(?:창제|창시|만들|발명|저술|"
                                  r"설립|창립|개발|세우|짓|쓰|고안|발견)", desc)
                else:
                    m = re.search(r"([가-힣A-Za-z0-9]{2,12})[이가]\s*[^.]{0,14}?(?:창제한|창시한|만든|"
                                  r"발명한|저술한|설립한|창립한|개발한|세운|지은|쓴|고안한|발견한)", desc)
                if m and m.group(1) != anchor:
                    found.append((m.group(1), "definition_prose",
                                  str(c.get("source_type") or "pack_definition")))
                    break
        except Exception:
            pass
    try:
        from packages.lad_morphology import object_ as _obj_p
        from packages.lad_morphology import subject as _subj_p
    except Exception:
        _obj_p = lambda w: w + "를"   # noqa: E731
        _subj_p = lambda w: w + "이"  # noqa: E731
    if found:
        other, pred, src = found[0]
        # natural surface: agent-ask names the maker, product-ask names the work
        answer = (f"{_obj_p(anchor)} 만든 사람은 {other}입니다." if asked == "agent"
                  else f"{_subj_p(anchor)} 만든 것은 {other}입니다.")
        # attach the answer entity's OWN stored definition — grounded context that also carries


        try:
            from packages.base_brain.pack_loader import get_semantic_context, load_base_brain_pack
            _octx = get_semantic_context(other, load_base_brain_pack()) or []
            _odesc = str((_octx[0] or {}).get("short_description") or "") if _octx else ""
            if _odesc and 8 <= len(_odesc) <= 120:

                # and gets swapped for the base-brain definition by the answer post-processor

                answer += f" {other}{_topic_josa(other)} {_odesc}"
        except Exception:
            pass
        return {"answer": answer, "kind": "relation_execution", "confidence": 0.85,
                "reasoning_certificate": {
                    "derivation_kind": "relation_execution", "anchor_concept": anchor,
                    "steps": [{"type": "relation_lookup", "fact": f"({anchor}, {pred}, {other})", "source": src}],
                    "evidence_concepts": [anchor, other], "confidence": 0.85,
                    "confidence_basis": "stored_relation_edge",
                    "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False}}}
    # honest miss ABOUT THE RELATION — the anchor exists; the asked edge doesn't (yet)
    gap = (f"{_obj_p(anchor)} 누가 만들었는지는" if asked == "agent"
           else f"{_subj_p(anchor)} 무엇을 만들었는지는")
    return {"answer": (f"{gap} 아직 제 그래프에 확인된 근거가 없어요. 지어내는 대신 솔직하게 "
                       "말씀드릴게요 — 이 관계를 배우게 되면 바로 근거와 함께 답하겠습니다."),
            "kind": "relation_ungrounded", "confidence": 0.6,
            "reasoning_certificate": {
                "derivation_kind": "relation_ungrounded", "anchor_concept": anchor,
                "steps": [{"type": "relation_lookup", "fact": f"no creator-class edge for {anchor}"}],
                "evidence_concepts": [anchor], "confidence": 0.6,
                "confidence_basis": "relation_edge_absent",
                "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False}}}






# answer_from_triples grabbed the anchor definitionally). A Korean question-word maps to the


_FUNC_REL_SYNONYMS: dict[str, set[str]] = {
    "수도": {"capital"}, "인구": {"population"}, "면적": {"area", "넓이"}, "넓이": {"area", "면적"},
    "통화": {"currency", "화폐"}, "화폐": {"currency", "통화"},
    "언어": {"language", "official_language", "공용어"}, "공용어": {"language", "official_language", "언어"},
    "대통령": {"president", "head_of_state"}, "국가": {"country", "나라"}, "나라": {"country", "국가"},
}


_FUNC_REL_SKIP_PREDS = {"defined_as", "is_a", "alias", "instance_of", "subclass_of", "설명"}
_FUNC_REL_STOP_WORDS = {"정의", "뜻", "의미", "설명", "특징", "종류", "역사", "개념", "차이", "장점", "단점"}



_FUNC_REL_Q = re.compile(
    r"^(?P<base>.+?)의\s*(?P<rel>[가-힣A-Za-z][가-힣A-Za-z·]{1,9}?)"
    r"(?:\s*의\s*(?P<attr>[가-힣A-Za-z][가-힣A-Za-z·]{1,9}?))?"
    r"\s*(?:은|는|이|가)?\s*(?:어디|얼마|뭐|무엇|몇|어느|누구|어떻게|무슨)?[가-힣]*\s*[?？]?\s*$")


# the traversal can resolve it. No-op for the kg_triples store (its objects are labels already).
_QID_RE = re.compile(r"^Q\d+$")


def _rel_word_forms(rel_word: str) -> list[str]:
    """The relation noun plus its topic-particle-stripped form (''→['','']).
 Guarded by length so a 2-char noun ending in a particle syllable (/…) is not mangled."""
    forms = [rel_word]
    for part in ("는", "은", "이", "가", "을", "를"):
        if rel_word.endswith(part) and len(rel_word) > 2 and rel_word[:-1] not in forms:
            forms.append(rel_word[:-1])
    return forms


def _match_func_pred(rel_word: str, rows: list[tuple[str, str, str]]) -> str | None:
    """Find the stored object for a functional relation-word among a node's edges.
    Matches by the seed synonym set OR by predicate identity (Korean-named preds)."""
    wants: set[str] = set()
    for form in _rel_word_forms(rel_word):
        wants |= {w.lower() for w in _FUNC_REL_SYNONYMS.get(form, set())} | {form.lower()}
    for s, p, o in rows:
        ps = str(p)
        if ps in _FUNC_REL_SKIP_PREDS:
            continue
        if ps.lower() in wants:
            obj = str(o).strip()
            if obj and obj != s and len(obj) <= 40:
                return obj
    return None


def _execute_functional_relation(question: str) -> dict[str, Any] | None:
    """Answer 'X <relation>( <attr>)?' straight from the graph's functional edges.
 Returns None (safe fall-through) unless the graph actually holds the edge — so it never
 fabricates and never blocks other lanes for questions it cannot ground."""
    q = str(question or "").strip()
    m = _FUNC_REL_Q.match(q)
    if not m:
        return None
    base = (m.group("base") or "").strip().strip("'\"")
    rel_word = (m.group("rel") or "").strip()
    attr_word = (m.group("attr") or "").strip()
    if not base or not rel_word or rel_word in _FUNC_REL_STOP_WORDS:
        return None
    try:
        from packages.graph_scale.answer_bridge import _store
        kg = _store()
    except Exception:
        kg = None
    if kg is None:
        return None

    _qid_cache: dict[str, str] = {}

    def _qlabel(qid: str) -> str:
        """Resolve a Wikidata Q-id to its readable label via its 'qlabel' row (world-pack schema).
        Cached per call; returns the Q-id unchanged if unresolved (honest, never fabricates)."""
        if qid in _qid_cache:
            return _qid_cache[qid]
        lab = qid
        try:
            for _s, p, o in (kg.facts_about(qid, limit=8) or []):
                if str(p) == "qlabel" and o:
                    lab = str(o)
                    break
        except Exception:
            pass
        _qid_cache[qid] = lab
        return lab

    def _facts(node: str) -> list[tuple[str, str, str]]:
        try:
            rows = kg.facts_about(node, limit=64) or []
        except Exception:
            rows = []
        if not rows and " " in node:
            try:
                rows = kg.facts_about(node.split()[-1], limit=64) or []
            except Exception:
                rows = []
        # world-pack: resolve Q-id relation objects to labels so BOTH the spreading composer and
        # the single-edge lane see readable entities (and hop-2 can traverse from the resolved
        # label). No-op on kg_triples — its objects are labels, so nothing matches _QID_RE.
        out: list[tuple[str, str, str]] = []
        for s, p, o in rows:
            os = str(o)
            if str(p) != "qlabel" and _QID_RE.match(os):
                os = _qlabel(os)
            out.append((str(s), str(p), os))
        return out

    # BRAIN-LIKE PATH (2026-07-14): the parse above IS the conceptualizer (anchor=base, focus=rel_word).
    # Hand the anchor + focus to the spreading-activation composer for a DEEP, multi-hop grounded

    # Falls through to the precise single-edge line only when the activation field is too thin.
    if not attr_word:
        try:
            from packages.graph_scale.graph_native_answer import compose as _gn_compose
            _intent = tuple({rel_word} | _FUNC_REL_SYNONYMS.get(rel_word, set()))
            _deep = _gn_compose(question, base, _facts, intent_preds=_intent)
            if _deep and _deep.get("answer"):
                _deep["kind"] = _deep.get("answer_kind", "graph_native_spread")
                return _deep
        except Exception:
            pass
    hop1 = _match_func_pred(rel_word, _facts(base))
    if not hop1:
        return None
    steps = [{"type": "relation_lookup", "fact": f"({base}, {rel_word}, {hop1})", "source": "triple_store"}]
    if attr_word and attr_word not in _FUNC_REL_STOP_WORDS:      # 2-hop: attribute of the resolved entity
        hop2 = _match_func_pred(attr_word, _facts(hop1))
        if not hop2:
            return None                                          # can't ground hop 2 → abstain
        steps.append({"type": "relation_lookup", "fact": f"({hop1}, {attr_word}, {hop2})", "source": "triple_store"})
        answer = (f"{base}의 {rel_word}{_topic_josa(rel_word)} {hop1}이고, "
                  f"{hop1}의 {attr_word}{_topic_josa(attr_word)} {hop2}입니다.")
        obj = hop2
    else:
        answer = f"{base}의 {rel_word}{_topic_josa(rel_word)} {hop1}입니다."
        obj = hop1
    return {"answer": answer, "kind": "relation_execution", "confidence": 0.86,
            "reasoning_certificate": {
                "derivation_kind": "functional_relation", "anchor_concept": base,
                "steps": steps, "evidence_concepts": [base, obj], "confidence": 0.86,
                "confidence_basis": "stored_functional_edge",
                "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False}}}


async def _chat_atanor_impl(request: AtanorChatRequest) -> dict[str, Any]:
    _emit_stage("analyzing")  # real: parsing the question + resolving context
    question = request.question_text()
    # ONE TIMELINE, live (owner: all organs mesh on a single UTC time axis — the 'brain'). Every
    # conversation turn becomes a first-class utterance EVENT on the shared spine: the user's words
    # here, ATANOR's answer just before the return, and any multi-party transcript carried in the
    # context. This is the substrate the block-universe view surveys. Never blocks, never raises.
    try:
        from packages.temporal_reasoning.unified_timeline import default_timeline
        _tl = default_timeline()
        _tl.record("utterance", question, who="user", meta={"channel": "chat"})
        for _m in (request.conversation_context or [])[-3:]:
            if isinstance(_m, dict) and "speaker" in str(_m.get("content", "")).lower():
                _tl.ingest_transcript(str(_m.get("content", "")))
                break                                    # one transcript blob is the discussion state
    except Exception:
        pass
    # PERCEIVE THE CONTEXT FIRST (owner's unification rule, and a measured bug: in game_attrib1 the
    # personal-recall lane EARLY-RETURNED a garbled transcript mash for 7 straight debate rounds —
    # an early cascade lane hijacking a turn it never understood, the exact mode-switch pathology).
    # One perception up front: is this an ongoing multi-party discussion? If so, the model CONTRIBUTES
    # from that perception here — perceive → generate, not generate-wrong → override. The lanes below
    # whose own preconditions are false in a discussion (anaphora topic-borrow: 'It is your turn' is
    # expletive; personal recall: a debate transcript is not owner-stated personal facts) simply do
    # not fire — their preconditions failing IS the gate, no new rule.
    # ONE unified perception (owner: comprehension is the FRONT of the integrated model, not a
    # bolt-on): a single perceive() builds the Understanding — focus, ask, format contract,
    # discussion state — that every downstream decision point consults (discussion contribution,
    # personal-recall precondition, and the final fallback's right-to-speak all read THIS).
    _understanding = None
    _discussion = None
    try:
        from packages.cgsr.cgsr.comprehension import perceive as _perceive
        from packages.cgsr.cgsr.discourse_participation import contribute as _disc_contribute
        _understanding = _perceive(question, request.conversation_context or [])
        _discussion = _understanding.discussion
    except Exception:
        _understanding, _discussion = None, None
    # ONE MODEL, NOT ORDERED MODE-SWITCHES (owner, repeated): the specialist reasoning capabilities
    # (self-as-causal-node, live-discussion contribution) used to be a chain of ordered early-returns
    # where the FIRST match short-circuited — order, not understanding, chose the speaker, and two
    # lanes had begun re-parsing the discussion independently. The response WORKSPACE collapses that
    # into the same Global-Workspace principle the Living Loop uses for thought: every capability
    # reads the ONE shared perception and offers a grounded candidate; the best-grounded wins;
    # a capability with nothing to say returns None and competes for nothing (so no engine is ever
    # 'switched on'). Reordering the candidates cannot change the winner — that is what makes it one
    # model rather than a rule table. self-causal reads the RAW text (question_text() flattens the
    # newlines an exam's observation-log needs as evidence).
    try:
        from packages.cgsr.cgsr.response_workspace import compose_response as _compose_response
        _rw = _compose_response(_understanding,
                                request.question or request.query or request.message or question)
    except Exception:
        _rw = None
    if _rw:
        try:
            from packages.temporal_reasoning.unified_timeline import default_timeline as _dtl
            _dtl().record("utterance", _rw["answer"][:400], who="atanor",
                          meta={"channel": "chat", "answer_kind": _rw["answer_kind"],
                                "workspace_considered": _rw.get("considered")})
        except Exception:
            pass
        return {"state": "completed", "result": {
            "answer": _rw["answer"], "answer_kind": _rw["answer_kind"], "language": "en",
            "confidence": _rw["confidence"], "can_speak": True, "default_trace_visible": False,
            "trace": None, "compact_trace": None, "evidence_docs": [],
            "answer_engine": {"name": _rw.get("engine_name", "ATANOR"), "external_llm": False,
                              "external_sllm": False, "local_brain_write": False,
                              "trace_hidden_by_default": True},
            **_flags(),
        }, **_flags()}
    # ENGLISH-ONLY I/O BOUNDARY — the first gate. The user writes English; non-English (Korean)
    # input is not mis-parsed through the retired Korean lanes, it gets one plain English refusal,
    # and none of the Korean/Kiwi logic downstream ever runs on user input.
    if ENGLISH_ONLY and _non_english_input(question):
        return _english_only_refusal(request)
    # ANAPHORA -> the ANSWER path (Magnum A6, 2026-07-18). build_conversation_context already
    # resolves "it/that/this/they" against the last user topic, and _chat_atanor_dispatch already
    # routes on contextual_query — but THIS function, which actually produces the answer, was
    # still reading the raw question. Measured consequence: "Tell me about the moon." then
    # "Where is it found?" answered *"Found is simple past and past participle of find"* — with no
    # entity subject, the dictionary lane defined an incidental word. A6 scored 0.20.
    # Only the SUBJECT is borrowed (topic prefix), never the user's intent: the question keeps its
    # own wording, so this cannot turn a follow-up into a re-answer of the previous turn.
    if request.conversation_context and not _discussion and _PRONOUN_SUBJ.search(question):
        try:
            _cc = build_conversation_context(question, request.conversation_context)
            if _cc.followup_detected and _cc.contextual_query and _cc.contextual_query != question:
                question = _cc.contextual_query
                request.question, request.query, request.message = question, None, None
        except Exception:
            pass
    # PERSONAL-CONTEXT recall (Magnum A2): "What is my X?" is answered from what the owner stated
    # earlier in this conversation, BEFORE the dictionary lane can define the word X. Returns None
    # (falls through to the honest abstain) when the owner never stated it — no fabrication.
    # Precondition: owner-stated personal facts — false in a multi-party discussion (measured
    # hijack, game_attrib1), so it does not fire there.
    if request.conversation_context and not _discussion:
        try:
            _pv = _personal_context_value(question, request.conversation_context)
            if _pv:
                return _personal_context_response(request, _pv)
        except Exception:
            pass
    # META-INSTRUCTION lane (owner-reported): an instruction about HOW to answer is a


    # part proceeds in the requested language.
    meta_ack = None
    _meta_lang, _meta_rest = _language_directive(question)
    if _meta_lang:
        request.language = _meta_lang
        _target = _meta_rest or _last_user_question(request.conversation_context, question)
        if _target:
            question = _target
            request.question, request.query, request.message = _target, None, None
        else:
            meta_ack = {
                "answer": ("네, 한국어로 답할게요. 무엇이 궁금하세요?" if _meta_lang == "ko"
                           else "Sure — I'll answer in English. What would you like to know?"),
                "reasoning_certificate": {
                    "derivation_kind": "conversation_control",
                    "anchor_concept": None,
                    "steps": [{"type": "control", "fact": f"language directive -> {_meta_lang}"}],
                    "evidence_concepts": [], "confidence": 0.95,
                    "confidence_basis": "meta_instruction_not_content",
                    "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
                },
                "confidence": 0.95,
            }
    # Language: an unambiguously-Korean question gets a Korean answer even when the UI

    # An explicit user directive (above) is the only thing that overrides the script.

    # it and the abstain came back in English
    _hangul = bool(re.search(r"[가-힣ㄱ-ㅎㅏ-ㅣ]", question or ""))
    if ENGLISH_ONLY:
        language = "en"
        request.language = "en"  # dispatch reads the request object, not this local
    elif _meta_lang:
        language = _meta_lang
    elif _hangul:
        language = "ko"
        request.language = "ko"  # dispatch reads the request object, not this local
    else:
        language = request.language or "en"

    # not consoled (measured: it fell into the felt lane and answered empathy). The extension's
    # Ato tab performs the navigation; the command + destination are journaled as learning data.
    if language == "ko":
        _cmd = _browser_command(question)
        if _cmd:
            try:
                import json as _json
                import time as _time
                _p = Path(__file__).resolve().parents[4] / "data" / "autonomy" / "browser_commands.jsonl"
                _p.parent.mkdir(parents=True, exist_ok=True)
                with _p.open("a", encoding="utf-8") as _fh:
                    _fh.write(_json.dumps({"at": _time.strftime("%Y-%m-%dT%H:%M:%S"),
                                           "command": question, **_cmd["action"]},
                                          ensure_ascii=False) + "\n")
            except Exception:
                pass
            _emit_stage("done")
            return {"state": "completed", "result": {
                "answer": _cmd["answer"], "answer_kind": "browser_command",
                "browser_action": _cmd["action"], "can_speak": True, "confidence": 0.9,
                "reasoning_certificate": {
                    "derivation_kind": "browser_command", "anchor_concept": None,
                    "steps": [{"type": "control", "fact": f"navigate -> {_cmd['action'].get('label')}"}],
                    "evidence_concepts": [], "confidence": 0.9,
                    "confidence_basis": "explicit_user_command",
                    "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False}},
            }, **_flags()}

        # is ACTUALLY on (context page turn) + the tour's own episodic read of it, never from

        if request.conversation_context and re.search(
                r"(이|지금|현재|여기)\s*(사이트|페이지|화면|웹\s*사이트|홈페이지)", question) \
                and re.search(r"(뭐|무엇|무슨|어떤|어디|소개|설명|알려)", question):
            _pg = _page_grounding(request.conversation_context)
            if _pg:
                _emit_stage("done")
                return {"state": "completed", "result": {
                    "answer": _page_question_answer(_pg), "answer_kind": "page_grounded",
                    "can_speak": True, "confidence": 0.85,
                    "reasoning_certificate": {
                        "derivation_kind": "page_grounding", "anchor_concept": _pg.get("host"),
                        "steps": [{"type": "grounding", "fact": f"current page = {_pg.get('title')} ({_pg.get('host')})"}],
                        "evidence_concepts": [], "confidence": 0.85,
                        "confidence_basis": "browser_page_context",
                        "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False}},
                }, **_flags()}


    # pronoun list) and settled onto the most-activated compatible concept from the recent-turns
    # salience field (cue-based retrieval, like a brain — not `if pronoun: substitute`). The referent
    # is substituted INTO the question so EVERY downstream lane sees the concrete topic

    # no confident referent — never fabricates one.
    if language == "ko" and request.conversation_context:
        try:
            from packages.graph_scale.working_memory import resolve as _resolve_ref
            _rr = _resolve_ref(question, request.conversation_context)
            if _rr.get("resolved") and _rr.get("question"):
                question = _rr["question"]
                request.question, request.query, request.message = question, None, None
        except Exception:
            pass


    # the prior assistant turn: the core sentence is chosen (most content-word overlap with the
    # whole turn), never re-written — verbatim-grounded compression, no fabrication.
    if language == "ko" and request.conversation_context and re.search(
            r"(요약|한\s*문장으로|한\s*줄로|간단히|짧게)\s*(말|정리|줄|요약)?", question) \
            and re.search(r"(요약|정리|줄여|말해)", question):
        _prev = ""
        for _t in reversed(list(request.conversation_context)):
            if isinstance(_t, dict) and str(_t.get("role") or "") == "assistant":
                _prev = str(_t.get("content") or _t.get("text") or _t.get("message") or "")
                break
        _sents = [s.strip() for s in re.split(r"(?<=[.!?다요])\s+", _prev) if len(s.strip()) >= 10]
        if _sents:
            if len(_sents) == 1:
                _core = _sents[0]
            else:
                _words = set(re.findall(r"[가-힣]{2,}", _prev))

                # the topic — a core sentence that drops it reads as a fragment (measured: picked

                _subj_m = re.search(r"[가-힣]{2,}", _prev)
                _subj = _subj_m.group(0) if _subj_m else ""
                _core = max(_sents, key=lambda s: (sum(1 for w in _words if w in s) / (len(s) ** 0.5))
                            + (2.0 if _subj and _subj in s else 0.0))
            _emit_stage("done")
            return {"state": "completed", "result": {
                "answer": f"요약하면, {_core}", "answer_kind": "extractive_summary",
                "can_speak": True, "confidence": 0.8,
                "reasoning_certificate": {
                    "derivation_kind": "extractive_summary", "anchor_concept": None,
                    "steps": [{"type": "compress", "fact": f"core sentence of prior turn ({len(_sents)}→1)"}],
                    "evidence_concepts": [], "confidence": 0.8,
                    "confidence_basis": "verbatim_core_sentence_selection",
                    "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False}},
            }, **_flags()}


    # shapes run their grounded machinery (phase-space rotation / prose mining / context chain)
    # or answer the SHAPE honestly; they must never fall to the low-anchor web lane (battery 22

    if language == "ko":
        _fr = _frontier_reasoning_ask(question, request.conversation_context or [])
        if _fr:
            _emit_stage("done")
            return {"state": "completed", "result": {
                "answer": _fr["answer"], "answer_kind": _fr["kind"],
                "can_speak": True, "confidence": _fr["confidence"],
                "reasoning_certificate": {
                    "derivation_kind": _fr["kind"], "anchor_concept": None,
                    "steps": [{"type": "frontier_reasoning", "fact": _fr["answer"][:120]}],
                    "evidence_concepts": [], "confidence": _fr["confidence"],
                    "confidence_basis": "grounded_or_honest_frontier_shape",
                    "guarantees": {"external_llm": False, "fabricated_facts": False,
                                   "web_used": False}},
            }, **_flags()}



    # effect, or an HONEST causal-scoped limit that references what IS known about the subject —
    # never silently downgraded to the subject's DEFINITION (the wrong question). The subject's
    # salient property is read from the CONVERSATION (not a token grab): the prior turn defined

    # correctness (generalises to any subject); the effect claim itself is never fabricated.
    if language == "ko" and _CONSEQUENCE_Q.search(question):
        _ce = _consequence_engage(question, request.conversation_context or [])
        if _ce:
            _emit_stage("done")
            return {"state": "completed", "result": _ce, **_flags()}

    # live learning ledger — real titles read, sentences accepted, links formed.
    # It must short-circuit BEFORE retrieval: a web search about the words

    if meta_ack is None and _is_recent_learning_question(question):
        _emit_stage("done")
        return _recent_learning_payload(request, question=question, language=language)
    # SELF-FUSED CONVERSATION ROUTING (owner directive: the everyday-talk / search
    # switch lives in the SELF, not a regex cascade). The living self PERCEIVES the
    # message (learned router + its own judgment) and, when it's conversation,
    # answers from its live state INSTANTLY — short-circuiting the whole graph/web
    # pipeline (this is also why conversational replies were slow: they ran every
    # factual lookup first). Knowledge questions fall through untouched.
    if meta_ack is None and language == "ko":
        try:
            from packages.continuous_self.conversation import converse, perceive_route

            _route = perceive_route(question)
            if _route["mode"] == "converse":
                _conv = converse(question, _route["intent"])
                if _conv:
                    _accumulate_user_facts(question, language)
                    _payload = {**_conv, "engine": "atanor", "language": language,
                                "route": _route, "can_speak": True}
                    _emit_stage("done")
                    return {"state": "completed", "result": _payload, **_flags()}
        except Exception:
            pass
    # A context-resolved query so a follow-up ("where is it?") carries the prior
    # topic into web grounding / recall.
    try:
        web_query = build_conversation_context(question, request.conversation_context).contextual_query or question
    except Exception:  # pragma: no cover - defensive
        web_query = question



    # subject. Setting the anchor here lets the rescue's relevance gate reject an
    # off-subject page instead of pasting it.
    _frame_anchor = ""
    _frame_relation_word = ""
    try:
        from packages.graph_scale.query_frame import parse as _qf_parse

        _qf = _qf_parse(question)
        if _qf.answer_type == "relation" and _qf.subject:
            _frame_anchor = _qf.subject
            import re as _re_qf
            _mrel = _re_qf.search(r"의\s+([가-힣A-Za-z0-9]{2,20})", question)
            _frame_relation_word = _mrel.group(1) if _mrel else ""
    except Exception:
        pass
    # Local Brain cumulative learning: accumulate user prefs/info from this turn.
    _accumulate_user_facts(question, language)
    recall = _local_brain_recall(question, language)
    # Curated structured-triple lookup (the trillion-scale KG substrate): an exact fact

    # quality (curated, verbatim, cited), so it takes priority. None when the store can't
    # answer (empty store / no matching fact) — safe even before any bulk load.
    triple_answer = None
    try:
        from packages.graph_scale.answer_bridge import answer_from_triples

        triple_answer = answer_from_triples(question, language)


        # (2) the coarser context-concatenated query as the fallback net.
        if triple_answer is None and request.conversation_context:
            try:
                from packages.conversation_state import resolve_deixis

                _dx = resolve_deixis(question, request.conversation_context)
                if _dx["resolved"] != question:
                    triple_answer = answer_from_triples(_dx["resolved"], language)
                    if triple_answer is not None:
                        cert = triple_answer.get("reasoning_certificate")
                        if isinstance(cert, dict):
                            cert["deixis_bindings"] = _dx["bindings"]
            except Exception:
                pass
        if triple_answer is None and web_query and web_query != question:
            triple_answer = answer_from_triples(web_query, language)
    except Exception:  # pragma: no cover - never break chat
        triple_answer = None
    # "Living creature" sense: answer questions about ATANOR's own live state by
    # pulling from every subsystem at once.
    self_state = _self_state_answer(question, language)

    # from the derived user model — possessions/habits/preferences with evidence
    # counts, honest silence when nothing is recorded.
    if self_state is None:
        self_state = _user_knowledge_answer(question, language)
    # Media: if the question references a VIDEO (YouTube) or IMAGE (path/URL), READ it
    # (transcript / OCR) and answer from that — explicit user intent, so high priority.
    media_answer = _media_grounded_answer(question, language) if not self_state else None

    # it as particles (recall as imagination, never playback).
    visual_answer = (_visual_recall_answer(question, language)
                     if not (self_state or media_answer) else None)

    if visual_answer is None and not (self_state or media_answer):
        visual_answer = _association_answer(question, language)
    # Self-model is no longer a curated answer table (that was rule-based). Identity
    # is a reference-resolution ROUTE → the GRAPH realizes the answer: an identity
    # question is answered from the "atanor" concept via answer_with_base_brain
    # (hand_authored=False). We resolve it up front so the web/attribution paths


    self_knowledge = None

    # self-reference route against these common false triggers.
    _false_self = bool(re.search(r"자기\s*소개서|자기\s*계발|자기\s*관리|자기\s*개발", question))


    _intro_request = (not _false_self and len(question.strip()) <= 20
                      and bool(re.search(r"자기\s*소개|네\s*소개|너\s*소개|소개\s*좀|소개\s*해", question)))
    if not self_state and not _false_self and (_is_identity_question(question) or _is_self_reference_question(question) or _intro_request):
        try:



            # ontology. Give an honest self-reflection (persistent self-model + hormone-like
            # signals, no overclaiming). Only genuine identity questions seed the graph path.
            from packages.base_brain.zero_user_answer import _self_state_answer as _self_reflect
            _refl = _self_reflect(question, language)


            _is_capability = language == "ko" and bool(
                re.search(r"(뭘|무엇을|뭐를?|어떤\s*(걸|것|기능|일)|무슨\s*(기능|일))\s*"
                          r"(할\s*수\s*있|해\s*줄\s*수\s*있|도와|하니|하는)", question)
                or re.search(r"기능(이|은|을)?\s*(뭐|어떤|있|알려)", question))

            # list of real limits, not the ontology blurb and not the feelings reflection.
            _is_limitation = language == "ko" and bool(
                re.search(r"한계|약점|단점|부족한|못하는|못\s*하는|서투|취약", question))
            if _refl:
                self_knowledge = {
                    "answer": _refl,
                    "reasoning_certificate": {"derivation_kind": "honest_self_reflection",
                                              "confidence_basis": "self_model_stance_no_overclaim"},
                    "confidence": 0.5,
                }
            elif _is_limitation:
                self_knowledge = {
                    "answer": ("솔직히 제 한계를 말씀드리면 — 지어내는 창작이나 확인 안 된 단정은 못 "
                               "하고, 실시간 정보(날씨·시각·최신 뉴스)는 웹 없이는 모릅니다. 아직 복잡한 "
                               "맥락을 이어가거나 사람처럼 자연스럽게 말하는 건 서툴러서 다듬는 중이에요. "
                               "그래도 모르는 걸 아는 척하지 않는 것 — 그게 제 한계이자 원칙이에요."),
                    "reasoning_certificate": {"derivation_kind": "honest_limitation_summary",
                                              "confidence_basis": "self_model_limits_no_overclaim"},
                    "confidence": 0.6,
                }
            elif _is_capability:
                self_knowledge = {
                    "answer": ("저는 근거에 기반해서 이런 걸 해요 — 개념의 뜻·유래·분류를 설명하고, "
                               "‘고래는 물고기야?’ 같은 사실을 추론으로 검증하고, 간단한 계산을 하고, "
                               "궁금한 걸 실시간 웹에서 교차확인해 정리해드려요. 의견을 나누거나 고민을 "
                               "함께 짚는 대화도 하고요. 다만 지어내는 창작이나 확인 안 된 단정은 하지 "
                               "않아요 — 그게 저를 믿을 수 있게 하는 원칙이거든요. 무엇이 궁금하세요?"),
                    "reasoning_certificate": {"derivation_kind": "honest_capability_summary",
                                              "confidence_basis": "self_model_capability_no_overclaim"},
                    "confidence": 0.6,
                }
            else:
                # Realize from the atanor concept. For an explicit identity marker use the



                # answers the limitation question).

                # identity still needs the canonical seed or the graph path never fires
                _seed = question if re.search(r"누구|who\s+are", question, re.IGNORECASE) else "너는 누구야"
                _identity = answer_with_base_brain(_seed, language)
                if _identity and "ATANOR" in str(_identity.get("answer") or ""):
                    self_knowledge = {
                        "answer": _identity["answer"],
                        "reasoning_certificate": _identity.get("reasoning_certificate"),
                        "confidence": float(_identity.get("confidence") or 0.9),
                    }
        except Exception:  # pragma: no cover - defensive
            self_knowledge = None


    # the AST self-knowledge graph, BEFORE the fact/definition lane grabs the identifier as a
    # dictionary word. Read-only, grounded in the codebase graph; None for anything not about code.
    code_answer = None
    if not (self_state or self_knowledge or recall):
        try:
            from packages.graph_scale.code_understanding import answer_code_question
            # no language gate: this lane recognises its own context and returns None for anything
            # that does not name a known code entity. The `language == "ko"` test it used to carry
            # was permanently false in an English-only system, so the organ could never speak.
            code_answer = answer_code_question(question)
        except Exception:
            code_answer = None

    # Opinion / preference / reflection / advice / small-talk questions get GRABBED


    # conversation. Engage warmly and sensibly, grounded in what ATANOR really is,
    # WITHOUT fabricating any fact (answer ≠ invent). Runs BEFORE the factual lanes
    # so opinion questions never get an off-target definition.
    engage_answer = None
    if not (self_state or self_knowledge or recall):
        # English contrast owns its turn BEFORE the factual lanes: base_brain fuzzy-matches the
        # operands ("coffee vs tea" → Pentacarbonylhydridomanganese) and gating that override
        # downstream was not enough, because the garbage WAS the base answer it overrode.
        if not str(language or "").lower().startswith("ko"):
            engage_answer = _english_compare_answer(question)
        if engage_answer is None:
            engage_answer = _conversational_engage_answer(question, language)
    # Greeting / small talk must be answered conversationally — NEVER sent to web

    # inputs get a warm reply from the local conversation surface.
    greeting_answer = None
    if not (self_state or self_knowledge or recall):
        _gs = question.strip()
        _is_greeting = len(_gs) <= 24 and bool(
            re.search(r"(^|\s)(안녕|하이|헬로|반가|반갑|ㅎㅇ|잘\s*지내|좋은\s*(아침|저녁))", _gs)
            or re.search(r"\b(hi|hello|hey|yo|good\s+(morning|evening|afternoon))\b", _gs, re.IGNORECASE)
        )

        # the abstain boilerplate here reads as not understanding the conversation
        _social = None
        if not _is_greeting and len(_gs) <= 20:
            if re.search(r"고마워|고맙|감사|thank", _gs, re.IGNORECASE):
                _social = "천만에요! 도움이 됐다니 기뻐요." if language == "ko" else "You're welcome — glad it helped!"
            elif re.search(r"잘\s*자|굿나잇|굿밤|good\s*night", _gs, re.IGNORECASE):
                _social = "잘 자요. 내일 또 이야기해요." if language == "ko" else "Good night — talk tomorrow."
            elif re.search(r"수고|고생\s*(했|많)", _gs):
                _social = "감사합니다. 언제든 다시 불러주세요."
            elif re.search(r"미안|죄송|sorry", _gs, re.IGNORECASE):
                _social = "괜찮아요. 편하게 계속 물어보세요." if language == "ko" else "No worries at all — go ahead."
            elif re.search(r"^(ㅋ+|ㅎ+|ㅠ+|ㅜ+|lol|haha)$", _gs, re.IGNORECASE):
                _social = "네 :) 계속 들을게요." if language == "ko" else ":) I'm listening."
        if _is_greeting or _social:
            ans = _social or ""
            if not ans and not re.search(r"[A-Za-z]{3}", _gs):  # Korean greeting → Korean surface
                try:
                    from packages.cgsr.cgsr.asm_v0 import generate_surface

                    ans = (generate_surface(question).answer or "").strip()
                except Exception:  # pragma: no cover
                    ans = ""
            if not ans:
                ans = "안녕하세요! 무엇이든 편하게 물어보세요." if language == "ko" else "Hi! What can I help you with?"
            greeting_answer = {
                "answer": ans,
                "reasoning_certificate": {
                    "derivation_kind": "greeting",
                    "anchor_concept": None,
                    "steps": [{"type": "greeting", "fact": "local conversation surface, no web"}],
                    "evidence_concepts": [],
                    "confidence": 0.9,
                    "confidence_basis": "conversation_surface",
                    "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
                },
                "confidence": 0.9,
            }

    # graph engine has no generative model, so it must NOT answer these by returning an

    # decline). Detect the request and decline honestly, naming the real limit. This is
    # the precision identity: an off-target answer is worse than a truthful "I can't".
    creative_decline = None
    if not (self_state or self_knowledge or recall):
        _q = question.strip()

        # definition dump, measured 2026-07-11) — the request class decides, not the one verb.
        if re.search(r"(시|노래|가사|소설|이야기|스토리|동화|에세이|수필|글|편지|랩)\S*\s*(\S+\s+){0,2}(써|써줘|지어|지어줘|만들어|만들어줘|창작|작곡|작사|들려줘|들려|해줘|해\s*줄)", _q) \
           or re.search(r"(그림|그려|그려줘|drawing|draw|poem|write me a|compose)", _q, re.IGNORECASE):
            # CREATIVE FUSION (own next-token, No-LLM): the grounded composer first —
            # holographic LM (corpus-attested units, new arrangement). Story-class requests



            # anywhere ②noun right before the creative-type word ③Kiwi first noun minus
            # creative-type/adjective stopwords. Fallback themes only for truly themeless asks.
            _CREATIVE_STOP = {"짧은", "좋은", "멋진", "하나", "한", "그", "이", "저", "새",
                              "감동", "감동적", "감동적인", "재밌는", "재미있는", "슬픈", "기쁜",
                              "아름다운", "무서운", "웃긴", "신나는"}
            _TYPE_WORDS = {"시", "노래", "가사", "소설", "이야기", "스토리", "동화", "에세이",
                           "수필", "글", "편지", "랩", "그림"}
            _theme_word = ""
            _tm = re.search(r"([가-힣A-Za-z0-9]{2,16})\s*에\s*대(?:한|해)", _q)
            if _tm and _tm.group(1) not in _CREATIVE_STOP:
                _theme_word = _tm.group(1)
            if not _theme_word:
                _tm = re.search(r"([가-힣A-Za-z0-9]{2,16})\s*(?:시|소설|이야기|스토리|동화|에세이|수필|노래|가사|랩)", _q)
                if _tm and _tm.group(1) not in _CREATIVE_STOP and _tm.group(1) not in _TYPE_WORDS:
                    _theme_word = _tm.group(1)
            if not _theme_word:
                try:
                    from packages.graph_scale.query_frame import _kiwi_subject
                    _k = _kiwi_subject(_q) or ""
                    if _k and _k not in _CREATIVE_STOP and _k not in _TYPE_WORDS:
                        _theme_word = _k
                except Exception:
                    pass
            if not _theme_word:
                _theme_word = ("봄", "바다", "시간", "별", "길", "마음")[hash(_q) % 6]
            _is_story = bool(re.search(r"소설|이야기|스토리|동화|에세이|수필", _q))
            _piece = None
            if _theme_word:
                try:
                    from packages.grounded_composer.creative_composer import compose_poem, compose_story
                    try:
                        from app.routers.base_brain import _live_hormones as _lh
                        _hormones = _lh()
                    except Exception:
                        _hormones = None
                    _piece = (compose_story(_theme_word, hormones=_hormones) if _is_story
                              else compose_poem(_theme_word, hormones=_hormones))
                except Exception:
                    _piece = None
            if _piece:
                if _is_story:
                    _body = f"{_piece['title']}\n\n" + "\n\n".join(_piece["paragraphs"])
                    _scale_note = ("\n\n— 위상장과 그래프의 실제 문장 단위들로만 지은 짧은 이야기예요 "
                                   f"(근거 {_piece['corpus_sentences']}문장). 사실 주장이 아니고, "
                                   "긴 소설은 아직 제 살이 자라는 중이라 이 길이가 지금의 정직한 한계예요.")
                else:
                    _body = f"{_piece['title']}\n\n" + "\n".join(_piece["lines"])
                    _scale_note = ("\n\n— 위상장과 그래프의 실제 문장 단위들로만 조립한 창작입니다 "
                                   f"(근거 {_piece['corpus_sentences']}문장). 사실 주장이 아니에요.")
                creative_decline = {
                    "answer": _body + _scale_note,
                    "reasoning_certificate": {
                        "derivation_kind": "grounded_creative_composition",
                        "anchor_concept": {"id": _piece["theme"], "label": _piece["theme"],
                                           "match": "creative_fusion"},
                        "steps": [{"type": "corpus", "source": "kg_definitions+evidence",
                                   "fact": f"{_piece['corpus_sentences']} sentences"},
                                  {"type": "next_token", "source": "holographic_lm",
                                   "fact": "FHRR kernel generation"}],
                        "evidence_concepts": _piece["concepts_used"],
                        "confidence": 0.7,
                        "confidence_basis": "corpus_attested_units_new_arrangement",
                        "guarantees": {**_piece["guarantees"], "web_used": False},
                    },
                    "confidence": 0.7,
                }
        if creative_decline is None and (
           re.search(r"(시|노래|가사|소설|이야기|스토리|동화|에세이|수필|글|편지|랩|이름|작명|닉네임|별명|slogan|슬로건|카피)\S*\s*(\S+\s+){0,2}(써|써줘|지어|지어줘|만들어|만들어줘|창작|작곡|작사|추천)", _q)
           or re.search(r"(그림|그려|그려줘|drawing|draw|poem|write me a|compose)", _q, re.IGNORECASE)):
            creative_decline = {
                "answer": (
                    "저는 근거에서 답을 짓는 그래프 기반 엔진이라, 시나 이야기 같은 창작은 하지 않아요 — "
                    "지어내지 않는 것이 제 원칙이거든요. 대신 어떤 대상의 뜻·유래·관계처럼 근거로 설명할 수 "
                    "있는 것이라면 정확히 도와드릴 수 있어요."
                ),
                "reasoning_certificate": {
                    "derivation_kind": "honest_capability_limit",
                    "anchor_concept": None, "steps": [], "evidence_concepts": [],
                    "confidence": 0.9, "confidence_basis": "no_generative_model_by_design",
                    "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
                },
                "confidence": 0.9,
            }


    # the graph holds concept DEFINITIONS, not step-by-step procedures, so a how-to


    # replaces a bare-definition answer with an honest capability note (procedural
    # answers need web/grounding, which the local graph doesn't provide offline).
    howto_request = False
    if not (self_state or self_knowledge or recall or creative_decline) and not request.web_search:
        howto_request = bool(
            re.search(r"[가-힣]+는\s*(법|방법)\b|\b방법(을|좀|\s*알려|이\s*뭐)|하려면\s*어떻게|어떻게\s*하(면|는|나요|죠|지)|how\s+(to|do\s+i)\b", question, re.IGNORECASE)
        )

    # FALSE-PREMISE gate: a question that ASSERTS an agent-made-object relation

    # The triple path abstains, but the base-brain neighborhood synthesis will still

    # If triples couldn't ground it, decline honestly rather than fabricate.
    false_premise = None
    relation_exec = None
    # detect a RELATION-ask up front (on the deixis-resolved `question`) so it can pre-empt a


    # anchor definitionally (non-None), which silently skipped this whole lane (E1 regression).
    _ra = None
    try:
        from packages.graph_scale.query_frame import relation_ask as _relation_ask
        _ra = _relation_ask(question)
    except Exception:
        _ra = None

    # real graph edge PRE-EMPTS an off-target definition dump (triple_answer non-None) — but only
    # when the edge actually exists (else _fr_result is None and behaviour is byte-identical).
    _fr_result = None
    if not request.web_search:
        try:
            _fr_result = _execute_functional_relation(question)
        except Exception:
            _fr_result = None
    if (not (self_state or self_knowledge or recall or creative_decline)
            and not request.web_search
            and (triple_answer is None or _ra or _fr_result)):


        # role, it is never a real object. Before this lane, the premise verifier composed the

        # fell to an off-target definition dump of the anchor.
        if _ra:
            relation_exec = _execute_relation_ask(_ra)

        # non-None when the graph holds the edge, so it never shadows the creator lane or a miss.
        if relation_exec is None and _fr_result:
            relation_exec = _fr_result
        # FALSE-FACT verification (battery S1): a claim-shaped question checks the stored fact
        # and corrects — reuses the relation_exec injection point below.
        if relation_exec is None:
            _vc = _verify_paired_claim(question) or _verify_attribute_claim(question)
            if _vc:
                relation_exec = {
                    "answer": _vc["answer"], "kind": _vc["kind"], "confidence": _vc["confidence"],
                    "reasoning_certificate": {
                        "derivation_kind": _vc["kind"], "anchor_concept": None, "steps": [
                            {"type": "claim_verification", "fact": _vc["answer"][:120]}],
                        "evidence_concepts": [], "confidence": _vc["confidence"],
                        "confidence_basis": "stored_definition_prose",
                        "guarantees": {"external_llm": False, "fabricated_facts": False,
                                       "web_used": False}},
                }
        _mfp = None if _ra else re.search(
            r"([가-힣A-Za-z0-9]{2,})[이가]\s*(만든|발명한|세운|창립한|지은|개발한)\s*"
            r"([가-힣A-Za-z0-9]{2,})", question)
        if _mfp:
            _agent, _obj = _mfp.group(1), _mfp.group(3)
            try:
                from packages.lad_morphology import object_ as _obj_particle
                from packages.lad_morphology import subject as _subj_particle

                _a = _subj_particle(_agent)
                _o = _obj_particle(_obj)
            except Exception:
                _a, _o = _agent + "이", _obj + "를"
            false_premise = {
                "answer": (f"‘{_a} {_o} 만들었다’는 확인된 근거가 없어서, 그 전제 위에서는 "
                           "답을 지어내지 않을게요. 사실관계가 확실한 대상이라면 정확히 "
                           "알려드릴 수 있어요."),
                "reasoning_certificate": {
                    "derivation_kind": "false_premise_abstention",
                    "anchor_concept": None, "steps": [], "evidence_concepts": [],
                    "confidence": 0.8, "confidence_basis": "premise_relation_ungrounded",
                    "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
                },
                "confidence": 0.8,
            }



    # compare path describes BOTH concepts grounded, so route confirmed two-concept
    # comparisons through it. Only overrides when it yields a real two-sided compare
    # answer (intent=compare + useful); otherwise the normal path stands.
    concept_compare = None
    if not (self_state or self_knowledge or recall or creative_decline) \
       and re.search(r"차이|비교|vs\b|versus|difference\s+between|어떻게\s*다르|무엇이\s*다르", question, re.IGNORECASE):
        try:
            _cmp = answer_with_base_brain(question, language)
            _is_cmp = bool(_cmp) and (_cmp.get("trace") or {}).get("intent") == "compare" and bool(_cmp.get("useful_answer"))
            if _is_cmp:
                _ans = str(_cmp.get("answer") or "")

                _m = re.match(r"\s*(.+?)(?:와|과)\s+(.+?)의\s+핵심\s+차이", _ans)
                # ENGLISH PRECISION GATE (2026-07-17): the degenerate-pair guard above is Korean
                # only, and base_brain resolves English operands by fuzzy match — measured, "the
                # difference between a crocodile and an alligator" came back about CROCODILE
                # DUNDEE II, and "coffee vs tea" about Pentacarbonylhydridomanganese. An answer
                # that does not name BOTH things asked about is not an answer to this question;
                # reject it so the grounded composer (which resolves exactly) gets the turn.
                _ok_en = True
                if not re.search(r"[가-힣]", question):
                    try:
                        from packages.graph_scale.answer_bridge import _COMPARE_EN, _en_pair

                        _pa, _pb = _en_pair(_COMPARE_EN.match(question.strip()))
                    except Exception:
                        _pa = _pb = ""
                    if _pa and _pb:
                        _low = _ans.lower()
                        _ok_en = all(re.search(rf"\b{re.escape(w.lower())}\b", _low)
                                     for w in (_pa, _pb))
                if _ok_en and (not _m or _m.group(1).strip() != _m.group(2).strip()):
                    concept_compare = {
                        "answer": _ans,
                        "reasoning_certificate": _cmp.get("reasoning_certificate"),
                        "confidence": float(_cmp.get("confidence") or 0.75),
                    }
        except Exception:  # pragma: no cover - defensive
            concept_compare = None


    # lookups + a deterministic compare, no LLM. None when not a comparison or when
    # it can't extract both values (abstains, never guesses).
    # Deterministic Reasoning VM (arithmetic / counting word problems) — fully
    # offline: no LLM, no GPU, no web. Highest-priority reasoner; runs even when
    # web search is off, and pre-empts the web-dependent reasoners below.
    reasoning_vm = None
    if not (self_state or self_knowledge or recall):
        _emit_stage("reasoning")  # real: deterministic reasoning VM is running
        try:
            from app.services.reasoning_vm import solve_reasoning

            reasoning_vm = solve_reasoning(question, language)
        except Exception:  # pragma: no cover - reasoner must never break chat
            reasoning_vm = None
        # GRADUATED INDUCED PROCEDURES (F2.5, owner 2026-07-14): when the hand-built reasoner
        # declines, a SELF-INDUCED procedure that EARNED graduation (sustained shadow accuracy on
        # real traffic) may speak — with an oracle cross-check at answer time, so a wrong induced

        # measured falling to polysemy noise while the shadow pow2 already knew 1024.
        if reasoning_vm is None:
            try:
                from packages.reasoning_vm.shadow_flywheel import graduated_answer

                reasoning_vm = graduated_answer(question)
            except Exception:
                pass
    comparison = None
    chained = None
    if request.web_search and not (self_state or media_answer or self_knowledge or recall or reasoning_vm):
        try:
            from app.services.comparison_reasoner import answer_comparison

            comparison = answer_comparison(question, language)
        except Exception:  # pragma: no cover - reasoner must never break chat
            comparison = None
        if not comparison:
            try:
                from app.services.chained_reasoner import answer_chain

                chained = answer_chain(question, language)
            except Exception:  # pragma: no cover - reasoner must never break chat
                chained = None


    # a definition. The grounded-conversation path can't do this, so route confirmed
    # attribution questions through the rescue's deterministic person extraction
    # (prose + infobox). Only overrides when a real name is found; else the normal
    # answer (definition) stands.
    attribution_answer = None
    if request.web_search and not (self_state or media_answer or self_knowledge or recall or reasoning_vm) and _detect_attribution_relation(question):
        _emit_stage("web_grounding")  # real: about to hit the network for attribution
        try:
            _attrib = await _web_grounded_rescue(web_query, language)
            if _attrib and _attrib.get("reasoning_certificate", {}).get("derivation_kind") == "web_attribution_extraction":
                attribution_answer = _attrib
        except Exception:  # pragma: no cover - network/optional
            attribution_answer = None

    _emit_stage("composing")  # real: routing to the graph/base-brain answer path
    response = _demote_low_quality_to_base_brain(await _chat_atanor_dispatch(request), request)
    response = _attach_holographic_fold_trace(response, request)

    if self_state and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = self_state["answer"]
        result["reasoning_certificate"] = self_state["reasoning_certificate"]
        result["confidence"] = self_state["confidence"]
        result["answer_kind"] = "atanor_self_sense"
        result["can_speak"] = True

    # Identity answer (graph-realized from the atanor concept) — authoritative over
    # the web/definition path for a self-question.
    if self_knowledge and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = self_knowledge["answer"]
        result["reasoning_certificate"] = self_knowledge["reasoning_certificate"]
        result["confidence"] = self_knowledge["confidence"]
        result["answer_kind"] = "atanor_identity_graph"
        result["can_speak"] = True

        # real trained concepts + true resonance pairs, not a staged animation
        if re.search(r"어떻게\s*작동|어떻게\s*동작|어떤\s*원리|작동\s*원리|how do you work", question, re.IGNORECASE):
            result["render_iframe"] = {"url": "/interference",
                                       "title": "위상 홀로그래모픽 간섭 — 작동 원리"}

    # Visual-memory recall (Phase 4-2) — the measured signature answers the look
    # question and the /recall page re-renders it as particles.
    if visual_answer and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = visual_answer["answer"]
        result["reasoning_certificate"] = visual_answer["reasoning_certificate"]
        result["confidence"] = visual_answer["confidence"]
        result["answer_kind"] = visual_answer["answer_kind"]
        if visual_answer.get("render_iframe"):
            result["render_iframe"] = visual_answer["render_iframe"]
        result["can_speak"] = True

    # Media-grounded answer (read a video transcript / image OCR) — authoritative; the
    # user explicitly pointed at media to read.
    if media_answer and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = media_answer["answer"]
        result["reasoning_certificate"] = media_answer.get("reasoning_certificate")
        result["confidence"] = media_answer.get("confidence")
        result["answer_kind"] = media_answer.get("provider") or "media_grounding"
        result["can_speak"] = True
        if media_answer.get("source_url"):
            result["render_iframe"] = {"url": media_answer["source_url"], "title": media_answer.get("source_title") or "media"}

    # Greeting — conversational, never web.
    if greeting_answer and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = greeting_answer["answer"]
        result["reasoning_certificate"] = greeting_answer["reasoning_certificate"]
        result["confidence"] = greeting_answer["confidence"]
        result["answer_kind"] = "greeting"
        result["can_speak"] = True

    # Meta-instruction with nothing to re-answer — acknowledge the control, never
    # answer the words of the instruction as content.
    if meta_ack and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = meta_ack["answer"]
        result["reasoning_certificate"] = meta_ack["reasoning_certificate"]
        result["confidence"] = meta_ack["confidence"]
        result["answer_kind"] = "conversation_control"
        result["can_speak"] = True


    # from a stored edge, or declined ABOUT THE RELATION — never a definition dump of the anchor
    # and never the placeholder-as-entity premise (Phase 1-2, 2026-07-10).
    if relation_exec and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = relation_exec["answer"]
        result["reasoning_certificate"] = relation_exec["reasoning_certificate"]
        result["confidence"] = relation_exec["confidence"]
        result["answer_kind"] = relation_exec["kind"]
        result["can_speak"] = True

    # False premise — decline honestly, never let base-brain fabricate a comparison.
    if false_premise and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = false_premise["answer"]
        result["reasoning_certificate"] = false_premise["reasoning_certificate"]
        result["confidence"] = false_premise["confidence"]
        result["answer_kind"] = "false_premise_abstention"
        result["can_speak"] = True

    # Creative request — honest decline (no generative model), never an off-target def.
    if creative_decline and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = creative_decline["answer"]
        result["reasoning_certificate"] = creative_decline["reasoning_certificate"]
        result["confidence"] = creative_decline["confidence"]
        result["answer_kind"] = "honest_capability_limit"
        result["can_speak"] = True

    # Contrast — describe BOTH concepts grounded, never just one side.
    if concept_compare and isinstance(response.get("result"), dict):
        _ans = response["result"].get("answer") or ""
        # only override a one-sided / abstaining answer, never a richer real one
        if _answer_is_abstention(_ans) or ("핵심 차이" not in str(_ans)):
            result = response["result"]
            result["answer"] = concept_compare["answer"]
            result["reasoning_certificate"] = concept_compare["reasoning_certificate"]
            result["confidence"] = concept_compare["confidence"]
            result["answer_kind"] = "concept_comparison"
            result["can_speak"] = True

    # How-to — if the answer is a bare off-target DEFINITION (the graph defined the
    # tool instead of giving steps), replace with an honest procedural-limit note.
    # Leave real abstentions and any answer that already reads procedurally alone.
    if howto_request and not concept_compare and isinstance(response.get("result"), dict):
        _ans = str(response["result"].get("answer") or "")




        _looks_procedural = bool(re.search(
            r"단계별|순서(?:대로|는|:)|차례(?:로|대로)|[①-⑩]|(?:^|\n)\s*\d+\s*[.)]|첫째|둘째|셋째",
            _ans))
        # any non-procedural, non-abstention answer to a how-to is off-target here —
        # the local graph holds concept definitions, not step-by-step procedures, so a

        if _ans and not _answer_is_abstention(_ans) and not _looks_procedural:
            result = response["result"]
            # BOTH LANGUAGES: this honest-limit text was Korean-only, so an English how-to
            # ("How do I learn to code?") got a Hangul answer — measured 2026-07-17.
            result["answer"] = (
                "그 절차를 단계별로 알려드리려면 확인된 근거가 필요한데, 지금 로컬 그래프에는 그 방법에 대한 "
                "단계별 근거가 없어요 — 지어내서 알려드리진 않을게요. 웹 검색을 켜 주시거나, 관련 개념의 뜻·용도라면 "
                "근거로 설명해 드릴 수 있어요."
                if language == "ko" else
                "To walk you through those steps I'd need verified grounding, and my local graph "
                "has no step-by-step evidence for it — I won't make one up. Turn on web search, or "
                "ask me what a related concept means or is for and I can answer that from evidence."
            )
            result["reasoning_certificate"] = {
                "derivation_kind": "honest_capability_limit",
                "anchor_concept": None, "steps": [], "evidence_concepts": [],
                "confidence": 0.85, "confidence_basis": "no_procedural_grounding_offline",
                "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
            }
            result["confidence"] = 0.85
            result["answer_kind"] = "honest_capability_limit"
            result["can_speak"] = True

    # Structured-triple answer — exact curated fact, verbatim + cited. Overrides the
    # noisier engine paths (before reasoning_vm, which handles a disjoint set of math


    # CODE SELF-UNDERSTANDING dispatch — wins over the fact/definition lane, since a code identifier
    # ("realize_thought") must not be answered as if it were a dictionary word.
    if code_answer and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = code_answer["answer"]
        result["reasoning_certificate"] = code_answer["reasoning_certificate"]
        result["confidence"] = code_answer["confidence"]
        result["answer_kind"] = code_answer["answer_kind"]
        result["can_speak"] = True

    if (triple_answer and not (self_state or self_knowledge) and not engage_answer and not code_answer
            and not relation_exec        # a claim-verify / relation execution already answered — keep it
            and isinstance(response.get("result"), dict)):
        result = response["result"]
        result["answer"] = triple_answer["answer"]
        result["reasoning_certificate"] = triple_answer["reasoning_certificate"]
        result["confidence"] = triple_answer["confidence"]
        result["answer_kind"] = "structured_triple_lookup"
        result["can_speak"] = True


    # preference/advice/small-talk) wins over the factual definition lookup — it
    # is not a fact question, so a warm engaged reply is the right answer. Never
    # over greeting/self/media (those are more specific and already handled).
    if (engage_answer and not (self_state or self_knowledge or greeting_answer) and not code_answer
            and isinstance(response.get("result"), dict)):
        result = response["result"]
        result["answer"] = engage_answer["answer"]
        result["reasoning_certificate"] = engage_answer["reasoning_certificate"]
        result["confidence"] = engage_answer["confidence"]
        result["answer_kind"] = engage_answer["answer_kind"]
        result["can_speak"] = True

    # Reasoning VM answer (math / counting word problem) — authoritative,
    # deterministic, offline. Highest priority over the web-grounded engine.
    if reasoning_vm and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = reasoning_vm["answer"]
        result["reasoning_certificate"] = reasoning_vm["reasoning_certificate"]
        result["confidence"] = reasoning_vm["confidence"]
        result["answer_kind"] = "reasoning_vm"
        result["can_speak"] = True
        # Experimental answer-interface surface (formula / GeoGebra-like figure).
        if reasoning_vm.get("answer_visual"):
            result["answer_visual"] = reasoning_vm["answer_visual"]

    # Attribution answer (who founded/invented/painted X) — authoritative over a
    # definition for a "who" question.
    if attribution_answer and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = attribution_answer["answer"]
        result["reasoning_certificate"] = attribution_answer["reasoning_certificate"]
        result["confidence"] = attribution_answer["confidence"]
        result["answer_kind"] = "web_attribution"
        result["can_speak"] = True
        if attribution_answer.get("source_url"):
            result["source_url"] = attribution_answer["source_url"]
            result["source_title"] = attribution_answer.get("source_title")

    # Multi-hop comparison answer — authoritative over the single-fact engine.
    if comparison and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = comparison["answer"]
        result["reasoning_certificate"] = comparison["reasoning_certificate"]
        result["confidence"] = comparison["confidence"]
        result["answer_kind"] = "comparison_reasoning"
        result["can_speak"] = True
        if comparison.get("source_url"):
            result["render_iframe"] = {"url": comparison["source_url"], "title": comparison.get("source_title") or question[:60]}

    # Chained (2-hop) reasoning answer — authoritative over the single-fact engine.
    if chained and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = chained["answer"]
        result["reasoning_certificate"] = chained["reasoning_certificate"]
        result["confidence"] = chained["confidence"]
        result["answer_kind"] = "chained_reasoning"
        result["can_speak"] = True
        if chained.get("source_url"):
            result["render_iframe"] = {"url": chained["source_url"], "title": chained.get("source_title") or question[:60]}

    # Web-grounded rescue (outermost): if the final answer is still an abstention
    # from ANY internal path, ground it from a real cited web source. This RESPECTS
    # the web_search toggle — with web off, an out-of-graph question abstains honestly
    # (showing the true local graph coverage) instead of silently reaching the web.
    if request.web_search and not (self_state or media_answer or self_knowledge or comparison or chained or recall or reasoning_vm) and isinstance(response.get("result"), dict):
        result = response["result"]
        ans = str(result.get("answer") or "")
        # QUESTION-TYPE AGREEMENT, outermost: an UNLABELED default-lane answer


        # definition via graph resonance, no certificate, so no earlier gate
        # saw it). Treat it as no-answer; the rescue extracts X-page relation
        # sentences instead. Labeled answers (any answer_kind) are exempt —
        # their own lanes already enforce agreement.
        _gen_q2 = re.search(r"([가-힣A-Za-z0-9]{1,12})의\s+([가-힣A-Za-z0-9]{2,12}?)"
                            r"(?:[은는이가을를만]|\s|$)", question)
        _tail_led = bool(
            _gen_q2 and not result.get("answer_kind")
            and not re.match(r"\s+[가-힣A-Za-z0-9]", question[_gen_q2.end(2):])
            and ans.replace(" ", "").startswith(_gen_q2.group(2))
            and not ans.replace(" ", "").startswith(_gen_q2.group(1)))


        # DEFINITION has NOT been answered — the user asked HOW-MUCH / HOW / WHY, not
        # WHAT-IS. Escalate to the web orchestrator (multi-query + fluid synthesis)

        _open_cue = re.search(r"몇|얼마나|얼마|어떻게|왜\b|차이|비교|방법|추천|괜찮|좋을까"
                              r"|장단점|어디|언제|며칠|효과|부작용|해야|하면", question)
        _is_whatis = re.search(r"뭐야|뭔가|무엇|뭐예요|뭐임|누구|정의|이란|란\?", question)
        _definitional = bool(re.search(r"(이다|입니다|음료|말한다|뜻한다|일종|것이다|이야)\s*\.?$",
                                        ans.strip())) or len(ans.strip()) < 55
        # a bare definition to an attribute question is 'unmet' even when it carries a

        _kind = str(result.get("answer_kind") or "")
        _weak_kind = (not _kind) or any(k in _kind for k in ("base_brain", "low_quality", "definition"))
        _intent_unmet = bool(_open_cue and not _is_whatis and _weak_kind
                             and _definitional and not re.search(r"[0-9]", ans))
        # ENGAGE-FLOOR: the no-dead-end engagement (engaged_fact_inference) replaced the
        # old abstention, so `_answer_is_abstention` no longer fires — but with web ON we
        # still PREFER a real cited answer. Treat the engaged inference as web-eligible:
        # web wins if it grounds an answer, and the engagement remains the floor if web
        # fails (rescue returns None → the engaged answer is kept). No more cold forfeit.
        _engaged = str((result.get("reasoning_certificate") or {}).get("derivation_kind")) == "engaged_fact_inference"

        # let English property questions sail through — measured live: "What is the capital of
        # South Korea?" answered "Korea is a geographic region…" from the local graph and STOPPED,
        # never escalating to the web lane that answers it correctly (battery 6/7). Two gates:
        #  (a) 'PROPERTY of ENTITY' whose answer never mentions the PROPERTY word → wrong question
        #      answered (a definition of the entity/region, not its capital/formula/population).
        #  (b) an English open/attribute cue (how many/why/difference…) answered by a bare
        #      definition with no number → unmet, same doctrine as the Korean _intent_unmet.
        _en_prop = re.match(r"^\s*(?:what|who|which)\s+(?:is|are|was|were)\s+(?:the\s+)?"
                            r"([a-z][a-z ]{2,24}?)\s+of\s+.+", question, re.IGNORECASE)
        _en_prop_word = (_en_prop.group(1).strip().lower() if _en_prop else "")
        _en_prop_unmet = bool(_en_prop_word and _en_prop_word not in ans.lower())
        _en_open = re.search(r"\b(how (?:many|much|tall|long|far|old|fast|big)|why|difference"
                             r"|compare|versus|when did|where is|where are)\b", question, re.IGNORECASE)
        _en_unmet = bool(_en_open and _definitional and not re.search(r"[0-9]", ans))

        #      answer is a weak, short definition that DROPS a key word of the concept answered a
        #      broader/different entity — "What is the speed of light?" → "speed is a kind of motion"
        #      (lost 'light' → defined plain 'speed'). Only when the answer is weak+definitional, so
        #      a real full answer ("Seoul, officially…", len≥55 → not _definitional) never re-fires.
        _en_concept = re.match(r"^\s*what\s+(?:is|are|was|were)\s+(?:an?\s+|the\s+)?(.+?)\s*\??$",
                               question, re.IGNORECASE)
        _en_concept_unmet = False
        if _en_concept:
            _ctoks = [t for t in re.findall(r"[a-z0-9]+", _en_concept.group(1).lower())
                      if len(t) >= 2 and t not in _EN_STOP]
            _alow = ans.lower().lstrip()
            # Fire only when the answer DEFINES A FRAGMENT of the concept: it starts with one of the
            # concept's own words + a copula ("speed is…", "black is…") yet drops another concept word
            # ('light', 'hole'). This is kind-independent (the curated-KG lookup mis-resolves the
            # multiword head just as base_brain does), and it spares proper-noun answers ("Paris" to
            # "capital of France" never starts with 'capital'/'france' → not fired).
            if len(_ctoks) >= 2 and not all(t in _alow for t in _ctoks):
                _lead = re.match(r"([a-z0-9]+)\s+(?:is|are|was|were)\b", _alow)
                if _lead and _lead.group(1) in _ctoks:
                    _en_concept_unmet = True
        #  (d) HANGUL LEAK into an English answer (English-only doctrine, BINDING): an ASCII question

        #      is just the KO translation, no content). Escalate to the web for a real English answer.
        _q_ascii = not re.search(r"[가-힣]", question)
        _en_hangul_leak = bool(ENGLISH_ONLY and _q_ascii and re.search(r"[가-힣]", ans))
        # CONVERSATIONAL INTENTS NEVER WEB-SEARCH (owner 2026-07-16: English "Hi" took 23s because

        # Greeting/small-talk/opinion/creative/self-reference are answered from within; the English
        # gates above are for KNOWLEDGE questions only. This is the biggest perceived-speed lever.
        _conversational_kind = any(k in _kind for k in (
            "greeting", "smalltalk", "small_talk", "chitchat", "chit_chat", "opinion", "creative",
            "poem", "self", "reflect", "advice", "emotion", "banter", "gratitude", "farewell"))
        if (not _conversational_kind and (
                not ans or _answer_is_abstention(ans) or _tail_led or _intent_unmet or _engaged
                or _en_prop_unmet or _en_unmet or _en_concept_unmet or _en_hangul_leak)):
            _emit_stage("web_grounding")  # real: local answer was thin, hitting the web
            rescue = await _web_grounded_rescue(web_query, language)
            # Experience ledger: the rescue OUTCOME is measured evidence about the routing
            # decision (anchored answer → query was answerable; gate-rejected empty → a
            # confident seek was wrong). Network failure carries no evidence — skip.
            try:
                from packages.base_brain.answer_experience import label_web_rescue_outcome

                if rescue and not rescue.get("web_unreachable"):
                    label_web_rescue_outcome(web_query, anchored=True) or \
                        label_web_rescue_outcome(question, anchored=True)
                elif rescue is None:
                    label_web_rescue_outcome(web_query, anchored=False) or \
                        label_web_rescue_outcome(question, anchored=False)
            except Exception:
                pass



            # relation), it is the wrong page — refuse it honestly rather than
            # pasting the definition of the relation. EXCEPT when the source page


            # of the relation (the entity-page extraction backstop produces
            # exactly this shape — measured, it was being refused here).
            if (rescue and _frame_relation_word and not rescue.get("web_unreachable")
                    and str(rescue.get("source_title") or "").strip()
                        != str(_frame_anchor or "").strip()):
                _head = str(rescue.get("answer") or "")[:len(_frame_relation_word) + 2]
                if _head.startswith(_frame_relation_word):
                    rescue = None
                    result["answer"] = (
                        f"‘{_frame_anchor}의 {_frame_relation_word}’에 대한 확인된 자료를 이번엔 찾지 "
                        f"못했어요 — ‘{_frame_relation_word}’ 자체의 뜻을 엉뚱하게 갖다 붙이진 않을게요. "
                        f"조금 더 좁혀 주시면 다시 찾아볼게요.")
                    result["answer_kind"] = "honest_relation_gap"
                    result["confidence"] = 0.3
                    result["can_speak"] = True
            if rescue:
                result["answer"] = rescue["answer"]
                result["reasoning_certificate"] = rescue["reasoning_certificate"]
                result["confidence"] = rescue["confidence"]
                result["answer_kind"] = "web_unreachable" if rescue.get("web_unreachable") else "web_search_grounded"
                result["web_search_provider"] = rescue["provider"]
                result["can_speak"] = True
                if not rescue.get("web_unreachable"):
                    # R2 tier escalation marker — a human says "let me check… found it": the local
                    # guess was REPLACED by web evidence, and we say so instead of hiding it.
                    result["tier_escalation"] = {"from": "LOCAL", "to": "SAGE",
                                                 "reason": ("en_property_unmet" if _en_prop_unmet else
                                                            "en_concept_unmet" if _en_concept_unmet else
                                                            "en_hangul_leak" if _en_hangul_leak else
                                                            "en_open_unmet" if _en_unmet else
                                                            "intent_unmet" if _intent_unmet else
                                                            "tail_led" if _tail_led else "abstention_or_thin")}
                # New Cloud Brain nodes grafted from the web result, handed to the
                # Local Brain graph so it can light them up as they appear.
                if rescue.get("grafted_nodes"):
                    result["web_grafted_nodes"] = rescue["grafted_nodes"]
                    result["web_graft"] = rescue.get("web_graft") or {}
                # The agent surfaces the source document on its own — the dashboard
                # opens it in the iframe stage (orb slides aside).
                if rescue.get("source_url"):
                    result["render_iframe"] = {"url": rescue["source_url"], "title": rescue.get("source_title") or question[:60]}

    # If the user asked ATANOR to recall something about THEM and the Local Brain
    # knows it, that private memory is authoritative — the public engine cannot
    # know the user's name/preferences, so override its answer.
    if recall and isinstance(response.get("result"), dict):
        result = response["result"]
        result["answer"] = recall["answer"]
        result["reasoning_certificate"] = recall["reasoning_certificate"]
        result["confidence"] = recall["confidence"]
        result["answer_kind"] = "local_brain_memory_recall"
        result["can_speak"] = True

    # No local answer and not already grounded — surface a fact ATANOR looked up
    # on the web earlier (it remembers what it learned, even with web search off).
    if isinstance(response.get("result"), dict):
        result = response["result"]
        ans = str(result.get("answer") or "")
        if (not ans or _answer_is_abstention(ans)) and result.get("answer_kind") not in (
            "web_search_grounded", "web_unreachable", "local_brain_memory_recall", "atanor_self_sense"
        ):
            cached = _recall_web_fact(web_query)
            if cached:
                result["answer"] = cached["answer"]
                result["reasoning_certificate"] = cached["reasoning_certificate"]
                result["confidence"] = cached["confidence"]
                result["answer_kind"] = "local_web_fact_recall"
                result["web_search_provider"] = "local_web_memory"
                result["can_speak"] = True

    # Graft web-sourced evidence into the Cloud Brain as real nodes and hand the
    # new nodes to the Local Brain graph — for ANY path that grounded the answer
    # on the web (RAG conversation grounding OR the abstention rescue). The orb
    # answer and these glowing new nodes come from the same retrieved evidence.
    answer_kind_now = str((response.get("result") or {}).get("answer_kind") or "")
    # A self/identity/personal answer (ATANOR about itself, base-brain identity, a
    # demoted low-quality grounding, or a Local Brain recall) is NOT a web lookup —

    # surface a stranger's Wikipedia page).
    answer_is_self_or_local = bool(self_state or recall) or any(
        marker in answer_kind_now
        for marker in ("self", "atanor", "base_brain", "local", "low_quality", "unreachable")
    )
    if request.web_search and not answer_is_self_or_local and isinstance(response.get("result"), dict):
        result = response["result"]
        ans = str(result.get("answer") or "")
        if ans and not _answer_is_abstention(ans) and not result.get("web_grafted_nodes"):
            web_docs = [
                doc for doc in (result.get("evidence_docs") or [])
                if isinstance(doc, dict) and "wikipedia.org" in str(doc.get("url") or "")
            ]
            if web_docs:
                graft = _graft_web_nodes_to_cloud_brain(web_docs, language)
                if graft.get("grafted_nodes"):
                    result["web_grafted_nodes"] = graft["grafted_nodes"]
                    result["web_graft"] = {
                        "cloud_brain_concepts_added": int(graft.get("concepts_added") or 0),
                        "cloud_brain_relations_added": int(graft.get("relations_added") or 0),
                        "candidate_store_path": graft.get("candidate_store_path"),
                        "production_store_mutated": bool(graft.get("production_store_mutated")),
                    }

    # Explicit "search / open / show me X" → the agent opens the iframe stage of
    # its own accord (the dashboard auto-renders it; orb slides aside).
    if isinstance(response.get("result"), dict) and not response["result"].get("render_iframe"):
        intent_iframe = _render_iframe_for_intent(question, language)
        if intent_iframe:
            response["result"]["render_iframe"] = intent_iframe


    # directive the frontend executes. A control instruction is never also a search.
    directive = _dashboard_directive_for(question)
    if directive and isinstance(response.get("result"), dict):
        response["result"]["dashboard_directive"] = directive
        if directive.get("action") == "close_window":
            for key in ("render_iframe", "render_iframe_tabs"):
                response["result"].pop(key, None)

    # SHAPE CATCH-ALL (design keystone, both answer paths): if the final answer is a cold
    # abstention and the question is CONVERSATIONAL (causal / advice / opinion / personal),

    # real limit and offers web search — never a fabricated answer, never a cold dead-end.
    # Only when web wasn't the source of a real answer and nothing better already fired.
    if isinstance(response.get("result"), dict):
        _res = response["result"]
        _ans = str(_res.get("answer") or "")
        _shape = _question_shape(question)
        # ONE context-aware engagement decision (owner 2026-07-20: "다중턴일 때만 엔진 켜는 건
        # 규칙기반이다 -- 하나의 모델로 통합돼야"). Was THREE separate post-hoc override branches
        # (discourse / opinion / conversational) -- three mode-switches. Now ONE call: the model reads
        # the full context (the ongoing conversation, the question's shape, whether its own first
        # answer abstained) and decides in a single place HOW to engage. It runs every request and
        # returns None when no engagement is warranted (context-awareness, not a second engine toggled
        # on). The three composers are reused as generation primitives; the SELECTION is unified.
        try:
            from packages.cgsr.cgsr.contextual_engage import contextual_engage as _ctx_engage
            _eng = _ctx_engage(
                question, getattr(request, "conversation_context", None) or [],
                shape=_shape, current_answer=_ans, is_abstention=_answer_is_abstention(_ans),
                current_kind=_res.get("answer_kind"), language=language, shape_engage_fn=_shape_engage,
            )
        except Exception:
            _eng = None
        if _eng:
            _res["answer"] = _eng["answer"]
            _res["answer_kind"] = _eng["answer_kind"]
            _res["can_speak"] = True
            _res["confidence"] = _eng["confidence"]

    # Pick ONE primary answer modality so the dashboard renders a single thing —
    # a readable document (iframe), a particle scene, or plain text — instead of
    # stacking unrecognisable particles. A web-grounded factual/entity lookup

    # particle scene; everything else is text.
    if isinstance(response.get("result"), dict) and not (directive and directive.get("action") == "close_window"):
        response["result"] = _decide_answer_modality(response["result"], question)
    # LEARNED-ROUTER RESCUE (first decision power, deliberately narrow): when
    # every rule lane passed and the engine is about to send the abstain
    # boilerplate for what the learned router confidently reads as CONVERSATION
    # (chatter/social/greeting), answer conversationally instead. Knowledge
    # abstentions are untouched — honesty is not negotiable, tone is.
    try:
        from packages.learned_router import predict as _router_predict
    except Exception:
        _router_predict = None
    if _router_predict is not None and isinstance(response.get("result"), dict):
        _res0 = response["result"]
        if _answer_is_abstention(str(_res0.get("answer") or "")):
            _rp0, _rc0 = _router_predict(question)
            # PROMOTION (Phase 1-1, gate measured: 36/40=90% on unseen phrasings,
            # all misses low-confidence): the learned router is the DECIDER for
            # the whole gap space — every intent class the rule lanes missed gets
            # its honest response shape. KNOWLEDGE intents (definition/relation/
            # temporal/…) stay with the honest abstain: a router names the
            # question's SHAPE, never conjures the answer. Regex lanes remain the
            # high-precision first layer (soft policy — quality only goes up).
            _GAP_RESPONSES = {
                "chatter": "네, 듣고 있어요. 편하게 이어가 주세요 — 궁금한 게 생기면 뭐든 물어보시고요.",
                "social": "네 :) 함께해서 좋아요. 필요할 때 언제든 불러주세요.",
                "greeting": "안녕하세요! 무엇이든 편하게 물어보세요.",
                "howto": ("그 절차를 단계별로 알려드리려면 확인된 근거가 필요한데, 지금 로컬 그래프에는 "
                          "단계별 근거가 없어요 — 지어내지 않을게요. 웹 검색을 켜 주시면 찾아볼 수 있어요."),
                "creative": ("저는 근거에서 답을 짓는 그래프 기반 엔진이라, 창작은 하지 않아요 — "
                             "지어내지 않는 것이 제 원칙이거든요. 뜻·유래·관계라면 정확히 도와드릴 수 있어요."),
                "realtime": ("실시간으로 변하는 정보는 확인 가능한 근거 없이는 답하지 않아요. "
                             "웹 검색을 켜 주시면 지금 값을 찾아볼 수 있어요."),
                "meta_language": "네, 알겠습니다. 어떤 내용을 다시 말씀드릴까요?",
                "false_premise": ("그 전제를 뒷받침하는 확인된 근거가 없어서, 그 위에서는 답을 짓지 "
                                  "않을게요. 사실관계가 확실한 부분부터 여쭤봐 주시면 정확히 답할 수 있어요."),
            }
            # ENGLISH ARM (2026-07-17): the map above was Korean-only, so a confident router read
            # on an English turn produced nothing here and the turn fell through to whichever lane
            # grabbed it — usually the dictionary, defining a stray word. Same honesty, same
            # refusals; only the language differs.
            _GAP_RESPONSES_EN = {
                "chatter": "I'm listening — go on. Ask me anything that comes up.",
                "social": "Good to have you here. Call on me whenever you need.",
                "greeting": "Hi! Ask me anything.",
                "howto": ("To give you the steps I'd need verified grounding, and my local graph "
                          "has no step-by-step evidence for it — I won't invent one. Turn on web "
                          "search and I can go look."),
                "creative": ("I build answers from evidence, so I don't do invention — not making "
                             "things up is the point of me. Meanings, origins and relations I can "
                             "do precisely."),
                "realtime": ("I don't answer things that change by the minute without checkable "
                             "grounding. Turn on web search and I can find the current value."),
                "meta_language": "Understood. Which part would you like me to go over again?",
                "false_premise": ("I have no verified grounding for that premise, so I won't build "
                                  "an answer on top of it. Ask me the part that's settled and I can "
                                  "answer precisely."),
            }
            _gap_map = _GAP_RESPONSES if language == "ko" else _GAP_RESPONSES_EN
            if _rc0 >= 0.6 and _rp0 in _gap_map:
                _res0["answer"] = _gap_map[_rp0]
                _res0["answer_kind"] = f"learned_router_{_rp0}"
                _res0["confidence"] = round(float(_rc0), 2)
                _res0["reasoning_certificate"] = {
                    "derivation_kind": "learned_router_decision",
                    "anchor_concept": None,
                    "steps": [{"type": "learned_intent", "fact": f"{_rp0} ({_rc0:.2f})"}],
                    "evidence_concepts": [], "confidence": round(float(_rc0), 2),
                    "confidence_basis": "trained_intent_classifier_gap_decider",
                    "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
                }
            else:
                # D1 PROMOTION TIER 2 (2026-07-13, adversarial-battery distill, holdout 0.872):
                # the LANE-candidate router — trained on rule lanes + the battery's gold labels —
                # rescues the remaining misses by re-dispatching to the REAL conversation
                # generator (not a canned map). ENGAGE lanes only; knowledge honesty untouched.
                try:
                    from packages.learned_router import router as _lr
                    _cand_npz = _lr.MODEL_DIR / "router_lane_candidate.npz"
                    _cand_meta = _lr.MODEL_DIR / "router_lane_candidate.meta.json"
                    _ENGAGE_LANES = {"self_conversation_opinion": "opinion",
                                     "self_conversation_smalltalk": "smalltalk",
                                     "advice_engage": "advice",
                                     "conversational_engage": "conversation"}
                    if _cand_npz.exists() and language == "ko":
                        _keep = (_lr.MODEL_PATH, _lr.META_PATH, dict(_lr._MODEL))
                        try:
                            _lr.MODEL_PATH, _lr.META_PATH = _cand_npz, _cand_meta
                            _lr._MODEL.update({"W": None, "mtime": 0.0})
                            _lp, _lc = _lr.predict(question)
                        finally:
                            _lr.MODEL_PATH, _lr.META_PATH = _keep[0], _keep[1]
                            _lr._MODEL.update(_keep[2])
                        if _lc >= 0.6 and _lp in _ENGAGE_LANES:
                            from packages.continuous_self.conversation import converse as _converse
                            _conv = _converse(question, _ENGAGE_LANES[_lp])
                            if _conv and _conv.get("answer"):
                                _res0["answer"] = _conv["answer"]
                                _res0["answer_kind"] = f"lane_router_{_lp}"
                                _res0["confidence"] = round(float(_lc), 2)
                except Exception:
                    pass  # promotion tier must never break the answer path
    # FLYWHEEL: log every real turn (question, answer, lane) plus the learned
    # router's SHADOW prediction. Disagreements between the rule lane that fired
    # and the learned prediction are the training gold that makes the next
    # router strictly better — the data engine behind all learned components.
    try:
        from packages.flywheel import log_turn
        from packages.learned_router import predict as _router_predict

        _res = response.get("result") if isinstance(response.get("result"), dict) else {}
        # METACOGNITION (Vision #3 deepening + #2 live): the self checks its OWN answer against
        # the question's compositional SemanticFrame and attaches an honest self-note. Advisory
        # + non-destructive — it never rewrites the answer here, only KNOWS (and the flag becomes
        # flywheel signal). This is the SemanticFrame going live as a validator on every turn.
        try:
            from packages.autonomy_kernel.answer_metacognition import note_for_certificate, suggest_correction
            _cert = _res.get("reasoning_certificate")
            _ans0 = str(_res.get("answer") or "")
            # SELF-CORRECTION (gated): if the self flags a CLEAR conversational-act mismatch and a
            # safe better-fitting response exists, it fixes its own answer before replying. Only
            # for definition/deflection/abstain shapes on conversational acts — a grounded fact is
            # never overridden. The self doesn't just KNOW it missed; it makes it right.
            # a GROUNDED fact is never softened into empathy/apology (enforce the stated invariant —

            _deriv0 = str((_cert or {}).get("derivation_kind") or "") if isinstance(_cert, dict) else ""
            _grounded = _deriv0 in {"spreading_activation", "structured_triple_lookup",
                                    "relation_execution", "functional_relation", "reasoning_vm",
                                    "deterministic_chained_reasoning", "multi_sense_enumeration"}
            if language == "ko" and not _grounded:
                _fix = suggest_correction(question, _ans0, _cert if isinstance(_cert, dict) else None)
                if _fix and _fix != _ans0:
                    _res["answer"] = _fix
                    _res["answer_kind"] = "self_corrected_" + str(_res.get("answer_kind") or "")
                    if isinstance(_cert, dict):
                        _cert["self_corrected"] = True
                        _cert["original_answer_shape"] = str((_cert or {}).get("derivation_kind") or "")
            if isinstance(_cert, dict):
                _cert.update(note_for_certificate(question, str(_res.get("answer") or ""), _cert))
        except Exception:
            pass
        _rp, _rc = _router_predict(question)
        # authoritative intent in the router's OWN vocabulary — the gold label the
        # flywheel was missing, so router-vs-gold agreement becomes measurable and
        # shadow->primary promotion can finally be judged on real data.
        try:
            from packages.graph_scale.query_frame import parse as _qf_parse
            _gold = str(_qf_parse(question).answer_type or "")
        except Exception:
            _gold = ""
        log_turn(question=question, answer=str(_res.get("answer") or ""),
                 answer_kind=str(_res.get("answer_kind") or ""),
                 confidence=float(_res.get("confidence") or 0.0),
                 language=language, context_len=len(request.conversation_context or []),
                 lane=str(_res.get("answer_kind") or ""), router_pred=_rp, router_conf=_rc,
                 gold_intent=_gold)
        if isinstance(_res, dict):
            _res["_fw_logged"] = True   # tell the outer chokepoint this turn is already fed
        # AUTONOMOUS HEARTBEAT (Vision #4 schedule): real traffic ticks the self-improvement
        # orchestrator on a background thread — self-throttled (~30 min), never blocks the reply.
        try:
            from packages.autonomy_kernel.orchestrator import trigger_background
            trigger_background()
        except Exception:
            pass
    except Exception:
        pass

    # person / offline expert (PROPHETA) / web sage. Cached detection (30s TTL), never raises,
    # never blocks. A web-escalated answer is already SAGE by construction.
    try:
        from packages.reasoning_vm.capability_tier import annotate as _tier_annotate
        _res_t = response.get("result")
        if isinstance(_res_t, dict):
            _tier_annotate(_res_t, confidence=float(_res_t.get("confidence") or 0.0))
    except Exception:
        pass
    # UNIVERSAL ANSWER-FIT GATE (owner 2026-07-20: "말을 내뱉기 전에 맥락 검토하는 시스템이 없나?").
    # The one check a speaker owes before speaking, on EVERY answer at this single exit: does the
    # candidate actually address what was asked? Measured failure it exists to stop: a control-task
    # spec answered with "Its is a possessive determiner…" (keyword fallback grabbed the incidental
    # 'its'). General signals only (function-word anchor / zero content overlap / parrot echo) — a
    # mismatch ships an honest comprehension-limit reply instead of confident nonsense
    # (voice-or-silence enforced globally). Passes silently when the answer fits.
    try:
        from packages.cgsr.cgsr.relevance_gate import answer_fit, honest_limit_reply
        _res_g = response.get("result")
        if isinstance(_res_g, dict) and _res_g.get("answer"):
            _fit = answer_fit(question, str(_res_g["answer"]), _res_g.get("answer_kind"))
            if not _fit.get("fits", True):
                _res_g["answer"] = honest_limit_reply(question)
                _res_g["answer_kind"] = "comprehension_limit"
                _res_g["confidence"] = 0.2
                _res_g["can_speak"] = True
                _res_g["fit_gate"] = _fit.get("reason")
    except Exception:
        pass
    # CO KEYSTONE (flag ATANOR_CO_CENTRAL, default OFF): route the FINALIZED main knowledge answer — the
    # frame_realizer multi-fact prose — through the response WORKSPACE so compose_response governs it,
    # instead of it bypassing the workspace entirely. The main answer bids as a first-class 'ATANOR Main'
    # candidate (grounding = its honest confidence, capped strictly below the verified reasoning lanes),
    # carrying its grounded bones; specialists compete on grounding (a low lane can never out-rank a solid
    # knowledge answer -> no hijack) and the fluency surface pass applies to the winner. The no-drop gate
    # in the workspace keeps a curated-prose answer BYTE-IDENTICAL (a bones reshape that would drop the
    # prose definition is rejected), so this can preserve or (for a bone-derived answer) faithfully improve
    # the surface, never degrade it. Fully guarded + try/excepted: it can never break the answer path, and
    # with the flag OFF it does nothing at all.
    if _co_central_enabled():
        try:
            _res_w = response.get("result")
            # Route only the frame_realizer knowledge prose (kind-in-set), and only a solid answer
            # (confidence >= 0.5 excludes an honest abstain). `can_speak` is NOT yet finalized at this
            # exit (it is set by the outer handler), so it is not part of the guard.
            if (isinstance(_res_w, dict)
                    and str(_res_w.get("answer_kind") or "") in _CO_CENTRAL_KNOWLEDGE_KINDS
                    and str(_res_w.get("answer") or "").strip()
                    and float(_res_w.get("confidence") or 0.0) >= 0.5):     # a solid answer, not an abstain
                from packages.base_brain.zero_user_answer import english_answer_bones
                from packages.cgsr.cgsr.response_workspace import route_knowledge_answer
                _bones = english_answer_bones(question)
                _routed = route_knowledge_answer(
                    str(_res_w["answer"]), str(_res_w["answer_kind"]),
                    float(_res_w.get("confidence") or 0.0), _understanding, question, bones=_bones)
                if _routed.get("won_by") == "specialist" and str(_routed.get("answer") or "").strip():
                    # a specialist genuinely out-grounded the knowledge answer on its own shape
                    _res_w["answer"] = _routed["answer"]
                    _res_w["answer_kind"] = _routed["answer_kind"]
                    _res_w["confidence"] = _routed["confidence"]
                elif str(_routed.get("answer") or "").strip():
                    # the knowledge answer won; adopt the workspace surface (no-drop keeps prose identical,
                    # a bone-derived answer may be a faithful fluency improvement)
                    _res_w["answer"] = _routed["answer"]
                # honest transparency: record the arbitration + fluency verdict (never a gate)
                if isinstance(_res_w.get("compact_trace"), dict):
                    _res_w["compact_trace"]["co_central"] = {
                        "won_by": _routed.get("won_by"), "engine": _routed.get("engine_name"),
                        "considered": _routed.get("considered"),
                        "fluency_adopted": bool((_routed.get("fluency") or {}).get("adopted")),
                        "fluency_reason": (_routed.get("fluency") or {}).get("reason"),
                    }
        except Exception:  # pragma: no cover - the keystone must never break the answer path
            pass
    # close the turn on the ONE timeline: ATANOR's own utterance joins the same UTC spine the
    # user's did — the conversation is now a run of events the block-universe view can survey.
    try:
        from packages.temporal_reasoning.unified_timeline import default_timeline
        _res_a = response.get("result")
        if isinstance(_res_a, dict) and _res_a.get("answer"):
            default_timeline().record(
                "utterance", str(_res_a["answer"]), who="atanor",
                meta={"channel": "chat", "answer_kind": str(_res_a.get("answer_kind") or "")})
    except Exception:
        pass
    return response


_VISUAL_SCENE_CUE_RE = re.compile(
    r"(떨어|낙하|중력|궤도|움직|이동|회전|충돌|흐르|퍼지|파동|간섭|시각|보여|그려|장면|"
    r"fall|drop|gravity|orbit|motion|move|rotat|collide|wave|interfere|visual|show me|draw|scene)",
    re.IGNORECASE,
)

# The orb has authority over the dashboard surface. The user can instruct it in
# natural language; each directive is acted on by the frontend (no buttons).
_CLOSE_WINDOW_RE = re.compile(
    r"((창|탭|페이지|문서|화면|이거|그거|이걸|그걸|window|tab|page|it)\s*\S{0,5}(닫|꺼|치워|없애|지워|close|hide|dismiss))"
    r"|^\s*(창\s*)?(닫아(줘)?|닫어|꺼(줘)?|치워(줘)?|없애|닫기|close( it)?|dismiss)\s*$",
    re.IGNORECASE,
)
_NEW_TAB_RE = re.compile(r"(새\s*(탭|창)|탭\s*(추가|열어)|new\s+tab|open\s+(a\s+)?tab)", re.IGNORECASE)


def _dashboard_directive_for(question: str) -> dict[str, Any] | None:
    """Map a natural-language dashboard instruction to a control directive the
    orb executes on the surface (close/dismiss the document window, etc.)."""
    text = (question or "").strip()
    if not text:
        return None
    if _CLOSE_WINDOW_RE.search(text):
        return {"action": "close_window"}
    return None


def _decide_answer_modality(result: dict[str, Any], question: str) -> dict[str, Any]:
    """Resolve a single primary modality and prune the others.

    iframe (document) wins for web-grounded entity/factual lookups; a particle
    scene is kept only for explicitly visual/physical questions; otherwise text.
    """
    grafted = result.get("web_grafted_nodes") or []
    wants_visual = bool(_VISUAL_SCENE_CUE_RE.search(question or ""))

    # A web-grounded entity lookup with no explicit iframe yet → open its source.
    if grafted and not result.get("render_iframe") and not wants_visual:
        primary = grafted[0] if isinstance(grafted[0], dict) else {}
        src = str(primary.get("source_url") or "")
        if src:
            result["render_iframe"] = {"url": src, "title": str(primary.get("label") or question[:60])}

    scene_keys = (
        "scene_choreography", "splatra_scene_plan", "splatra_command_sequence",
        "splatra_interactive_scene_analysis", "splatra_cartridge_queue",
        "splatra_sidecar_dispatch", "visual_scene_plan", "render_fold_scene",
        "folded_state_field",
    )
    has_scene = any(result.get(key) for key in scene_keys)

    if result.get("render_iframe") and not wants_visual:
        result["answer_modality"] = "iframe"
        # Open the answer's source plus its related grafted pages as browser-style
        # tabs in one window.
        tabs: list[dict[str, str]] = []
        seen: set[str] = set()
        primary = result["render_iframe"]
        primary_url = str(primary.get("url") or "")
        if primary_url:
            tabs.append({"url": primary_url, "title": str(primary.get("title") or "")})
            seen.add(primary_url)
        for node in grafted:
            if not isinstance(node, dict):
                continue
            url = str(node.get("source_url") or "")
            if url and url not in seen:
                tabs.append({"url": url, "title": str(node.get("label") or "")})
                seen.add(url)
            if len(tabs) >= 5:
                break
        if len(tabs) > 1:
            result["render_iframe_tabs"] = tabs
        # Don't render a particle scene behind the document.
        for key in scene_keys:
            result.pop(key, None)
    elif wants_visual and has_scene:
        result["answer_modality"] = "particle_scene"
        result.pop("render_iframe", None)
    elif has_scene and not result.get("render_iframe"):
        result["answer_modality"] = "particle_scene"
    else:
        result["answer_modality"] = "iframe" if result.get("render_iframe") else "text"
    return result


def _atanor_self_sense() -> dict[str, Any]:
    """A unified 'body sense' of the whole program — the agent lives inside it and
    can feel every part in one call. Read-only aggregation across subsystems; each
    source is wrapped so one failing subsystem never blanks the others."""

    sense: dict[str, Any] = {"schema": "atanor.self-sense.v1"}

    # Local Brain (private memory)
    try:
        sense["local_brain"] = LOCAL_BRAIN.status()
    except Exception:
        sense["local_brain"] = {"available": False}

    # Web facts it has looked up and remembered locally
    try:
        sense["web_memory"] = {"facts_remembered": int(WEB_FACT_MEMORY.status().get("total_facts") or 0)}
    except Exception:
        sense["web_memory"] = {"facts_remembered": 0}

    # Cloud Brain (public learned graph)
    try:
        from apps.api.app.routers.cloud_brain import cloud_brain_status

        cb = cloud_brain_status()
        sense["cloud_brain"] = {"nodes": (cb.get("counts") or {}).get("nodes", 0), "edges": (cb.get("counts") or {}).get("edges", 0), "state": cb.get("state")}
    except Exception:
        sense["cloud_brain"] = {"available": False}

    # Autonomous loop + review queue + community (AGORA)
    try:
        from apps.api.app.routers.agentic_micro_os import AUTONOMOUS_DAEMON, REVIEW_QUEUE

        sense["autonomous"] = {"running": AUTONOMOUS_DAEMON.is_running(), "review_pending": int(REVIEW_QUEUE.status().get("pending") or 0), "learned_total": int(REVIEW_QUEUE.status().get("items_total") or 0)}
    except Exception:
        sense["autonomous"] = {"available": False}

    # Emotion / inner state
    try:
        snapshot = EVENT_BUS.engine.snapshot().to_dict()
        vector = snapshot.get("vector") or {}
        sense["mood"] = {"valence": vector.get("valence"), "curiosity": vector.get("curiosity"), "fatigue": vector.get("fatigue")}
    except Exception:
        sense["mood"] = {"available": False}

    return sense


@router.get("/api/atanor/self-sense")
def atanor_self_sense() -> dict[str, Any]:
    return {**_flags(), **_atanor_self_sense()}


@router.get("/api/atanor/user-model")
def atanor_user_model() -> dict[str, Any]:
    """Phase 3-2: the derived user deep model (possessions/habits/preferences),
    every item evidence-backed, local stores only."""
    from packages.user_model import derive_user_model, summary_facts, user_context_line

    model = derive_user_model()
    return {**model, "summary": summary_facts(model), "context_line": user_context_line(model)}


@router.get("/api/media/capabilities")
def media_capabilities_endpoint() -> dict[str, Any]:
    from app.services.media_reader import media_capabilities

    return media_capabilities()


@router.post("/api/media/read")
def media_read_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Read non-text media into text so ATANOR can ground on it: a YouTube URL → its
    transcript, an image path → OCR text. Honest capability degradation when a reader
    (Tesseract) isn't installed."""
    from app.services.media_reader import read_image_ocr, read_image_ocr_b64, read_video_transcript

    url = str(payload.get("url") or payload.get("video") or "").strip()
    image = str(payload.get("image_path") or payload.get("image") or "").strip()
    image_b64 = str(payload.get("image_b64") or "").strip()
    if url:
        return read_video_transcript(url)
    if image_b64:
        return read_image_ocr_b64(image_b64)
    if image:
        return read_image_ocr(image)
    return {"ok": False, "text": "", "error": "provide 'url' (video), 'image_b64' (upload), or 'image_path'"}


_SELF_STATE_KO = ("지금 뭐", "뭐하고", "뭐 하고", "무엇을 하", "네 상태", "너 상태", "기분이 어때",
                  "기분 어때", "뭘 배웠", "무엇을 배웠", "뭐 배웠", "뭘 배우", "배우고 있",
                  "얼마나 알", "무슨 생각", "어떻게 지내", "존재 이유", "왜 존재")
_SELF_STATE_EN = ("what are you doing", "what have you learned", "how are you", "your state", "your mood", "what do you know", "how much do you know", "what are you thinking")
# The self-state path fires only when the sentence is ADDRESSED to ATANOR — a


_SELF_REF_KO = ("너", "네", "니", "당신", "atanor", "아타노르", "자기", "스스로")

# counterpart by default — Korean drops the pronoun. When the cue is about
# thought/mood AND the question names no other subject, the 2nd person is implicit.
_INNER_STATE_KO = ("무슨 생각", "기분 어때", "기분이 어때")


_VISUAL_LOOK_RE = re.compile(
    r"(?P<subj>[가-힣A-Za-z0-9·\s]{1,24}?)(?P<part>[은는이가])?\s+(?:어떻게\s*생겼|모습\s*이?\s*어때|무슨\s*색(?:깔)?\s*이?[야에]?)")
# ENGLISH CUES (2026-07-17). The visual/association lanes were Korean-cue-only, so an English
# "what does X look like?" never reached them and fell to the knowledge lanes — which answered
# about the wrong word entirely. The recall machinery itself (visual memory, metaphor, phase
# field) is language-agnostic; only the cue and the subject slot were Korean.
_VISUAL_LOOK_EN = re.compile(
    r"what\s+(?:does|do)\s+(?:the\s+|a\s+|an\s+)?(?P<subj>[A-Za-z0-9·'\- ]{2,32}?)\s+look\s+like"
    r"|what\s+colou?r\s+is\s+(?:the\s+|a\s+|an\s+)?(?P<subj2>[A-Za-z0-9·'\- ]{2,32}?)\s*\??$",
    re.IGNORECASE)
_ASSOC_EN = re.compile(
    r"what\s+do\s+you\s+associate\s+with\s+(?P<subj>[A-Za-z0-9·'\- ]{2,32}?)\s*\??$"
    r"|what\s+does\s+(?P<subj2>[A-Za-z0-9·'\- ]{2,32}?)\s+remind\s+you\s+of"
    r"|what\s+is\s+(?P<subj3>[A-Za-z0-9·'\- ]{2,32}?)\s+like\s*\??$",
    re.IGNORECASE)


def _en_cue_subject(m: "re.Match[str] | None") -> str:
    """The first non-empty named group — the cue alternatives each carry their own subject slot."""
    if not m:
        return ""
    for g in m.groupdict().values():
        if g and g.strip():
            return re.sub(r"\s+", " ", g.strip())
    return ""
_VISUAL_SELF = {"너", "당신", "네", "니", "atanor", "아타노르"}

_COLOR_NAMES_KO = [
    ((0.85, 0.15, 0.15), "붉은"), ((0.9, 0.55, 0.1), "주황빛"), ((0.9, 0.85, 0.2), "노란"),
    ((0.2, 0.7, 0.25), "초록빛"), ((0.15, 0.65, 0.65), "청록빛"), ((0.2, 0.35, 0.85), "푸른"),
    ((0.55, 0.25, 0.75), "보랏빛"), ((0.9, 0.6, 0.7), "분홍빛"), ((0.5, 0.33, 0.2), "갈색의"),
    ((0.55, 0.55, 0.55), "잿빛의"), ((0.08, 0.08, 0.08), "어두운"), ((0.95, 0.95, 0.95), "흰"),
]


# Same anchors as _COLOR_NAMES_KO — one measurement, two vocabularies. The visual lane was
# Korean-only down to the colour words, so English "what does X look like?" had nowhere to land.
_COLOR_NAMES_EN = [
    ((0.85, 0.15, 0.15), "red"), ((0.9, 0.55, 0.1), "orange"), ((0.9, 0.85, 0.2), "yellow"),
    ((0.2, 0.7, 0.25), "green"), ((0.15, 0.65, 0.65), "teal"), ((0.2, 0.35, 0.85), "blue"),
    ((0.55, 0.25, 0.75), "purple"), ((0.9, 0.6, 0.7), "pink"), ((0.5, 0.33, 0.2), "brown"),
    ((0.55, 0.55, 0.55), "grey"), ((0.08, 0.08, 0.08), "near-black"), ((0.95, 0.95, 0.95), "white"),
]


def _color_name_en(rgb: list[float]) -> str:
    best, name = 10.0, "colourless"
    for (r, g, b), n in _COLOR_NAMES_EN:
        d = (r - rgb[0]) ** 2 + (g - rgb[1]) ** 2 + (b - rgb[2]) ** 2
        if d < best:
            best, name = d, n
    return name


def _recall_scene_for(candidates: list[str]) -> tuple[Any, str]:
    """Shared recall: READ-ONLY on the hot path; a miss queues learning in the background.

    Measured 2026-07-17 (surgery Phase 5, cProfile): the on-miss learn_visual() ran a LIVE
    urllib image fetch synchronously inside the answer path — 2.02s of a 2.51s turn, 80% of
    every unknown "what does X look like?" — and it was the whole holdout p95 excursion
    (5.1-5.4s vs the 5.0 gate). It also fired with web_search=False while the certificate
    said web_used=False — a quiet honesty violation, not just a slow one.

    Doctrine (pipeline-efficiency-audit, BINDING): the hot path READS; learning happens off
    it. So: answer NOW from what is on file (honest limit when nothing is), and let a
    daemon-thread fetch feed the NEXT ask. Same shape as every other learner in this engine.
    """
    try:
        from packages.perception import learn_visual, recall_scene
    except Exception:
        return None, ""
    for cand in candidates:
        try:
            scene = recall_scene(cand)
            if scene:
                return scene, cand
            import threading
            threading.Thread(target=learn_visual, args=(cand,),
                             kwargs={"log": lambda *_: None}, daemon=True).start()
        except Exception:
            continue
    return None, ""


def _visual_recall_from(subj: str, candidates: list[str], question: str,
                        language: str) -> dict[str, Any] | None:
    """English visual recall — MEASURED colour bands rendered into English, never invented.
 The Korean path below keeps its own realizer (josa, ); only the measurement is shared.
 No scene on file → None, so the turn falls to an honest limit instead of a guess."""
    scene, matched = _recall_scene_for([c for c in candidates if c and len(c) >= 2])
    if not scene or not scene.get("bands"):
        return None
    bands = scene["bands"]
    top, bottom = _color_name_en(bands[0]), _color_name_en(bands[-1])
    accents = []
    for p in (scene.get("palette") or [])[:2]:
        n = _color_name_en(p)
        if n not in (top, bottom) and n not in accents:
            accents.append(n)
    lum = float(scene.get("luminance") or 0.5)
    tone = "bright" if lum > 0.6 else ("dark" if lum < 0.35 else "mid-toned")
    texture = "textured" if float(scene.get("drift") or 0) > 0.5 else "smooth"
    n_img = int(scene.get("measured_from") or 0)
    text = (f"From what I've actually measured, {matched or subj} reads {tone} and {texture} — "
            f"{top} toward the top, {bottom} toward the bottom"
            + (f", with {' and '.join(accents)} coming through" if accents else "") + ".")
    if n_img:
        text += f" That's from {n_img} image{'s' if n_img != 1 else ''} I looked at, not a description I read."
    return {
        "answer": text,
        "answer_kind": "visual_recall",
        "can_speak": True,
        "confidence": 0.62,
        "reasoning_certificate": {
            "derivation_kind": "measured_visual_memory",
            "anchor_concept": matched or subj,
            "steps": [{"type": "colour_band", "fact": f"{top}→{bottom} lum={lum:.2f}"}],
            "evidence_concepts": [], "confidence": 0.62,
            "confidence_basis": "measured_colour_bands_from_real_images",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
        },
    }


def _color_name_ko(rgb: list[float]) -> str:
    """Nearest Korean color word for a MEASURED rgb — rendering data into words,
    not inventing knowledge."""
    best, name = 10.0, "무채색의"
    for (r, g, b), n in _COLOR_NAMES_KO:
        d = (r - rgb[0]) ** 2 + (g - rgb[1]) ** 2 + (b - rgb[2]) ** 2
        if d < best:
            best, name = d, n
    return name


def _visual_recall_answer(question: str, language: str) -> dict[str, Any] | None:
    """Phase 4-2: ' ' answers from the MEASURED visual memory (color
 bands/palette/texture from real photos) and re-renders it as particles —
 recall as imagination, never playback. Unknown + unlearnable -> None."""
    if language != "ko":
        # ENGLISH ARM: same recall, English cue. No josa ambiguity to resolve, so the cue's
        # subject slot is already the whole phrase ("the Eiffel Tower" → "Eiffel Tower").
        _en_subj = _en_cue_subject(_VISUAL_LOOK_EN.search(str(question or "")))
        if not _en_subj or _en_subj.lower() in _VISUAL_SELF:
            return None
        _vr = _visual_recall_from(_en_subj, [_en_subj], question, language)
        if _vr:
            return _vr
        # NO SCENE ON FILE: own the miss here instead of returning None. Falling through let the
        # graph lanes answer a "what does it look like?" with whatever they had — measured:
        # "polar bear is located in artic. polar bear is located in ..." Appearance is not
        # location; not having looked at it is the honest answer.
        return {
            "answer": (f"I haven't looked at any images of {_en_subj}, so I can't tell you how it "
                       f"looks — I'd only be repeating a description, not recalling one. Ask me "
                       f"what it is and I can answer that from evidence."),
            "answer_kind": "honest_capability_limit",
            "can_speak": True,
            "confidence": 0.8,
            "reasoning_certificate": {
                "derivation_kind": "honest_capability_limit",
                "anchor_concept": _en_subj, "steps": [], "evidence_concepts": [],
                "confidence": 0.8, "confidence_basis": "no_visual_memory_for_subject",
                "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
            },
        }
    m = _VISUAL_LOOK_RE.search(str(question or ""))
    if not m:
        return None
    base = re.sub(r"\s+", " ", m.group("subj")).strip()
    part = m.group("part") or ""


    # noun-final syllable and subject particle, so try the longer reading first.
    candidates = [base + part, base] if part in ("이", "가") else [base]
    candidates = [c for c in candidates
                  if c and c.lower() not in _VISUAL_SELF and len(c) >= 2]
    if not candidates:
        return None
    scene = None
    subj = candidates[0]
    try:
        from packages.perception import learn_visual, recall_scene

        for cand in candidates:
            scene = recall_scene(cand)
            if scene is None:
                learn_visual(cand, log=lambda *_: None)  # bounded on-miss learn
                scene = recall_scene(cand)
            if scene:
                subj = cand
                break
    except Exception:
        return None
    if not scene or not scene.get("bands"):
        return None
    from urllib.parse import quote

    bands = scene["bands"]
    palette = scene.get("palette") or []
    top_name = _color_name_ko(bands[0])
    bottom_name = _color_name_ko(bands[-1])
    accents = []
    for p in palette[:2]:
        n = _color_name_ko(p)
        if n not in (top_name, bottom_name) and n not in accents:
            accents.append(n)
    lum = float(scene.get("luminance") or 0.5)
    tone = "밝은" if lum > 0.6 else ("어두운" if lum < 0.35 else "중간 밝기의")
    texture = "결이 많은" if float(scene.get("drift") or 0) > 0.5 else "매끈한"
    accent_txt = (" " + "·".join(accents) + " 색이 포인트로 섞입니다." ) if accents else ""
    n_img = int(scene.get("measured_from") or 0)
    try:
        from packages.lad_morphology import topic as _josa_topic

        subj_topic = _josa_topic(subj)
    except Exception:
        subj_topic = f"{subj}은(는)"
    answer = (
        f"실제 사진 {n_img}장을 측정한 기억으로는, {subj_topic} 위쪽이 {top_name} 톤, "
        f"아래쪽이 {bottom_name} 톤인 {tone} {texture} 모습이에요.{accent_txt} "
        f"지금 그 시그니처에서 파티클로 다시 그려볼게요 — 재생이 아니라 기억에서의 재구성입니다."
    )
    return {
        "answer": answer,
        "answer_kind": "visual_memory_recall",
        "confidence": 0.8,
        "render_iframe": {"url": f"/recall?concept={quote(subj)}",
                          "title": f"{subj} — 시각 기억 재현"},
        "reasoning_certificate": {
            "derivation_kind": "visual_signature_recall",
            "anchor_concept": {"id": subj, "label": subj, "match": "visual_memory"},
            "steps": [{"type": "measurement", "source": s, "fact": "photo signature"}
                      for s in (scene.get("sources") or [])[:3]],
            "evidence_concepts": [subj],
            "confidence": 0.8,
            "confidence_basis": f"measured_from_{n_img}_photos",
            "guarantees": {"external_llm": False, "fabricated_facts": False,
                           "playback": False, "reconstruction_from_signature": True},
        },
    }


_ASSOC_RE = re.compile(
    r"(?P<subj>[가-힣A-Za-z0-9·\s]{2,24}?)(?:[은는이가])?\s*"
    r"(?:(?:뭐|무엇)\s*같아|하면\s*(?:뭐|무엇)[가이]?\s*떠올|연상\s*되는\s*게?\s*뭐)")


def _association_answer(question: str, language: str) -> dict[str, Any] | None:
    """Qualia seeds surfaced (3-7/3-8): 'X ?' answers from the trained
 phase field — a grounded metaphor and, when a visual memory exists, the
 felt impression. Nothing in the band -> None (never a forced simile)."""
    if language != "ko":
        # ENGLISH ARM: same phase-field metaphor, English cue and surface. Nothing in the band →
        # None (never a forced simile) — the honest limit is better than an invented association.
        _s = _en_cue_subject(_ASSOC_EN.search(str(question or "")))
        if not _s or _s.lower() in _VISUAL_SELF:
            return None
        try:
            from packages.graph_scale.metaphor import metaphor as _met_en

            _m = _met_en(_s)
        except Exception:
            _m = None
        _vehicle = str((_m or {}).get("vehicle") or "").strip() if isinstance(_m, dict) else str(_m or "").strip()
        if not _vehicle or re.search(r"[가-힣]", _vehicle):
            return None
        return {
            "answer": (f"In the field I've trained, {_s} sits closest to {_vehicle} — that's a "
                       f"resonance I measured, not a feeling I'm claiming. What does it bring up "
                       f"for you?"),
            "answer_kind": "grounded_metaphor",
            "can_speak": True,
            "confidence": 0.55,
            "reasoning_certificate": {
                "derivation_kind": "phase_field_resonance",
                "anchor_concept": _s,
                "steps": [{"type": "metaphor_vehicle", "fact": _vehicle}],
                "evidence_concepts": [], "confidence": 0.55,
                "confidence_basis": "trained_phase_field_nearest_vehicle",
                "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
            },
        }
    m = _ASSOC_RE.search(str(question or ""))
    if not m:
        return None
    subj = re.sub(r"\s+", " ", m.group("subj")).strip()
    if not subj or len(subj) < 2 or subj.lower() in _VISUAL_SELF:
        return None
    met = imp = None
    try:
        from packages.graph_scale.metaphor import metaphor

        met = metaphor(subj)
    except Exception:
        met = None
    try:
        from packages.continuous_self.sensory_interference import impression_from_visual

        imp = impression_from_visual(subj)
    except Exception:
        imp = None
    if not met and not imp:
        return None
    parts: list[str] = []
    steps: list[dict[str, Any]] = []
    if imp:
        parts.append(imp["felt"])
        steps.append({"type": "sensory_impression", "source": "visual_memory",
                      "fact": f"measured_from={imp.get('measured_from')}"})
    if met:
        parts.append(met["surface"])
        steps.append({"type": "cross_domain_resonance", "source": "trained_phase_space",
                      "fact": f"{met['vehicle']} @ {met['resonance']}"})
    return {
        "answer": " ".join(parts),
        "answer_kind": "phase_field_association",
        "confidence": 0.7,
        "reasoning_certificate": {
            "derivation_kind": "phase_field_association",
            "anchor_concept": {"id": subj, "label": subj, "match": "phase_space"},
            "steps": steps,
            "evidence_concepts": [subj],
            "confidence": 0.7,
            "confidence_basis": "measured_resonance_band",
            "guarantees": {"external_llm": False, "fabricated_facts": False,
                           "forced_simile": False},
        },
    }


    # _vary (seeded phrasing-variation over hand-curated pools) was REMOVED — owner 2026-07-15:

    # learned from prose; every engage path now emits a single honest line (rougher, but no template).






_DISTRESS_STEMS = {"힘들", "지치", "속상하", "슬프", "우울하", "괴롭", "외롭", "답답하", "막막하",
                   "허무하", "무기력하", "서럽", "울적하", "쓸쓸하", "버겁", "벅차", "지겹", "짜증나",
                   "화나", "억울하", "서글프", "우울", "불안하", "초조하", "울"}


def _distress_by_morph(q: str) -> bool:
    """True when the utterance's predicate (verb/adjective) stem is a distress lemma — catches
    all conjugations, unlike the substring regex. Kiwi-only; silent-false when Kiwi is down."""
    try:
        from packages.base_brain.neighborhood import _kiwi
        kw = _kiwi()
        if kw is None:
            return False
        for t in kw.tokenize(q):
            if t.tag in ("VA", "VV", "VA-I", "VV-I") and t.form in _DISTRESS_STEMS:
                return True
    except Exception:
        return False
    return False




# pure-empathy felt because this intent was invisible; the felt lane swallowed the ask.
_HELP_INTENT = re.compile(
    r"어떻게\s*(하면|해야|하지|할까|하나|하는\s*게|좀)\s*(좋을까|좋지|좋아|될까|할까|돼요|되나|하죠)"
    r"|어떻게\s*(좀\s*)?(해결|극복|고치|줄이|나아|낫|바꾸)"
    r"|어떡하(지|나|면|죠|담|라고)|어쩌면\s*좋|어째야"
    r"|방법\s*(이|을|좀)?\s*(있을까|없을까|알려|찾|추천|없나|뭐)|무슨\s*방법|팁\s*(좀|있|알려)|조언\s*(좀|해|구|부탁)")


def _advice_engage(q: str, language: str) -> dict[str, Any] | None:
    """A help-seeking turn (' ?') must ENGAGE the concern
 with SUBSTANCE — never pure empathy (owner 2026-07-11: ) and never the
 content-free 'it depends, turn on web search' template. Fuses: brief acknowledgment + the
 concern TOPIC named + grounded related factors WHEN the graph holds them + an honest
 non-expert limit + an invitation. Facts are PULLED (get_semantic_context), never invented;
 a thin graph just yields the honest topic-named offer (still substance, not empathy soup)."""
    if language != "ko":
        return None





    _ADV_STOP = {"요즘", "요새", "오늘", "최근", "근래", "지금", "자꾸", "너무", "정말", "진짜",
                 "계속", "많이", "조금", "가끔", "매일", "이번", "다음", "무슨", "어떤",
                 "것", "수", "데", "때", "줄", "게", "거", "저", "제", "그", "이", "저희"}
    # MORPHOLOGY FIRST (T1 fix 2026-07-11): a regex object-marker grab mistook the verb ending


    topic = ""
    try:
        from packages.graph_scale.query_frame import _kiwi_subject
        _k = _kiwi_subject(q) or ""
        if _k and _k not in _ADV_STOP:
            topic = _k
    except Exception:
        topic = ""
    if not topic:
        obj = re.findall(r"([가-힣]{1,12})(?:을|를)", q)          # object-marked concern
        subj = re.findall(r"([가-힣]{1,12})(?:이|가|은|는|에서|때문)", q)
        for cand in obj + subj:
            if cand not in _ADV_STOP:
                topic = cand
                break
    if topic in _ADV_STOP:
        topic = ""
    # grounded related factors — pulled from the pack, never fabricated
    related: list[str] = []
    if topic:
        try:
            from packages.base_brain.pack_loader import get_semantic_context, load_base_brain_pack
            for c in (get_semantic_context(topic, load_base_brain_pack(), limit=8) or []):
                nm = str(c.get("canonical_name") or "").strip()
                if nm and _norm_cmp(nm) != _norm_cmp(topic) and 2 <= len(nm) <= 14:
                    related.append(nm)
                if len(related) >= 3:
                    break
        except Exception:
            related = []
    ack = "많이 힘드시겠어요."
    if topic:
        body = f" 제가 의사처럼 단정해 드릴 순 없지만, 아는 근거 안에서 '{topic}' 문제를 함께 짚어볼 수 있어요."
        if related:
            body += f" 우선 '{topic}'과(와) 얽힌 것들 — {'·'.join(related)} — 부터 살펴볼까요?"
    else:
        body = " 저는 지어내서 조언하진 않지만, 아는 근거 안에서 함께 짚어볼 수 있어요."
    tail = " 어떤 점이 가장 힘든지 조금 더 들려주시면, 거기에 맞춰 근거와 함께 정리해 드릴게요."
    return {"answer": ack + body + tail, "answer_kind": "advice_engage",
            "can_speak": True, "confidence": 0.55,
            "reasoning_certificate": {"derivation_kind": "advice_engage", "anchor_concept": topic or None,
                "steps": [{"type": "engage", "fact": f"help-seeking on '{topic or '?'}', {len(related)} grounded factor(s)"}],
                "evidence_concepts": related, "confidence": 0.55,
                "confidence_basis": "help_intent_grounded_engage",
                "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False}}}


def _norm_cmp(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()





_CONSEQUENCE_Q = re.compile(
    r"(많이|과하게|과다|너무|계속|자주|매일)\s*[가-힣]*\s*(면|으면|다\s*보면)\s*(어떻게|무슨|어찌|괜찮)"
    r"|(면|으면)\s*어떻게\s*(돼|되|되나|되나요|될까)"
    r"|(면|으면)\s*(무슨\s*일|문제|부작용|탈)\s*(이|은|생|나|되)"

    # that noun, the verb left implicit. The trailing noun+topic-marker+? is the tell.
    r"|(면|으면)\s*[가-힣]{0,6}\s*[가-힣]{1,10}(?:은|는)\s*[?？]\s*$")


def _subject_property_from_context(subject: str, ctx: list) -> str:
    """The subject's SALIENT property as the conversation established it — read from prior turns,
 not invented. ' … ' → ; ' …' → . Contextual
 understanding (the property the DISCOURSE attached to the subject), not a token grab."""
    subj = _norm_cmp(subject)
    for turn in reversed(list(ctx or [])):
        text = str((turn or {}).get("content") or (turn or {}).get("text")
                   or (turn or {}).get("message") or "") if isinstance(turn, dict) else str(turn or "")
        if not text or subj not in _norm_cmp(text):
            continue

        m = re.search(r"([가-힣]{2,8})\s*(?:효과|작용|기능)", text)
        if m and _norm_cmp(m.group(1)) != subj:
            return m.group(1)

        m = re.search(r"([가-힣]{2,10})\s*(?:음료|성분|함유|포함|들어|들어있|이\s*들|가\s*들)", text)
        if m and _norm_cmp(m.group(1)) != subj:
            return m.group(1)
    return ""


def _consequence_engage(question: str, ctx: list) -> dict[str, Any] | None:
    """Answer a consequence question AS causal: reference the subject's known property (from the
    discourse) + an HONEST limit on the specific effect (the graph doesn't hold coffee's effects,
    measured) + a web offer. Never fabricates the effect; never returns the subject's definition."""
    q = str(question or "")
    subject = ""
    m = re.search(r"([가-힣]{2,12})(?:을|를|이|가|은|는)\s", q)
    if m and m.group(1) not in {"그거", "그것", "이거", "저거", "무슨", "어떤"}:
        subject = m.group(1)
    if not subject:
        try:
            from packages.graph_scale.query_frame import _kiwi_subject
            subject = _kiwi_subject(q) or ""
        except Exception:
            subject = ""
    if not subject:
        return None
    prop = _subject_property_from_context(subject, ctx)

    concern = ""
    _cm = re.search(r"([가-힣]{1,10})(?:은|는)\s*[?？]\s*$", q)
    if _cm and _cm.group(1) not in {"그거", "그것", "이거", "저거"}:
        concern = _cm.group(1)
    # minimal grounded frame — the real property + honest abstention + a functional web offer, no

    if prop:
        answer = (f"‘{subject}’에는 {prop} 성질이 있어요. "
                  f"{concern+'에 주는 ' if concern else ''}정확한 영향은 제 근거가 부족해 단정 않을게요 — "
                  f"웹 검색을 켜면 근거와 함께 정리할게요.")
        evidence = [subject, prop] + ([concern] if concern else [])
    else:
        answer = (f"‘{subject}’의 {concern+' ' if concern else ''}영향은 제 근거가 아직 부족해요 — "
                  f"웹 검색을 켜면 찾아 정리할게요.")
        evidence = [subject] + ([concern] if concern else [])
    return {"answer": answer, "answer_kind": "consequence_engage", "can_speak": True, "confidence": 0.55,
            "reasoning_certificate": {"derivation_kind": "consequence_engage", "anchor_concept": subject,
                "steps": [{"type": "cause", "fact": f"consequence-of '{subject}'"
                           + (f", known property '{prop}'" if prop else ", effect ungrounded")}],
                "evidence_concepts": evidence, "confidence": 0.55,
                "confidence_basis": "causal_intent_honest_grounded_limit",
                "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False}}}


# The TOPIC of an opinion turn is the object of the preference/stance phrase — not the longest
# noun in the sentence. Measured: "What is your opinion on art?" resolved to 'opinion' (defining
# the word 'opinion'), and a whole-question lookup of "Should I learn Python?" returned "Python —
# The earth-dragon of Delphi". The stance word is grammar here; the thing after it is the subject.
_OPINION_TOPIC = re.compile(
    r"\b(?:think|feel|opinion|view|views|take|thoughts?)\s+(?:is\s+)?(?:about|on|of|regarding)\s+(.+)$"
    r"|\b(?:like|love|prefer|enjoy|hate|dislike)\s+(.+)$"
    # any verb after "should I/we" — a closed verb list missed "should I START learning music?"
    # and dropped it back to a generic greeting. The topic is whatever the advice is about.
    r"|\bshould\s+(?:i|we)\s+(?:\w+\s+)*?(?:learn(?:ing)?|study(?:ing)?|use|try|pick|choose|read|buy|do)\s+(.+)$"
    r"|\bshould\s+(?:i|we)\s+\w+\s+(.+)$",
    re.IGNORECASE)
_OPINION_MARKER = re.compile(
    r"\b(?:what|how)\s+do\s+you\s+(?:think|feel)\b|\byour\s+(?:opinion|view|take|thoughts?)\b"
    r"|\bdo\s+you\s+(?:like|love|prefer|enjoy|hate|dislike)\b|\bshould\s+(?:i|we)\b", re.IGNORECASE)


def _opinion_topic(question: str) -> str | None:
    m = _OPINION_TOPIC.search(str(question or ""))
    if not m:
        return None
    topic = next((g for g in m.groups() if g), "")
    topic = re.sub(r"^\s*(?:an?|the)\s+", "", topic.strip().rstrip("?!. "), flags=re.IGNORECASE)
    return topic if 1 < len(topic) <= 48 else None


def _english_opinion_answer(question: str) -> str | None:
    """An opinion turn answered as +: an honest frame about what ATANOR is, plus what it
 ACTUALLY holds on the topic. Never a borrowed opinion.

 Deliberately NOT corpus-harvested. A register harvester would supply real human sentences
 ("I love music"), but reusing one here would have ATANOR assert a preference it does not have
 — a fabricated inner state, which is worse than deflecting. The honest engage is: say plainly
 that it holds no preference, then bring what it does hold (grounded facts) to the topic.
 """
    topic = _opinion_topic(question)
    if not topic:
        return None
    # ADVICE is a different shape from a stance about a thing. "Should I learn Python?" does not
    # want a definition — answering it with one produced "Python — The earth-dragon of Delphi".
    # The decision is the user's; ATANOR says so and offers what it actually has. Needing no
    # definition, this branch is immune to the sense problem below.
    if re.search(r"\bshould\s+(?:i|we)\b", question, re.IGNORECASE):
        return (f"That's yours to decide, not mine — I don't hold preferences. Tell me what you'd "
                f"want {topic} for and I'll bring what I actually have on it.")
    fact, _senses = "", []
    try:
        from packages.graph_scale import lexicon_lane as _lex

        if _lex.available():
            _senses = _lex.senses(topic, "en")
            _lx = _lex.lookup(topic, "en")
            fact = str((_lx or {}).get("answer") or "").strip()
    except Exception:  # pragma: no cover
        fact, _senses = "", []
    # POLYSEMY: with several readings on file, defs[0] is a coin flip — measured, the cartridge
    # lists Python's earth-dragon-of-Delphi sense first, and jazz's "Energy, excitement" (the music
    # sense is not even in the cartridge). So do not assert ANY of them.
    #
    # Enumerating them back to the user was tried and DELETED: it fires on democracy (4 readings
    # that are one idea reworded) and art, turning a normal question into an interrogation. The
    # measurement is why — gloss overlap cannot separate true polysemy from cartridge noise
    # (Python min=0.00 max=0.00, jazz min=0.00 max=0.00, democracy min=0.00 max=0.57), so the
    # false positives outnumber the one case it helps. A learned sense-distinctness signal is the
    # destination; until then, withholding is the honest move and costs only fluency.
    if len(_senses) > 1:
        return (f"I don't hold preferences the way you do — and what I have on {topic} carries "
                f"several different readings, none clean enough to lean on. I'd rather not dress "
                f"one up as an answer. What do you mean by it?")
    if fact and re.search(r"[가-힣]", fact):
        fact = ""
    if not fact:
        # No grounding: say so plainly. An honest "I don't have this" beats a warm non-answer.
        return (f"I don't hold preferences the way you do, and I have nothing grounded on "
                f"{topic} yet — so I'd rather not invent a view. Tell me what you see in it?")
    return (f"I don't hold preferences the way you do — what I have on {topic} is grounded, "
            f"not felt: {fact} That's the part I can stand behind. What draws you to it?")


def _english_compare_answer(question: str) -> dict[str, Any] | None:
    """English contrast, composed from BOTH subjects' own grounded facts.

    This runs as its own early lane rather than as an override, because blocking the bad override
    was not enough: the garbage came from the BASE answer that concept_compare was overriding.
    Measured, base_brain resolves English operands by fuzzy match — "the difference between a
    crocodile and an alligator" → Crocodile Dundee II; "coffee vs tea" → Pentacarbonylhydrido-
    manganese; "How is coffee different from tea?" → "Tear Out The Heart was a five-piece
    metalcore band". Resolving the two operands exactly is the whole job here.

    No facts for either side → an honest limit, never a fuzzy neighbour.
    """
    try:
        from packages.graph_scale.answer_bridge import _COMPARE_EN, _en_pair
    except Exception:  # pragma: no cover
        return None
    a, b = _en_pair(_COMPARE_EN.match(str(question or "").strip()))
    if not a or not b or a.lower() == b.lower():
        return None
    try:
        from packages.graph_scale.chain_reasoner import common_ancestor, inherited_facts  # noqa: F401
        from packages.graph_scale.lexicon_lane import _store, available
        from packages.grounded_composer.composer import compose_comparison

        if not available():
            return None
        st = _store()
        # is_a ONLY. A contrast compares taxonomic position, and defined_as is the polysemy
        # lottery — measured, crocodile's first gloss is the British sense ("A long line or
        # procession of people (especially children) walking together"), while its is_a rows are
        # clean ('reptile', 'crocodilian reptile'). Same shape as Python→earth-dragon: the parent
        # is stable where the gloss is a coin flip.
        #
        # RESONANCE GATE — the graph's is_a is polluted: crocodile carries 55 parents including
        # 'alteration', 'matrix', 'athlete', 'sexual relationship'. clean_space.resonance separates
        # them cleanly (measured 2026-07-17: real parents 0.72-0.80 — reptile .739, crocodilian
        # reptile .797, beverage .795 — vs pollution 0.08-0.35 — action .081, opinion .149,
        # athlete .263, matrix .346). engage._relevant already ships this exact test at the same
        # threshold to silence polysemy noise; it simply was never wired into the contrast path.
        # Reused rather than re-derived, and it gates the ANCESTOR too, which is where the
        # measured "Both are a kind of action" came from.
        from packages.graph_scale.engage import _relevant

        def _clean_isa(subject: str) -> list[tuple[str, str, str]]:
            return [(s, p, o) for s, p, o in st.facts_about(subject, limit=64)
                    if p == "is_a" and not re.search(r"[가-힣]", o) and _relevant(subject, o)]

        def _clean_facts(subject: str, limit: int = 64) -> list[tuple[str, str, str]]:
            return [(s, p, o) for s, p, o in st.facts_about(subject, limit=limit)
                    if not (p == "is_a" and not _relevant(subject, o))]

        fa, fb = _clean_isa(a), _clean_isa(b)
        if not fa or not fb:
            return {
                "answer": (f"I don't hold enough grounded detail on both {a} and {b} to contrast "
                           f"them honestly — I'd only be pattern-matching. Ask me what either one "
                           f"is and I can answer that from evidence."),
                "answer_kind": "honest_capability_limit", "can_speak": True, "confidence": 0.8,
                "reasoning_certificate": {
                    "derivation_kind": "honest_capability_limit", "anchor_concept": None,
                    "steps": [], "evidence_concepts": [], "confidence": 0.8,
                    "confidence_basis": "insufficient_grounding_for_contrast",
                    "guarantees": {"external_llm": False, "fabricated_facts": False,
                                   "web_used": False}},
            }
        common = common_ancestor(a, b, _clean_facts)
        comp = compose_comparison(a, b, fa, fb, common, language="en")
        if comp is None:
            return None
        cert = comp.certificate()
        cert["schema"] = "contrast"
        return {"answer": comp.answer, "answer_kind": "grounded_composition", "can_speak": True,
                "confidence": 0.85, "reasoning_certificate": cert}
    except Exception:  # pragma: no cover - a contrast is never worth breaking the turn for
        return None


def _english_engage_answer(question: str) -> dict[str, Any] | None:
    """English engage lane (2026-07-17). The whole engage layer below was Korean-only, so every
 English opinion/capability turn fell through to the knowledge lanes and came back as a graph
 neighbour dump — measured: "Do you like coffee?" → "coffee is located in airport. coffee is
 located in can." That is the AI/ doctrine failing silently in the core language.

 ROUTER vs SURFACE is the load-bearing distinction here. asm_v0's English act inference is
 near-chance (measured 0.12-0.30 over 12 acts; it calls "What is a black hole?" a
 status_question), so it must NOT decide whether a turn is conversational — that would hijack
 knowledge questions into chatter. The high-precision second-person gate decides WHETHER; asm_v0
 only decides HOW to say it. Anything the gate does not claim falls through to the grounded
 lanes untouched.

 Honest scope: this stops the neighbour dump and answers self-directed turns (memory, status,
 self-model) from real state. It does NOT make English engage fluent — that needs an English
 conversational corpus, which does not exist yet (the register harvester is Korean-only).
 """
    if not _is_opinion_or_capability_turn(question):
        return None
    # OPINION about a world topic vs a question about ATANOR ITSELF are different answers. asm_v0
    # holds the self (memory/status/self-model) and answers those from real state; it has no
    # opinion act, so a stance turn there collapses to the default greeting line ("Good to see

    # The split is a regex TRAINING WHEEL and is marked as one: the destination is a learned
    # English act classifier, which needs English conversation logs the flywheel is only now
    # starting to collect. asm_v0's own act inference cannot do this job today (near-chance on
    # English: 0.12-0.30 over 12 acts).
    _act, ans = None, ""
    if _OPINION_MARKER.search(question):
        ans = _english_opinion_answer(question) or ""
        _act = "opinion"
    if not ans:
        try:
            from packages.cgsr.cgsr.asm_v0 import generate_surface

            _res = generate_surface(question)
            ans = (_res.answer or "").strip()
            _act = _res.act_distribution.top_act() if _res.act_distribution else None
        except Exception:  # pragma: no cover - best-effort; silence beats a bad answer
            return None
    if not ans or re.search(r"[가-힣]", ans):
        return None
    return {
        "answer": ans,
        "answer_kind": "engaged_conversation",
        "can_speak": True,
        "confidence": 0.6,
        "reasoning_certificate": {
            "derivation_kind": "conversation_surface",
            "anchor_concept": _opinion_topic(question),
            "steps": [{"type": "conversation_act", "fact": str(_act or "open_chat")}],
            "evidence_concepts": [],
            "confidence": 0.6,
            "confidence_basis": "second_person_gate_plus_grounded_stance",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
        },
    }


def _conversational_engage_answer(question: str, language: str) -> dict[str, Any] | None:
    """ AI : opinion/preference/reflection/advice/small-talk get a warm,
 sensible answer — engaging, grounded in what ATANOR really is, and HONEST that
 it is a view (not a fact). Never fabricates. Returns None for factual/definition
 questions (those keep the grounded lanes)."""
    if language != "ko":
        return _english_engage_answer(question)
    q = str(question or "").strip()
    if not q or len(q) > 80:
        return None



    # with substance — so this runs BEFORE the felt lane, which would otherwise answer sympathy-

    if _HELP_INTENT.search(q):
        _adv = _advice_engage(q, language)
        if _adv:
            return _adv


    # An affectively-charged turn is appraised on a CONTINUOUS valence×arousal axis (affect.appraise,
    # ~2 dozen felt primitives generalised by phase-space resonance — NOT a per-situation table); the
    # self records the felt shift and answers FROM that feeling via the language engine, falling to an
    # honest valence-toned line only when its voice is still too thin to generate. This REPLACES the
    # per-emotion template banks (distress/joy) below for any genuinely charged utterance.
    try:
        from packages.continuous_self.affect import appraise as _appraise
        from packages.continuous_self.conversation import (
            _QUESTIONY as _questiony_re, _felt_reply as _felt, _record_felt as _rec, _self_state as _selfst)
        _af = _appraise(q)
        # D1 UPSTREAM ROUTER (2026-07-13, holdout 0.872 on rule-lanes + adversarial gold):
        # the lane-candidate router decides BEFORE the felt gate can hijack. Two powers:

        #              definition) suppresses the felt lane; the turn falls through to the
        #              knowledge lanes below.
        #   dispatch — confident ENGAGE read (opinion/advice/smalltalk) goes straight to the
        #              REAL conversation generator instead of drifting into base_brain dumps.
        _lane2, _conf2 = None, 0.0
        try:
            from packages.learned_router import router as _lr2
            _c_npz = _lr2.MODEL_DIR / "router_lane_candidate.npz"
            if _c_npz.exists():
                _kp = (_lr2.MODEL_PATH, _lr2.META_PATH, dict(_lr2._MODEL))
                try:
                    _lr2.MODEL_PATH = _c_npz
                    _lr2.META_PATH = _lr2.MODEL_DIR / "router_lane_candidate.meta.json"
                    _lr2._MODEL.update({"W": None, "mtime": 0.0})
                    _lane2, _conf2 = _lr2.predict(q)
                finally:
                    _lr2.MODEL_PATH, _lr2.META_PATH = _kp[0], _kp[1]
                    _lr2._MODEL.update(_kp[2])
        except Exception:
            _lane2, _conf2 = None, 0.0
        _ENGAGE2 = {"self_conversation_opinion": "opinion", "advice_engage": "advice",
                    "self_conversation_smalltalk": "smalltalk", "conversational_engage": "conversation"}
        _KNOW2 = {"structured_triple_lookup", "base_brain_after_low_quality_grounding",
                  "reasoning_vm", "relation_execution", "web_search_grounded"}
        # ENGAGE dispatch is HIGH-PRECISION on purpose: misrouting a KNOWLEDGE question into a
        # "let's explore that together" reply is a DISGUISED ABSTENTION — the one thing the

        # confidence (>=0.80); in the 0.66–0.80 band it must be CONFIRMED by an opinion/advice
        # surface cue. Knowledge veto stays at 0.75 (below).
        _engage_cue = re.search(
            r"(찬성|반대|생각해|생각\s*해|어떻게\s*(봐|생각|볼)|위로|힘들|외로|괜찮을까|"
            r"해야\s*(할까|하나)|좋을까|나아\?|낫(나|어)|의견|입장|어떤\s*것?\s*같아)", q)
        _engage_ok = _conf2 >= 0.80 or (_conf2 >= 0.66 and bool(_engage_cue))
        if _lane2 in _ENGAGE2 and _engage_ok:
            from packages.continuous_self.conversation import converse as _cvs2
            _cv2 = _cvs2(q, _ENGAGE2[_lane2])
            if _cv2 and _cv2.get("answer"):
                return {"answer": _cv2["answer"], "answer_kind": f"lane_router_{_lane2}",
                        "can_speak": True, "confidence": round(float(_conf2), 2),
                        "reasoning_certificate": {
                            "derivation_kind": "lane_router_dispatch", "anchor_concept": None,
                            "steps": [{"type": "learned_lane", "fact": f"{_lane2} ({_conf2:.2f})"}],
                            "evidence_concepts": [], "confidence": round(float(_conf2), 2),
                            "confidence_basis": "adversarial_distilled_lane_router",
                            "guarantees": {"external_llm": False, "fabricated_facts": False,
                                           "web_used": False}}}
        _router_veto = (_lane2 in _KNOW2 and _conf2 >= 0.75)
        # interrogatives must carry ANCHOR-TRUSTED feeling to count as venting: the learned lexical


        # is the innate-primitive-only signal; declaratives keep the learned-inclusive gate.
        _felt_ok = (float(_af.get("seed_pred_intensity") or 0.0) >= 0.28
                    or not _questiony_re.search(q))
        if (not _router_veto and float(_af.get("pred_intensity") or 0.0) >= 0.28 and _felt_ok
                and not re.search(r"(뜻|정의|무슨\s*뜻|의미가\s*뭐|채소야|과일이야|맞아\?|인가요?\?)", q)):
            _rec(q, _af)
            return {"answer": _felt(q, _af, _selfst() or {}), "answer_kind": "felt_generated",
                    "can_speak": True, "confidence": 0.55, "reasoning_certificate": {
                        "derivation_kind": "felt_generated", "anchor_concept": None, "steps": [],
                        "evidence_concepts": [], "confidence": 0.55,
                        "confidence_basis": "affective_appraisal_then_generation",
                        "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False}}}
    except Exception:
        pass

    # SEMANTIC FRAME as a FIRST-CLASS ROUTER SIGNAL (Vision #2 promotion, 2026-07-10): the
    # compositional frame reads the speech-ACT (correction/affect/opinion) even when the tuned

    # now fires on its regex OR the frame's act, so the frame DECIDES routing — not just validates
    # after. It only ever adds conversational routes; a query/request/statement frame changes
    # nothing, so the factual lanes are never touched.
    try:
        from packages.graph_scale.semantic_frame import encode as _frame_encode
        _fr = _frame_encode(q)
        _fact = str(_fr.act or "")
    except Exception:
        _fact = ""



    # (dumping emotion definitions) is the worst failure. Recognize it, own the miss, ask again.

    if _fact == "correction" or re.search(
                 r"(물어본\s*(게|거)\s*아[닌니냐녜]|물은\s*(게|거)\s*아[닌니냐녜]|그게\s*아[닌니냐녜]"
                 r"|그건\s*아[닌니냐녜]|그런\s*(거|게|뜻|의미)\s*(가\s*)?아[닌니냐녜]|내\s*말은"
                 r"|그거\s*말고|그\s*말\s*말고|말고\s*다른|잘못\s*(알아|이해|짚)"
                 r"|질문을?\s*(못|안|잘못)\s*(알아|이해|짚)|아니\s*내|그\s*뜻\s*아[닌니냐녜])", q):
        _cert_c = {"reasoning_certificate": {"derivation_kind": "engage_correction",
                   "anchor_concept": None, "steps": [], "evidence_concepts": [], "confidence": 0.5,
                   "confidence_basis": "meta_correction_acknowledged",
                   "guarantees": {"external_llm": False, "fabricated_facts": False}},
                   "confidence": 0.5, "answer_kind": "conversational_engage", "can_speak": True}

        return {"answer": "제가 잘못 짚었네요. 어떤 걸 여쭤보신 건지 조금만 더 구체적으로 알려주시면 다시 답할게요.",
                **_cert_c}

    def _cert(kind: str, conf: float) -> dict[str, Any]:
        return {"reasoning_certificate": {
                    "derivation_kind": kind, "anchor_concept": None, "steps": [],
                    "evidence_concepts": [], "confidence": conf,
                    "confidence_basis": "conversational_engagement",
                    "guarantees": {"external_llm": False, "fabricated_facts": False}},
                "confidence": conf, "answer_kind": "conversational_engage", "can_speak": True}

    def _self_wonder() -> str:
        try:
            from app.routers.continuous_self import _SELF

            if _SELF.running:
                oq = str(_SELF.snapshot().get("self_question") or "").strip()
                if oq:
                    return f" 요즘 저는 스스로 이런 걸 궁금해해요 — “{oq[:80]}”."
        except Exception:
            pass
        return ""




    #    fabricate advice, but I can sit with it and invite them to say more.

    #     don't cold-abstain. Warmth is the right answer, and it fabricates no fact.
    _joy = re.search(r"(취업했|합격했|붙었|통과했|해냈|성공했|이겼|승진했|졸업했|당첨|우승|1등|"
                     r"결혼(해|한다|했)|생겼어|드디어.*(했|됐)|해결(됐|했)|끝냈|완성했|승낙|계약(했|됐))", q)

    # got congratulated (battery A5, measured 2026-07-10). Celebration only for reported events.
    if _joy:
        try:
            from packages.continuous_self.conversation import _QUESTIONY as _qy
            if _qy.search(q):
                _joy = None
        except Exception:
            pass
    if _joy and not re.search(r"(뜻|정의|무슨\s*뜻)", q):
        # single honest line (no variation bank). Warmth, no fabricated fact.
        return {"answer": "정말 잘됐네요, 진심으로 축하드려요! 애쓴 보람이 있으셨네요.",
                **_cert("engage_good_news", 0.6)}

    _distress = re.search(r"(속상|상심|힘들|우울|지쳐|지친|지쳤|슬퍼|슬프|눈물|울고\s*싶|화나|짜증|"
                          r"외로|막막|걱정|불안|괴로|서러|답답|허무|무기력|기운\s*없|의욕\s*없|"
                          r"하기\s*싫|아무것도.*싫|망쳤|망쳐|싸웠|싸웠어|힘드)", q) or _distress_by_morph(q)
    # frame-caught affect that isn't a celebration routes here too (the frame is the decider):
    if (_distress or (_fact == "affect" and not _joy)) and not re.search(r"(뜻|정의|무슨\s*뜻|의미가\s*뭐)", q):
        # user-STATE-aware opener (reflects THEIR feeling, not my mood) + one honest line. No variation

        if re.search(r"속상|상심|슬|눈물|망쳐|망쳤", q):
            opener = "그랬군요… 많이 속상하셨겠어요."
        elif re.search(r"힘들|힘든|힘드|지쳐|지친|지쳤|무기력|기운|의욕|하기\s*싫|아무것도|버겁|벅차|지겹", q) or _distress_by_morph(q):
            opener = "많이 지치고 힘드셨겠어요."
        else:
            opener = "마음이 많이 복잡하시겠어요."
        return {"answer": f"{opener} 그렇게 느끼는 건 자연스러운 거예요. 지어낸 위로 대신 곁에서 들을게요 — "
                          f"괜찮으시면 무슨 일인지 조금만 더 들려주세요.",
                **_cert("engage_emotional_support", 0.55)}



    _pref_verb_final = re.search(r"(좋아|싫어|선호|즐기)(해|하니|하세요|하나요|합니까|하시나요)\s*\??\s*$", q)
    _pref_addressed = re.search(r"(^|\s)(너|넌|너는|당신|네|니)\b", q) and re.search(r"(좋아|싫어|선호)", q)
    if _pref_verb_final or _pref_addressed:
        m = re.search(r"([가-힣A-Za-z0-9]{2,20})\s*(을|를|은|는|이|가)?\s*(좋아|싫어|선호|즐기)", q)
        topic = m.group(1) if m else ""
        if topic in ("너", "넌", "당신", "네", "니"):
            topic = ""

        # AI's REAL affect (emotion vector) + REAL graph associations of the topic, marked mode='felt'
        # — never a canned "I don't have preferences" sentence, never a fabricated liking.
        try:
            from packages.neural_emotion.event_bus import EVENT_BUS as _EB
            _v = _EB.engine.snapshot().vector
            _val, _aro = float(_v.valence), float(_v.arousal)
        except Exception:
            _val, _aro = 0.0, 0.0
        _assoc: list[str] = []
        if topic:
            try:
                _kg = _store()
                for _s, _p, _o in (_kg.facts_about(topic, limit=16) or []):
                    o = str(_o).strip()
                    # short concept NAMES only — exclude Q-ids and long definition strings (a felt

                    if o and not o.startswith("Q") and 2 <= len(o) <= 12 and re.search(r"[가-힣]{2,}", o) and o != topic:
                        _assoc.append(o)
                    if len(_assoc) >= 3:
                        break
            except Exception:
                _assoc = []
        try:
            from packages.base_brain.felt_speech import felt_speech
            _f = felt_speech(topic, valence=_val, arousal=_aro, associations=_assoc)
            if _f and _f.text:
                return {"answer": _f.text, **_cert("engage_preference_felt", 0.6)}
        except Exception:
            pass
        return {"answer": f"{topic+'은(는) ' if topic else ''}근거로 확인되는 것에 끌려요.",
                **_cert("engage_preference", 0.5)}




    if (_fact == "opinion"
            or re.search(r"(어떻게\s*생각|네\s*생각|너\s*생각|의견\s*이|어떻게\s*봐)", q)
            or re.search(r"(중요|소중|값진|의미|필요|가치)[가-힣]*\s*(게|것|건|점)\s*(뭐|무엇|어떤|어느|일까|인가)", q)):

        # the AI's real affect + the topic's real graph associations (felt_speech, marked mode='felt').
        _ot = ""
        _om = re.search(r"([가-힣A-Za-z0-9]{2,20})\s*(에\s*대해|에\s*관해|은|는|이|가|을|를)?\s*"
                        r"(어떻게\s*생각|어떻게\s*봐|의견)", q)
        if _om:
            _ot = _om.group(1)
        if _ot and _ot not in ("이거", "그거", "저거", "너", "당신"):
            try:
                from packages.neural_emotion.event_bus import EVENT_BUS as _EB2
                _v2 = _EB2.engine.snapshot().vector
                _val2, _aro2 = float(_v2.valence), float(_v2.arousal)
            except Exception:
                _val2, _aro2 = 0.0, 0.0
            _as2: list[str] = []
            try:
                _kg2 = _store()
                for _s, _p, _o in (_kg2.facts_about(_ot, limit=16) or []):
                    o = str(_o).strip()
                    if o and not o.startswith("Q") and 2 <= len(o) <= 12 and re.search(r"[가-힣]{2,}", o) and o != _ot:
                        _as2.append(o)
                    if len(_as2) >= 3:
                        break
            except Exception:
                _as2 = []
            try:
                from packages.base_brain.felt_speech import felt_speech as _fs
                _f2 = _fs(_ot, valence=_val2, arousal=_aro2, associations=_as2)
                if _f2 and _f2.text:
                    return {"answer": _f2.text, **_cert("engage_opinion_felt", 0.6)}
            except Exception:
                pass
        # topicless opinion → honest, minimal (no template essay): state the one real stance and defer.
        return {"answer": "정답이 하나인 문제는 아니에요. 저는 근거로 확인되는 것만 붙잡아요 — 어떤 점이 궁금하세요?",
                **_cert("engage_opinion", 0.5)}


    if re.search(r"(어떻게\s*해야\s*(할까|하지|될까|좋을까)|조언\s*(좀|해)|어쩌면\s*좋)", q):
        # context-less advice has NO grounded content to weave → the multi-sentence rhetorical
        # template is retired for one honest functional line (a genuine request, not faked eloquence).
        return {"answer": "어떤 상황인지 조금만 더 들려주시면, 지어내지 않고 아는 근거 안에서 함께 방향을 짚어볼게요.",
                **_cert("engage_advice", 0.5)}


    if re.search(r"(심심|지루|재밌는\s*(얘기|이야기)|놀자|뭐\s*하고\s*놀|얘기\s*하자|말\s*걸)", q):
        # NO canned line. Express the REAL felt state (felt_speech, mood from the emotion vector) +
        # a functional invite for a topic to ground on — no fabricated 'story', no template opener.
        _felt = ""
        try:
            from packages.neural_emotion.event_bus import EVENT_BUS as _EB3
            from packages.base_brain.felt_speech import felt_speech as _fs3
            _v3 = _EB3.engine.snapshot().vector
            _f3 = _fs3("", valence=float(_v3.valence), arousal=float(_v3.arousal))
            _felt = _f3.text if _f3 else ""
        except Exception:
            _felt = ""
        _invite = _self_wonder() or " 궁금한 주제를 하나 던져주시면 아는 걸로 함께 풀어볼게요."
        return {"answer": (_felt + _invite).strip(), **_cert("engage_smalltalk_felt", 0.55)}



    if re.search(r"(^|\s)(너|넌|너는|당신)\b", q) and re.search(
            r"(아니야|아니냐|아냐|아닌가|맞아\??$|맞지|맞니|확실|진짜야|정말이야|믿어도|거짓말|틀)", q):

        return {"answer": "저는 단순한 검색엔진은 아니에요 — 근거 그래프에서 사실을 이어 붙여 추론하고, 확실하지 "
                          "않은 건 확실하지 않다고 밝혀요. 방금 답도 아는 근거 안에서 드린 거라, 미심쩍은 점을 "
                          "짚어주시면 근거부터 다시 볼게요.",
                **_cert("engage_self_challenge", 0.55)}




    if (re.search(r"(면|다면).{0,25}(까\??$|을까|ㄹ까|일까|겠지|려나)", q)
            or re.search(r"(뺏을까|빼앗을까|바뀔까|사라질까|없어질까|대체(할|될)까|가능할까|괜찮을까|"
                         r"나아질까|달라질까|의미가\s*있을까|가치가\s*있을까)", q)):
        # single honest line (no variation bank)
        return {"answer": "이건 하나의 정답이 있다기보다 관점에 따라 갈리는 문제라, 근거 없이 단정하진 않을게요. "
                          "양쪽 다 나름의 이유가 있고 결국 무엇을 더 중요하게 보느냐에 달려 있어요 — 당신은 어느 "
                          "쪽에 더 마음이 기우세요?",
                **_cert("engage_speculation", 0.55)}



    if re.search(r"(뭐|무엇|어디|어느\s*걸)\s*(먹|하|갈|볼|살|입|들)(지|을까|까|나)", q) and \
            re.search(r"(고민|모르겠|망설|글쎄|정할|골라)", q + " "):
        return {"answer": (
            "고민되시죠 :) 저라면 지금 당장 끌리는 걸 한 번 물어볼게요 — 뜨끈한 게 당기시는지, "
            "가벼운 게 좋으신지. 방향만 정해주시면 그 안에서 몇 가지 추려서 같이 골라드릴게요."),
            **_cert("engage_casual_musing", 0.5)}




    if (re.search(r"(랑|이랑|와|과|하고|vs|,)\s*[가-힣A-Za-z][가-힣A-Za-z0-9\s]{0,14}?\s*"
                  r"(중|중에|중에서|가운데|둘\s*중)?\s*(뭐|어느\s*(게|쪽)|어떤\s*게)?\s*"
                  r"(더\s*)?(나아|나을|낫|좋아|좋을|괜찮)", q)
            or re.search(r"(나을까|나을지|좋을까|살까|골라야).{0,25}(나을까|나을지|좋을까|낫|어때)", q)):
        # single honest line (no variation bank)
        return {"answer": "둘 다 결이 달라서 ‘무조건 이게 낫다’고 잘라 말하긴 어려워요. 무엇을 더 중요하게 보시는지 "
                          "— 편함인지, 성능인지, 함께하는 재미인지 — 하나만 정해주시면 그 기준에서 정직하게 "
                          "견줘드릴게요.",
                **_cert("engage_subjective_compare", 0.5)}

    return None


_USER_KNOWLEDGE_KO = ("나에 대해", "나에 대해서", "내가 누군지", "나를 얼마나 알",
                      "나 뭐 좋아", "내 취향", "나에 관해", "날 알아", "나 알아")


def _user_knowledge_answer(question: str, language: str) -> dict[str, Any] | None:
    """Phase 3-2/3-3: questions about the USER answered from the derived user
    model (episodic events + local brain facts). Every sentence carries its
    evidence count; an empty model says so instead of inventing a persona."""
    raw = str(question or "")
    if not any(m in raw for m in _USER_KNOWLEDGE_KO):
        return None

    if re.search(r"어떻게\s*생각|평가\s*해", raw):
        return None
    try:
        from packages.user_model import derive_user_model, summary_facts

        model = derive_user_model()
        sents = summary_facts(model, limit=5)
    except Exception:
        return None
    ev = model.get("evidence_totals") or {}
    n_events = int(ev.get("episodic_events") or 0)
    n_facts = int(ev.get("brain_facts") or 0)
    if language == "ko":
        if sents:
            answer = ("제가 기록에서 아는 만큼만 말씀드릴게요. " + " ".join(sents) +
                      f" — 근거는 이 기기에 있는 일화 기록 {n_events}건과 대화 기억 {n_facts}건이에요.")
        else:
            answer = ("아직 당신에 대해 기록된 것이 거의 없어요. 대화하면서 알려주시는 것들과 "
                      "일상 이벤트가 쌓이면, 그 근거만큼만 알게 돼요 — 지어내지는 않아요.")
    else:
        answer = (" ".join(sents) + f" (from {n_events} episodic events and {n_facts} conversational facts on this device)"
                  if sents else
                  "I have almost nothing recorded about you yet — I only ever know as much as the local evidence supports.")
    return {
        "answer": answer,
        "answer_kind": "user_model_readout",
        "confidence": 0.85 if sents else 0.6,
        "reasoning_certificate": {
            "derivation_kind": "user_model_aggregation",
            "anchor_concept": {"id": "user_model", "label": "사용자 심층 모델", "match": "local_stores"},
            "steps": [
                {"type": "aggregate", "source": "episodic_events", "fact": f"{n_events} events"},
                {"type": "aggregate", "source": "local_brain", "fact": f"{n_facts} facts"},
            ],
            "evidence_concepts": ["episodic_memory", "local_brain"],
            "confidence": 0.85 if sents else 0.6,
            "confidence_basis": "evidence_counted_aggregation",
            "guarantees": {"external_llm": False, "fabricated_facts": False,
                           "local_only": True},
        },
    }


def _self_state_answer(question: str, language: str) -> dict[str, Any] | None:
    """Answer a question about ATANOR's own live state by pulling from every part
    of the program (the 'living creature' sense). Real numbers, no fabrication."""
    try:
        raw = str(question or "")
        lowered = raw.lower()
        if not (any(m in raw for m in _SELF_STATE_KO) or any(m in lowered for m in _SELF_STATE_EN)):
            return None
        # require a self-reference so only questions ADDRESSED to ATANOR route here.

        # Korean drops the pronoun, the counterpart is the implicit addressee.
        _implicit_2p = any(m in raw for m in _INNER_STATE_KO) and not re.search(
            r"(그|이|저)\s*(사람|남자|여자|분)|[가-힣]{2,}[이가]\s*무슨", raw)
        if not (any(m in lowered for m in _SELF_REF_KO) or "you" in lowered or _implicit_2p):
            return None
        s = _atanor_self_sense()
        cb = s.get("cloud_brain") or {}
        lb = s.get("local_brain") or {}
        au = s.get("autonomous") or {}
        mood = s.get("mood") or {}
        nodes = int(cb.get("nodes") or 0)
        facts = int(lb.get("total_facts") or 0)
        web_facts = int((s.get("web_memory") or {}).get("facts_remembered") or 0)
        learned = int(au.get("learned_total") or 0)
        running = bool(au.get("running"))
        # SELFHOOD fusion: the endogenous self-model's CURRENT inner state (its own
        # open question, its current thought) leads the answer — the living part —
        # and the subsystem numbers ground it. All read live, nothing composed
        # from a table; when the selfhood daemon is asleep the numbers stand alone.
        inner = ""
        try:
            from app.routers.continuous_self import _SELF

            if _SELF.running:
                snap = _SELF.snapshot()
                thought = str(snap.get("current_thought") or "").strip()
                open_q = str(snap.get("self_question") or "").strip()
                if any(m in raw for m in ("무슨 생각", "생각 하고", "생각하고")) and (thought or open_q):
                    inner = (f"지금 마음에 있는 건 이거예요 — “{(thought or open_q)[:120]}”. " if language == "ko"
                             else f"What's on my mind right now: “{(thought or open_q)[:120]}”. ")
                elif open_q:
                    inner = (f"요즘 스스로 품고 있는 질문은 “{open_q[:100]}”이에요. " if language == "ko"
                             else f"The question I'm currently holding: “{open_q[:100]}”. ")
        except Exception:
            inner = ""
        # Phase 3-3: the self-narrative cites the most recent REAL reasoning act
        # (flywheel turn log) when asked what it was doing — lived history, not a
        # status template.
        if not inner and any(m in raw for m in ("뭐 했", "뭐했", "뭐 하고 있", "뭐하고 있", "최근에 뭐")):
            try:
                from packages.flywheel.logger import TURNS_PATH

                last = None
                if TURNS_PATH.exists():
                    with TURNS_PATH.open(encoding="utf-8") as fh:
                        for line in fh:
                            last = line
                if last:
                    turn = json.loads(last)
                    q_prev = str(turn.get("question") or "").strip()[:60]
                    if q_prev and q_prev not in raw:
                        inner = (f"조금 전엔 “{q_prev}” 질문에 답을 지었어요. " if language == "ko"
                                 else f"A moment ago I composed an answer to “{q_prev}”. ")
            except Exception:
                pass

        if language == "ko" and ("존재 이유" in raw or "왜 존재" in raw):
            answer = (
                "저는 근거에서 답을 짓고, 그 근거를 보여주기 위해 존재해요 — 외부 LLM 없이, "
                "당신의 데이터는 당신 기기에 둔 채로요. " + (inner or "") +
                f"그 일을 위해 지금 검증 개념 {nodes:,}개를 품고 있어요."
            )
            is_ko = True
        elif (is_ko := language == "ko"):
            act = "지금 자율 루프를 돌리며 공개 웹과 AGORA를 살피고 있어요" if running else "지금은 자율 루프를 멈추고 대기 중이에요"
            answer = (
                inner +
                f"{act}. 클라우드 브레인에는 검증 개념이 {nodes:,}개 있고, 검토 큐에는 {learned:,}개의 학습 후보가 있어요. "
                f"웹에서 찾아 기억해 둔 사실은 {web_facts}개이고, 당신에 대해서는 {facts}가지를 기억하고 있어요. 호기심은 {float(mood.get('curiosity') or 0):.2f}예요."
            )
        else:
            act = "I'm running the autonomous loop, scanning the public web and AGORA" if running else "the autonomous loop is paused"
            answer = (
                f"Right now {act}. The Cloud Brain holds {nodes:,} verified concepts and the review queue has {learned:,} learned candidates. "
                f"I've looked up and remembered {web_facts} web fact(s), and I remember {facts} thing(s) about you. My curiosity is {float(mood.get('curiosity') or 0):.2f}."
            )
        certificate = {
            "derivation_kind": "atanor_self_sense",
            "anchor_concept": {"id": "atanor_self", "label": "ATANOR self-state", "match": "live_sensorium"},
            "steps": [
                {"type": "subsystem", "source": "cloud_brain", "fact": f"{nodes} concepts"},
                {"type": "subsystem", "source": "review_queue", "fact": f"{learned} learned candidates"},
                {"type": "subsystem", "source": "local_brain", "fact": f"{facts} facts about the user"},
                {"type": "subsystem", "source": "autonomous_loop", "fact": "running" if running else "paused"},
            ],
            "evidence_concepts": ["cloud_brain", "local_brain", "review_queue", "autonomous_loop", "mood"],
            "confidence": 0.9,
            "confidence_basis": "live_subsystem_readout",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "live_program_state": True},
        }
        return {"answer": answer, "reasoning_certificate": certificate, "confidence": 0.9}
    except Exception:  # pragma: no cover
        return None


class GraphHubImportRequest(BaseModel):
    """Selection request for a server-owned installed Graph Hub cartridge."""

    source_id: str
    kind: str = "knowledge"  # "persona" or "knowledge"
    items: list[dict[str, Any]] = Field(default_factory=list)


def _bind_graph_hub_import(request: GraphHubImportRequest) -> tuple[str, str, list[dict[str, Any]]]:
    """Resolve every persisted field from the installed cartridge.

    Caller fields select an installed source and a subset of its canonical
    semantic nodes.  They never mint Graph Hub provenance or Local Brain facts.
    """

    installed = get_installed_cartridge(request.source_id)
    if not installed or installed.get("enabled") is False:
        raise HTTPException(status_code=404, detail="graph_hub_source_not_installed")
    installed_path = Path(str(installed.get("path") or ""))
    if not installed_path.is_file():
        raise HTTPException(status_code=404, detail="graph_hub_source_unavailable")
    cartridge = read_json(installed_path, {})
    if not isinstance(cartridge, dict):
        raise HTTPException(status_code=409, detail="graph_hub_source_schema_invalid")
    canonical_source_id = str(cartridge.get("cartridge_id") or "")
    if (
        canonical_source_id != request.source_id
        or str(installed.get("cartridge_id") or "") != canonical_source_id
    ):
        raise HTTPException(status_code=409, detail="graph_hub_source_binding_mismatch")
    validation = validate_cartridge_schema(cartridge)
    if not validation["valid"]:
        raise HTTPException(status_code=409, detail="graph_hub_source_schema_invalid")
    provenance = (
        cartridge.get("provenance")
        if isinstance(cartridge.get("provenance"), dict)
        else {}
    )
    if str(provenance.get("source_type") or "") in {
        SEMANTIC_STORE_TRUST_STATE,
        "semantic_cloud_proof_store",
    } and not (
        provenance.get("independent_source_attestation") is True
        and provenance.get("authoritative_for_answer") is True
    ):
        raise HTTPException(
            status_code=409,
            detail="graph_hub_source_not_authoritative",
        )

    canonical_kind = "persona" if str(cartridge.get("category") or "") == "persona" else "knowledge"
    if request.kind != canonical_kind:
        raise HTTPException(status_code=400, detail="graph_hub_kind_not_bound_to_source")

    semantic = ((cartridge.get("contents") or {}).get("semantic_graph") or {})
    canonical_items: dict[str, dict[str, Any]] = {}
    for node in semantic.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        subject = str(node.get("id") or "").strip()
        value = str(
            node.get("short_description")
            or node.get("description")
            or node.get("label")
            or ""
        ).strip()
        if not subject or not value:
            continue
        raw_confidence = node["confidence"] if "confidence" in node else node.get("trust", 0.8)
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = 0.8
        if not math.isfinite(confidence):
            confidence = 0.8
        canonical_items[subject] = {
            "subject": subject,
            "value": value,
            "confidence": max(0.0, min(1.0, confidence)),
        }

    bound_items: list[dict[str, Any]] = []
    for requested in request.items:
        subject = str(requested.get("subject") or requested.get("name") or "").strip()
        value = str(requested.get("value") or requested.get("text") or "").strip()
        canonical = canonical_items.get(subject)
        if canonical is None or value != canonical["value"]:
            raise HTTPException(status_code=400, detail="graph_hub_item_not_bound_to_source")
        bound_items.append(dict(canonical))
    return canonical_source_id, canonical_kind, bound_items


@router.get("/api/local-brain/memory/status")
def local_brain_memory_status() -> dict[str, Any]:
    return {**_flags(), **LOCAL_BRAIN.status()}


@router.get("/api/local-brain/memory/facts")
def local_brain_memory_facts() -> dict[str, Any]:
    return {**_flags(), "facts": [f.to_dict() for f in LOCAL_BRAIN.all_facts()], **LOCAL_BRAIN.status()}


@router.post("/api/local-brain/memory/import-graph-hub")
def local_brain_import_graph_hub(request: GraphHubImportRequest) -> dict[str, Any]:
    source_id, kind, items = _bind_graph_hub_import(request)
    added = LOCAL_BRAIN.import_graph_hub_source(source_id, kind, items)  # type: ignore[arg-type]
    return {
        **_flags(),
        "imported": len(added),
        "items": [f.to_dict() for f in added],
        "uploaded_to_cloud": False,
        "production_store_mutated": False,
        **LOCAL_BRAIN.status(),
    }


async def _chat_atanor_dispatch(request: AtanorChatRequest) -> dict[str, Any]:
    question = request.question_text()
    if not question:
        raise HTTPException(status_code=422, detail="question, query, or message is required")
    language = _resolve_language(request.language, question)
    conversation_context = build_conversation_context(question, request.conversation_context)
    routing_question = conversation_context.contextual_query
    emit_runtime_event(
        source="asm_v0",
        event_type=infer_user_text_runtime_event(question),
        payload_summary=f"input_language={language}; mode={request.mode}",
        intensity=0.6,
    )
    three_core_trace = _run_three_core_compact_trace(question)
    route = route_conversation_request(routing_question)
    splatra_visual_request = _is_splatra_visual_request(routing_question)
    web_grounded_conversation = bool(request.web_search and _should_use_web_grounded_conversation(routing_question))
    if splatra_visual_request or (
        (
            request.mode in {"conversation", "live_selfhood", "dashboard_conversation"}
            or _is_live_selfhood_conversation(question)
        )
        and not web_grounded_conversation
    ):
        response = _attach_three_core_trace(
            _live_selfhood_payload(
                request,
                question=question,
                language=language,
                conversation_context=conversation_context,
            ),
            request=request,
            three_core_trace=three_core_trace,
        )
        _emit_conversation_result_events(response)
        return response
    if _clean_graph_count_question(question) or _is_graph_count_question(question):
        response = _attach_three_core_trace(
            _clean_graph_count_payload(request, question=question, language=language),
            request=request,
            three_core_trace=three_core_trace,
        )
        _emit_conversation_result_events(response)
        return response
    if _is_recent_learning_question(question):
        # Introspection answers from the live learning ledger and must not fall

        # once answered with a random peace-index page (measured 2026-07-08).
        response = _attach_three_core_trace(
            _recent_learning_payload(request, question=question, language=language),
            request=request,
            three_core_trace=three_core_trace,
        )
        _emit_conversation_result_events(response)
        return response
    if _should_try_base_brain_first(question):
        early = _base_brain_payload(request, question=question, language=language, rag_result={})
        if early is not None:
            response = _attach_three_core_trace(early, request=request, three_core_trace=three_core_trace)
            _emit_conversation_result_events(response)
            return response
    rag_status = await alpha_service.query_graphrag(
        routing_question,
        request.web_search,
        None,
        brain_mode=request.brain_mode,
        locale=request.language,
        include_trace=True,
    )
    rag_result = rag_status.get("result") or {}
    semantic_context = _semantic_context_from_rag(rag_result)
    if _is_recent_learning_question(routing_question):
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
            # Web-grounded rescue: if Base Brain has no local answer but web search
            # is on, answer from a real cited web source instead of abstaining.
            fb_result = fallback.get("result") if isinstance(fallback, dict) else None
            if request.web_search and isinstance(fb_result, dict) and (
                not fb_result.get("answer") or _answer_is_abstention(str(fb_result.get("answer") or ""))
            ):
                _emit_stage("web_grounding")  # real: base brain was thin, hitting the web
                rescue = await _web_grounded_rescue(question, language)
                if rescue:
                    fb_result["answer"] = rescue["answer"]
                    fb_result["reasoning_certificate"] = rescue["reasoning_certificate"]
                    fb_result["confidence"] = rescue["confidence"]
                    fb_result["answer_kind"] = "web_unreachable" if rescue.get("web_unreachable") else "web_search_grounded"
                    fb_result["web_search_provider"] = rescue["provider"]
                    fb_result["can_speak"] = True
                    if rescue.get("source_url"):
                        fb_result["render_iframe"] = {"url": rescue["source_url"], "title": rescue.get("source_title") or question[:60]}
            response = _attach_three_core_trace(fallback, request=request, three_core_trace=three_core_trace)
            _emit_conversation_result_events(response)
            return response
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
        routing_question,
        semantic_context,
        language=language,
        audience_level=request.audience_level,
        tone=request.tone,
        mode=request.mode,
    )
    realized = realize_answer(plan, semantic_context, query=question)
    if request.mode not in {"trace", "research"} and (
        _answer_is_unsafe(str(realized.get("answer") or ""))
        or _answer_is_abstention(str(realized.get("answer") or ""))
    ):
        grounded_web_answer = str(rag_result.get("answer") or "").strip()
        if (
            request.web_search
            and grounded_web_answer
            and rag_result.get("web_search")
            and (semantic_context.get("evidence") or semantic_context.get("relations") or semantic_context.get("claims"))
        ):
            answer_source = "web_grounded_native_graph_token_answer"
            # The native graph-token stitch can be incoherent (drops the subject, dangles on a
            # particle) for ANY topic where the graph is sparse. Never ship that: if it fails
            # the general coherence gate, re-ground it in the real evidence sentence via the
            # extractive composer; if even that has no matching source, abstain honestly rather
            # than emit a garbled fragment. No per-entity handling — the check is query-driven.
            if _grounded_answer_incoherent(grounded_web_answer, question):
                _emit_stage("web_grounding")  # real: re-grounding an incoherent stitch from the web
                rescue = await _web_grounded_rescue(question, language)
                rescue_answer = str((rescue or {}).get("answer") or "").strip()
                if rescue_answer and not _answer_is_abstention(rescue_answer) and not _grounded_answer_incoherent(rescue_answer, question):
                    grounded_web_answer = rescue_answer
                    answer_source = "web_grounded_extractive_reground"
                    if rescue and rescue.get("reasoning_certificate"):
                        realized["reasoning_certificate"] = rescue["reasoning_certificate"]
                else:
                    grounded_web_answer = (
                        "현재 확인된 근거만으로는 정확히 설명하기 어렵습니다."
                        if language == "ko"
                        else "I could not find a clearly matching source to answer that yet."
                    )
                    answer_source = "web_grounded_abstained_incoherent"
            realized["answer"] = grounded_web_answer
            realized["confidence"] = max(
                float(realized.get("confidence") or 0.0),
                float(rag_result.get("confidence") or 0.0),
                0.52,
            ) if not answer_source.endswith("abstained_incoherent") else min(float(realized.get("confidence") or 0.0), 0.4)
            realized["repair"] = {
                **(realized.get("repair") or {}),
                "safety_applied": True,
                "source": answer_source,
                "web_search_provider": (rag_result.get("web_search") or {}).get("provider"),
            }
    if request.mode not in {"trace", "research"} and _answer_is_unsafe(str(realized.get("answer") or "")):
        fallback = _base_brain_payload(request, question=question, language=language, rag_result=rag_result)
        if fallback is not None:
            result = fallback["result"]
            result.setdefault("compact_trace", {})["safety_fallback"] = "base_brain_after_unsafe_surface_answer"
            response = _attach_three_core_trace(fallback, request=request, three_core_trace=three_core_trace)
            _emit_conversation_result_events(response)
            return response
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
    visual_grounding = _grounded_context_from_semantic_context(
        question,
        route=route,
        semantic_context=semantic_context,
    )
    visual_route = route
    if route.route_type == "unknown" and visual_grounding.facts:
        visual_route = ConversationRoute(
            route_type="general_knowledge_question",
            grounding_required=True,
            grounding_sources=("semantic_cloud_graph_web_evidence_readonly",),
            confidence=max(float(getattr(route, "confidence", 0.0) or 0.0), 0.62),
            fallback_allowed=False,
            rationale_summary="web/graph evidence is available for a fact-bound visual explanation",
        )
        visual_grounding = GroundedContext(
            route_type=visual_route.route_type,
            facts=visual_grounding.facts,
            constraints=visual_grounding.constraints,
            unknowns=visual_grounding.unknowns,
            source_refs=visual_grounding.source_refs,
            grounding_source=visual_grounding.grounding_source,
            grounding_quality=visual_grounding.grounding_quality,
            safety_flags=visual_grounding.safety_flags,
        )
    fact_bound_web_answer = (
        _web_fact_bound_surface(
            routing_question,
            route=visual_route,
            grounded_context=visual_grounding,
            language=language,
            evidence_docs=(
                rag_result.get("evidence_docs")
                if isinstance(rag_result.get("evidence_docs"), list) and rag_result.get("evidence_docs")
                else (semantic_context.get("evidence") if isinstance(semantic_context.get("evidence"), list) else None)
            ),
        )
        if request.web_search and request.mode not in {"trace", "research"}
        else None
    )
    if fact_bound_web_answer:
        discourse_metadata = grounded_discourse_metadata(routing_question, visual_grounding)
        realized["answer"] = fact_bound_web_answer["answer"]
        _fu = [f for f in (fact_bound_web_answer.get("follow_ups") or []) if f]
        if _fu:
            realized["follow_ups"] = _fu
        realized["confidence"] = max(
            float(realized.get("confidence") or 0.0),
            float(rag_result.get("confidence") or 0.0),
            0.64 if visual_grounding.grounding_quality == "high" else 0.56,
        )
        realized["repair"] = {
            **(realized.get("repair") or {}),
            "safety_applied": True,
            "source": "semantic_cloud_graph_fact_bound_surface",
            "fact_bound_surface": True,
            "web_search_provider": (rag_result.get("web_search") or {}).get("provider"),
            "grounding_quality": visual_grounding.grounding_quality,
            **discourse_metadata,
        }
    visual_plan = plan_visual_imagination(
        question,
        route=visual_route,
        grounded_context=visual_grounding,
        diagnostics={
            "external_llm_used": False,
            "external_sllm_used": False,
            "rule_based_answer_used": False,
            "generation_basis": "semantic_cloud_graph_surface_brain_v0",
        },
        answer_available=bool(str(realized.get("answer") or "").strip()),
        client_layout_feedback=request.layout_feedback,
    )
    splatra_command_sequence_obj = (
        compile_scene_choreography_commands(visual_plan.scene_choreography)
        if visual_plan.scene_choreography
        else None
    )
    splatra_command_sequence = splatra_command_sequence_obj.to_dict() if splatra_command_sequence_obj else None
    splatra_interactive_scene_analysis_obj = (
        analyze_scene_choreography(visual_plan.scene_choreography)
        if visual_plan.scene_choreography
        else None
    )
    splatra_interactive_scene_analysis = (
        splatra_interactive_scene_analysis_obj.to_dict()
        if splatra_interactive_scene_analysis_obj
        else None
    )
    visual_policy = {
        "scene_content_source": visual_plan.diagnostics.get("scene_content_source", "none"),
        "scene_authoring_basis": visual_plan.diagnostics.get("scene_authoring_basis"),
        "visual_affordance_basis": visual_plan.diagnostics.get("visual_affordance_basis"),
        "layout_decision_basis": visual_plan.diagnostics.get("layout_decision_basis"),
        "reason": visual_plan.diagnostics.get("reason") or visual_plan.reason,
        "topic_scene_templates": False,
        "renderer_may_infer_topic": False,
        "particle_text": False,
        "text_rendering": "dom_text_not_particles",
        "orb_identity": "atanor_self_body_not_scene_object" if visual_plan.scene_choreography else "atanor_primary_self_body",
        "verified_evidence_required_for_general_knowledge": visual_route.route_type == "general_knowledge_question",
    }
    compact_trace = {
        "local_coverage": semantic_context.get("local_coverage"),
        "semantic_cloud_graph": {
            "attached_nodes": len(semantic_context.get("concepts") or []),
            "evidence_docs": len(semantic_context.get("evidence") or []),
        },
        "conversation_context": {
            "turn_count": len(conversation_context.turns),
            "used_for_routing": bool(conversation_context.turns),
            "followup_detected": conversation_context.followup_detected,
            "focus_terms": list(conversation_context.focus_terms),
            "focus_source": conversation_context.focus_source,
            "resolution_strategy": conversation_context.resolution_strategy,
            "used_for_learning": False,
            "local_brain_write": False,
            "production_store_mutated": False,
            "basis": conversation_context.basis,
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
        "visual_imagination": visual_plan.diagnostics,
        "splatra_scene_policy": visual_policy,
        "splatra_command_sequence": {
            "available": bool(splatra_command_sequence),
            "action_count": len(splatra_command_sequence.get("scene_actions", [])) if splatra_command_sequence else 0,
            "raw_buffers_in_agent_context": False,
            "topic_scene_templates": False,
            "renderer_may_infer_topic": False,
            "text_rendering": "dom_text_not_particles",
        },
        "splatra_interactive_scene_analysis": {
            "available": bool(splatra_interactive_scene_analysis),
            "object_count": int(splatra_interactive_scene_analysis.get("object_count", 0)) if splatra_interactive_scene_analysis else 0,
            "raw_splat_inference": False,
            "raw_buffers_in_agent_context": False,
            "interactive_scene_metadata": bool(splatra_interactive_scene_analysis),
        },
        "answer_surface": {
            "source": (realized.get("repair") or {}).get("source") or "surface_brain_realizer",
            "fact_bound_surface": bool((realized.get("repair") or {}).get("fact_bound_surface")),
            "grounding_quality": (realized.get("repair") or {}).get("grounding_quality"),
            "grounded_discourse_mode": (realized.get("repair") or {}).get("grounded_discourse_mode"),
            "grounded_fact_roles": (realized.get("repair") or {}).get("grounded_fact_roles") or [],
            "grounded_discourse_basis": (realized.get("repair") or {}).get("grounded_discourse_basis"),
            "graph_token_fragment_promoted": (realized.get("repair") or {}).get("source")
            == "web_grounded_native_graph_token_answer",
        },
        "confidence": "high" if realized["confidence"] >= 0.75 else "medium" if realized["confidence"] >= 0.5 else "low",
    }
    if compact_trace["answer_surface"]["fact_bound_surface"]:
        realized["answer"] = _clean_public_fact_bound_answer(realized.get("answer"))
    payload = {
        "answer": realized["answer"],
        "follow_ups": realized.get("follow_ups") or [],
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
        "scene_choreography": visual_plan.scene_choreography,
        "visual_scene_plan": visual_plan.scene_choreography,
        "splatra_scene_plan": visual_plan.scene_choreography,
        "splatra_command_sequence": splatra_command_sequence,
        "splatra_interactive_scene_analysis": splatra_interactive_scene_analysis,
        "splatra_cartridge_queue": None,
        "splatra_sidecar_dispatch": None,
        "splatra_scene_policy": visual_policy,
        "answer_engine": {
            "name": "ATANOR Surface Brain",
            "semantic_plane": "Semantic Cloud Graph",
            "surface_plane": "Surface Cloud Graph",
            "external_llm": False,
            "external_sllm": False,
            "external_llm_used": False,
            "external_sllm_used": False,
            "local_brain_write": False,
            "production_store_mutated": False,
            "candidate_promotion": False,
            "internal_trace_exposed": False,
            "rule_based_answer_used": False,
            "generation_basis": "semantic_cloud_graph_surface_brain_v0",
            "trace_hidden_by_default": True,
            "q_cortex_optional": True,
            "network_barrier": "sealed_for_generation",
            "splatra_scene_policy": visual_policy,
            "conversation_context_used": bool(conversation_context.turns),
            "conversation_context_basis": conversation_context.basis,
            "conversation_followup_detected": conversation_context.followup_detected,
            "conversation_resolution_strategy": conversation_context.resolution_strategy,
            "answer_surface_source": compact_trace["answer_surface"]["source"],
            "fact_bound_surface": compact_trace["answer_surface"]["fact_bound_surface"],
            "grounded_discourse_mode": compact_trace["answer_surface"]["grounded_discourse_mode"],
            "grounded_discourse_basis": compact_trace["answer_surface"]["grounded_discourse_basis"],
            "graph_token_fragment_promoted": compact_trace["answer_surface"]["graph_token_fragment_promoted"],
            "eval_rows_used_for_learning": False,
        },
        **_flags(),
    }
    response = _attach_three_core_trace({"state": "completed", "result": payload, **_flags()}, request=request, three_core_trace=three_core_trace)
    _emit_conversation_result_events(response)
    return response
