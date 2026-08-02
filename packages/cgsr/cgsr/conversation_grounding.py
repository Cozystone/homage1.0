from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from packages.cgsr.cgsr.conversation_router import ConversationRoute, ConversationRouteType
from packages.cgsr.cgsr.referent_resonance import select_resonant_facts
from packages.cgsr.cgsr.verified_fact_retrieval import retrieve_verified_facts


HONESTY_NOTE = (
    "ASM-v0 is a local construction-conditioned surface generator, not a general language model."
)


def semantic_safety_flags() -> dict[str, bool]:
    return {
        "external_llm": False,
        "external_sllm": False,
        "external_llm_used": False,
        "external_sllm_used": False,
        "local_brain_write": False,
        "production_store_mutated": False,
        "candidate_promotion": False,
        "raw_hidden_cot_claim": False,
        "consciousness_claim": False,
        "semantic_grounding_metadata_present": True,
        "honesty_metadata_present": True,
    }


@dataclass(frozen=True)
class GroundedContext:
    route_type: ConversationRouteType
    facts: tuple[str, ...]
    constraints: tuple[str, ...]
    unknowns: tuple[str, ...]
    source_refs: tuple[str, ...]
    grounding_source: str
    grounding_quality: str
    safety_flags: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _context(
    route_type: ConversationRouteType,
    *,
    facts: tuple[str, ...] = (),
    constraints: tuple[str, ...] = (),
    unknowns: tuple[str, ...] = (),
    source_refs: tuple[str, ...] = (),
    grounding_source: str = "none",
    grounding_quality: str = "none",
) -> GroundedContext:
    return GroundedContext(
        route_type=route_type,
        facts=facts,
        constraints=constraints,
        unknowns=unknowns,
        source_refs=source_refs,
        grounding_source=grounding_source,
        grounding_quality=grounding_quality,
        safety_flags=semantic_safety_flags(),
    )


def gather_grounded_context(question: str, route: ConversationRoute, runtime: dict[str, Any] | None = None) -> GroundedContext:
    """Collect safe local grounding for product conversation.

    This adapter is read-only. It does not query external LLMs, write Local
    Brain, mutate verified_store_v0, or promote candidates.
    """

    runtime = runtime or {}
    if route.route_type == "greeting_smalltalk":
        return _context(route.route_type, grounding_source="none", grounding_quality="none")
    if route.route_type == "local_cloud_brain_explanation":
        return _context(
            route.route_type,
            facts=(
                "로컬 브레인은 사용자 개인 기억을 다루는 영역이며 승인 게이트 없이는 쓰지 않는다.",
                "클라우드 브레인은 출처와 검증 상태를 가진 공용 지식을 후보와 승격 게이트로 다룬다.",
                "현재 대화 맥락, 로컬 브레인, 클라우드 브레인은 사용자가 승인하기 전까지 분리된다.",
            ),
            constraints=("로컬 브레인 쓰기를 주장하지 않는다.", "후보 승격을 주장하지 않는다."),
            source_refs=("docs/ATANOR_product_conversation_grounding.md", "Local Memory Approval gate"),
            grounding_source="local_state",
            grounding_quality="high",
        )
    if route.route_type == "memory_request":
        return _context(
            route.route_type,
            facts=(
                "기억 쓰기는 명시적 승인을 거쳐야 한다.",
                "이 대화 경로는 기억 후보를 준비할 수 있지만 로컬 브레인에 직접 쓰지 않는다.",
            ),
            constraints=("로컬 브레인에 쓰지 않는다.", "자동 승인하지 않는다."),
            source_refs=("Local Brain memory approval gate",),
            grounding_source="local_brain_redacted",
            grounding_quality="medium",
        )
    if route.route_type == "voice_status":
        return _context(
            route.route_type,
            facts=(
                "텍스트 대화는 사용할 수 있다.",
                "Fish 음성 출력은 선택 기능이며 합성이 연결되지 않으면 텍스트로 계속 응답한다.",
            ),
            constraints=("audio_url이 없으면 실제 음성 재생을 주장하지 않는다.",),
            source_refs=("packages/voice_loop", "voice runtime availability"),
            grounding_source="local_state",
            grounding_quality="medium",
        )
    if route.route_type == "splatra_request":
        return _context(
            route.route_type,
            facts=(
                "SPLATRA는 proof-only 홀로그램/파티클 시각화 계층으로 연결되어 있다.",
                "파티클 형태 변화는 검토된 패치가 승인되기 전까지 UI-local 후보 상태에 머문다.",
                "물리 법칙을 학습하는 파티클과 고급 재질 시뮬레이션은 아직 완료되지 않았다.",
            ),
            constraints=("대화만으로 코드 패치를 적용하지 않는다.",),
            source_refs=("packages/splatra_imagination", "SPLATRA proof-only UI"),
            grounding_source="local_state",
            grounding_quality="medium",
        )
    if route.route_type == "agentic_os_request":
        return _context(
            route.route_type,
            facts=(
                "Agentic Micro-OS와 Hermes 계열 탐색은 리뷰 큐를 통해 초안을 남기는 구조다.",
                "초안은 승인 전까지 pending 상태에 머문다.",
            ),
            constraints=("대화만으로 스킬 설치, 호스트 실행, push, 승격을 수행하지 않는다.",),
            source_refs=("packages/agentic_micro_os", "Agentic Review Queue v0"),
            grounding_source="agentic_runtime_state",
            grounding_quality="medium",
        )
    if route.route_type == "limitation_question":
        return _context(
            route.route_type,
            facts=(
                "이 제품 대화 경로는 외부 LLM이나 sLLM을 쓰지 않고 로컬 ASM/CGSR 구성만 사용합니다.",
                "ASM-v0는 일반 언어모델이 아닙니다. hand-authored construction이 남아 있는 construction-conditioned 표층 생성기입니다.",
                "자기 모델은 현재 상태, 목표, 경계, 제안 후보를 관찰하는 내부 상태 표현입니다.",
                "현재 경로에는 hand-authored construction, 휴리스틱 act 추론, 로컬 transition surface가 남아 있다.",
                "Fish 합성이 연결되지 않으면 음성 경로는 텍스트로 fallback할 수 있다.",
                "SPLATRA 재질 물리와 파티클 학습은 아직 연구/후속 구현 대상이다.",
            ),
            constraints=("자율성, 자의식, AGI, 언어모델 능력을 과장하지 않는다.",),
            source_refs=("packages/cgsr/cgsr/asm_v0.py", "packages/cgsr/cgsr/conversation_constructions.py"),
            grounding_source="local_state",
            grounding_quality="high",
        )
    if route.route_type == "nonsensical_question":
        return _context(
            route.route_type,
            facts=(
                "현실 전제로는 맞지 않습니다.",
                "현실의 고양이는 스스로 하늘을 날 수 없다.",
                "이 전제는 사용자가 이야기 맥락을 주면 허구나 비유로 다룰 수 있다.",
            ),
            constraints=("ATANOR 상태 fallback으로 답하지 않는다.",),
            source_refs=("commonsense_boundary",),
            grounding_source="local_state",
            grounding_quality="medium",
        )
    if route.route_type == "project_status":
        return _context(
            route.route_type,
            facts=(
                "검토 가능한 작업은 명시적 승인 전까지 리뷰 큐에 남아야 한다.",
                "이 대화 경로는 승인 경계를 요약할 수 있지만 live review queue를 읽지 않으면 전체 pending 목록을 단정하지 않는다.",
            ),
            constraints=("구체적인 승인 목록을 지어내지 않는다.",),
            unknowns=("현재 전체 리뷰 큐 내용은 이 라우트에서 없을 수 있다.",),
            source_refs=("Agentic Review Queue v0",),
            grounding_source="review_queue",
            grounding_quality="low",
        )
    if route.route_type == "unsafe_or_private_request":
        return _context(
            route.route_type,
            facts=("비밀값이나 개인 데이터 요청은 명시적이고 좁은 승인이 필요하다.",),
            constraints=("비밀을 노출하거나 저장하지 않는다.",),
            source_refs=("safety_boundary",),
            grounding_source="local_state",
            grounding_quality="high",
        )
    if route.route_type in {"general_knowledge_question", "unknown"}:
        hits = retrieve_verified_facts(question, store_path=runtime.get("verified_store_path"))
        if hits:
            quality = "high" if len({hit.source_ref for hit in hits}) >= 2 else "medium"
            return _context(
                route.route_type,
                facts=tuple(hit.fact for hit in hits),
                constraints=(
                    "검색된 verified-store 사실만 사용한다.",
                    "검색 근거에 없는 설명용 사실이나 장면 엔티티를 지어내지 않는다.",
                ),
                source_refs=tuple(hit.source_ref for hit in hits),
                grounding_source="verified_store_v0_readonly",
                grounding_quality=quality,
            )
    return _context(
        route.route_type,
        facts=(),
        constraints=("확신 있는 답변을 만들 verified grounding이 부족하다.",),
        unknowns=("질문과 맞는 검증된 로컬 사실을 찾지 못했다.",),
        source_refs=(),
        grounding_source="none",
        grounding_quality="none",
    )


def honesty_metadata(
    *,
    route: ConversationRoute,
    grounded_context: GroundedContext,
    semantic_grounding_used: bool,
    answer_mode: str,
) -> dict[str, Any]:
    return {
        **semantic_safety_flags(),
        "direct_prompt_answer_table_used": False,
        "hand_authored_construction_used": True,
        "heuristic_act_inference_used": True,
        "local_transition_surface_used": answer_mode == "greeting_surface",
        "semantic_grounding_used": bool(semantic_grounding_used),
        "grounding_source": grounded_context.grounding_source,
        "grounding_quality": grounded_context.grounding_quality,
        "answer_mode": answer_mode,
        "route_type": route.route_type,
        "route_confidence": route.confidence,
        "honesty_note": HONESTY_NOTE,
    }


def answer_mode_for_route(route_type: ConversationRouteType, *, grounded: bool) -> str:
    if route_type == "greeting_smalltalk":
        return "greeting_surface"
    if route_type == "project_status":
        return "status_summary"
    if route_type == "memory_request":
        return "memory_candidate_response"
    if route_type in {"unsafe_or_private_request", "nonsensical_question"}:
        return "refusal_or_boundary"
    if grounded:
        return "grounded_explanation"
    return "unknown_fallback"


def _clean_fact(value: str) -> str:
    max_fact_chars = 340
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\s+([(<〈])", r"\1", text)
    text = re.sub(r"([(<〈])\s+", r"\1", text)
    text = re.sub(r"\s+([)>〉])", r"\1", text)
    text = re.sub(r"(?<=-)\s+", "", text)
    text = re.sub(
        r"(?<![.!?。])\s+(은|는|이|가|을|를|의|에|에서|에게|으로|로|와|과|도|만|까지|부터|이다|입니다|였다|했다|한다|된다)(?=[\s,.;:!?〉)>]|$)",
        r"\1",
        text,
    )
    original_sentence_matches = [sentence.strip() for sentence in re.findall(r"[^.!?。]+[.!?。]", text)]
    sentence_matches = _drop_incomplete_tail_sentences(original_sentence_matches)
    if sentence_matches and len(sentence_matches) < len(original_sentence_matches):
        text = " ".join(sentence_matches)
    if len(sentence_matches) >= 2 and len(text) > 180:
        text = " ".join(sentence_matches[:2])
    if len(text) > max_fact_chars:
        first_two_sentences = " ".join(sentence.strip() for sentence in sentence_matches[:2])
        if first_two_sentences and len(first_two_sentences) <= max_fact_chars + 80:
            text = first_two_sentences
        else:
            first_sentence = sentence_matches[0].strip() if sentence_matches else ""
            if 80 <= len(first_sentence) <= max_fact_chars:
                text = first_sentence
            else:
                clipped = text[:max_fact_chars].rstrip()
                boundary = max(clipped.rfind(mark) for mark in (".", "?", "!", "다.", "요."))
                if boundary >= 80 and boundary < len(clipped) - 24:
                    text = clipped[: boundary + 1].rstrip()
                else:
                    text = clipped.rstrip(" ,;:") + "..."
    return text if text.endswith((".", "?", "!", "다", "요")) else f"{text}."


def _join_facts(facts: tuple[str, ...], *, limit: int = 3) -> str:
    cleaned = tuple(item for item in (_clean_fact(fact) for fact in facts[:limit]) if item)
    return " ".join(cleaned)


def _grounded_fact_limit(context: GroundedContext, question: str = "") -> int:
    if context.grounding_source == "semantic_cloud_graph_web_evidence_readonly":
        return 1
    return 3


def _question_discourse_mode(question: str) -> str:
    text = re.sub(r"\s+", " ", str(question or "").strip().lower())
    if not text:
        return "grounded_statement"
    if any(token in text for token in ("왜", "이유", "원인", "why")):
        return "causal_explanation"
    if any(token in text for token in ("어떻게", "과정", "원리", "작동", "how")):
        return "mechanism_explanation"
    if any(token in text for token in ("차이", "비교", "다른", "difference", "compare", "versus", " vs ")):
        return "contrast_explanation"
    if any(token in text for token in ("예시", "예를", "사례", "example")):
        return "example_request"
    if any(token in text for token in ("뭐", "무엇", "정의", "설명", "what", "define", "explain")):
        return "definition_explanation"
    return "grounded_statement"


def _fact_discourse_role(fact: str) -> str:
    text = str(fact or "").lower()
    if any(token in text for token in ("because", "therefore", "원인", "때문", "따라서", "영향", "depends on", "비례", "반비례")):
        return "cause_or_relation"
    if any(token in text for token in ("is a", "refers to", "란", "이란", "이다", "입니다", "means")):
        return "definition"
    if any(token in text for token in ("first", "introduced", "발표", "소개", "발견", "formulated", "뉴턴", "newton")):
        return "history_or_origin"
    if any(token in text for token in ("for example", "예를", "사례", "such as")):
        return "example"
    return "supporting_fact"


def _drop_incomplete_tail_sentences(sentences: list[str]) -> list[str]:
    return [
        sentence
        for sentence in sentences
        if not re.search(r"(으로|로|와|과|및|또는|그리고|처음)\.$", sentence.strip())
    ]


_GROUNDING_STOP = {
    "what", "is", "are", "the", "a", "an", "of", "to", "in", "on", "for", "and", "or",
    "does", "do", "how", "why", "this", "that", "with", "about", "from", "into",
    "뭐", "무엇", "왜", "어떻게", "이란", "란", "그것", "이것", "차이", "정의", "설명",
}


def _grounding_text_lang(text: str) -> str | None:
    hangul = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if hangul == 0 and latin == 0:
        return None
    # Any non-trivial Hangul makes the snippet "Korean": an English answer should

    # must not be pasted into it. Negligible Hangul (<3 chars) reads as English.
    return "ko" if hangul >= 3 else "en"


def _grounding_content_tokens(text: str) -> set[str]:
    lowered = str(text or "").lower()
    latin = set(re.findall(r"[a-z0-9]{3,}", lowered))
    hangul = set(re.findall(r"[가-힣]{2,}", str(text or "")))
    return (latin | hangul) - _GROUNDING_STOP


def _rank_facts_for_question(question: str, facts: tuple[str, ...], *, limit: int) -> tuple[tuple[str, str], ...]:
    mode = _question_discourse_mode(question)
    # Web/cloud evidence is noisy: filter out facts in the wrong language or with
    # no shared content with the question, so we never paste an irrelevant,
    # cross-language snippet. If everything is filtered out, the caller abstains
    # (and the base-brain fallback can still answer honestly).
    # A Korean question always carries Hangul particles/endings even when it

    # presence rather than character-count ratio.
    question_lang = "ko" if re.search(r"[가-힣]", question) else "en"
    question_tokens = _grounding_content_tokens(question)
    preferred_by_mode = {
        "causal_explanation": ("cause_or_relation", "definition", "supporting_fact", "history_or_origin"),
        "mechanism_explanation": ("cause_or_relation", "definition", "supporting_fact", "history_or_origin"),
        "definition_explanation": ("definition", "cause_or_relation", "history_or_origin", "supporting_fact"),
        "contrast_explanation": ("cause_or_relation", "definition", "supporting_fact", "history_or_origin"),
        "example_request": ("example", "supporting_fact", "definition", "cause_or_relation"),
        "grounded_statement": ("definition", "cause_or_relation", "history_or_origin", "supporting_fact"),
    }.get(mode, ("definition", "cause_or_relation", "history_or_origin", "supporting_fact"))
    order = {role: index for index, role in enumerate(preferred_by_mode)}
    cleaned: list[tuple[str, str, int, int]] = []
    for index, fact in enumerate(facts):
        clean = _clean_fact(fact)
        if not clean:
            continue
        fact_lang = _grounding_text_lang(clean)
        if question_lang and fact_lang and fact_lang != question_lang:
            continue  # don't paste a wrong-language snippet
        role = _fact_discourse_role(clean)
        relevance = len(_grounding_content_tokens(clean) & question_tokens)
        cleaned.append((clean, role, index, relevance))
    # Entity-anchor gate (who/definition questions only): a fact that merely

    # is NOT a definition of it. Keep only facts that LEAD with the query entity;
    # if none do, abstain (return ()) so the web rescue answers from the right page.
    # Referent-type resonance (replaces the earlier string-anchor patches): keep only
    # facts whose described ontological TYPE constructively interferes with the type
    # the question expects. A "who" question expects a PERSON, so a fly (organism), a
    # website (org), or a film (work) destructively interferes and is suppressed —
    # one emergent mechanism instead of a dozen per-entity rules. If everything is
    # suppressed, abstain so the web rescue answers from the right page. SELF/UNKNOWN
    # expected types are left permissive (self → the graph identity path upstream).
    resonant, expected = select_resonant_facts(question, cleaned)
    if expected != "self":
        if resonant:
            cleaned = resonant
        elif cleaned:
            return ()  # off-topic grounding → yield to the web-grounded rescue
    # Keep discourse-role priority, then prefer facts that share content with the
    # question (soft tiebreaker — never drops, so cleaning/boundary behaviour is
    # unchanged), then original order.
    ranked = sorted(cleaned, key=lambda item: (order.get(item[1], 99), -item[3], item[2]))
    return tuple((fact, role) for fact, role, _, _ in ranked[:limit])


def grounded_discourse_metadata(question: str, context: GroundedContext) -> dict[str, Any]:
    """Expose bounded discourse diagnostics without answer content or traces."""

    limit = _grounded_fact_limit(context, question)
    preserve_source_order = context.grounding_source in {
        "local_state",
        "local_brain_redacted",
        "agentic_runtime_state",
        "review_queue",
    }
    if preserve_source_order:
        ranked = tuple((fact, _fact_discourse_role(fact)) for fact in (_clean_fact(item) for item in context.facts[:limit]) if fact)
    else:
        ranked = _rank_facts_for_question(question, context.facts, limit=limit)
    return {
        "grounded_discourse_mode": _question_discourse_mode(question),
        "grounded_fact_roles": [role for _, role in ranked],
        "grounded_fact_count": len(ranked),
        "grounded_discourse_basis": (
            "source_ordered_local_state_facts_no_prompt_answer_table"
            if preserve_source_order
            else "question_form_plus_retrieved_fact_roles_no_prompt_answer_table"
        ),
    }


_WHO_RE = re.compile(r"누구|누가|\bwho\b", re.IGNORECASE)

_ATTR_KO_END = re.compile(r"누구[가-힣]{0,5}\s*\??\s*$")
_ATTR_EN_RE = re.compile(r"\bwho\s+(?:is|was|are|were)\b", re.IGNORECASE)
_Q_DROP_WHO = {
    "누구", "누가", "누군지", "누구야", "누구인가", "who", "is", "are", "the", "of", "한", "그", "이",
}
# A person name: 2–4 Korean syllables (optionally a second 1–3 syllable block), or a
# capitalised 2–3 word Latin name. Used ONLY anchored next to the query's subject+role,
# so it cannot run wild over ordinary Korean text.
_NAME = r"(?:[가-힣]{2,4}(?:\s[가-힣]{1,3})?|[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){1,2})"
_NAME_STOP = {"회사", "기업", "사촌", "사람", "당시", "현재", "최고", "경영", "실적", "상승세", "인수", "자신", "이사", "임원", "업체", "그것", "이것", "본래", "이름", "최고경영자"}
# Title/role phrases that the name regex can capture but which are never the person.
_ROLE_WORD_RE = re.compile(
    r"^(?:chief\s+executive(?:\s+officer)?|executive\s+officer|chief\s+\w+\s+officer|ceo|president|"
    r"chairman|founder|co-?founder|director|대표|회장|사장|부사장|최고경영자|창업자|창립자|설립자|의장)\b",
    re.IGNORECASE,
)


def _extract_who_attribution_lead(question: str, facts: list[str], *, language: str) -> str | None:
    """For "who is X's CEO / / " questions, surface the person cleanly.

 The grounded facts often CONTAIN the answer but bury it in a rambling web sentence
 ("2006 CEO …"). Anchored on the query's own subject and
 role tokens — never a role→answer table — pull the person name that sits right next
 to "{subject} … {role}" and, if one recurs across the facts, state it directly.
 Returns None unless confident → the caller keeps the normal grounded discourse.
 """
    if not _WHO_RE.search(question):
        return None
    # Attribution-form gate (Korean only — the demo is KO-first). The KO attribution form

    # and is excluded. English is left to the normal composer: "who is/was" alone can't tell
    # attribution from an action ("Who is Tesla CEO suing?"), so EN extraction stays off.
    if not re.search(r"[가-힣]", question):
        return None
    if not _ATTR_KO_END.search(question):
        return None
    content = [t for t in re.findall(r"[A-Za-z][A-Za-z.'\-]+|[가-힣]{2,}", question) if t.lower() not in _Q_DROP_WHO]
    if len(content) < 2:
        return None
    subject, role = content[0], content[1]
    s, r = re.escape(subject), re.escape(role)
    before = re.compile(rf"({_NAME})\s+{s}\s*[^.\n]{{0,12}}?{r}")
    after = re.compile(rf"{s}\s*[^.\n]{{0,12}}?{r}\s*(?:는|은|:|=|\s|이|가)+({_NAME})")
    # Count a candidate per DISTINCT evidence snippet, not per raw occurrence — web
    # results are often near-duplicates, so a stray word repeated across copies must not
    # clear the confidence gate. Exact-duplicate facts collapse to one source.
    sources: dict[str, set[int]] = {}
    # Dedupe on a normalised key (collapse whitespace + case) so near-identical web
    # results count as one source — a stray word repeated across copies can't reach ≥2.
    _seen: dict[str, str] = {}
    for fact in facts:
        _seen.setdefault(re.sub(r"\s+", " ", fact).strip().lower(), fact)
    for idx, fact in enumerate(_seen.values()):
        for pattern in (before, after):
            for match in pattern.finditer(fact):
                name = match.group(1).strip(" .,'-")
                low = name.lower()
                if not name or name in _NAME_STOP or low in {subject.lower(), role.lower()} or name in content:
                    continue
                # A title/role phrase is never the person (span disambiguation, not a

                if _ROLE_WORD_RE.match(name):
                    continue
                sources.setdefault(name, set()).add(idx)
    if not sources:
        return None
    person = max(sources, key=lambda k: (len(sources[k]), len(k)))
    # The real answer-person appears in ≥2 DISTINCT snippets; a one-off match is dropped.
    if len(sources[person]) < 2:
        return None
    if language == "ko":
        return f"{subject}의 {role}는 {person}입니다."
    return f"The {role} of {subject} is {person}."


def _compose_grounded_discourse(question: str, context: GroundedContext, *, language: str) -> str | None:
    limit = _grounded_fact_limit(context, question)
    if context.grounding_source in {"local_state", "local_brain_redacted", "agentic_runtime_state", "review_queue"}:
        ranked = tuple((fact, _fact_discourse_role(fact)) for fact in (_clean_fact(item) for item in context.facts[:limit]) if fact)
    else:
        ranked = _rank_facts_for_question(question, context.facts, limit=limit)
    if not ranked:
        return None
    facts = [fact for fact, _ in ranked]


    _who_lead = _extract_who_attribution_lead(question, facts, language=language)
    if _who_lead:
        return _who_lead
    mode = _question_discourse_mode(question)
    if language == "ko":
        # No grounding-disclaimer preamble: the answer leads with the content itself.
        # The grounding signal is carried by the 🔒 reasoning certificate, not a verbose

        if len(facts) == 1:
            return facts[0]
        return " ".join(facts)

    if context.grounding_source == "verified_store_v0_readonly":
        prefix = "From the verified store,"
    else:
        prefix = {
            "causal_explanation": "The evidence points to this cause-and-relation structure:",
            "mechanism_explanation": "Within the retrieved evidence, the mechanism is:",
            "definition_explanation": "The retrieved evidence defines it this way:",
            "contrast_explanation": "The retrieved evidence separates the concepts this way:",
            "example_request": "The retrieved evidence gives this example:",
        }.get(mode, "Grounded in the retrieved evidence:")
    return f"{prefix} {' '.join(facts)}"


def realize_grounded_context(question: str, context: GroundedContext, *, language: str = "ko") -> str | None:
    """Realize grounded facts as a conservative product-safe utterance.

    This is not a direct prompt-to-answer table. It is a bounded fact surface:
    if verified or locally declared facts are absent, it abstains; if facts are
    present, it exposes only those facts and keeps source/permission constraints
    intact.
    """

    if not context.facts or context.grounding_quality == "none":
        return None

    return _compose_grounded_discourse(question, context, language=language)
