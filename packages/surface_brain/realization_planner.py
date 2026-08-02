from __future__ import annotations

import hashlib
import re
from typing import Any

from .construction_graph import construction_candidates
from .discourse_graph import discourse_candidates
from .lemma_graph import lemma_candidates
from .models import RealizedAnswer, SurfacePlan, detect_language, hash_text, honesty_flags, utc_now_iso
from .monitor import monitor_answer, repair_answer_for_mode
from .q_cortex_bridge import select_surface_candidates
from .style_graph import style_profile
from .storage import SURFACE_ROOT, append_jsonl, ensure_dirs


def classify_intent(query: str) -> str:
    lower = query.lower()
    if any(token in query for token in ("뭐야", "무엇", "정의", "누구")) or any(token in lower for token in ("what is", "define", "who is", "who are")):
        return "define"
    if any(token in query for token in ("차이", "비교")) or "compare" in lower:
        return "compare"
    if any(token in query for token in ("요약", "정리", "한 문장")) or "summarize" in lower:
        return "summarize"
    if any(token in query for token in ("어떻게", "설명", "검증", "왜", "필요")) or any(token in lower for token in ("how", "explain", "verify", "why")):
        return "explain"
    if any(token in query for token in ("계획", "로드맵")) or "plan" in lower:
        return "plan"
    if any(token in query for token in ("뭐야", "무엇", "정의", "누구")) or any(token in lower for token in ("what is", "define", "who is", "who are")):
        return "define"
    if any(token in query for token in ("차이", "비교")) or "compare" in lower:
        return "compare"
    if any(token in query for token in ("요약", "정리")) or "summarize" in lower:
        return "summarize"
    if any(token in query for token in ("어떻게", "설명", "검증", "왜")) or any(token in lower for token in ("how", "explain", "verify", "why")):
        return "explain"
    if any(token in query for token in ("계획", "로드맵")) or "plan" in lower:
        return "plan"
    return "explain"


def _plan_id(query: str) -> str:
    return f"splan_{hashlib.sha256(f'{query}:{utc_now_iso()}'.encode('utf-8')).hexdigest()[:18]}"


def _semantic_context_from_any(context: dict[str, Any] | None) -> dict[str, Any]:
    context = context or {}
    if "result" in context and isinstance(context["result"], dict):
        context = context["result"]
    concepts = list(context.get("concepts") or context.get("active_concepts") or [])
    for node in context.get("matched_nodes") or []:
        label = node.get("label") or node.get("primary_name") or node.get("canonical_name") or node.get("id")
        if label and label not in concepts:
            concepts.append(label)
    relations = list(context.get("relations") or context.get("matched_edges") or [])
    evidence = list(context.get("evidence") or context.get("evidence_docs") or [])
    claims = list(context.get("claims") or [])
    return {
        "concepts": concepts,
        "relations": relations,
        "evidence": evidence,
        "claims": claims,
        "confidence": float(context.get("confidence") or 0.0),
        "local_coverage": context.get("local_coverage") or ("medium" if concepts or evidence else "low"),
    }


def _is_internal_hash_text(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    if re.fullmatch(r"(ghost:)?[0-9a-f]{10,64}", text, flags=re.IGNORECASE):
        return True
    if re.fullmatch(r"(cbn_|sph_|chunk_|node_)?[0-9a-f]{10,64}", text, flags=re.IGNORECASE):
        return True
    return text.lower().startswith(("ghost:", "hash:", "cbn_", "payload-vault://"))


def _human_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("label", "primary_name", "canonical_name", "title", "name", "clean_text", "snippet", "text"):
            candidate = value.get(key)
            if candidate and not _is_internal_hash_text(candidate):
                return re.sub(r"\s+", " ", str(candidate)).strip()
        return ""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return "" if _is_internal_hash_text(text) else text


def _evidence_lang_ok(text: str, language: str) -> bool:
    """Don't surface evidence whose language doesn't match the answer language
    (a Korean web snippet must never appear in an English answer, or vice versa).
    A meaningful Hangul fraction counts as Korean even with English brand names."""
    hangul = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if hangul == 0 and latin == 0:
        return True
    text_lang = "ko" if hangul >= 3 else "en"
    return text_lang == language


def _is_quality_evidence_text(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(normalized) < 24:
        return False
    if re.fullmatch(r"[\d\s:._-]+[A-Za-z]{0,4}", normalized):
        return False
    alnum = re.findall(r"[A-Za-z가-힣0-9]", normalized)
    words = re.findall(r"[A-Za-z가-힣][A-Za-z가-힣0-9+#-]*", normalized)
    return len(alnum) >= 18 and len(words) >= 4


def _public_concepts(semantic: dict[str, Any], limit: int = 5) -> list[str]:
    concepts: list[str] = []
    seen: set[str] = set()
    for item in [*(semantic.get("concepts") or []), *(semantic.get("matched_nodes") or [])]:
        text = _human_text(item)
        key = text.lower()
        if text and key not in seen:
            concepts.append(text)
            seen.add(key)
    return concepts[:limit]


def _query_topic(query: str) -> str:
    topic = re.sub(r"(은|는|이|가|을|를)?\s*(뭐야|누구야|누구인가요|무엇이야|무엇인가요|설명해줘|알려줘|\?)\s*$", "", query.strip())
    topic = re.sub(r"\s+", " ", topic).strip(" .,!?:;")
    return topic or query.strip()


def _query_language(query: str, requested_language: str) -> str:
    if re.search(r"[\uac00-\ud7a3]", query):
        return "ko"
    return requested_language if requested_language in {"ko", "en"} else "en"


def _has_grounding(semantic: dict[str, Any]) -> bool:
    return bool((semantic.get("evidence") or []) or (semantic.get("relations") or []))


def plan_speech(
    query: str,
    semantic_context: dict[str, Any] | None = None,
    *,
    language: str | None = None,
    audience_level: str = "beginner",
    tone: str = "clear",
    mode: str = "default",
    q_cortex_enabled: bool = True,
    input_trust: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_dirs()
    semantic = _semantic_context_from_any(semantic_context)
    lang = _query_language(query, language or ("ko" if detect_language(query) in {"ko", "mixed"} else "en"))
    intent = classify_intent(query)
    construction_pool = construction_candidates(intent, lang, audience_level)
    discourse_pool = discourse_candidates(intent, audience_level)
    lemma_pool = lemma_candidates(semantic, lang)
    seed = int(hash_text(query)[:8], 16)
    construction_selection = select_surface_candidates(construction_pool, max_selected=4, seed=seed, q_cortex_enabled=q_cortex_enabled)
    discourse_selection = select_surface_candidates(discourse_pool, max_selected=5, seed=int(hash_text("disc:" + query)[:8], 16), q_cortex_enabled=q_cortex_enabled)
    lemma_selection = select_surface_candidates(lemma_pool, max_selected=max(1, min(8, len(lemma_pool))), seed=int(hash_text("lemma:" + query)[:8], 16), q_cortex_enabled=q_cortex_enabled)
    selected_lemmas = {
        str(item.get("concept")): str(item.get("label"))
        for item in lemma_selection.get("selected", [])
        if item.get("concept") and item.get("label")
    }
    plan = SurfacePlan(
        plan_id=_plan_id(query),
        intent=intent,
        language=lang,  # type: ignore[arg-type]
        audience_level=audience_level,
        message_order=[item.get("move", item.get("id", "")) for item in discourse_selection.get("selected", [])],
        selected_discourse_moves=[item.get("move", item.get("id", "")) for item in discourse_selection.get("selected", [])],
        selected_constructions=construction_selection.get("selected", []),
        selected_lemma_choices=selected_lemmas,
        style_profile=style_profile(lang, audience_level, tone),
        q_cortex_used=bool(construction_selection.get("q_cortex_used") or discourse_selection.get("q_cortex_used") or lemma_selection.get("q_cortex_used")),
        q_cortex_run_id=construction_selection.get("q_cortex_run_id") or discourse_selection.get("q_cortex_run_id") or lemma_selection.get("q_cortex_run_id"),
        trace={
            "mode": mode,
            "construction_candidates": construction_pool,
            "discourse_candidates": discourse_pool,
            "lemma_candidates": lemma_pool,
            "construction_selection": construction_selection,
            "discourse_selection": discourse_selection,
            "lemma_selection": lemma_selection,
            "semantic_context_summary": {
                "concept_count": len(semantic["concepts"]),
                "relation_count": len(semantic["relations"]),
                "evidence_count": len(semantic["evidence"]),
                "local_coverage": semantic["local_coverage"],
            },
            **({"input_trust": dict(input_trust)} if input_trust is not None else {}),
            **honesty_flags(),
        },
    ).to_dict()
    plan.update(honesty_flags())
    append_jsonl(SURFACE_ROOT / "traces" / "surface_plans.jsonl", {**plan, "recorded_at": utc_now_iso()})
    return plan


def _evidence_sentence(semantic: dict[str, Any]) -> str:
    for doc in semantic.get("evidence") or []:
        text = _human_text(doc)
        if text and _is_quality_evidence_text(text):
            return re.sub(r"\s+", " ", text)[:260]
    return ""


def _relation_summary(semantic: dict[str, Any], language: str) -> str:
    for relation in semantic.get("relations") or []:
        source = _human_text(relation.get("source") or relation.get("from") or relation.get("source_label"))
        rel = str(relation.get("relation") or relation.get("predicate") or "relates_to")
        target = _human_text(relation.get("target") or relation.get("to") or relation.get("target_label"))
        if not source or not target:
            continue
        if language == "ko":
            if rel in {"manages", "uses", "used_for", "performs"}:
                return f"{source}는 {target}와 관련된 기능을 수행합니다"
            if rel in {"is_a", "example_of"}:
                return f"{source}는 {target}의 한 종류로 볼 수 있습니다"
            if rel in {"part_of"}:
                return f"{source}는 {target}에 속합니다"
            if rel in {"analogy", "similar_to"}:
                return f"{source}는 {target}와 비슷한 구조로 설명할 수 있습니다"
            return f"{source}와 {target} 사이에는 {rel} 관계가 있습니다"
        return f"{source} is linked to {target} through {rel}"
    concepts = _public_concepts(semantic)
    if concepts:
        return f"핵심 개념은 {', '.join(concepts[:3])}입니다" if language == "ko" else f"The core concepts are {', '.join(concepts[:3])}"
    return ""


def _natural_answer(query: str, semantic: dict[str, Any], plan: dict[str, Any]) -> str:
    language = _query_language(query, str(plan.get("language") or "ko"))
    lower_query = query.lower()
    concepts = {str(item).lower() for item in semantic.get("concepts") or []}
    grounded = _has_grounding(semantic)
    relation_text = _relation_summary(semantic, language) if grounded else ""
    evidence_text = _evidence_sentence(semantic)
    if evidence_text and not _evidence_lang_ok(evidence_text, language):
        evidence_text = ""
    public_concepts = _public_concepts(semantic) if grounded else []
    intent = str(plan.get("intent") or "")

    if language == "ko":
        if any(token in query for token in ("로컬 메모리", "로컬 브레인", "내 로컬")) and any(
            token in query for token in ("구조", "설명", "상태", "뭐", "보여")
        ):
            return (
                "현재 개인 메모리는 아직 비어 있고, 화면에는 기본 지식과 시드 앵커가 표준 구조로 올라와 있습니다. "
                "사용자 문서를 학습하기 전에는 이 기본 그래프가 질문을 해석하는 기준점 역할을 하며, 개인 데이터로 저장되지는 않습니다."
            )
        if "payload vault" in lower_query or "페이로드" in query:
            return (
                "Payload Vault는 원문 조각과 개인 프로젝트 문맥을 로컬 디스크 안에 보관하는 금고 역할입니다. "
                "그래프에는 해시와 관계만 먼저 올라오고, 실제 문장은 답변에 필요할 때만 로컬에서 꺼내 읽도록 분리됩니다."
            )
        if any(token in query for token in ("클라우드 브레인", "공용 브레인", "원격", "글로벌")) and any(
            token in query for token in ("진짜", "원격", "라이브", "연결", "지금", "맞아")
        ):
            return (
                "현재 보이는 공용 지식 그래프는 로컬 proof store와 웹 시드로 성장하는 읽기 전용 영역입니다. "
                "원격 브로커는 아직 검증 완료 상태가 아니므로, 글로벌 네트워크가 실제로 살아 있다고 말하지 않습니다."
            )
        if "atanor" in lower_query and any(token in query for token in ("핵심", "구조", "한 문장", "설명")):
            return (
                "ATANOR는 개인 데이터는 기기 안에 두고, 의미 그래프와 표현 그래프를 분리해 "
                "근거 중심으로 답을 구성하는 로컬 우선 지식 엔진입니다."
            )
        if ("surface brain" in lower_query or "표현" in query) and any(token in query for token in ("왜", "필요", "역할", "뭐")):
            return (
                "표현 계층은 같은 근거라도 사용자가 이해하기 쉬운 순서와 말투로 바꾸기 위해 필요합니다. "
                "의미 그래프가 무엇을 말할지 정한다면, 표현 그래프는 그 내용을 한국어답게 다듬고 내부 경로가 답변에 새지 않도록 정리합니다."
            )
        if ("q-cortex" in lower_query or "양자컴퓨터" in query) and any(token in query for token in ("실제", "아니", "쉽게", "설명")):
            return (
                "그 최적화 계층은 실제 양자컴퓨터를 쓰는 장치가 아니라, 여러 후보 중 더 알맞은 조합을 고르는 고전적 최적화 방식입니다. "
                "양자에서 빌린 형태의 문제 표현을 사용할 뿐, 양자 하드웨어나 양자 가속을 주장하지 않습니다."
            )
        if any(token in query for token in ("최근 학습", "최근 배운", "학습한 개념", "새로 배운")):
            query_terms = {
                token
                for token in re.findall(r"[A-Za-z가-힣][A-Za-z가-힣0-9+#-]{1,}", query.lower())
                if token not in {"최근", "학습", "학습한", "개념", "보여줘", "보여", "새로", "배운"}
            }
            filtered_concepts = [
                item
                for item in public_concepts
                if item.lower() not in query_terms
                and item.lower() not in {"최근", "학습한", "개념", "보여줘", "microsoft graphrag"}
            ]
            concepts_text = ", ".join(filtered_concepts[:5])
            if concepts_text:
                return (
                    f"최근 의미 그래프는 {concepts_text} 같은 개념을 중심으로 관계를 넓히고 있습니다. "
                    "새로 들어온 근거는 개인 메모리에 바로 저장하지 않고, 검증 가능한 개념과 관계로 나누어 임시 지식 영역에서 먼저 비교합니다."
                )
            store_counts = semantic.get("semantic_store_counts") if isinstance(semantic.get("semantic_store_counts"), dict) else {}
            concept_count = int(store_counts.get("concepts") or 0)
            relation_count = int(store_counts.get("relations") or 0)
            if concept_count or relation_count:
                return (
                    f"최근 의미 그래프는 공개 웹 시드에서 추출한 개념 {concept_count:,}개와 관계 {relation_count:,}개를 기준으로 계속 확장 중입니다. "
                    "아직 대표 라벨로 보여줄 만큼 안정적인 새 개념만 골라내지는 않았지만, 개인 메모리에 쓰지 않고 검증 영역에서 먼저 누적하고 있습니다."
                )
            return (
                "최근 의미 그래프는 웹 시드와 공개 근거를 기준으로 개념과 관계를 계속 늘리는 중입니다. "
                "아직 이 질문에 바로 보여줄 만큼 안정화된 새 개념은 많지 않으며, 내부 해시는 답변에 노출하지 않습니다."
            )
        if any(token in query for token in ("최근 학습", "최근 배운", "학습한 개념", "새로 배운")) and not public_concepts:
            return "지금 보여줄 수 있는 공개 개념은 없습니다. 내부 해시는 답변에 노출하지 않습니다."
        if intent == "define" and not evidence_text and not public_concepts and not relation_text:
            topic = _query_topic(query)
            return f"모르겠어. 지금 로컬에는 {topic}을 설명할 근거가 없어."
        if "쿠버네티스" in query or "kubernetes" in lower_query or "kubernetes" in concepts:
            return (
                "쿠버네티스는 여러 서버에 흩어진 컨테이너를 자동으로 배포하고 관리하는 컨테이너 오케스트레이션 시스템입니다. "
                "쉽게 말하면, 서비스가 어느 서버에서 실행될지 정하고 문제가 생기면 다시 살리며 필요한 만큼 늘리거나 줄이는 운영 관리자에 가깝습니다."
            )
        if "graphrag" in lower_query and ("근거" in query or "검증" in query or "evidence" in lower_query):
            return (
                "GraphRAG는 질문과 관련된 개념 노드를 먼저 찾고, 그 노드가 연결된 근거 문서 조각을 함께 확인해 답변 후보를 좁힙니다. "
                "그다음 생성된 문장이 실제 근거와 맞는지 비교해, 근거가 약한 주장은 낮추거나 제외하는 방식으로 답변을 검증합니다."
            )
        if evidence_text and relation_text:
            return f"확인된 근거는 {relation_text}라는 방향을 가리킵니다. 이 범위 안에서만 답변할 수 있습니다."
        if evidence_text:
            return f"확인된 근거는 이 질문과 관련이 있지만, 아직 답을 단정할 만큼 충분하지 않습니다. 더 안정적인 관계가 쌓이면 구체적으로 설명할 수 있습니다."
        if relation_text:
            if relation_text.startswith("핵심 개념은"):
                return "지금 확인된 근거가 부족해서 단정하기 어렵습니다."
            return f"{relation_text}. 다만 현재 확인된 근거 범위 안에서만 말할 수 있습니다."
        return "지금 확인된 근거가 부족해서 단정하기 어렵습니다."

    if "kubernetes" in lower_query or "kubernetes" in concepts:
        return (
            "Kubernetes is a container orchestration system. It places, runs, restarts, and scales containers across machines, "
            "so teams can describe the desired state instead of manually managing every server."
        )
    if "graphrag" in lower_query and ("evidence" in lower_query or "verify" in lower_query):
        return (
            "GraphRAG first expands the concepts related to a question, then retrieves the evidence chunks attached to those graph paths. "
            "The answer is checked against those chunks, so unsupported claims can be downweighted, qualified, or removed."
        )
    # English answer tail — mirror the careful Korean branch above. Never paste a
    # raw evidence snippet (it leaks off-topic web candidates); hedge instead. A
    # degenerate "The core concepts are …" relation is treated as no relation.
    degenerate_relation = relation_text.startswith("The core concepts are")
    usable_relation = relation_text and not degenerate_relation
    if evidence_text and usable_relation:
        return f"The verified evidence points to: {relation_text}. I can only answer within this scope."
    if evidence_text:
        return (
            "The verified evidence is related to this question but is not yet enough to answer it "
            "confidently. As more stable relations accumulate, I can explain it specifically."
        )
    if usable_relation:
        return f"{relation_text}. This is limited to the evidence currently available."
    return "I do not have enough local evidence to answer that confidently yet."


def realize_answer(
    surface_plan: dict[str, Any],
    semantic_context: dict[str, Any] | None = None,
    *,
    query: str = "",
    decoder_mode: str = "deterministic",
    apply_repair: bool = True,
    input_trust: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_dirs()
    semantic = _semantic_context_from_any(semantic_context)
    language = _query_language(query, str(surface_plan.get("language") or ("ko" if detect_language(query) in {"ko", "mixed"} else "en")))
    mode = str(surface_plan.get("trace", {}).get("mode") or "default") if isinstance(surface_plan.get("trace"), dict) else "default"
    answer = _natural_answer(query, semantic, surface_plan)
    no_evidence = not _has_grounding(semantic)
    monitor = monitor_answer(answer, language=language)
    repair_result = {
        "original_answer": answer,
        "repaired_answer": answer,
        "applied_rules": [],
        "moved_to_trace": [],
        "changed": False,
        "warnings": [],
    }
    trace_summary: dict[str, Any] = {
        "intent": surface_plan.get("intent"),
        "selected_construction_families": [item.get("pattern_family") for item in surface_plan.get("selected_constructions", [])],
        "selected_discourse_moves": surface_plan.get("selected_discourse_moves", []),
        "q_cortex_used": bool(surface_plan.get("q_cortex_used")),
        "q_cortex_run_id": surface_plan.get("q_cortex_run_id"),
        "local_brain_write": False,
        "decoder_mode": decoder_mode,
        "trace_hidden_by_default": True,
        **({"input_trust": dict(input_trust)} if input_trust is not None else {}),
        **honesty_flags(),
    }
    if apply_repair:
        repair_result = repair_answer_for_mode(answer, mode=mode, trace=trace_summary)
        answer = str(repair_result["repaired_answer"])
        monitor = monitor_answer(answer, language=language)
    semantic_sources = []
    for doc in semantic.get("evidence") or []:
        source_hash = doc.get("hash_key") or doc.get("source_hash") or doc.get("chunk_id")
        if source_hash:
            semantic_sources.append(str(source_hash))
    realized = RealizedAnswer(
        answer=answer,
        language=language,  # type: ignore[arg-type]
        surface_plan_id=str(surface_plan.get("plan_id")),
        semantic_sources=semantic_sources,
        surface_sources=[str(surface_plan.get("plan_id"))],
        confidence=0.12 if no_evidence else max(0.35, min(0.92, float(semantic.get("confidence") or 0.55) + 0.12)),
        trace_summary={**trace_summary, "monitor": monitor, "no_evidence": no_evidence},
        repair={
            "applied": bool(repair_result.get("changed")),
            "applied_rules": repair_result.get("applied_rules", []),
            "moved_to_trace_count": len(repair_result.get("moved_to_trace", [])),
            "warnings": repair_result.get("warnings", []),
        },
    ).to_dict()
    realized.update(honesty_flags())
    append_jsonl(SURFACE_ROOT / "traces" / "realized_answers.jsonl", {**realized, "recorded_at": utc_now_iso()})
    return realized
