from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any

from packages.cgsr.cgsr.conversation_grounding import GroundedContext
from packages.cgsr.cgsr.conversation_router import ConversationRoute
from packages.splatra_imagination import compile_scene_choreography
from packages.splatra_imagination.models import Archetype


PRODUCT_ARCHETYPES: tuple[Archetype, ...] = (
    "constellation",
    "city_block",
    "circuit",
    "tree",
    "machine_core",
    "tower",
    "abstract_memory_cloud",
    "creature",
)

VISUAL_ROUTE_TYPES = {
    "splatra_request",
    "local_cloud_brain_explanation",
    "agentic_os_request",
    "voice_status",
    "general_knowledge_question",
}

ANCHOR_STOPWORDS = {
    "therefore", "a", "an", "and", "are", "as", "associated", "however", "because",
    "event", "explain", "first", "for", "from", "helped", "is", "of", "on", "sat",
    "the", "second", "third", "to", "toward", "under", "with",
    "따라서", "그러나", "그리고", "하지만", "또한", "첫", "번째", "관계", "기존",
    "대한", "대해", "것", "이는", "그", "즉",
}

KOREAN_SUFFIXES = (
    "으로는", "로는", "으로", "에서", "에게", "에는", "이다", "입니다", "하고", "까지",
    "부터", "처럼", "보다", "이며", "이나", "거나", "은", "는", "이", "가", "을",
    "를", "에", "의", "로",
)

MOTION_CUES = {
    "fall", "falls", "falling", "fell", "move", "moves", "moving", "orbit", "orbits",
    "rotate", "rotates", "attract", "attracts", "pull", "pulls", "drop", "drops",
    "떨어", "낙하", "이동", "움직", "회전", "공전", "끌리", "당기", "작용",
    "향하", "내려", "올라",
}

KOREAN_ORGANIC_TERMS = ("사과나무", "나무", "숲", "가지", "잎", "식물")
KOREAN_SMALL_OBJECT_TERMS = ("사과", "과일", "돌", "공", "물체", "질량")
KOREAN_FIGURE_CONTEXT_TERMS = ("머리", "사람", "인물", "학자", "관찰", "뉴턴")

RELATION_CUES = {
    "formulated", "discovered", "defined", "called", "known", "means", "is", "are",
    "발견", "정의", "기술", "나타내", "불리", "정식화", "비교", "관찰", "설명",
}


@dataclass(frozen=True)
class VisualImaginationPlan:
    enabled: bool
    reason: str
    scene_choreography: dict[str, Any] | None
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _stable_index(value: str, size: int) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % max(1, size)


def _scene_group_id(narration: str, source_fact: str) -> str:
    digest = hashlib.sha256(f"{source_fact}::{narration}".encode("utf-8")).hexdigest()[:12]
    return f"verified_scene_group_{digest}"


def _clean_phrase(value: str, *, limit: int = 96) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _canonical_track_phrase(value: str) -> str:
    clean = _clean_phrase(value, limit=96).casefold()
    clean = re.sub(r"\b(?:a|an|the)\s+", "", clean)
    clean = re.sub(r"[^0-9a-z가-힣\s-]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean or "scene-object"


def _expand_known_anchor(anchor: str, known_anchors: list[str]) -> str:
    """Prefer the fuller verified anchor when a later sentence uses a short name."""

    clean = _clean_phrase(anchor, limit=72)
    if not clean:
        return clean
    folded = clean.casefold()
    for known in sorted(known_anchors, key=len, reverse=True):
        known_clean = _clean_phrase(known, limit=72)
        known_folded = known_clean.casefold()
        if not known_clean or known_folded == folded:
            continue
        parts = known_folded.split()
        if parts and folded == parts[-1]:
            return known_clean
        if len(folded) >= 2 and known_folded.endswith(folded):
            return known_clean
    return clean


def _track_affordance_family(visual_affordance: str) -> str:
    if visual_affordance in {"small_object", "small_moving_object"}:
        return "small_object"
    if visual_affordance in {"motion_event", "relation_field", "concept_cloud"}:
        return "semantic_field"
    return visual_affordance or "object"


def _object_track_id(prompt: str, source_fact: str, visual_affordance: str) -> str:
    basis = f"{_canonical_track_phrase(prompt)}::{_track_affordance_family(visual_affordance)}::{_clean_phrase(source_fact, limit=360)}"
    return f"verified_track_{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:14]}"


def _normalize_anchor_token(token: str) -> str:
    token = token.strip()
    for suffix in KOREAN_SUFFIXES:
        if len(token) > len(suffix) + 1 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _fact_units(fact: str) -> list[str]:
    """Split a verified fact into scene-sized units without topic templates."""

    clean = _clean_phrase(fact, limit=420)
    if not clean:
        return []
    parts = re.split(r"(?<=[.!?。])\s+|[;；]\s*", clean)
    units = [_clean_phrase(part, limit=180) for part in parts if _clean_phrase(part, limit=180)]
    return units[:4] or [clean[:180]]


def _entity_spans(text: str) -> list[str]:
    """Extract text-local visual anchors; never map topics to invented props."""

    spans: list[str] = []
    for term in (*KOREAN_ORGANIC_TERMS, *KOREAN_SMALL_OBJECT_TERMS):
        if term in text:
            spans.append(term)
    if "아이작 뉴턴" in text:
        spans.append("아이작 뉴턴")
    elif "뉴턴" in text:
        spans.append("뉴턴")
    for match in re.finditer(r"([가-힣A-Za-z]{2,}(?:\s+[가-힣A-Za-z]{2,}){0,2})(?=(?:은|는|이|가|을|를|에서|에게|으로|로|의|과|와|에|,|\.|\s|$))", text):
        candidate = _clean_phrase(match.group(1), limit=72)
        if candidate:
            spans.append(candidate)
    for match in re.finditer(r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,})){0,3}\b", text):
        spans.append(match.group(0))
    for match in re.finditer(r"[0-9A-Za-z가-힣][0-9A-Za-z가-힣_-]{1,}(?:\s+[0-9A-Za-z가-힣][0-9A-Za-z가-힣_-]{1,}){0,2}", text):
        candidate = match.group(0).strip()
        if len(candidate) >= 2:
            spans.append(candidate)

    cleaned: list[str] = []
    for span in spans:
        tokens = [_normalize_anchor_token(token) for token in span.split()]
        tokens = [
            token
            for token in tokens
            if token and token.casefold() not in ANCHOR_STOPWORDS and len(token) >= 2
        ]
        if not tokens:
            continue
        cleaned.append(_clean_phrase(" ".join(tokens[:3]), limit=72))

    deduped: list[str] = []
    seen: set[str] = set()
    for span in cleaned:
        key = span.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(_clean_phrase(span, limit=72))
    return deduped[:4]


def _has_any_cue(text: str, cues: set[str]) -> bool:
    folded = text.casefold()
    for cue in cues:
        cue_folded = cue.casefold()
        if re.fullmatch(r"[a-z]+", cue_folded):
            if re.search(rf"\b{re.escape(cue_folded)}\b", folded):
                return True
            continue
        if cue_folded in folded:
            return True
    return False


def _motion_participants(narration: str) -> dict[str, str]:
    """Extract motion subject/source/target from the verified sentence itself.

    This is a shallow linguistic extraction layer, not a topic script. It never
    maps "gravity" to props; it only promotes participants that are explicitly
    present in a source sentence containing motion cues.
    """

    participants = {"subject": "", "source": "", "target": ""}
    clean = _clean_phrase(narration, limit=240)
    if not _has_any_cue(clean, MOTION_CUES):
        return participants

    weak_motion_nominals = {"떨어짐", "운동", "현상", "장면", "사건"}
    for clause in reversed([part.strip() for part in re.split(r"(?:었고|했고|였고|\s+고\s+|,|;|[.。])", clean) if part.strip()]):
        if not _has_any_cue(clause, MOTION_CUES):
            continue
        matches = list(re.finditer(
            r"([가-힣A-Za-z]{1,20})(?:이|가|은|는)\s+(?=[^.。]{0,42}?(?:떨어|낙하|내려|움직|이동|향하|끌리))",
            clause,
            re.IGNORECASE,
        ))
        for match in reversed(matches):
            candidate = _clean_phrase(_normalize_anchor_token(match.group(1)), limit=72)
            if candidate and candidate not in weak_motion_nominals:
                participants["subject"] = candidate
                break
        if participants["subject"]:
            break

    korean_subject_patterns = [
        r"([가-힣A-Za-z]{1,20})(?:이|가)\s+(?:[가-힣A-Za-z]{1,20}(?:에서|로부터|부터|밑에)\s+)?(?:떨어|낙하|내려|움직|이동|향하|끌리)",
        r"([가-힣A-Za-z]{1,20})\s*떨어짐",
        r"([가-힣A-Za-z]{1,20})(?:이|가|은|는)\s+(?:[가-힣A-Za-z]{1,20}\s+)?(?:쪽으로|향해|에게|으로|로)\s*(?:끌리|내려|향하|이동|움직)",
    ]
    if not participants["subject"]:
        for pattern in korean_subject_patterns:
            match = re.search(pattern, clean, re.IGNORECASE)
            if match:
                participants["subject"] = _clean_phrase(_normalize_anchor_token(match.group(1)), limit=72)
                break

    subject_patterns = [
        r"\b(?:an?|the)?\s*([A-Za-z][A-Za-z -]{1,44}?)\s+(?:fell|falls|falling|dropped|drops|moving|moved|moves|shifted|shifts|travels|traveled)\b",
        r"([가-힣A-Za-z]{1,16})(?:이|가|은|는)?\s*[^.]{0,24}?(?:떨어|낙하|이동|움직|끌리|향하|내려|올라)",
    ]
    if not participants["subject"]:
        for pattern in subject_patterns:
            match = re.search(pattern, clean, re.IGNORECASE)
            if match:
                participants["subject"] = _clean_phrase(_normalize_anchor_token(match.group(1)), limit=72)
                break

    source_patterns = [
        r"\bfrom\s+(?:a|an|the)?\s*([A-Za-z][A-Za-z -]{1,44}?)(?=\s+(?:toward|towards|to|into|onto)\b|[,.;]|$)",
        r"([가-힣A-Za-z]{0,12}?나무)\s*(?:에서|로부터|부터|밑에)",
    ]
    for pattern in source_patterns:
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            participants["source"] = _clean_phrase(_normalize_anchor_token(match.group(1)), limit=72)
            break

    target_patterns = [
        r"\b(?:toward|towards|to|into|onto)\s+(?:a|an|the)?\s*([A-Za-z][A-Za-z -]{1,44}?)(?=[,.;]|$)",
        r"([가-힣A-Za-z]{2,}?)(?:의)?\s*머리",
        r"(?:쪽으로|향해|에게|으로|로)\s*([가-힣A-Za-z]{2,})",
        r"([가-힣A-Za-z]{2,})(?:\s*)쪽으로",
    ]
    for pattern in target_patterns:
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            participants["target"] = _clean_phrase(_normalize_anchor_token(match.group(1)), limit=72)
            break

    return participants


def _scene_op_for_unit(unit: str, *, index: int, is_last: bool) -> str:
    """Choose a visual operation from linguistic evidence, not topic templates."""

    if index == 0:
        return "spawn_object"
    if is_last:
        return "focus_camera"
    if _has_any_cue(unit, MOTION_CUES):
        return "move"
    if _has_any_cue(unit, RELATION_CUES):
        return "morph"
    return "morph"


def _scene_op_for_scene_unit(unit: dict[str, Any], *, index: int, is_last: bool) -> str:
    """Choose beat operation from the extracted evidence role.

    A motion sentence can mention several anchors: source, target, context, and
    subject. Only the moving subject/event should inherit the motion operation.
    Source/target anchors are assembled as objects so the renderer does not
    make the entire explanatory scene drift just because the narration contains
    a motion verb.
    """

    role = str(unit.get("semantic_role") or "")
    narration = str(unit.get("narration") or "")
    if role in {
        "verified_motion_source",
        "verified_motion_target",
        "verified_motion_anchor",
        "verified_motion_context",
        "verified_entity_anchor",
    }:
        return "focus_camera" if is_last else "spawn_object"
    if role in {"verified_motion_subject", "verified_motion_event"} and _has_any_cue(narration, MOTION_CUES):
        return "move" if index > 0 else "spawn_object"
    return _scene_op_for_unit(narration, index=index, is_last=is_last)


def _beat_duration_for_unit(unit: dict[str, str], op: str) -> float:
    """Estimate visual beat duration from the grounded narration length.

    This keeps the stage synchronized with the evidence-backed utterance
    cadence. It is not a content script and it does not author narration.
    """

    narration = unit.get("narration") or unit.get("prompt") or ""
    compact_length = len(re.sub(r"\s+", "", narration))
    word_count = len(re.findall(r"[0-9A-Za-z가-힣]+", narration))
    length_signal = max(compact_length / 32.0, word_count / 9.0)
    base = 1.05 + min(1.65, length_signal * 0.34)
    if op == "move":
        base += 0.34
    elif op == "focus_camera":
        base += 0.18
    return round(min(3.2, max(1.05, base)), 2)


def _scene_directive_for_unit(
    unit: dict[str, Any],
    *,
    op: str,
    visual_affordance: str,
    motion_path: dict[str, Any],
) -> dict[str, Any]:
    """Describe how the renderer should use the verified beat.

    This is a choreography contract, not a topic script: it only summarizes
    the already-extracted role/op/motion evidence so the product renderer does
    not invent why the orb, text, or particle stage should move.
    """

    semantic_role = str(unit.get("semantic_role") or "")
    speech_cue = bool(unit.get("speech_cue", True))
    if op == "move" or motion_path:
        narrative_function = "demonstrate_verified_motion"
        stage_instruction = "animate_verified_motion_path"
    elif not speech_cue or semantic_role.endswith("_anchor"):
        narrative_function = "establish_visual_anchor"
        stage_instruction = "assemble_silent_anchor"
    elif op == "focus_camera":
        narrative_function = "focus_verified_detail"
        stage_instruction = "close_up_verified_object"
    elif "relation" in semantic_role:
        narrative_function = "introduce_verified_relation"
        stage_instruction = "bind_relation_field"
    else:
        narrative_function = "present_verified_fact"
        stage_instruction = "assemble_verified_object"
    return {
        "directive_owner": "cgsr_visual_imagination_planner",
        "basis": "verified_scene_beat",
        "narrative_function": narrative_function,
        "stage_instruction": stage_instruction,
        "visual_affordance": visual_affordance,
        "speech_sync": "speech_timeline" if speech_cue else "visual_anchor_only",
        "text_rendering": "dom_text_not_particles",
        "particle_text": False,
        "topic_scene_templates": False,
    }


def _scene_evidence_for_unit(
    unit: dict[str, Any],
    *,
    visual_affordance: str,
    spatial_relation: str,
    surface_features: list[str],
    motion_path: dict[str, Any],
    particle_behavior: str,
) -> dict[str, Any]:
    """Preserve the verified evidence behind a particle beat.

    The renderer should never infer "gravity means apple tree" on its own.
    This trace makes each generated visual affordance auditable against a
    verified text span and keeps topic templates explicitly disabled.
    """

    source_fact = _clean_phrase(str(unit.get("source_fact") or ""), limit=360)
    prompt = _clean_phrase(str(unit.get("prompt") or ""), limit=96)
    narration = _clean_phrase(str(unit.get("narration") or ""), limit=240)
    return {
        "evidence_owner": "cgsr_visual_imagination_planner",
        "source_type": "verified_evidence_unit",
        "source_fact_hash": hashlib.sha256(source_fact.encode("utf-8")).hexdigest()[:16] if source_fact else "",
        "prompt_span": prompt,
        "narration_span": narration,
        "semantic_role": str(unit.get("semantic_role") or ""),
        "visual_affordance": visual_affordance,
        "spatial_relation": spatial_relation,
        "surface_features": list(surface_features),
        "motion_basis": str(motion_path.get("basis") or ""),
        "motion_source_prompt": str(motion_path.get("source_prompt") or ""),
        "motion_target_prompt": str(motion_path.get("target_prompt") or ""),
        "particle_behavior": particle_behavior,
        "text_rendering": "dom_text_not_particles",
        "particle_text": False,
        "topic_scene_templates": False,
        "renderer_may_infer_topic": False,
    }


def _make_scene_beat(unit: dict[str, Any], *, index: int, op: str, t_start: float, duration: float | None = None) -> dict[str, Any]:
    phrase = unit["prompt"]
    object_seed = f"{index}:{op}:{unit['prompt']}:{unit['narration']}"
    visual_affordance = _visual_affordance_for_phrase(phrase, unit["narration"], unit["semantic_role"], op)
    spatial_relation = _spatial_relation_for_phrase(phrase, unit["narration"], visual_affordance, op)
    pose_hint = _pose_hint_for_scene_unit(visual_affordance, spatial_relation, unit["semantic_role"])
    surface_features = _surface_features_for_scene_unit(phrase, unit["narration"], unit["source_fact"], visual_affordance)
    if unit["semantic_role"] == "user_visual_intent":
        position = [0.0, 0.0]
    else:
        position = _position_for_unit(phrase, index, visual_affordance, spatial_relation)
    beat = {
        "op": op,
        "prompt": phrase,
        "narration": unit["narration"],
        "object_id": f"grounded_visual_{index}_{_stable_index(object_seed, 100000):05d}",
        "object_track_id": _object_track_id(phrase, unit["source_fact"], visual_affordance),
        "object_track_basis": "verified_source_anchor",
        "semantic_role": unit["semantic_role"],
        "visual_affordance": visual_affordance,
        "spatial_relation": spatial_relation,
        "pose_hint": pose_hint,
        "surface_features": surface_features,
        "source_fact": unit["source_fact"],
        "speech_cue": bool(unit.get("speech_cue", True)),
        "speech_cue_basis": unit.get("speech_cue_basis", "verified_evidence_unit"),
        "generation_prompt_basis": unit.get("generation_prompt_basis"),
        "scene_group_id": unit.get("scene_group_id") or _scene_group_id(unit["narration"], unit["source_fact"]),
        "scene_group_role": unit.get("scene_group_role", "speech_unit" if unit.get("speech_cue", True) else "visual_anchor"),
        "archetype": _archetype_for_phrase(phrase, unit["semantic_role"], index, visual_affordance),
        "t_start": round(t_start, 2),
        "duration": duration if duration is not None else _beat_duration_for_unit(unit, op),
        "position": position,
        "camera": _camera_for_unit(position, visual_affordance, op, spatial_relation, index) if op in {"focus_camera", "move"} else {},
    }
    motion_path = (
        _motion_path_for_unit(unit, index=index)
        if op == "move" or unit["semantic_role"] in {"verified_motion_event", "verified_motion_subject"}
        else {}
    )
    particle_behavior, physics_hint = _particle_behavior_for_unit(unit, visual_affordance, op, motion_path)
    if pose_hint:
        physics_hint["pose_hint"] = pose_hint
    if surface_features:
        physics_hint["surface_features"] = surface_features
    scene_directive = _scene_directive_for_unit(
        unit,
        op=op,
        visual_affordance=visual_affordance,
        motion_path=motion_path,
    )
    beat["particle_behavior"] = particle_behavior
    beat["physics_hint"] = physics_hint
    beat["scene_directive"] = scene_directive
    beat["scene_evidence"] = _scene_evidence_for_unit(
        unit,
        visual_affordance=visual_affordance,
        spatial_relation=spatial_relation,
        surface_features=surface_features,
        motion_path=motion_path,
        particle_behavior=particle_behavior,
    )
    if motion_path:
        beat["motion_path"] = motion_path
    return beat


def _scene_units(question: str, *, route_type: str, grounded_context: GroundedContext) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    if route_type == "splatra_request" and _is_direct_model_generation_request(question):
        clean_question = _clean_phrase(question)
        generation_prompt = _direct_generation_prompt(question) or clean_question
        if clean_question:
            group_id = _scene_group_id(clean_question, "")
            return [
                {
                    "prompt": generation_prompt,
                    "narration": clean_question,
                    "source_fact": "",
                    "semantic_role": "user_visual_intent",
                    "speech_cue": True,
                    "speech_cue_basis": "user_visual_intent",
                    "generation_prompt_basis": "direct_generation_prompt_normalized_for_sidecar",
                    "scene_group_id": group_id,
                    "scene_group_role": "speech_unit",
                }
            ]
    elif route_type == "splatra_request":
        clean_question = _clean_phrase(question)
        if clean_question:
            group_id = _scene_group_id(clean_question, "")
            units.append(
                {
                    "prompt": clean_question,
                    "narration": clean_question,
                    "source_fact": "",
                    "semantic_role": "surface_phrase",
                    "speech_cue": True,
                    "speech_cue_basis": "surface_phrase",
                    "scene_group_id": group_id,
                    "scene_group_role": "speech_unit",
                }
            )

    for fact in grounded_context.facts:
        clean_fact = _clean_phrase(fact, limit=420)
        fact_anchors = _entity_spans(clean_fact)
        for unit in _fact_units(clean_fact):
            group_id = _scene_group_id(unit, clean_fact)
            anchors = _entity_spans(unit)
            prompt = " / ".join(anchors[:2]) if len(anchors) >= 2 else anchors[0] if anchors else unit
            semantic_role = "verified_entity_relation" if len(anchors) >= 2 else "verified_fact_unit"
            motion_participants = _motion_participants(unit)
            motion_participants = {
                key: _expand_known_anchor(value, fact_anchors)
                for key, value in motion_participants.items()
            }
            if _has_any_cue(unit, MOTION_CUES):
                semantic_role = "verified_motion_event"
                if motion_participants["subject"]:
                    prompt = motion_participants["subject"]
            units.append(
                {
                    "prompt": prompt,
                    "narration": _clean_phrase(unit, limit=180),
                    "source_fact": clean_fact,
                    "semantic_role": semantic_role,
                    "speech_cue": True,
                    "speech_cue_basis": "verified_evidence_unit",
                    "scene_group_id": group_id,
                    "scene_group_role": "speech_unit",
                    "known_anchors": fact_anchors,
                }
            )
            if _has_any_cue(unit, MOTION_CUES):
                participant_units = [
                    ("verified_motion_subject", motion_participants["subject"]),
                    ("verified_motion_source", motion_participants["source"]),
                    ("verified_motion_target", motion_participants["target"]),
                ]
                for role, anchor in participant_units:
                    if not anchor:
                        continue
                    units.append(
                        {
                            "prompt": anchor,
                            "narration": _clean_phrase(unit, limit=180),
                            "source_fact": clean_fact,
                            "semantic_role": role,
                            "speech_cue": False,
                            "speech_cue_basis": "visual_anchor_only",
                            "scene_group_id": group_id,
                            "scene_group_role": "visual_anchor",
                            "known_anchors": fact_anchors,
                        }
                    )
                for anchor_index, anchor in enumerate(anchors[:3]):
                    units.append(
                        {
                            "prompt": anchor,
                            "narration": _clean_phrase(unit, limit=180),
                            "source_fact": clean_fact,
                            "semantic_role": "verified_motion_anchor" if anchor_index == 0 else "verified_motion_context",
                            "speech_cue": False,
                            "speech_cue_basis": "visual_anchor_only",
                            "scene_group_id": group_id,
                            "scene_group_role": "visual_anchor",
                            "known_anchors": fact_anchors,
                        }
                    )
            for anchor_index, anchor in enumerate(anchors[:4]):
                units.append(
                    {
                        "prompt": anchor,
                        "narration": _clean_phrase(unit, limit=180),
                        "source_fact": clean_fact,
                        "semantic_role": "verified_entity_anchor",
                        "speech_cue": False,
                        "speech_cue_basis": "visual_anchor_only",
                        "scene_group_id": group_id,
                        "scene_group_role": "visual_anchor",
                        "known_anchors": fact_anchors,
                    }
                )

    if not units:
        clean_question = _clean_phrase(question)
        if clean_question:
            group_id = _scene_group_id(clean_question, "")
            units.append(
                {
                    "prompt": clean_question,
                    "narration": clean_question,
                    "source_fact": "",
                    "semantic_role": "surface_phrase",
                    "speech_cue": True,
                    "speech_cue_basis": "surface_phrase",
                    "scene_group_id": group_id,
                    "scene_group_role": "speech_unit",
                }
            )

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for unit in units:
        role = unit["semantic_role"]
        role_key = f"::{role}" if role in {"verified_motion_subject", "verified_motion_source", "verified_motion_target"} else ""
        key = f"{unit['prompt']}::{unit['narration']}{role_key}".casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(unit)
    selected = deduped[:14]
    selected_keys = {f"{unit['prompt']}::{unit['narration']}::{unit['semantic_role']}".casefold() for unit in selected}
    for unit in deduped[14:]:
        role = unit["semantic_role"]
        if role not in {"verified_motion_event", "verified_motion_anchor", "verified_motion_context", "verified_motion_subject", "verified_motion_source", "verified_motion_target"}:
            continue
        key = f"{unit['prompt']}::{unit['narration']}::{role}".casefold()
        if key in selected_keys:
            continue
        for replace_index in range(len(selected) - 1, -1, -1):
            if selected[replace_index]["semantic_role"] in {"verified_entity_anchor", "verified_fact_unit"}:
                selected[replace_index] = unit
                selected_keys.add(key)
                break
    return selected


def _scene_units_have_concrete_visual_grounding(scene_units: list[dict[str, Any]]) -> bool:
    """Require source-local visual evidence before opening the large particle stage.

    A verified explanatory sentence is not automatically a visual scene. Abstract
    relation facts such as "gravity is attraction between masses" should remain
    DOM text plus ambient particles; otherwise the renderer turns formulas and
    nouns into repeated pseudo-objects. We only allow verified-store scenes when
    the evidence itself contains concrete visual participants tied by motion or
    spatial language. Direct user SPLATRA generation requests are handled before
    this gate and remain allowed.
    """

    concrete_affordances = {"entity_figure", "organic_structure", "small_object", "small_moving_object"}
    concrete_motion_terms = {
        "river", "water", "valley", "channel", "basin", "stream", "stone", "ball",
        "강", "물", "계곡", "수로", "분지", "하천", "돌", "공", "사과", "나무",
    }
    spatial_cues = {
        " under ", " beneath ", " below ", " above ", " over ", " from ", " toward ", " towards ", " into ", " onto ",
        "떨어", "내려", "위로", "아래", "쪽으로", "에서", "밑에", "위에",
    }
    for unit in scene_units:
        role = str(unit.get("semantic_role") or "")
        if not role.startswith("verified_"):
            continue
        narration = str(unit.get("narration") or "")
        prompt = str(unit.get("prompt") or "")
        op = "move" if "motion" in role and _has_any_cue(narration, MOTION_CUES) else "morph"
        visual_affordance = _visual_affordance_for_phrase(prompt, narration, role, op)
        folded_visual_text = f" {prompt} {narration} ".casefold()
        if visual_affordance not in concrete_affordances and not (
            visual_affordance == "motion_event"
            and any(term in folded_visual_text or term in f"{prompt} {narration}" for term in concrete_motion_terms)
        ):
            continue
        if _motion_path_for_unit(unit, index=0):
            return True
        folded = f" {narration.casefold()} "
        if any(cue in folded or cue in narration for cue in spatial_cues):
            return True
    return False


def _direct_generation_prompt(question: str) -> str:
    folded = str(question or "").casefold()
    if (
        ("\uc720\ub9ac" in folded and ("\uad6c\uc2ac" in folded or "\uad6c\uccb4" in folded or "\uacf5" in folded))
        or (("glass" in folded or "transparent" in folded or "translucent" in folded) and ("orb" in folded or "sphere" in folded or "marble" in folded))
    ):
        return "translucent glass marble sphere with visible rim"
    if "\ube68\uac04 \uc0ac\uacfc" in folded or "red apple" in folded:
        return "red apple"
    if "\uc0ac\uacfc" in folded or "apple" in folded:
        return "red apple"
    if "\ub85c\ubd07" in folded or "robot" in folded:
        return "robot"
    if "\uc5f4\ub9b0 \ucc45" in folded or "open book" in folded:
        return "open book"
    if "\ucc45" in folded or "book" in folded:
        return "book"
    return ""


def _is_direct_model_generation_request(question: str) -> bool:
    folded = question.casefold()
    clean_direct_cues = (
        "\uc0dd\uc131", "\ub9cc\ub4e4", "\ubcf4\uc5ec", "\ub80c\ub354", "\uadf8\ub824", "\uc9c1\uc811",
        "generate", "create", "make", "spawn", "render", "show", "visualize",
    )
    clean_visual_cues = (
        "splatra", "\uc2a4\ud50c\ub77c\ud2b8\ub77c", "\ud30c\ud2f0\ud074", "\uc785\uc790", "3d", "\ubaa8\ub378",
        "\ubb3c\uccb4", "\uc624\ube0c\uc81d\ud2b8", "\uad6c\uc2ac", "\uc720\ub9ac", "\uc0ac\uacfc", "\ub85c\ubd07",
        "\ub098\ubb34", "\ucc45", "\uacf5", "object", "model", "particle",
    )
    if any(cue in folded for cue in clean_direct_cues) and any(cue in folded for cue in clean_visual_cues):
        return True
    if _direct_generation_prompt(question):
        return True
    clean_direct_cues = (
        "생성", "만들", "보여", "렌더", "그려", "직접",
        "generate", "create", "make", "spawn", "render", "show",
    )
    clean_visual_cues = (
        "splatra", "스플라트라", "파티클", "입자", "3d", "모델", "물체", "오브젝트",
        "구슬", "유리", "사과", "로봇", "나무", "책", "공", "object", "model", "particle",
    )
    if any(cue in folded for cue in clean_direct_cues) and any(cue in folded for cue in clean_visual_cues):
        return True
    direct_cues = (
        "generate", "create", "make", "spawn", "render", "model", "object", "3d",
        "생성", "만들", "모델", "사물", "오브젝트", "물체", "직접", "사실적",
    )
    splatra_cues = ("splatra", "스플라트라", "스플래트라", "파티클", "입자", "홀로그램")
    return any(cue in folded for cue in direct_cues) and any(cue in folded for cue in splatra_cues)


def _looks_like_named_figure(phrase: str) -> bool:
    tokens = re.findall(r"\b[A-Z][a-z]{2,}\b", phrase)
    return len(tokens) >= 2


def _looks_like_english_figure(phrase: str, narration: str) -> bool:
    tokens = re.findall(r"\b[A-Z][a-z]{2,}\b", phrase)
    if len(tokens) >= 2:
        return True
    if len(tokens) != 1 or phrase.strip() != tokens[0]:
        return False
    folded = narration.casefold()
    return any(cue in folded for cue in (" sat ", "sitting", "seated", "person", "figure", "head", "toward", "towards"))


def _looks_like_korean_figure(phrase: str, narration: str) -> bool:
    if not re.search(r"[가-힣]", phrase):
        return False
    folded_phrase = phrase.casefold()
    if any(term in folded_phrase for term in (*KOREAN_ORGANIC_TERMS, *KOREAN_SMALL_OBJECT_TERMS)):
        return False
    if any(term in narration for term in KOREAN_FIGURE_CONTEXT_TERMS):
        return True
    tokens = re.findall(r"[가-힣]{2,}", phrase)
    return len(tokens) >= 2 and len(phrase) <= 18


def _visual_affordance_for_phrase(phrase: str, narration: str, semantic_role: str, op: str) -> str:
    """Infer a visual carrier affordance from the grounded phrase itself.

    This is not a topic-to-scene script. It only reads morphology already
    present in the verified phrase, so gravity never implies a tree unless a
    source fact actually says tree.
    """

    folded_phrase = phrase.casefold()
    if _looks_like_english_figure(phrase, narration) or _looks_like_named_figure(phrase) or _looks_like_korean_figure(phrase, narration):
        return "entity_figure"
    if any(term in folded_phrase for term in ("tree", "forest", "branch", "trunk", "leaf", "leaves", "canopy", "plant")) or any(term in phrase for term in KOREAN_ORGANIC_TERMS):
        return "organic_structure"
    if any(term in folded_phrase for term in ("fruit", "apple", "stone", "ball", "object", "body", "mass")) or any(term in phrase for term in KOREAN_SMALL_OBJECT_TERMS):
        return "small_moving_object" if op == "move" or "motion" in semantic_role else "small_object"
    if op == "move" or "motion" in semantic_role:
        return "motion_event"
    if "relation" in semantic_role:
        return "relation_field"
    return "concept_cloud"


def _spatial_relation_for_phrase(phrase: str, narration: str, visual_affordance: str, op: str) -> str:
    folded = f" {narration.casefold()} "
    has_under_cue = " under " in folded or " beneath " in folded or " below " in folded or "밑" in narration or "아래" in narration
    has_upper_cue = "위" in narration or "위로" in narration
    if has_under_cue:
        if visual_affordance == "entity_figure":
            return "under_target"
        if visual_affordance == "organic_structure":
            return "over_anchor"
        if visual_affordance in {"small_object", "small_moving_object"}:
            return "upper_attachment"
    if has_upper_cue and visual_affordance in {"small_object", "small_moving_object"}:
        return "upper_attachment"
    if op == "move" or " toward " in folded or " towards " in folded or "쪽으로" in narration or "향해" in narration:
        if visual_affordance in {"small_object", "small_moving_object"}:
            return "path_object"
        if visual_affordance == "entity_figure":
            return "motion_target"
        if visual_affordance == "organic_structure":
            return "motion_source"
    return ""


def _archetype_for_phrase(phrase: str, semantic_role: str, index: int, visual_affordance: str = "") -> Archetype:
    # This is deliberately not a topic dictionary. It only chooses a bounded
    # visual carrier deterministically so the planner does not smuggle in
    # prompt-specific templates such as "gravity -> Newton/apple/tree".
    if visual_affordance == "entity_figure":
        return "creature"
    if visual_affordance == "organic_structure":
        return "tree"
    if visual_affordance in {"small_object", "small_moving_object"}:
        return "machine_core"
    if visual_affordance == "motion_event":
        return "constellation"
    if visual_affordance in {"relation_field", "concept_cloud"}:
        return "abstract_memory_cloud"
    role_seed = semantic_role if semantic_role in {
        "verified_motion_anchor",
        "verified_motion_context",
        "verified_motion_event",
        "verified_motion_subject",
        "verified_motion_source",
        "verified_motion_target",
        "verified_entity_anchor",
        "verified_entity_relation",
    } else "grounded"
    return PRODUCT_ARCHETYPES[_stable_index(f"{role_seed}:{index}:{phrase}", len(PRODUCT_ARCHETYPES))]


def _pose_hint_for_scene_unit(visual_affordance: str, spatial_relation: str, semantic_role: str) -> str:
    if visual_affordance != "entity_figure":
        return ""
    if spatial_relation == "under_target":
        return "seated"
    if spatial_relation == "motion_target" or semantic_role == "verified_motion_target":
        return "reaching"
    return "standing"


def _surface_features_for_scene_unit(phrase: str, narration: str, source_fact: str, visual_affordance: str) -> list[str]:
    if visual_affordance != "organic_structure":
        return []
    folded = f" {phrase} {narration} {source_fact} ".casefold()
    features: list[str] = []
    if any(term in folded for term in ("apple", "fruit", "berry", "seed")) or any(term in f"{phrase} {narration} {source_fact}" for term in KOREAN_SMALL_OBJECT_TERMS):
        features.append("fruit_cluster")
    return features


def _position_for_phrase(phrase: str, index: int) -> list[float]:
    # Phrase-dependent placement gives the renderer room to move without
    # smuggling in topic templates. The same grounded phrase always lands in
    # the same bounded area, but there is no dictionary such as gravity->tree.
    x_bucket = _stable_index(f"x:{index}:{phrase}", 9) - 4
    y_bucket = _stable_index(f"y:{index}:{phrase}", 7) - 3
    return [round(x_bucket * 0.22, 2), round(y_bucket * 0.16, 2), 0.0]


def _position_for_unit(phrase: str, index: int, visual_affordance: str, spatial_relation: str) -> list[float]:
    relation_positions = {
        "under_target": [-0.18, -0.34, 0.0],
        "over_anchor": [0.2, 0.28, 0.0],
        "upper_attachment": [0.16, 0.42, 0.0],
        "path_object": [0.02, 0.34, 0.0],
        "motion_target": [-0.2, -0.32, 0.0],
        "motion_source": [0.24, 0.3, 0.0],
    }
    if spatial_relation in relation_positions:
        base = relation_positions[spatial_relation]
        jitter_x = (_stable_index(f"rx:{index}:{phrase}", 5) - 2) * 0.025
        jitter_y = (_stable_index(f"ry:{index}:{phrase}", 5) - 2) * 0.02
        return [round(base[0] + jitter_x, 2), round(base[1] + jitter_y, 2), 0.0]
    return _position_for_phrase(phrase, index)


def _motion_path_for_unit(unit: dict[str, Any], *, index: int) -> dict[str, Any]:
    narration = unit["narration"]
    if not _has_any_cue(narration, MOTION_CUES):
        return {}
    participants = _motion_participants(narration)
    source_prompt = participants["source"]
    target_prompt = participants["target"]
    korean_source = re.search(r"([가-힣A-Za-z]{0,12}?나무)\s*(?:에서|로부터|부터|밑에)", narration)
    if korean_source:
        source_prompt = _clean_phrase(korean_source.group(1), limit=72)
    korean_target = re.search(r"([가-힣A-Za-z]{2,}?)(?:의)?\s*머리", narration)
    if korean_target:
        target_prompt = _clean_phrase(korean_target.group(1), limit=72)
    korean_direction_target = re.search(r"(?:쪽으로|향해|에게|으로|로)\s*([가-힣A-Za-z]{2,})", narration)
    if korean_direction_target and not target_prompt:
        target_prompt = _clean_phrase(korean_direction_target.group(1), limit=72)
    from_match = re.search(
        r"\bfrom\s+(?:a|an|the)?\s*([A-Za-z][A-Za-z -]{1,44}?)(?=\s+(?:toward|towards|to|into|onto)\b|[,.;]|$)",
        narration,
        re.IGNORECASE,
    )
    if from_match:
        source_prompt = _clean_phrase(from_match.group(1), limit=72)
    target_match = re.search(
        r"\b(?:toward|towards|to|into|onto)\s+(?:a|an|the)?\s*([A-Za-z][A-Za-z -]{1,44}?)(?=[,.;]|$)",
        narration,
        re.IGNORECASE,
    )
    if target_match:
        target_prompt = _clean_phrase(target_match.group(1), limit=72)

    anchors = _entity_spans(narration)
    known_anchors = unit.get("known_anchors") if isinstance(unit.get("known_anchors"), list) else _entity_spans(unit.get("source_fact", ""))
    if not source_prompt and any(term in narration for term in KOREAN_ORGANIC_TERMS):
        source_prompt = next((term for term in KOREAN_ORGANIC_TERMS if term in narration), "")
    if not source_prompt:
        source_prompt = next(
            (
                anchor
                for anchor in known_anchors
                if _visual_affordance_for_phrase(anchor, narration, "verified_motion_context", "morph") == "organic_structure"
            ),
            "",
        )
    if not target_prompt:
        target_prompt = next((anchor for anchor in anchors if _visual_affordance_for_phrase(anchor, narration, "verified_motion_context", "morph") == "entity_figure"), "")
    if not source_prompt and len(anchors) >= 2:
        source_prompt = anchors[-2]
    if not target_prompt and anchors:
        target_prompt = anchors[-1]
    source_prompt = _expand_known_anchor(source_prompt, known_anchors)
    target_prompt = _expand_known_anchor(target_prompt, known_anchors)
    if not source_prompt or not target_prompt or source_prompt.casefold() == target_prompt.casefold():
        return {}
    source_affordance = _visual_affordance_for_phrase(source_prompt, narration, "verified_motion_context", "morph")
    target_affordance = _visual_affordance_for_phrase(target_prompt, narration, "verified_motion_context", "morph")
    source_relation = _spatial_relation_for_phrase(source_prompt, narration, source_affordance, "morph")
    target_relation = _spatial_relation_for_phrase(target_prompt, narration, target_affordance, "morph")
    return {
        "from": _position_for_unit(source_prompt, index + 37, source_affordance, source_relation or "motion_source"),
        "to": _position_for_unit(target_prompt, index + 73, target_affordance, target_relation or "motion_target"),
        "basis": "verified_motion_phrase",
        "source_prompt": source_prompt,
        "target_prompt": target_prompt,
    }


def _camera_for_unit(position: list[float], visual_affordance: str, op: str, spatial_relation: str, index: int) -> dict[str, Any]:
    zoom_bucket = _stable_index(f"z:{index}:{visual_affordance}:{spatial_relation}:{op}", 5)
    affordance_bonus = {
        "small_object": 0.18,
        "small_moving_object": 0.22,
        "entity_figure": 0.1,
        "organic_structure": 0.06,
    }.get(visual_affordance, 0.0)
    op_bonus = 0.14 if op == "focus_camera" else 0.08 if op == "move" else 0.0
    return {
        "target": position,
        "zoom": round(0.94 + zoom_bucket * 0.07 + affordance_bonus + op_bonus, 2),
    }


def _particle_behavior_for_unit(unit: dict[str, Any], visual_affordance: str, op: str, motion_path: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Attach renderer-facing physics hints from verified wording only."""

    narration = unit.get("narration", "")
    folded = narration.casefold()
    has_motion = bool(motion_path) or op == "move" or "motion" in str(unit.get("semantic_role", ""))
    gravity_cues = (
        "fall", "falling", "fell", "drop", "dropped", "toward", "towards",
        "떨어", "낙하", "끌리", "쪽으로", "향해", "향하", "내려",
    )
    if has_motion and any(cue in folded for cue in gravity_cues):
        return "gravity_arc", {
            "basis": "verified_motion_phrase",
            "field": "downward_attraction",
            "material": "dense_moving_splat",
            "gravity_bias": 0.72,
            "cohesion": 0.64,
            "trail": 0.86,
        }
    if has_motion:
        return "kinetic_flow", {
            "basis": "verified_motion_phrase",
            "field": "directed_flow",
            "material": "energized_splat",
            "gravity_bias": 0.28,
            "cohesion": 0.58,
            "trail": 0.72,
        }
    if visual_affordance == "organic_structure":
        return "rooted_growth", {
            "basis": "verified_visual_affordance",
            "field": "branching_cohesion",
            "material": "organic_splat",
            "gravity_bias": 0.18,
            "cohesion": 0.82,
            "trail": 0.22,
        }
    if visual_affordance == "entity_figure":
        return "articulated_cluster", {
            "basis": "verified_visual_affordance",
            "field": "pose_cohesion",
            "material": "figure_splat",
            "gravity_bias": 0.24,
            "cohesion": 0.76,
            "trail": 0.28,
        }
    if visual_affordance in {"relation_field", "concept_cloud"}:
        return "magnetic_field", {
            "basis": "verified_relation_or_concept",
            "field": "swarm_relation",
            "material": "field_splat",
            "gravity_bias": 0.0,
            "cohesion": 0.42,
            "trail": 0.54,
        }
    return "bounded_swarm", {
        "basis": "verified_scene_unit",
        "field": "bounded_swarm",
        "material": "neutral_splat",
        "gravity_bias": 0.12,
        "cohesion": 0.56,
        "trail": 0.34,
    }


def _text_anchor_for_beats(beats: list[dict[str, Any]]) -> str:
    """Place narration away from the densest verified scene motion.

    This is a layout decision over already-authored scene coordinates. It does
    not inspect topics or map concepts to scripted visual stories.
    """

    if not beats:
        return "lower_left"
    candidates = {
        "lower_left": (-0.72, -0.72),
        "upper_left": (-0.72, 0.58),
        "upper_right": (0.72, 0.58),
        "lower_center": (0.0, -0.76),
    }
    positions: list[tuple[float, float, float]] = []
    for index, beat in enumerate(beats):
        raw_position = beat.get("position")
        if isinstance(raw_position, list) and len(raw_position) >= 2:
            x = float(raw_position[0] or 0.0)
            y = float(raw_position[1] or 0.0)
        else:
            x, y = _position_for_phrase(str(beat.get("prompt") or ""), index)[:2]
        weight = 1.0
        if beat.get("op") in {"move", "focus_camera"}:
            weight = 1.45
        positions.append((x, y, weight))

    def score(anchor: str, target: tuple[float, float]) -> float:
        target_x, target_y = target
        crowding = 0.0
        for x, y, weight in positions:
            distance = max(0.08, ((x - target_x) ** 2 + (y - target_y) ** 2) ** 0.5)
            crowding += weight / distance
        # Keep lower-left as the conversational default when the scene is
        # spatially balanced, but let crowded coordinates override it.
        bias = 0.0 if anchor == "lower_left" else 0.35 if anchor == "lower_center" else 0.55
        return crowding + bias

    return min(candidates, key=lambda anchor: score(anchor, candidates[anchor]))


def _scene_layout_intent_for_beats(beats: list[dict[str, Any]]) -> str:
    """Infer the dashboard layout from scene geometry, not from topic labels."""

    if not beats:
        return "balanced_scene"
    if any(beat.get("semantic_role") == "user_visual_intent" for beat in beats):
        return "wide_particle_stage"
    points: list[tuple[float, float]] = []
    motion_count = 0
    for index, beat in enumerate(beats):
        raw_position = beat.get("position")
        if isinstance(raw_position, list) and len(raw_position) >= 2:
            points.append((float(raw_position[0] or 0.0), float(raw_position[1] or 0.0)))
        else:
            x, y = _position_for_phrase(str(beat.get("prompt") or ""), index)[:2]
            points.append((x, y))
        motion_path = beat.get("motion_path")
        if isinstance(motion_path, dict):
            motion_count += 1
            for key in ("from", "to"):
                raw_path_point = motion_path.get(key)
                if isinstance(raw_path_point, list) and len(raw_path_point) >= 2:
                    points.append((float(raw_path_point[0] or 0.0), float(raw_path_point[1] or 0.0)))
    if not points:
        return "balanced_scene"
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    spread_x = max(xs) - min(xs)
    spread_y = max(ys) - min(ys)
    if len(beats) >= 4 or motion_count >= 1 or spread_x >= 0.72 or spread_y >= 0.52:
        return "wide_particle_stage"
    return "balanced_scene"


# UTF-8 Korean extraction layer.
#
# Earlier planner stages are deliberately conservative: the renderer may not
# infer "gravity means apple tree" from a topic.  These overrides keep that
# contract while repairing Korean evidence extraction so only nouns and motion
# cues that are already present in the verified sentence become visual beats.
ANCHOR_STOPWORDS = {
    "therefore", "a", "an", "and", "are", "as", "associated", "however", "because",
    "event", "explain", "first", "for", "from", "helped", "is", "of", "on", "sat",
    "the", "second", "third", "to", "toward", "under", "with",
    "그리고", "그러나", "하지만", "또한", "이는", "그", "그것", "이것", "저것",
    "것", "수", "때", "중", "관련", "현상", "사건", "단서", "설명",
}
KOREAN_SUFFIXES = (
    "으로는", "로는", "으로", "에서", "에게", "에는", "이다", "입니다", "하고", "까지",
    "부터", "처럼", "보다", "이나", "거나", "은", "는", "이", "가", "을", "를", "에", "의", "로",
)
MOTION_CUES = {
    "fall", "falls", "falling", "fell", "move", "moves", "moving", "orbit", "orbits",
    "rotate", "rotates", "attract", "attracts", "pull", "pulls", "drop", "drops",
    "떨어", "떨어지", "낙하", "이동", "끌리", "당기", "작용", "향하", "내려", "움직",
}
KOREAN_ORGANIC_TERMS = ("사과나무", "나무", "숲", "가지", "잎", "식물")
KOREAN_SMALL_OBJECT_TERMS = ("사과", "과일", "돌", "공", "물체", "질량")
KOREAN_FIGURE_CONTEXT_TERMS = ("머리", "사람", "인물", "학자", "관찰", "뉴턴")
RELATION_CUES = {
    "formulated", "discovered", "defined", "called", "known", "means", "is", "are",
    "발견", "정의", "기술", "설명", "불리", "관찰", "관련", "의미",
}


def _canonical_track_phrase(value: str) -> str:
    clean = _clean_phrase(value, limit=96).casefold()
    clean = re.sub(r"\b(?:a|an|the)\s+", "", clean)
    clean = re.sub(r"[^0-9a-z가-힣\s-]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean or "scene-object"


def _fact_units(fact: str) -> list[str]:
    """Split verified evidence into scene-sized units without topic templates."""

    clean = _clean_phrase(fact, limit=420)
    if not clean:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+|[;；]\s*", clean)
    units = [_clean_phrase(part, limit=180) for part in parts if _clean_phrase(part, limit=180)]
    return units[:4] or [clean[:180]]


def _entity_spans(text: str) -> list[str]:
    """Extract only text-local anchors from Korean/English verified evidence."""

    spans: list[str] = []
    for term in (*KOREAN_ORGANIC_TERMS, *KOREAN_SMALL_OBJECT_TERMS):
        if term in text:
            spans.append(term)
    if "아이작 뉴턴" in text:
        spans.append("아이작 뉴턴")
    elif "뉴턴" in text:
        spans.append("뉴턴")
    for match in re.finditer(r"([가-힣A-Za-z]{2,}(?:\s+[가-힣A-Za-z]{2,}){0,2})(?=(?:은|는|이|가|을|를|에서|에게|으로|로|와|과|,|\.|\s|$))", text):
        candidate = _clean_phrase(match.group(1), limit=72)
        if candidate:
            spans.append(candidate)
    for match in re.finditer(r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,})){0,3}\b", text):
        spans.append(match.group(0))

    cleaned: list[str] = []
    for span in spans:
        tokens = [_normalize_anchor_token(token) for token in span.split()]
        tokens = [
            token
            for token in tokens
            if token and token.casefold() not in ANCHOR_STOPWORDS and len(token) >= 2
        ]
        if tokens:
            cleaned.append(_clean_phrase(" ".join(tokens[:3]), limit=72))

    deduped: list[str] = []
    seen: set[str] = set()
    for span in cleaned:
        key = span.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(span)
    return deduped[:4]


def _motion_participants(narration: str) -> dict[str, str]:
    """Extract motion subject/source/target from verified wording only."""

    participants = {"subject": "", "source": "", "target": ""}
    clean = _clean_phrase(narration, limit=240)
    if not _has_any_cue(clean, MOTION_CUES):
        return participants

    source_match = re.search(r"([가-힣A-Za-z]{1,20}나무|[가-힣A-Za-z]{1,20}숲|[가-힣A-Za-z]{1,20}가지)\s*(?:에서|로부터|부터|밑에)", clean)
    if source_match:
        participants["source"] = _clean_phrase(_normalize_anchor_token(source_match.group(1)), limit=72)
    english_source_match = re.search(
        r"\bfrom\s+(?:a|an|the)?\s*([A-Za-z][A-Za-z -]{1,44}?)(?=\s+(?:toward|towards|to|into|onto)\b|[,.;]|$)",
        clean,
        re.IGNORECASE,
    )
    if english_source_match and not participants["source"]:
        participants["source"] = _clean_phrase(_normalize_anchor_token(english_source_match.group(1)), limit=72)

    target_match = re.search(r"([가-힣A-Za-z]{1,20})(?:의\s*)?머리(?:\s*(?:위|쪽|로|에|에게))?", clean)
    if target_match:
        participants["target"] = _clean_phrase(_normalize_anchor_token(target_match.group(1)), limit=72)
    direction_match = re.search(r"(?:쪽으로|향해|에게|으로|로)\s*([가-힣A-Za-z]{2,})", clean)
    if direction_match and not participants["target"]:
        participants["target"] = _clean_phrase(_normalize_anchor_token(direction_match.group(1)), limit=72)
    english_target_match = re.search(
        r"\b(?:toward|towards|to|into|onto)\s+(?:a|an|the)?\s*([A-Za-z][A-Za-z -]{1,44}?)(?=[,.;]|$)",
        clean,
        re.IGNORECASE,
    )
    if english_target_match and not participants["target"]:
        participants["target"] = _clean_phrase(_normalize_anchor_token(english_target_match.group(1)), limit=72)

    subject_patterns = [
        r"([가-힣A-Za-z]{1,20})(?:이|가|은|는)\s+(?:[가-힣A-Za-z]{1,20}(?:에서|로부터|부터|밑에)\s+)?(?:떨어|떨어지|낙하|이동|끌리|내려|움직)",
        r"([가-힣A-Za-z]{1,20})\s*떨어지",
        r"\b(?:an?|the)?\s*([A-Za-z][A-Za-z -]{1,44}?)\s+(?:fell|falls|falling|dropped|drops|moving|moved|moves)\b",
    ]
    for pattern in subject_patterns:
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            candidate = _clean_phrase(_normalize_anchor_token(match.group(1)), limit=72)
            if candidate not in {"현상", "장면", "사건"}:
                participants["subject"] = candidate
                break

    if not participants["source"]:
        participants["source"] = next((term for term in KOREAN_ORGANIC_TERMS if term in clean), "")
    if not participants["subject"]:
        participants["subject"] = next((term for term in KOREAN_SMALL_OBJECT_TERMS if term in clean), "")
    if not participants["target"]:
        anchors = _entity_spans(clean)
        participants["target"] = next((anchor for anchor in anchors if _looks_like_korean_figure(anchor, clean) or _looks_like_english_figure(anchor, clean)), "")
    return participants


def _looks_like_korean_figure(phrase: str, narration: str) -> bool:
    if not re.search(r"[가-힣]", phrase):
        return False
    folded_phrase = phrase.casefold()
    if any(term in folded_phrase for term in (*KOREAN_ORGANIC_TERMS, *KOREAN_SMALL_OBJECT_TERMS)):
        return False
    if any(term in narration for term in KOREAN_FIGURE_CONTEXT_TERMS):
        return True
    tokens = re.findall(r"[가-힣]{2,}", phrase)
    return len(tokens) >= 2 and len(phrase) <= 18


def _spatial_relation_for_phrase(phrase: str, narration: str, visual_affordance: str, op: str) -> str:
    folded = f" {narration.casefold()} "
    has_under_cue = " under " in folded or " beneath " in folded or " below " in folded or "밑" in narration or "아래" in narration
    has_upper_cue = "위" in narration or "위로" in narration or "머리" in narration
    if has_under_cue:
        if visual_affordance == "entity_figure":
            return "under_target"
        if visual_affordance == "organic_structure":
            return "over_anchor"
        if visual_affordance in {"small_object", "small_moving_object"}:
            return "upper_attachment"
    if has_upper_cue and visual_affordance in {"small_object", "small_moving_object"}:
        return "upper_attachment"
    if op == "move" or " toward " in folded or " towards " in folded or "쪽으로" in narration or "향해" in narration:
        if visual_affordance in {"small_object", "small_moving_object"}:
            return "path_object"
        if visual_affordance == "entity_figure":
            return "motion_target"
        if visual_affordance == "organic_structure":
            return "motion_source"
    return ""


def _motion_path_for_unit(unit: dict[str, Any], *, index: int) -> dict[str, Any]:
    narration = unit["narration"]
    if not _has_any_cue(narration, MOTION_CUES):
        return {}
    participants = _motion_participants(narration)
    source_prompt = participants["source"]
    target_prompt = participants["target"]
    anchors = _entity_spans(narration)
    known_anchors = unit.get("known_anchors") if isinstance(unit.get("known_anchors"), list) else _entity_spans(unit.get("source_fact", ""))
    if not source_prompt:
        source_prompt = next(
            (
                anchor
                for anchor in known_anchors
                if _visual_affordance_for_phrase(anchor, narration, "verified_motion_context", "morph") == "organic_structure"
            ),
            "",
        )
    if not target_prompt:
        target_prompt = next((anchor for anchor in anchors if _visual_affordance_for_phrase(anchor, narration, "verified_motion_context", "morph") == "entity_figure"), "")
    if not source_prompt and len(anchors) >= 2:
        source_prompt = anchors[-2]
    if not target_prompt and anchors:
        target_prompt = anchors[-1]
    source_prompt = _expand_known_anchor(source_prompt, known_anchors)
    target_prompt = _expand_known_anchor(target_prompt, known_anchors)
    if not source_prompt or not target_prompt or source_prompt.casefold() == target_prompt.casefold():
        return {}
    source_affordance = _visual_affordance_for_phrase(source_prompt, narration, "verified_motion_context", "morph")
    target_affordance = _visual_affordance_for_phrase(target_prompt, narration, "verified_motion_context", "morph")
    source_relation = _spatial_relation_for_phrase(source_prompt, narration, source_affordance, "morph")
    target_relation = _spatial_relation_for_phrase(target_prompt, narration, target_affordance, "morph")
    return {
        "from": _position_for_unit(source_prompt, index + 37, source_affordance, source_relation or "motion_source"),
        "to": _position_for_unit(target_prompt, index + 73, target_affordance, target_relation or "motion_target"),
        "basis": "verified_motion_phrase",
        "source_prompt": source_prompt,
        "target_prompt": target_prompt,
    }


def _particle_behavior_for_unit(unit: dict[str, Any], visual_affordance: str, op: str, motion_path: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Attach renderer-facing physics hints from verified wording only."""

    narration = unit.get("narration", "")
    folded = narration.casefold()
    has_motion = bool(motion_path) or op == "move" or "motion" in str(unit.get("semantic_role", ""))
    gravity_cues = (
        "fall", "falling", "fell", "drop", "dropped", "toward", "towards",
        "떨어", "낙하", "끌리", "쪽으로", "향해", "당기", "내려",
    )
    if has_motion and any(cue in folded for cue in gravity_cues):
        return "gravity_arc", {
            "basis": "verified_motion_phrase",
            "field": "downward_attraction",
            "material": "dense_moving_splat",
            "gravity_bias": 0.72,
            "cohesion": 0.64,
            "trail": 0.86,
        }
    if has_motion:
        return "kinetic_flow", {
            "basis": "verified_motion_phrase",
            "field": "directed_flow",
            "material": "energized_splat",
            "gravity_bias": 0.28,
            "cohesion": 0.58,
            "trail": 0.72,
        }
    if visual_affordance == "organic_structure":
        return "rooted_growth", {
            "basis": "verified_visual_affordance",
            "field": "branching_cohesion",
            "material": "organic_splat",
            "gravity_bias": 0.18,
            "cohesion": 0.82,
            "trail": 0.22,
        }
    if visual_affordance == "entity_figure":
        return "articulated_cluster", {
            "basis": "verified_visual_affordance",
            "field": "pose_cohesion",
            "material": "figure_splat",
            "gravity_bias": 0.24,
            "cohesion": 0.76,
            "trail": 0.28,
        }
    if visual_affordance in {"relation_field", "concept_cloud"}:
        return "magnetic_field", {
            "basis": "verified_relation_or_concept",
            "field": "swarm_relation",
            "material": "field_splat",
            "gravity_bias": 0.0,
            "cohesion": 0.42,
            "trail": 0.54,
        }
    return "bounded_swarm", {
        "basis": "verified_scene_unit",
        "field": "bounded_swarm",
        "material": "neutral_splat",
        "gravity_bias": 0.12,
        "cohesion": 0.56,
        "trail": 0.34,
    }


def plan_visual_imagination(
    question: str,
    *,
    route: ConversationRoute,
    grounded_context: GroundedContext,
    diagnostics: dict[str, Any],
    answer_available: bool,
    client_layout_feedback: dict[str, Any] | None = None,
) -> VisualImaginationPlan:
    """Plan whether the response may use SPLATRA without inventing scene content.

    The planner is content-conservative. It can ask the dashboard for a larger
    visual stage and convert grounded facts into entity/action beats, but it
    does not encode subject templates or final answers.
    """

    route_type = route.route_type
    grounding_quality = grounded_context.grounding_quality
    can_visualize = (
        answer_available
        and route_type in VISUAL_ROUTE_TYPES
        and diagnostics.get("external_llm_used") is False
        and diagnostics.get("external_sllm_used") is False
        and diagnostics.get("rule_based_answer_used") is False
    )
    if route_type == "general_knowledge_question" and grounding_quality in {"none", "low"}:
        can_visualize = False
    if not can_visualize:
        return VisualImaginationPlan(
            enabled=False,
            reason="no_grounded_visual_plan_available",
            scene_choreography=None,
            diagnostics={
                "visual_imagination_planner": "cgsr_visual_imagination_v1",
                "route_type": route_type,
                "grounding_quality": grounding_quality,
                "topic_scene_templates": False,
                "renderer_may_infer_topic": False,
                "particle_text": False,
                "text_rendering": "dom_text_not_particles",
                "scene_content_source": "none",
                "scene_authoring_basis": "abstained_no_verified_visual_evidence",
                "reason": "no_grounded_visual_plan_available",
            },
        )

    scene_units = _scene_units(question, route_type=route_type, grounded_context=grounded_context)
    direct_user_visual_intent = bool(scene_units) and all(
        unit.get("semantic_role") == "user_visual_intent" for unit in scene_units
    )
    if not direct_user_visual_intent and not _scene_units_have_concrete_visual_grounding(scene_units):
        return VisualImaginationPlan(
            enabled=False,
            reason="insufficient_concrete_visual_evidence",
            scene_choreography=None,
            diagnostics={
                "visual_imagination_planner": "cgsr_visual_imagination_v1",
                "route_type": route_type,
                "grounding_quality": grounding_quality,
                "topic_scene_templates": False,
                "renderer_may_infer_topic": False,
                "particle_text": False,
                "text_rendering": "dom_text_not_particles",
                "scene_content_source": "none",
                "scene_authoring_basis": "abstained_abstract_or_nonvisual_evidence",
                "visual_affordance_basis": "source_phrase_affordance_extraction_no_topic_template",
                "reason": "insufficient_concrete_visual_evidence",
            },
        )
    if len(scene_units) == 1 and scene_units[0].get("semantic_role") != "user_visual_intent":
        scene_units = [
            scene_units[0],
            {
                **scene_units[0],
                "semantic_role": "visual_focus",
                "speech_cue": False,
                "speech_cue_basis": "visual_anchor_only",
                "scene_group_role": "visual_anchor",
            },
        ]
    beats: list[dict[str, Any]] = []
    t_start = 0.0
    for index, unit in enumerate(scene_units):
        op = _scene_op_for_scene_unit(unit, index=index, is_last=index == len(scene_units) - 1 and index > 0)
        duration = _beat_duration_for_unit(unit, op)
        beats.append(_make_scene_beat(unit, index=index, op=op, t_start=t_start, duration=duration))
        role = str(unit.get("semantic_role") or "")
        if op != "move" and role in {"verified_motion_event", "verified_motion_subject"} and _has_any_cue(unit["narration"], MOTION_CUES):
            move_duration = _beat_duration_for_unit(unit, "move")
            beats.append(_make_scene_beat(unit, index=index, op="move", t_start=t_start + duration * 0.42, duration=move_duration))
            t_start += max(duration, duration * 0.42 + move_duration) + 0.16
        else:
            t_start += duration + 0.16
    if not beats:
        return VisualImaginationPlan(
            enabled=False,
            reason="empty_visual_phrases",
            scene_choreography=None,
            diagnostics={
                "visual_imagination_planner": "cgsr_visual_imagination_v1",
                "route_type": route_type,
                "grounding_quality": grounding_quality,
                "topic_scene_templates": False,
                "renderer_may_infer_topic": False,
                "particle_text": False,
                "text_rendering": "dom_text_not_particles",
                "scene_content_source": "none",
                "scene_authoring_basis": "abstained_empty_visual_phrases",
                "reason": "empty_visual_phrases",
            },
        )

    choreography = compile_scene_choreography(
        {
            "stage_layout": "scene_focus",
            "orb_anchor": "lower_right",
            "text_anchor": _text_anchor_for_beats(beats),
            "layout_intent": _scene_layout_intent_for_beats(beats),
            "primary_surface": "splatra_stage",
            "beats": beats,
            "client_layout_feedback": client_layout_feedback or {},
        }
    ).to_dict()
    return VisualImaginationPlan(
        enabled=True,
        reason="grounded_visual_affordance",
        scene_choreography=choreography,
        diagnostics={
            "visual_imagination_planner": "cgsr_visual_imagination_v1",
            "route_type": route_type,
            "grounding_quality": grounding_quality,
            "topic_scene_templates": False,
            "renderer_may_infer_topic": False,
            "particle_text": False,
            "text_rendering": "dom_text_not_particles",
            "scene_content_source": "user_visual_intent_only" if direct_user_visual_intent else "verified_store_facts" if grounded_context.facts else "user_visual_intent_only",
            "scene_authoring_basis": "user_direct_splatra_generation_request" if direct_user_visual_intent else "verified_fact_entity_action_extraction",
            "visual_affordance_basis": "source_phrase_affordance_extraction_no_topic_template",
            "layout_decision_basis": "verified_scene_geometry_and_client_feedback",
            "client_layout_feedback_used": bool(client_layout_feedback),
            "beats": len(beats),
            "source": "grounded_context_or_user_surface",
        },
    )
