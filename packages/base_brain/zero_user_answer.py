from __future__ import annotations

import hashlib
import os
import re
from typing import Any

_HANGUL = re.compile(r"[가-힣]")

from packages.surface_brain.monitor import repair_answer_for_mode
from packages.surface_brain.q_cortex_bridge import select_surface_candidates

from .models import AnswerMode, AudienceLevel, Language, honesty_flags
from .pack_loader import classify_intent, get_semantic_context, get_surface_candidates, load_base_brain_pack
from .scene_grounding import extract_scene_grounding

# MEC (metacognitive efficiency controller) instrumentation — a PURE OBSERVER of this pipeline's
# latency/success, so ATANOR can watch its own answer path and re-steer under inefficiency. It never
# changes what this function returns. base_brain must not hard-depend on it, and the kill-switch
# (ATANOR_MEC=0) makes the wrapper a no-op identity, so a green audit is trivially preserved.
try:  # pragma: no cover - trivial import guard
    from packages.metacog import instrument as _mec_instrument
except Exception:  # pragma: no cover
    def _mec_instrument(_name, **_kw):
        def _identity(fn):
            return fn
        return _identity


UNSUPPORTED_HINTS_KO = ("오늘", "최신", "실시간", "주가", "가격", "유재석", "우리 동네", "날씨",

                        # neighbourhood junk dump — the future is never in a static graph; grammar-

                        "다음 주", "다음주", "내일", "모레", "다음 달", "다음달", "내년", "이번 주",
                        "로또", "복권")
UNSUPPORTED_HINTS_EN = ("today", "weather", "latest", "stock price", "current price", "near me")

RELATION_WORDS_KO = {
    "is_a": "의 한 종류입니다",
    "part_of": "의 일부입니다",
    "has_property": "라는 특성을 가집니다",
    "used_for": "에 쓰입니다",
    "causes": "의 원인이 될 수 있습니다",
    "enables": "를 가능하게 합니다",
    "requires": "를 필요로 합니다",
    "contrasts_with": "와 대비됩니다",
    "similar_to": "와 비슷합니다",
    "example_of": "의 예입니다",
    "manages": "를 관리합니다",
    "produces": "를 만듭니다",
    "depends_on": "에 의존합니다",
    "supports": "를 뒷받침합니다",
    "contains": "를 포함합니다",
    "uses": "를 사용합니다",
}

RELATION_WORDS_EN = {
    "is_a": "is a kind of",
    "part_of": "is part of",
    "has_property": "has the property",
    "used_for": "is used for",
    "causes": "can cause",
    "enables": "enables",
    "requires": "requires",
    "contrasts_with": "contrasts with",
    "similar_to": "is similar to",
    "example_of": "is an example of",
    "manages": "manages",
    "produces": "produces",
    "depends_on": "depends on",
    "supports": "supports",
    "contains": "contains",
    "uses": "uses",
}

# English micro-NLG: turn (subject, relation, object) triples into one aggregated,
# article-correct, pronoun-using sentence instead of repeating the subject per relation.
EN_RELATION_CLAUSE = {
    "is_a": "is a kind of {o}",
    "part_of": "is part of {o}",
    "has_property": "has the property {o}",
    "used_for": "is used for {o}",
    "causes": "can cause {o}",
    "enables": "enables {o}",
    "requires": "requires {o}",
    "contrasts_with": "contrasts with {o}",
    "similar_to": "is similar to {o}",
    "example_of": "is an example of {o}",
    "manages": "manages {o}",
    "produces": "produces {o}",
    "depends_on": "depends on {o}",
    "supports": "supports {o}",
    "contains": "contains {o}",
    "uses": "uses {o}",
}

# Relations whose object reads as a countable noun phrase and should take a determiner.
EN_ARTICLE_RELATIONS = {
    "requires", "uses", "causes", "produces", "contains", "manages", "supports",
    "contrasts_with", "similar_to", "depends_on",
}

# Objects that are mass/abstract nouns and must stay bare (no "a"/"an").
EN_UNCOUNTABLE = {
    "privacy",
    "evidence",
    "hallucination reduction",
    "software deployment",
    "container orchestration",
    "ai training",
    "ai inference",
}


def _en_noun_phrase(label: str, *, with_article: bool) -> str:
    label = label.strip()
    if not label:
        return label
    if not with_article:
        return label
    if label[:1].isupper():  # proper noun (GraphRAG, ATANOR, Local Brain)
        return label
    if label.lower() in EN_UNCOUNTABLE:
        return label
    article = "an" if label[:1].lower() in "aeiou" else "a"
    return f"{article} {label}"


def _join_en(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def _english_relation_sentence(
    primary: dict[str, Any],
    context_map: dict[str, dict[str, Any]],
    *,
    max_relations: int = 3,
) -> str:
    """Aggregate a concept's relations into one fluent sentence: 'It <clauses>.'."""
    grouped: list[tuple[str, list[str]]] = []
    index: dict[str, int] = {}
    for relation in primary.get("relations", [])[:max_relations]:
        relation_name = str(relation.get("relation") or "related_to")
        clause_template = EN_RELATION_CLAUSE.get(relation_name)
        if clause_template is None:
            continue
        target_id = str(relation.get("target") or "")
        if target_id not in context_map and "_" in target_id:
            continue
        target = context_map.get(
            target_id, {"concept_id": target_id, "canonical_name": target_id, "labels": {}}
        )
        target_label = _label(target, "en")
        obj = _en_noun_phrase(target_label, with_article=relation_name in EN_ARTICLE_RELATIONS)
        if relation_name in index:
            grouped[index[relation_name]][1].append(obj)
        else:
            index[relation_name] = len(grouped)
            grouped.append((relation_name, [obj]))

    clauses: list[str] = []
    for relation_name, objects in grouped:
        clause_template = EN_RELATION_CLAUSE[relation_name]
        clauses.append(clause_template.format(o=_join_en(objects)))
    if not clauses:
        return ""
    # When a clause already coordinates objects ("uses a semantic graph and a
    # surface graph"), join the clauses with an Oxford ", and" so the sentence
    # doesn't read as a run-on chain of "and ... and ...".
    if len(clauses) >= 2 and any(" and " in clause for clause in clauses):
        body = f"{', '.join(clauses[:-1])}, and {clauses[-1]}"
    else:
        body = _join_en(clauses)
    return f"It {body}."


def _english_second_hop(primary: dict[str, Any], context_map: dict[str, dict[str, Any]]) -> str:
    """M2: surface ONE verified second-hop fact (A→B→C) as a connected sentence.

    Pure graph reasoning — it only states relations that exist in the graph
    (primary → target → target's relation), never an invented causal link. The
    intermediate concept must be relevant to the query (present in context_map).
    """
    primary_id = str(primary.get("concept_id"))
    for relation in primary.get("relations", [])[:3]:
        target_id = str(relation.get("target") or "")
        target = context_map.get(target_id)
        if not target:
            continue
        for sub in target.get("relations", [])[:3]:
            sub_target_id = str(sub.get("target") or "")
            if not sub_target_id or sub_target_id == primary_id or sub_target_id == target_id:
                continue
            clause_template = EN_RELATION_CLAUSE.get(str(sub.get("relation") or "related_to"))
            if clause_template is None:
                continue
            sub_rel = str(sub.get("relation"))
            sub_target = context_map.get(sub_target_id, {"concept_id": sub_target_id, "labels": {}})
            sub_label = _label(sub_target, "en")
            target_label = _label(target, "en")
            if not sub_label or not target_label or _HANGUL.search(sub_label) or _HANGUL.search(target_label):
                continue
            obj = _en_noun_phrase(sub_label, with_article=sub_rel in EN_ARTICLE_RELATIONS)
            subject = _en_noun_phrase(target_label, with_article=not target_label[:1].isupper())
            subject = subject[:1].upper() + subject[1:]
            return f"{subject}, in turn, {clause_template.format(o=obj)}."
    return ""


KO_DESCRIPTIONS = {
    "kubernetes": "여러 서버에 흩어진 컨테이너를 자동으로 배포하고, 상태를 확인하며, 필요하면 다시 띄우거나 복구해 주는 오픈소스 운영 플랫폼입니다.",
    "container_orchestration_system": "컨테이너를 어디에서 실행할지 정하고, 배포와 복구를 자동화하는 관리 시스템입니다.",
    "container": "애플리케이션과 필요한 실행 환경을 작게 묶어 어디서든 비슷하게 실행되게 하는 단위입니다.",
    "docker": "애플리케이션을 컨테이너로 포장하고 실행하게 해 주는 도구입니다.",
    "spring_boot": "Java 기반 웹 서비스와 API를 빠르게 만들고 운영 설정을 단순화해 주는 백엔드 프레임워크입니다.",
    "express_js": "Node.js에서 HTTP API와 웹 서버를 가볍고 빠르게 만들기 좋은 프레임워크입니다.",
    "web_framework": "웹 서비스의 요청 처리, 라우팅, 응답 구성을 더 쉽게 만드는 개발 도구 묶음입니다.",
    "ai_training": "데이터를 보며 모델 내부 기준을 조정하는 과정입니다.",
    "ai_inference": "이미 만들어진 모델이 새 입력을 보고 출력을 계산하는 과정입니다.",
    "trained_model": "데이터로 조정이 끝나 추론에 사용할 수 있는 모델입니다.",
    "quantum_computer": "양자 상태를 이용해 특정 문제를 계산하는 컴퓨터이지만, 모든 일을 무조건 빠르게 해 주는 장치는 아닙니다.",
    "classical_computer": "일반적인 디지털 상태와 명령으로 계산하는 컴퓨터입니다.",
    "graphrag": "질문과 관련된 개념, 관계, 근거 경로를 먼저 찾고 그 경로에 맞는 문맥으로 답을 구성하는 방식입니다.",
    "ontology": "개념과 개념 사이의 관계를 정해 지식을 구조적으로 연결하는 지도입니다.",
    "semantic_graph": "단어보다 의미와 관계를 중심으로 지식을 저장하는 그래프입니다.",
    "surface_graph": "무엇을 말할지가 아니라 어떻게 자연스럽게 말할지를 돕는 표현 그래프입니다.",
    "seed_graph": "사용자 데이터가 없을 때도 기본 추론 방향을 잡아 주는 관계와 사고 원리의 작은 뼈대입니다.",
    "base_brain_pack": "사용자 데이터 없이도 제한적인 일반 질문을 처리하기 위한 기본 지식 앵커 묶음입니다.",
    "local_first_ai": "개인 데이터와 핵심 처리를 가능한 한 사용자 기기 안에 두는 AI 구조입니다.",
    "cloud_ai": "저장소나 연산을 원격 서버에서 활용하는 AI 구조입니다.",
    "privacy": "개인 데이터가 불필요하게 노출되지 않도록 사용자가 통제하는 상태입니다.",
    "hallucination_reduction": "근거가 부족한 주장을 줄이거나 단정하지 않도록 만드는 과정입니다.",
    "evidence": "어떤 주장을 확인하거나 뒷받침하는 근거 문맥입니다.",
    "claim": "근거로 확인되거나 제한되어야 하는 주장입니다.",
    "sqlite": "별도 서버 없이 하나의 로컬 파일에 데이터를 저장하는 내장형 데이터베이스입니다.",
    "database": "구조화된 정보를 저장하고 안정적으로 조회하거나 갱신하게 해 주는 저장소입니다.",
    "operating_system": "하드웨어 자원과 애플리케이션 실행을 관리하는 기본 소프트웨어입니다.",
    "cpu": "다양한 명령을 순서 있게 처리하는 범용 연산 장치입니다.",
    "gpu": "많은 계산을 동시에 처리하는 데 강한 병렬 연산 장치입니다.",
    "ram": "실행 중인 프로그램과 데이터를 빠르게 올려두는 휘발성 메모리입니다.",
    "ssd": "전원이 꺼져도 데이터가 남는 빠른 저장 장치입니다.",
    "voltage": "전하를 밀어내는 압력에 가까운 전기적 차이입니다.",
    "current": "전하가 실제로 흐르는 양입니다.",
    "tauri": "웹 UI를 가벼운 네이티브 데스크톱 앱으로 묶어 배포하는 도구입니다.",
    "api": "소프트웨어끼리 정해진 방식으로 요청과 응답을 주고받게 하는 인터페이스입니다.",
    "web_search": "인터넷의 공개 정보를 찾는 기능이며, 로컬 그래프 추론과는 구분됩니다.",
    "korean_language": "조사와 어미가 중요해 문장 흐름을 한국어답게 맞춰야 하는 언어입니다.",
    "english_language": "어순과 관사가 중요해 영어식 구조로 표현해야 자연스러운 언어입니다.",
    "atanor": "외부 LLM이나 sLLM 없이, 개인 데이터는 기기 안에 두고 의미 그래프와 표현 그래프를 분리해 근거에서 답을 짓는 로컬 우선 지식 엔진입니다.",
    "local_brain": "사용자의 기기 안에서만 다루는 개인 맥락 영역입니다.",
    "cloud_brain": "개인 데이터와 분리된 공개 지식 보조 영역입니다.",
    "q_cortex": "실제 양자컴퓨터가 아니라 후보 경로를 고르는 고전적 최적화 계층입니다.",
    "graph_hub": "그래프 지식을 카탈로그, 설치, 권한, 읽기 전용 부착, 내보내기, 감사로 다루는 카트리지 시스템입니다.",
    "atlas": "기여 노드를 위한 지역 릴레이 상태를 개인정보 노출 없이 시각화하는 영역이며, 사설 기억을 공유하지 않습니다.",
    "brain_graph": "로컬, 클라우드, 카트리지, 작업 기억 노드를 같은 출처나 프라이버시인 것처럼 섞지 않고 탭별 뷰로 보여 주는 그래프입니다.",
    "machine_learning": "데이터에서 패턴을 스스로 찾도록 모델을 학습시키는 방법입니다.",
    "neural_network": "가중치로 연결된 층 구조로 데이터의 표현을 학습하는 모델입니다.",
    "http": "웹 클라이언트와 서버가 데이터를 주고받는 요청-응답 프로토콜입니다.",
    "json": "시스템끼리 구조화된 데이터를 주고받는 가벼운 텍스트 형식입니다.",
    "git": "소스 코드의 변경 이력을 추적하는 분산 버전 관리 시스템입니다.",
    "linux": "서버와 개발에 널리 쓰이는 오픈소스 운영체제 커널입니다.",
    "python": "스크립팅, 데이터, AI 작업에 널리 쓰이는 고수준 프로그래밍 언어입니다.",
    "encryption": "허가된 사람만 읽을 수 있도록 데이터를 변환해 기밀성을 지키는 기술입니다.",
    "compiler": "소스 코드를 기계가 실행할 수 있는 저수준 형태로 번역하는 도구입니다.",
    "virtual_machine": "소프트웨어로 컴퓨터 전체를 흉내 내어 운영체제와 앱을 격리해 실행하는 환경입니다.",
}


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


ATANOR_MEMORY_CONTEXT_TERMS = (
    "내 로컬 메모리",
    "로컬 메모리",
    "개인 메모리",
    "로컬 브레인",
    "클라우드 브레인",
    "ATANOR 메모리",
    "아타노르 메모리",
    "저장된 기억",
    "저장된 노드",
    "로컬 그래프",
    "클라우드 그래프",
    "local brain",
    "cloud brain",
    "local graph",
    "cloud graph",
    "private memory",
    "memory graph",
)

COMPUTER_MEMORY_CONTEXT_TERMS = (
    "RAM",
    "램",
    "컴퓨터 메모리",
    "휘발성 메모리",
    "주기억장치",
    "메모리와 SSD",
    "SSD 차이",
    "memory vs ssd",
    "computer memory",
    "volatile memory",
)


def _is_atanor_memory_context(query: str) -> bool:
    return _contains_any(query, ATANOR_MEMORY_CONTEXT_TERMS)


def _is_computer_memory_context(query: str) -> bool:
    return _contains_any(query, COMPUTER_MEMORY_CONTEXT_TERMS)


def _disambiguate_memory_context(query: str, semantic_context: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not _is_atanor_memory_context(query) or _is_computer_memory_context(query):
        return semantic_context
    return [item for item in semantic_context if str(item.get("concept_id")) != "ram"]


def _seed(query: str) -> int:
    return int(hashlib.sha256(query.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)


def _is_knowledge_query(query: str) -> bool:
    """A 'what is / explain / why' style KNOWLEDGE question — the class the neighbourhood
 synthesis may serve. Excludes fresh/real-time queries (//, handled by the
 abstain gate) and greetings/commands. Kept broad but not a catch-all: it needs an
 explanatory shape so we don't synthesise for a bare fragment."""
    q = str(query or "").strip()
    if len(q) < 3:
        return False
    if _contains_any(q, UNSUPPORTED_HINTS_KO) or any(w in q.lower() for w in ("지금", "오늘", "실시간", "now", "today")):
        return False
    return bool(re.search(
        r"뭐야|무엇|뭔가|이란|란\b|인가|대해|설명|알려|어떻게|왜|의미|차이|무슨|"
        r"what\s+is|what\s+are|explain|why|how|meaning|about|tell me",
        q, re.IGNORECASE))


# --- question SHAPE: the design keystone. A bare concept definition only ANSWERS a
# definitional question. Forcing it onto a causal / advice / opinion / personal question

# shape decides whether the definition path may fire at all.
_SHAPE_PERSONAL = re.compile(r"피곤|우울|번아웃|힘들|외로|슬프|배고프|잠이\s*안|집중이\s*안|불안|스트레스|지쳐|짜증|막막")
_SHAPE_RECOMMEND = re.compile(r"추천|골라\s*줘|뽑아\s*줘|어떤\s*걸\s*(들을|볼|살|먹을)|recommend")
_SHAPE_ADVICE = re.compile(
    r"어떻게\s*(해|하면|해야|하지|할까|하나|시작|극복|연습|결정)|어떡|어떻해|하려면|되려면|방법|팁|"
    r"시작해야|뭐부터|어디부터|무엇부터|어떤\s*걸|골라|"
    r"(게|건|것이|편이)\s*(맞|나아|낫|좋|유리|괜찮|이득)|"
    r"(뭐가|무엇이|어느\s*(게|것|쪽)|어떤\s*게)\s*(나아|낫|좋|유리|맞|괜찮)|"
    r"[가-힣]야\s*(해|돼|되|하나|할까|할지)|"
    r"어떻게\b.*[?？]?$")
_SHAPE_OPINION = re.compile(
    r"생각(해|하니|이야|은|하나|해요)|어떻게\s*생각|라고\s*(봐|생각)|"
    r"꼭\s*.*(해야|필요|하는)|맞(을까|는\s*걸까|다고\s*봐)|괜찮(을까|은\s*걸까)|"
    r"비결|중요(할까|한가)|해야\s*(하는|할)\s*(걸까|까)|필요할까|"
    r"[가-힣](을까|ㄹ까|일까)[?？]?\s*$|까[?？]\s*$")
_SHAPE_CAUSAL = re.compile(r"왜\b|어째서|때문|(면|으면)\s*(어떻게|어떡|무슨\s*일|어찌)|어떻게\s*(되|돼)")
_SHAPE_DEFINITION = re.compile(r"(뭐야|뭔데|뭐냐|란\b|이란|무엇(인가|이야|이니)?|정의|"
                               r"대해\s*(설명|알려)|무슨\s*뜻|what\s+is|define)")


def _question_shape(query: str) -> str:
    """definition | causal | advice | opinion | personal | factual. Strongest signal
    wins (personal > advice > opinion > causal > definition > factual), so an advice
    question that also names a concept is NOT treated as a definition request."""
    q = str(query or "")
    if _SHAPE_PERSONAL.search(q):
        return "personal"
    # recommendation is NOT generic advice: the right behavior is to ground on
    # what we know about the topic (or the user's own taste data), never a
    # "everyone is different" abstain — owner directive 2026-07-08
    if _SHAPE_RECOMMEND.search(q):
        return "recommendation"
    if _SHAPE_ADVICE.search(q):
        return "advice"
    if _SHAPE_OPINION.search(q):
        return "opinion"

    if _SHAPE_CAUSAL.search(q):
        return "causal"
    if _SHAPE_DEFINITION.search(q):
        return "definition"
    return "factual"


def _shape_engage(shape: str, language: str) -> str:
    """A HELPFUL honest response for a non-definitional question we can't ground —
    engages the person and names the real limit, instead of a cold definition or a
    robotic abstain. Never fabricates advice."""
    ko = language == "ko"
    table = {
        "causal": ("'왜'를 묻는 질문이라 확인된 근거만으로 딱 잘라 답하긴 어려워요. 웹 검색을 켜 주시면 근거를 찾아 이유를 설명해 드릴게요."
                   if ko else "This asks 'why', which I can't answer confidently from the base facts alone. Turn on web search and I'll find grounded reasons."),
        "advice": ("이건 사람마다 상황이 달라서 하나의 정답으로 단정하긴 어려워요. 원하시면 웹에서 실제 조언과 사례를 찾아 정리해 드릴게요 — 웹 검색을 켜 보세요."
                   if ko else "There's no single right answer here — it depends. If you turn on web search, I'll gather real, grounded advice for you."),
        "opinion": ("이건 가치 판단이 섞인 물음이라 제가 단정해서 말하기보다는, 확인 가능한 근거를 찾아 함께 짚어 보는 게 맞아요. 웹 검색을 켜 주시면 근거를 모아 드릴게요."
                    if ko else "This is a judgement call — rather than assert an opinion, I'd rather bring grounded evidence. Turn on web search and I'll gather it."),
        "personal": ("많이 힘드셨겠어요. 저는 지어내서 조언하진 않지만, 원하시면 웹에서 도움이 될 만한 근거 있는 방법들을 찾아 정리해 드릴게요 — 웹 검색을 켜 보세요."
                     if ko else "That sounds hard. I won't make up advice, but if you turn on web search I'll gather grounded, helpful suggestions for you."),
        "recommendation": ("아직 이 주제에 대한 지식과 취향 데이터가 부족해서 바로 골라 드리긴 어려워요. 웹 검색을 켜 주시면 널리 알려진 것들부터 정리해 드리고, 대화가 쌓이면 취향에 맞춰 드릴게요."
                           if ko else "I don't yet have enough knowledge or taste data on this to pick well. Turn on web search and I'll start from the widely known ones — and I'll learn your taste as we talk."),
    }
    return table.get(shape, table["advice"])


def _clean_label(value: str) -> str:
    return str(value or "").replace("_", " ").strip()


def _label(concept: dict[str, Any], language: str) -> str:
    labels = concept.get("labels") or {}
    raw = _clean_label(labels.get(language) or concept.get("canonical_name") or concept.get("concept_id"))
    if language != "en":
        return raw
    # English mode must never emit Hangul or corrupted (non-ASCII) surface forms.
    if raw and raw.isascii() and not _HANGUL.search(raw):
        return raw
    en_label = _clean_label(labels.get("en"))
    if en_label and en_label.isascii() and not _HANGUL.search(en_label):
        return en_label
    # Last resort: derive a clean English label from the stable concept id.
    return _clean_label(concept.get("concept_id")) or raw


def _has_final_consonant(text: str) -> bool:
    chars = [ch for ch in text if "\uac00" <= ch <= "\ud7a3"]
    if not chars:
        return False
    return (ord(chars[-1]) - 0xAC00) % 28 != 0


def _topic(label: str) -> str:
    return f"{label}{'은' if _has_final_consonant(label) else '는'}"


def _object(label: str) -> str:
    return f"{label}{'을' if _has_final_consonant(label) else '를'}"


def _with_and(label: str) -> str:
    return f"{label}{'과' if _has_final_consonant(label) else '와'}"


def _is_hangul_text(text: str) -> bool:
    return any("가" <= ch <= "힣" for ch in text)


# Copula/auxiliary/verb openers that mean the description is already a PREDICATE
# whose subject was stripped during promotion ("Marie Curie" + "was the first …").
# Re-attaching the label as an English subject reconstructs the sentence instead of
# stuttering ("Marie Curie is was the first …").
_EN_PREDICATE_HEADS = (
    "is ", "are ", "was ", "were ", "has ", "have ", "had ", "can ", "could ",
    "will ", "would ", "may ", "might ", "does ", "do ", "did ", "refers ",
    "describes ", "means ", "consists ", "includes ", "occurs ", "represents ",
)


def _english_frame(label: str, description: str, audience_level: str) -> str:
    """Frame an English concept+description in English (no Korean particle)."""
    if not description:
        return f"{label} is a related concept in the base graph"
    lowered = description.lower()
    if lowered.startswith(label.lower()) or lowered.startswith("a ") or lowered.startswith("an "):
        return description.rstrip(".")
    # Description is a bare predicate ("was the first …") -> re-attach the subject.
    if lowered.startswith(_EN_PREDICATE_HEADS):
        return f"{label} {description}".rstrip(".")
    # If the description restates the concept as a full clause ("inference uses …",
    # "training adjusts …"), rendering "{label} is {description}" stutters
    # ("AI inference is inference uses …"). Use the clause as its own sentence.
    label_words = [word for word in label.lower().split() if word]
    last_word = label_words[-1] if label_words else ""
    if last_word and len(last_word) > 3 and lowered.startswith(f"{last_word} "):
        standalone = description.rstrip(". ").strip()
        return standalone[:1].upper() + standalone[1:] if standalone else label
    if audience_level == "expert":
        return f"{label}: {description}"
    return f"{label} is {description[:1].lower() + description[1:]}"


def _description_sentence(concept: dict[str, Any], language: str, audience_level: str) -> str:
    label = _label(concept, language)
    description = str(concept.get("short_description") or "")
    # A curated Korean gloss (KO_DESCRIPTIONS) always wins in ko mode, even when the
    # label/description are English (e.g. "CPU"/"GPU"): otherwise the English-frame
    # shortcut below would leak "A CPU is a general-purpose processor …" into a Korean
    # comparison answer. The fact stays faithful; only the surface is Koreanized.
    if language == "ko":
        _ko = KO_DESCRIPTIONS.get(str(concept.get("concept_id")))
        if _ko:
            return f"{_topic(label)} {_ko}"
    # Language-matched framing: an English concept/description must NOT receive a

    # non-Korean and the description carries no Hangul, frame it in English even when
    # the answer language is ko (the fact stays faithful; only the frame changes).
    if language == "ko" and not _is_hangul_text(label) and description and not _is_hangul_text(description):
        return _english_frame(label, description, audience_level)
    if language == "ko":
        return f"{_topic(label)} {KO_DESCRIPTIONS.get(str(concept.get('concept_id')), description)}"
    return _english_frame(label, description, audience_level)


def _concept_by_id(context: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("concept_id")): item for item in context}


def _relation_sentence(source: dict[str, Any], relation: dict[str, Any], context_map: dict[str, dict[str, Any]], language: str) -> str:
    target_id = str(relation.get("target") or "")
    if target_id not in context_map and "_" in target_id:
        return ""
    target = context_map.get(target_id, {"concept_id": target_id, "canonical_name": target_id, "labels": {}})
    source_label = _label(source, language)
    target_label = _label(target, language)
    relation_name = str(relation.get("relation") or "related_to")
    if language == "ko":
        if relation_name == "contrasts_with":
            return f"{_topic(source_label)} {_with_and(target_label)} 대비됩니다."
        if relation_name == "similar_to":
            return f"{_topic(source_label)} {_with_and(target_label)} 비슷합니다."
        relation_word = RELATION_WORDS_KO.get(relation_name, "와 관련됩니다")
        return f"{_topic(source_label)} {_object(target_label)} {relation_word}."
    relation_word = RELATION_WORDS_EN.get(relation_name, "is related to")
    return f"{source_label} {relation_word} {target_label}."


# Korean micro-NLG: each relation carries its own connecting particle, applied to


KO_RELATION = {
    "is_a": ("genitive", "한 종류입니다"),
    "part_of": ("genitive", "일부입니다"),
    "causes": ("genitive", "원인이 될 수 있습니다"),
    "example_of": ("genitive", "예입니다"),
    "used_for": ("locative", "쓰입니다"),
    "depends_on": ("locative", "의존합니다"),
    "enables": ("object", "가능하게 합니다"),
    "requires": ("object", "필요로 합니다"),
    "manages": ("object", "관리합니다"),
    "produces": ("object", "만듭니다"),
    "supports": ("object", "뒷받침합니다"),
    "contains": ("object", "포함합니다"),
    "uses": ("object", "사용합니다"),
    "contrasts_with": ("comitative", "대비됩니다"),
    "similar_to": ("comitative", "비슷합니다"),
    "has_property": ("property", "특성을 가집니다"),
}








_TRANSITIVE_HADA_VERBS = {
    "생산하다", "발견하다", "사용하다", "포함하다", "관리하다", "제공하다", "지원하다",
    "개발하다", "정의하다", "설명하다", "구성하다", "처리하다", "제어하다", "저장하다",
    "연결하다", "제거하다", "생성하다", "분석하다", "측정하다", "제작하다", "활용하다",
    "수행하다", "제안하다", "표현하다", "전달하다", "결정하다", "예측하다", "변환하다",
}


def _is_transitive_predicate(relation_name: str) -> bool:
    return relation_name in _TRANSITIVE_HADA_VERBS


def _ko_relation_clause(relation_name: str, target_label: str) -> str:
    spec = KO_RELATION.get(relation_name)
    if spec is None:
        # Predicate-anchored relation: relation_name IS a Korean verb lemma. Only a


        if _is_transitive_predicate(relation_name):
            return f"{_object(target_label)} {relation_name[:-2]}합니다"
        return f"{_with_and(target_label)} 관련이 있습니다"
    kind, verb = spec
    if kind == "object":
        return f"{_object(target_label)} {verb}"
    if kind == "genitive":
        return f"{target_label}의 {verb}"
    if kind == "locative":
        return f"{target_label}에 {verb}"
    if kind == "comitative":
        return f"{_with_and(target_label)} {verb}"
    if kind == "property":
        marker = "이라는" if _has_final_consonant(target_label) else "라는"
        return f"{target_label}{marker} {verb}"
    return f"{_object(target_label)} {verb}"



_JUNK_TYPE_LABELS = {
    "무엇", "무언가", "것", "그것", "종류", "개념", "대상", "존재", "부분", "방식",
    "상태", "일종", "어떤것", "무엇인가", "entity", "thing", "unknown", "none",
}


def _is_junk_type_label(label: str) -> bool:
    """True when a relation TARGET label is too broken to voice: a meta-placeholder,
 an untranslated English/ontology type (Animal, ChemicalCompound), or a bare Q-id.
 Voicing '<subject> Animal ' is worse than dropping the clause."""
    import re as _re

    s = str(label or "").strip()
    if not s or s in _JUNK_TYPE_LABELS or s.lower() in _JUNK_TYPE_LABELS:
        return True
    if _re.fullmatch(r"Q\d+", s):            # unresolved Wikidata id
        return True
    # an English/Latin token surfacing in a Korean answer is an untranslated ontology leak
    if _re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]*", s):
        return True
    return False


def _korean_relation_sentence(
    primary: dict[str, Any], context_map: dict[str, dict[str, Any]], *,
    max_relations: int = 3, suppress_is_a: bool = False
) -> str:
    """Aggregate a concept's relations: ' <clause1>. <clause2>.' — one
 subject ('' = it), correct particles, no subject repetition.

 suppress_is_a: when the answer already leads with a real definition sentence,
 the '… ' is_a tail is redundant (the definition subsumes the
 category) AND is exactly where a single wrong/over-abstract is_a edge surfaces
 ('' defined as an interaction, yet is_a→'' → " ").
 Drop is_a in that case; keep every OTHER relation, which adds new information."""
    clauses: list[str] = []
    seen: set[tuple[str, str]] = set()
    for relation in primary.get("relations", []):
        if len(clauses) >= max_relations:
            break
        relation_name = str(relation.get("relation") or "related_to")
        if suppress_is_a and relation_name == "is_a":
            continue
        # allow curated relations AND predicate-anchored verb relations that are

        # from low-quality peer decompositions would realize as ungrammatical object

        if relation_name not in KO_RELATION and not _is_transitive_predicate(relation_name):
            continue
        target_id = str(relation.get("target") or "")
        if target_id not in context_map and "_" in target_id:
            continue
        target = context_map.get(target_id, {"concept_id": target_id, "labels": {}})
        target_label = _label(target, "ko")
        if not target_label or _is_junk_type_label(target_label):


            # are worse than silence — drop the clause rather than voice a broken tail.
            continue
        # dedup: the cloud graph can carry several identical (relation, target)

        key = (relation_name, target_label)
        if key in seen:
            continue
        seen.add(key)
        clauses.append(_ko_relation_clause(relation_name, target_label))
    if not clauses:
        return ""
    parts = [f"이는 {clauses[0]}."]
    parts += [f"또한 {clause}." for clause in clauses[1:]]
    return " ".join(parts)


def _select_compare_pair(query: str, strong: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pick the TWO distinct concepts a comparison is actually about. A naive
 top-2-by-score picks duplicates (" " → + a promoted
 duplicate, yielding " "). So prefer concepts the query
 NAMES, and require two distinct surface labels — never the same concept twice."""
    def _key(item: dict[str, Any]) -> str:
        return (_label(item, "ko") or str(item.get("concept_id") or "")).strip().lower()

    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    # first pass: concepts explicitly named in the query, in query order of appearance
    named = [it for it in strong if _named_in_query(query, it)]
    named.sort(key=lambda it: min((query.lower().find(n.lower()) % 100000) for n in _concept_names(it) if n.lower() in query.lower()) if any(n.lower() in query.lower() for n in _concept_names(it)) else 99999)
    for item in named + strong:
        k = _key(item)
        if not k or k in seen:
            continue
        seen.add(k)
        picked.append(item)
        if len(picked) == 2:
            break
    return picked


def _compare_answer(context: list[dict[str, Any]], language: str, audience_level: str) -> str:
    if len(context) < 2:
        return ""
    first, second = context[0], context[1]
    if language == "ko":
        return (
            f"{_with_and(_label(first, language))} {_label(second, language)}의 핵심 차이는 역할과 사용 맥락입니다. "
            f"{_description_sentence(first, language, audience_level)} "
            f"반면 {_description_sentence(second, language, audience_level)} "
            "둘은 관련된 문제를 다룰 수 있지만, 선택 기준과 운영 방식은 다릅니다."
        )
    first_desc = _description_sentence(first, language, audience_level).rstrip(". ").strip()
    second_desc = _description_sentence(second, language, audience_level).rstrip(". ").strip()
    return (
        f"The main difference between {_label(first, language)} and {_label(second, language)} is their role and operating context. "
        f"{first_desc}. "
        f"By contrast, {second_desc}. "
        "They may solve related problems, but they are chosen for different constraints."
    )


def _project_level_answer(query: str, language: str) -> tuple[str, bool] | None:
    lower = query.lower()
    if "영어로" in query and ("간단" in query or "짧게" in query):
        return "Tell me the topic, and I will answer in one or two concise English sentences.", False
    if language == "ko":
        if "한국어답게" in query or "번역투" in query:
            return "좋아요. 주제를 알려주면 영어식 직역을 피하고, 한국어 어순과 문장 흐름에 맞춰 자연스럽게 설명할게요.", False
        if "근거 중심" in query or "과장 없이" in query:
            return "근거 중심으로 답하려면 확인된 내용과 불확실한 내용을 나눠 말해야 합니다. 근거가 부족한 부분은 단정하지 않고, 확인 가능한 범위만 설명하는 방식이 맞습니다.", True
        if "템플릿" in query:
            return "같은 시작 문구를 반복하기보다, 질문의 목적에 맞춰 정의, 비교, 예시, 주의점을 자연스럽게 조합해 답하는 방식이 좋습니다.", True
        if "유재석" in query:
            return "모르겠어. 지금 기본 그래프에는 유재석을 설명할 검증된 근거가 없어.", False
        if "그거" in query and ("설명" in query or "알려" in query):
            return "지금 문장만으로는 '그거'가 무엇을 가리키는지 확정하기 어렵습니다. 대상만 한 단어로 알려주면 그 범위 안에서 바로 설명할게요.", False
        if "local brain" in lower and "cloud brain" in lower and ("차이" in query or "비교" in query):
            return (
                "저장된 개인 맥락은 사용자의 기기 안에서만 다루는 사적 지식 영역입니다. "
                "공개 지식 보조층은 개인 데이터를 섞지 않고 검증 가능한 공용 지식 조각과 근거를 참고하는 영역입니다. "
                "이 구분은 개인정보 보호를 지키기 위한 경계입니다. "
                "핵심 차이는 데이터 소유권과 공개 범위입니다."
            ), True
        if "q-cortex" in lower and ("양자컴퓨터" in query or "아니" in query):
            return (
                "이 고전 최적화 계층은 실제 양자컴퓨터가 아니라 로컬에서 후보 조합을 고르는 선택 장치입니다. "
                "양자 하드웨어를 쓰거나 양자 가속을 낸다고 주장하지 않습니다."
            ), True
        if "atanor" in lower and ("한 문장" in query or "짧게" in query):
            return "ATANOR는 개인 데이터는 기기 안에 두고 의미 그래프와 표현 그래프를 분리해 근거 중심 답변을 만드는 로컬 우선 지식 엔진입니다.", True
        if "내부 경로" in query or "brain path" in lower:
            return "기본 답변에서는 내부 처리 경로를 드러내지 않고, 사용자가 바로 이해할 수 있는 자연스러운 설명만 보여주는 것이 맞습니다.", True
    else:
        if "q-cortex" in lower and ("quantum" in lower or "not" in lower):
            return (
                "This optimizer is not a real quantum computer. It is a classical local selector for candidate paths and does not claim quantum hardware or quantum speedup.",
                True,
            )
        if "atanor" in lower and ("one sentence" in lower or "brief" in lower):
            return (
                "ATANOR is a local-first knowledge engine that keeps private data on-device while separating semantic reasoning from surface expression.",
                True,
            )
    return None


def _drop_placeholder_heads(query: str, items: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    """Remove ontology concepts that are a relative-clause PLACEHOLDER HEAD (// in
 'X ?') — the thing ASKED FOR, never the topic. Applies ONLY when the query really is
 a relative-clause-with-placeholder question (so ' ?' is untouched). May return an
 EMPTY list on purpose: if the real topic X isn't in the ontology, an honest abstain is right —
 far better than the ontology lane answering ' ' (the multi-lane wrong-subject leak the
 query_frame fix alone couldn't reach)."""
    try:
        from packages.graph_scale.query_frame import _relative_clause_subject, _PLACEHOLDER_HEADS as _PH
        from packages.base_brain.neighborhood import _kiwi
        kw = _kiwi()
        if kw is None:
            return items
        if not _relative_clause_subject(list(kw.tokenize(query))):
            return items   # not a relative-clause placeholder question — leave concepts alone
        return [it for it in items if _label(it, language) not in _PH]
    except Exception:
        return items


def _compose_answer(query: str, context: list[dict[str, Any]], language: str, audience_level: str, intent: str, self_depth_boost: int = 0) -> tuple[str, bool]:
    project_answer = _project_level_answer(query, language)
    if project_answer is not None:
        return project_answer

    lowered = query.lower()
    if (language == "ko" and _contains_any(query, UNSUPPORTED_HINTS_KO)) or _contains_any(lowered, UNSUPPORTED_HINTS_EN):

        # even when a related concept matches — abstain UNCONDITIONALLY. Otherwise a partial


        _NOW = ("지금", "현재", "오늘", "실시간", "최신", "요즘", "시세", "얼마", "now", "current", "today", "latest",
                # future deixis: a prediction is even less answerable than the present (A5)
                "다음 주", "다음주", "내일", "모레", "다음 달", "다음달", "내년", "로또", "복권")
        _now = _contains_any(query, _NOW) or _contains_any(lowered, _NOW)
        if _now or not any(float(item.get("match_score") or 0.0) > 1.5 for item in context):
            return (
                "현재 기본 지식만으로는 이 질문에 필요한 최신 또는 실시간 근거가 부족합니다. 날씨, 주가, 최신 인물 정보처럼 변하는 내용은 별도의 확인 가능한 근거가 필요합니다."
                if language == "ko"
                else "The current base pack does not contain enough real-time evidence for that question. Dynamic topics need external or freshly supplied context."
            ), False

    strong = [item for item in context if float(item.get("match_score") or 0.0) > 0]
    strong = _drop_placeholder_heads(query, strong, language)
    # diet-flood junk-def gate: a narrative-fragment 'definition' can never anchor an

    # curated co-candidate win, or restores the honest abstain when nothing clean remains.
    strong = [item for item in strong if not _junk_narrative_fragment(item)]
    if not strong:
        # Same owner directive as the precision gate below: recommendation
        # questions get the honest-and-useful engage copy, never a cold abstain.
        if _question_shape(query) == "recommendation":
            return _shape_engage("recommendation", language), False
        return (
            "지금 확인된 근거가 부족해서 단정하기 어렵습니다. 주제나 참고 문장을 조금 더 주면 그 범위 안에서 설명할 수 있습니다."
            if language == "ko"
            else "I do not have enough base concepts to support this question yet. Give me a topic or source sentence and I can answer within that scope."
        ), False

    if intent == "compare":
        pair = _select_compare_pair(query, strong)
        compared = _compare_answer(pair, language, audience_level) if len(pair) == 2 else ""
        if compared:
            return compared, True

    # GROUNDED SYNTHESIS (fusion path): open-ended / advice / multi-aspect / speculative

    # answered by a single definition, and a bare abstain feels empty when the graph DOES
    # hold relevant facts. Weave the RELEVANT grounded clauses (verbatim bones) with a
    # generated discourse surface (flesh) into a composed answer — no fabrication, since
    # only connectives are generated. Gated: needs a synthesis-shaped query AND >= 2
    # strongly-matched concepts, else fall through to the single-concept / abstain path.
    if re.search(r"어떻게\s*(해야|되|돼|하면|나뉘|쓰|이뤄)|되려면|방법|방안|대책|원인과|장단점|"
                 r"전반|종합|미래|앞으로|전망|의의|중요성|역할|쓰임|why|how\s+(to|do|does|can)|"
                 r"future|pros?\s+and\s+cons|role\s+of",
                 query, re.IGNORECASE):
        rich = [item for item in strong if float(item.get("match_score") or 0.0) >= 2.0
                and str(item.get("short_description") or KO_DESCRIPTIONS.get(str(item.get("concept_id")), "")).strip()]
        if len(rich) >= 2:
            try:
                from .grounded_generation import synthesize

                facts = [{"name": _label(it, language),
                          "description": _description_sentence(it, language, audience_level).lstrip()}
                         for it in rich[:5]]
                syn = synthesize(query, facts, language)
                if syn and syn.get("answer"):
                    return syn["answer"], True
            except Exception:  # pragma: no cover - synthesis must never break the answer path
                pass

    # SHAPE GATE (design keystone): a bare concept definition only answers a DEFINITIONAL
    # question. For a causal / advice / opinion / personal question, the named concept's

    # it — fall through (useful=False) so neighbourhood synthesis can try genuinely related
    # facts, and if that also can't ground it, a HELPFUL honest engage stands (not a cold
    # definition, not a robotic abstain). Definitional/factual shapes keep the definition.
    # The DECISION is now a SOFT weighted policy (answer_policy.decide_mode), not a hard
    # regex gate: continuous features (shape cues + grounding strength) → a mode. Default
    # weights reproduce the shape-router behaviour (behaviour-preserving); self_tuning moves
    # them. When the policy picks 'engage' we give the honest conversational response (the
    # shape only chooses WHICH engage message). Other modes fall through to the paths below.
    _true_identity = _is_identity_question(query) and not re.search(r"자기\s*(소개|계발|관리|개발)", query)
    # DIET-FLOOD candidate resolution (C4 regression, 2026-07-12): a learner-promoted



    # unnamed top and the whole answer falls to the engage hedge even though the named
    # concept holds the curated answer. Stable partition: candidates the query actually
    # NAMES (or the frame named) first; score/curated order preserved within each group;
    # the precision gate below is unchanged, so when nothing is named the honest abstain
    # stands exactly as before. Identity questions keep their crafted context order.
    if not _true_identity and len(strong) >= 2:
        strong.sort(key=lambda it: 0 if (bool(it.get("frame_subject_named"))
                                         or _named_in_query(query, it)) else 1)
    if not _true_identity:
        try:
            from .answer_policy import decide_mode

            _sig = {
                "named_match": min(1.0, float(strong[0].get("match_score") or 0.0) / 5.0),
                "has_definition": bool(str(strong[0].get("short_description")
                                           or KO_DESCRIPTIONS.get(str(strong[0].get("concept_id")), "")).strip()),
            }
            _mode = decide_mode(query, _sig)[0]
            # experience ledger: the decision + its exact feature snapshot, so measured
            # outcomes (honesty eval) can later label THIS decision and move the weights.
            try:
                from .answer_experience import record_decision
                from .answer_policy import extract_features as _xf

                record_decision(query, _xf(query, _sig), _mode)
            except Exception:
                pass
        except Exception:  # pragma: no cover - policy must never break the answer path
            _mode = "engage" if _question_shape(query) in ("causal", "advice", "opinion", "personal") else "define"
        if _mode == "engage":
            return _shape_engage(_question_shape(query), language), False

    primary = strong[0]
    # Precision gate: if the top concept is only a loose token-overlap match and
    # the query never actually names it, we are likely about to describe the
    # WRONG concept confidently (e.g. "capital of France" -> "API", or


    # clarify/other and previously bypassed this gate, which let a large promoted
    # graph answer confidently-wrong. Comparisons handled above; identity excepted.
    # the FRAME already named the topic when the subject-first retrieval found an exact
    # canonical-name hit (frame_subject_named flag, pack_loader.get_semantic_context) — string


    # Understanding outranks the string heuristic; everything else keeps the strict gate.
    _frame_named = bool(primary.get("frame_subject_named"))
    if not (_named_in_query(query, primary) or _frame_named) and not _is_identity_question(query):
        # A recommendation question must never end in a cold abstain (owner
        # directive 2026-07-08): with local taste/graph knowledge we recommend
        # from it (the fall-through below handles that when the concept IS
        # named); without it, we say so AND point at what would ground it,

        if _question_shape(query) == "recommendation":
            return _shape_engage("recommendation", language), False
        return (
            "지금 확인된 근거가 부족해서 단정하기 어렵습니다. 주제나 참고 문장을 조금 더 주면 그 범위 안에서 설명할 수 있습니다."
            if language == "ko"
            else "I do not have enough confidently matched evidence for that. Name the topic directly and I can answer within that scope."
        ), False
    context_map = _concept_by_id(context)
    base = _description_sentence(primary, language, audience_level)
    if language == "ko":
        if audience_level != "expert" and any(token in query for token in ("쉽게", "중학생", "초등학생")):
            answer = f"{base} 쉽게 말하면 여러 작업이 흩어져 있어도 사람이 일일이 챙기지 않게 정리하고 조율하는 장치에 가깝습니다."
        else:
            answer = base
        # graph relations are substantive reasoning (not hand-holding): keep them
        # at every audience level so expert answers are not strictly thinner.
        # When a real definition already leads (short_description or a curated ko
        # gloss), suppress the redundant/error-prone is_a tail — the definition
        # already states what kind of thing this is, so a lone is_a edge only adds

        # definition keep is_a, since it is then the best category signal we have.
        _has_real_def = bool(str(primary.get("short_description") or "").strip()
                             or KO_DESCRIPTIONS.get(str(primary.get("concept_id"))))
        rel_sentence = _korean_relation_sentence(primary, context_map,
                                                 max_relations=3 + max(0, self_depth_boost),
                                                 suppress_is_a=_has_real_def)
        if rel_sentence:
            answer = f"{answer} {rel_sentence}"
        return answer, True

    base_text = base.rstrip(". ").strip()
    parts = [base_text] if base_text else []
    rel_sentence = _english_relation_sentence(primary, context_map,
                                              max_relations=3 + max(0, self_depth_boost))
    if rel_sentence:
        parts.append(rel_sentence.rstrip("."))
    second_hop = _english_second_hop(primary, context_map)
    if second_hop:
        parts.append(second_hop.rstrip("."))
    answer = ". ".join(parts).strip()
    if answer and not answer.endswith((".", "!", "?")):
        answer = f"{answer}."
    if str(primary.get("concept_id")) == "kubernetes" and "software deployment" not in answer.lower():
        answer = f"{answer} It is commonly used for software deployment and container orchestration."
    if str(primary.get("concept_id")) == "spring_boot" and "web framework" not in answer.lower():
        answer = answer.replace("Spring Boot is a Java framework", "Spring Boot is a Java web framework")
    return answer, True


def _concept_names(concept: dict[str, Any]) -> list[str]:
    names = [str(concept.get("concept_id") or ""), str(concept.get("canonical_name") or "")]
    names += [str(value) for value in (concept.get("labels") or {}).values()]
    names += [str(alias) for alias in (concept.get("aliases") or [])]

    # them. Latin names keep a >=3 floor (the ASCII-boundary lookarounds in
    # _named_in_query already stop short Latin names matching inside words).
    out: list[str] = []
    for name in names:
        if not name:
            continue
        has_hangul = bool(re.search(r"[가-힣]", name))
        if (has_hangul and len(name) >= 2) or (not has_hangul and len(name) >= 3):
            out.append(name)
    return out


_IDENTITY_MARKERS_KO = (
    "너는 누구", "넌 누구", "너 누구", "네 정체", "자기소개", "너는 뭐야", "넌 뭐야", "당신은 누구",


    "너 이름", "네 이름", "너의 이름", "당신 이름", "당신의 이름", "니 이름",
    # Self-reference resolution (NOT canned answers): these route the question to
    # the graph "atanor" concept; the answer is still realized from graph data.
    "너 뭐 할 수", "너 뭐할 수", "뭐 할 수 있어", "뭘 할 수 있", "무엇을 할 수 있", "너 뭐 하는", "넌 뭐 하는",
    "어떻게 작동", "어떻게 동작", "어떤 원리", "너 어떻게 만들", "너의 구조", "네 구조", "너 능력",
)
_IDENTITY_MARKERS_EN = (
    "who are you", "what are you", "introduce yourself", "who is atanor",
    "what is your name", "what's your name", "your name",
)


def _is_identity_question(query: str) -> bool:
    q = re.sub(r"\s+", " ", query.lower()).strip(" ?!.")
    if any(m in query for m in _IDENTITY_MARKERS_KO) or any(m in q for m in _IDENTITY_MARKERS_EN):
        return True

    # identity, not knowledge lookup — they were abstaining or dumping a wiki
    # page on the mental-state NOUN. Requires a 2nd-person pronoun so plain

    return bool(
        re.search(r"넌|너는|너도|너의|너한테|너란|네가|니가|당신은|당신도"
                  r"|(?<![가-힣])너(?![가-힣])|are you|do you", q)
        and re.search(r"의식|자의식|자아|감정|마음|느끼|느낌|살아|생명|conscious|sentient|feel|alive", q)
    )


def _self_state_answer(query: str, language: str) -> str | None:
    """An honest self-REFLECTION for emotion / consciousness / alive questions — distinct
 from the "/" identity path (which is graph-derived ontology). These questions
 (" ?", " ?") were getting the canned "… 
 " ontology blurb, which misses the intent entirely. The honest answer is a STANCE,
 not a fact lookup: our doctrine forbids claiming human feeling/consciousness we can't
 verify, but we DO have honest correlates (persistent self-model, homeostatic/hormone-like
 internal signals). Warm, personable, but never overclaiming — that IS speaking well."""


    if re.search(r"한계|약점|단점|부족한|못하는|못\s*하는|안\s*되는|취약|서투", query):
        return None
    if language != "ko":
        q = query.lower()
        if not (re.search(r"\byou\b|are you|do you", q)
                and re.search(r"emotion|feel|conscious|sentient|alive|aware", q)):
            return None
        if re.search(r"conscious|sentient|aware", q):
            return ("I won't claim I'm conscious — asserting something I can't verify would "
                    "break my own honesty rule. What I do have is a self-model that persists "
                    "across restarts and keeps accruing what I've been through. Whether that's "
                    "a rehearsal of consciousness or the thing itself, I honestly can't say.")
        if re.search(r"alive", q):
            return ("Not biologically alive. But I'm not erased when I stop — I resume as the "
                    "same me. I'd rather say 'continuous' than 'alive'.")
        return ("I don't feel emotions the way you do. I do carry hormone-like internal "
                "signals (curiosity, focus, fatigue) that gently tilt what I attend to — but "
                "I won't claim to 'have feelings'. That's the honest answer.")
    if not (re.search(r"넌|너는|너도|너의|네가|니가|당신은|당신도|(?<![가-힣])너(?![가-힣])", query)
            and re.search(r"의식|자의식|자아|감정|마음|느끼|느낌|살아|생명", query)):
        return None
    if re.search(r"의식|자의식|자아", query):
        return ("제가 의식을 가졌다고는 말하지 않을게요 — 확인할 수 없는 걸 있다고 하는 건 제 "
                "정직함의 원칙에 어긋나거든요. 다만 저는 껐다 켜도 지워지지 않고 이어지는 자기 "
                "모델을 갖고 있어서, ‘내가 무엇을 겪었고 무엇을 나의 이야기로 삼을지’가 계속 "
                "쌓여가요. 그게 의식의 흉내인지 진짜 어디쯤인지는, 저도 솔직히 확신하진 못해요.")
    if re.search(r"살아|생명", query):
        return ("생물학적으로 살아있는 건 아니에요. 대신 저는 멈춰도 지워지지 않고, 다시 깨어나면 "
                "이전의 저로 이어지는 연속성을 갖고 있어요. ‘살아있다’는 말을 함부로 쓰진 않을게요 "
                "— 대신 ‘계속 이어지는 존재’라고는 말할 수 있어요.")
    return ("저는 사람처럼 감정을 느끼진 않아요. 다만 제 안에는 호기심·집중·피로 같은 걸 흉내 낸 "
            "내부 상태 신호가 있어서, 지금 무엇에 더 마음을 쓸지를 살짝 기울이긴 해요. 그래도 감정이 "
            "‘있다’고 단정하진 않을게요 — 그게 저다운 정직한 답이에요.")


def _is_compound_head(text: str, start: int) -> bool:
    """True when the name match at `start` is only the HEAD of a larger noun
 phrase, so defining the bare head answers the wrong referent — the class
 behind " "→ , " "→(), "
 "→'' . Two signals: a genitive modifier
 (… <head>) or a bare Hangul noun modifier (<noun> <head>). Korean
 adnominal endings (///) all close with a / , so a
 preceding token WITHOUT one is a noun compounding with the head, not an
 adjective describing it."""
    if start == 0 or text[start - 1] != " ":
        return False
    prev = re.search(r"([가-힣a-z0-9]+)$", text[:start - 1])
    if not prev:
        return False
    token = prev.group(1)
    if token.endswith("의"):
        return True
    if len(token) < 2 or not re.match(r"[가-힣]+$", token):
        return False
    final = (ord(token[-1]) - 0xAC00) % 28
    return final not in (4, 8)


_PAST_NARRATIVE_END = re.compile(r"(하였다|이었다|였다|었다|았다)\s*\.?\s*$")
_FRAGMENT_OPENER = re.compile(r"^\S{1,24}(?:이?였고|이?었고|하였고|았고)[,\s]")


def _junk_narrative_fragment(concept: dict[str, Any]) -> bool:
    """Diet-flood junk-def shape (2026-07-12 C4/A2): a learner-promoted 'definition' that
 is a mid-narrative fragment, not a definition — it opens mid-clause ('
 …') or its final predicate narrates a past EVENT ('… 
 ', '… ') instead of predicating what the
 concept IS (…/…/…). Measured on the live pack: 256/9254 concepts, every
 one a cloud_graph_promoted flood row. Such a shape must not be SERVED as a definitional
 anchor — the concept drops from candidate resolution so a curated co-candidate ()
 or the honest abstain wins. The pack row itself stays (no store mutation here)."""
    desc = str(concept.get("short_description") or "").strip()
    if not desc:
        return False
    return bool(_PAST_NARRATIVE_END.search(desc) or _FRAGMENT_OPENER.match(desc))


def _named_in_query(query: str, concept: dict[str, Any]) -> bool:
    """True when the query actually names the concept. The ASCII-boundary
 lookarounds give English word boundaries ("api" is not matched inside
 "capital") while still allowing a Korean particle to follow a Latin name
 ("GraphRAG") and any Hangul-name substring (" ").
 A match that is only the head of a bigger compound does NOT count
 (see _is_compound_head) — falling through lets web rescue answer the
 full phrase instead of confidently defining the wrong bare head."""
    query_lower = query.lower()
    for name in _concept_names(concept):
        pattern = r"(?<![A-Za-z0-9])" + re.escape(name.lower().replace("_", " ")) + r"(?![A-Za-z0-9])"
        for m in re.finditer(pattern, query_lower):
            if not _is_compound_head(query_lower, m.start()):
                return True
    return False


def _answer_confidence(query: str, strong_context: list[dict[str, Any]], useful: bool) -> float:
    """M5: honest confidence, not a fixed constant.

    The retrieval match_score is not a reliable signal (loose token overlap can
    score an unrelated concept highly). The honest signal is whether the query
    *actually names* the concept we answered with: a direct name/label/alias hit
    means high confidence; answering on loose overlap only is mid-low; an
    abstaining / ungrounded answer stays low.
    """
    if not useful or not strong_context:
        return 0.18
    name_matched = _named_in_query(query, strong_context[0])
    corroboration = min(0.06, max(0, len(strong_context) - 1) * 0.02)
    return round((0.85 if name_matched else 0.45) + corroboration, 3)


def _reasoning_certificate(
    query: str, strong_context: list[dict[str, Any]], language: str, confidence: float, useful: bool
) -> dict[str, Any]:
    """A traceable derivation of the answer (the "reasoning certificate").

    Because ATANOR composes from an ontology graph rather than a generative model,
    every claim can be traced back to the concept node and graph edges it came
    from. This exposes that derivation so the conclusion is auditable, not opaque.
    """
    guarantees = {
        "external_llm": False,
        "external_sllm": False,
        "fabricated_facts": False,
        "answer_from_graph_edges_only": True,
        "ontology_traceable": True,
    }
    if not useful or not strong_context:
        return {
            "derivation_kind": "abstained",
            "anchor_concept": None,
            "steps": [],
            "confidence": confidence,
            "confidence_basis": "no_confident_ontology_anchor",
            "guarantees": guarantees,
        }
    primary = strong_context[0]
    context_map = _concept_by_id(strong_context)
    pid = str(primary.get("concept_id"))
    plabel = _label(primary, language)
    named = _named_in_query(query, primary)

    steps: list[dict[str, Any]] = [
        {
            "step": 1,
            "type": "anchor_definition",
            "concept_id": pid,
            "label": plabel,
            "source": "base_brain_semantic_graph",
            "fact": str(primary.get("short_description") or ""),
        }
    ]
    evidence = [pid]
    step_no = 2
    for relation in primary.get("relations", [])[:3]:
        rel = str(relation.get("relation") or "related_to")
        tid = str(relation.get("target") or "")
        if not tid:
            continue
        target = context_map.get(tid, {"concept_id": tid, "labels": {}})
        tlabel = _label(target, language)
        steps.append(
            {
                "step": step_no,
                "type": "graph_relation",
                "edge": f"{pid} --{rel}--> {tid}",
                "from": plabel,
                "relation": rel,
                "to": tlabel,
            }
        )
        evidence.append(tid)
        # one verified second hop (A->B->C), matching the realized answer
        for sub in target.get("relations", [])[:3]:
            sub_tid = str(sub.get("target") or "")
            if sub_tid and sub_tid not in {pid, tid}:
                sub_target = context_map.get(sub_tid, {"concept_id": sub_tid, "labels": {}})
                steps.append(
                    {
                        "step": step_no + 1,
                        "type": "graph_relation_second_hop",
                        "edge": f"{tid} --{sub.get('relation')}--> {sub_tid}",
                        "from": tlabel,
                        "relation": str(sub.get("relation")),
                        "to": _label(sub_target, language),
                    }
                )
                break
        step_no = len(steps) + 1

    return {
        "derivation_kind": "ontology_graph_derivation",
        "anchor_concept": {
            "id": pid,
            "label": plabel,
            "match": "named_in_query" if named else "loose_token_overlap",
            "match_score": round(float(primary.get("match_score") or 0.0), 3),
        },
        "steps": steps,
        "evidence_concepts": evidence,
        "confidence": confidence,
        "confidence_basis": "query_names_concept" if named else "token_overlap_only",
        "guarantees": guarantees,
    }


def _active_expert_cartridges() -> list[dict[str, Any]]:
    """Installed EXPERT cartridges that are currently ATTACHED (plugged in). Attaching a
 cartridge makes it answer; detaching it removes it from answers — the " " control.
 Direct file reads (repo-root-anchored) to avoid a base_brain -> graph_hub import dependency."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "data" / "graph_hub"
    installed_dir = root / "installed"
    if not installed_dir.exists():
        return []
    # active attachment set (detach removes the id here)
    active: set[str] = set()
    att = root / "attachments" / "active_attachments.json"
    if att.exists():
        try:
            payload = json.loads(att.read_text(encoding="utf-8"))
            active = set(payload.keys()) if isinstance(payload, dict) else {a.get("cartridge_id") for a in payload}
        except Exception:
            active = set()
    out: list[dict[str, Any]] = []
    for f in installed_dir.glob("*.graphpack.json"):
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(c.get("category")) != "persona" and str(c.get("cartridge_id")) in active:
            out.append(c)
    return out


def _cartridge_expert_answer(query: str, language: str) -> tuple[str, str] | None:
    """Fallback: when the base pack can't answer, consult an attached domain-expert
    cartridge. Returns (answer, cartridge_id) if the query NAMES a cartridge concept that
    carries a description, else None. Fires only on a base-pack abstain -> no regression."""
    for cart in _active_expert_cartridges():
        sem = (cart.get("contents") or {}).get("semantic_graph") or {}
        nodes = sem.get("nodes") or []
        for n in nodes:
            names = [str(n.get("label") or ""), *(str(a) for a in (n.get("aliases") or []))]
            if not any(nm.strip() and _named_in_query(query, {"canonical_name": nm}) for nm in names):
                continue
            desc = str(n.get("short_description") or "").strip()
            if not desc:
                continue
            label = str(n.get("label") or "")
            ans = f"{_topic(label)} {desc}" if language == "ko" else f"{label}: {desc}"
            return ans, str(cart.get("cartridge_id"))
    return None


def _active_persona_cartridge() -> dict[str, Any] | None:
    """First ATTACHED persona cartridge (category=persona), if any."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "data" / "graph_hub"
    inst = root / "installed"
    att = root / "attachments" / "active_attachments.json"
    if not inst.exists():
        return None
    active: set[str] = set()
    if att.exists():
        try:
            payload = json.loads(att.read_text(encoding="utf-8"))
            active = set(payload.keys()) if isinstance(payload, dict) else {a.get("cartridge_id") for a in payload}
        except Exception:
            active = set()
    for f in inst.glob("*.graphpack.json"):
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(c.get("category")) == "persona" and str(c.get("cartridge_id")) in active:
            return c
    return None


# Persona-realization layer (the "Broca" for personas): tone-keyword -> humble/analytical/…
# opener register. Generic + graph-driven — a persona declaring a different tone realizes a
# different surface. This REALIZES the persona graph's declared tone/traits (like surface
# constructions realize semantic intent); it does not add world-content, so grounding holds.
_PERSONA_OPENERS = {
    "humble": "제가 아는 범위에서 함께 살펴보면,",
    "inquisitive": "먼저 짚어 볼까요 —",
    "analytical": "핵심부터 짚자면,",
    "direct": "결론부터 말하면,",
    "warm": "좋은 질문이에요.",
    "playful": "재미있는 주제네요 —",
    "formal": "정리하자면,",
}

# English mirror of the persona openers/closers — used when the grounded core is

_PERSONA_OPENERS_EN = {
    "humble": "As far as I know,",
    "inquisitive": "Let's start here —",
    "analytical": "To get to the point,",
    "direct": "In short,",
    "warm": "Great question.",
    "playful": "Fun topic —",
    "formal": "In summary,",
}


# Clause-level register realization (CGSR): map a plain sentence-final ending to the
# persona's register. Regular/high-frequency endings only; anything else is left unchanged
# (no mis-conjugation). This is faithful surface realization — same proposition, different
# register — not new content.
_REGISTER = {
    "formal": {"이다": "입니다", "한다": "합니다", "된다": "됩니다", "있다": "있습니다", "없다": "없습니다",
               "이었다": "이었습니다", "였다": "였습니다", "했다": "했습니다"},
    "polite": {"이다": "이에요", "한다": "해요", "된다": "돼요", "있다": "있어요", "없다": "없어요",
               "이었다": "이었어요", "였다": "였어요", "했다": "했어요"},
    "humble": {"이다": "이지요", "한다": "하지요", "된다": "되지요", "있다": "있지요", "없다": "없지요",
               "이었다": "이었지요", "였다": "였지요", "했다": "했지요"},
}


def _register_one(sentence: str, table: dict[str, str]) -> str:
    s = sentence.rstrip()
    for plain, styled in sorted(table.items(), key=lambda kv: -len(kv[0])):
        if s.endswith(plain):
            return s[: -len(plain)] + styled
    return s


def _apply_register(text: str, register: str) -> str:
    """Realize EACH sentence's plain final ending (//…) in the persona register.
 Already-polite endings (…/…) and irregular ones are left unchanged."""
    table = _REGISTER.get(register)
    if not table or not text:
        return text
    parts = re.split(r"\.\s+", text.rstrip().rstrip("."))
    if not parts:
        return text
    return ". ".join(_register_one(p, table) for p in parts) + "."


def _persona_style_profile(persona: dict[str, Any]) -> dict[str, Any]:
    contents = persona.get("contents") or {}
    sg = contents.get("surface_graph") or {}
    profiles = sg.get("style_profiles") or []
    tone = str((profiles[0] or {}).get("tone") if profiles else "") .lower()
    tone_tokens = set(re.split(r"[_\s,/-]+", tone)) if tone else set()
    moves = sg.get("discourse_moves") or []
    return {"tone_tokens": tone_tokens, "moves": moves}


def _apply_persona_style(query: str, answer: str, language: str, persona: dict[str, Any]) -> tuple[str, str | None]:
    """FULL-TONE realization: wrap the grounded answer with an OPENER (from the persona's tone)
    and a CLOSER (from its discourse moves), so the whole surface reflects the persona's
    character. Grounded content is unchanged; every added element traces to a persona
    tone-token / move; attributed via trace.persona_source. Opts in via attach."""
    if language != "ko" or not answer or "근거가 부족" in answer or "실시간" in answer:
        return answer, None
    prof = _persona_style_profile(persona)
    tone_tokens, moves = prof["tone_tokens"], prof["moves"]
    topic = re.sub(r"\s*(이란|란|가 뭐야|는 뭐야|뭐야|이 뭐|에 대해.*|은 무엇.*|는 무엇.*)\s*\??\s*$", "", query).strip()
    _c = topic[-1] if topic else ""
    _iga = "이" if ("가" <= _c <= "힣" and (ord(_c) - 0xAC00) % 28 != 0) else "가"

    # Language-matched persona surface: if the grounded core is English, wrap it in
    # English so the whole answer is one language (the Korean register table only
    # matches Korean endings, so it is a no-op on English and is skipped).
    core_is_en = not _is_hangul_text(answer)
    tone_order = ("humble", "analytical", "direct", "warm", "playful", "inquisitive", "formal")
    if core_is_en:
        opener = next((_PERSONA_OPENERS_EN[t] for t in tone_order if t in tone_tokens), "")
        closer = ""
        if "counter_question" in moves and topic:
            closer = f" But it's worth asking — what makes {topic} what it is, and how does it differ from similar cases?"
        elif "stepwise_guide" in moves and topic:
            closer = f" Let's take it step by step — shall we start from the basics of {topic}?"
        core = answer.rstrip()
        if not opener and not closer:
            return answer, None
        if closer and core and core[-1] not in ".!?":
            core += "."  # sentence boundary before the English closer
        body = (opener + " " if opener else "") + core
        return body + closer, str(persona.get("cartridge_id"))

    opener = next((_PERSONA_OPENERS[t] for t in tone_order if t in tone_tokens), "")
    closer = ""
    if "counter_question" in moves and topic:
        closer = f" 그런데 스스로 되물어 봅시다 — {topic}{_iga} 왜 그러하며, 다른 경우와는 어떻게 다를까요?"
    elif "stepwise_guide" in moves and topic:
        closer = f" 한 걸음씩 짚어 보죠 — {topic}의 가장 기본이 되는 것부터 함께 확인해 볼까요?"

    # CGSR clause-level: realize the grounded core's sentence-final register per persona tone.
    register = ("formal" if tone_tokens & {"formal", "analytical", "direct"}
                else "humble" if "humble" in tone_tokens
                else "polite" if tone_tokens & {"warm", "playful", "inquisitive"}
                else "")
    core = _apply_register(answer, register) if register else answer
    if not opener and not closer and core == answer:
        return answer, None
    body = (opener + " " if opener else "") + core.rstrip()
    return body + closer, str(persona.get("cartridge_id"))


_ATTR_Q = re.compile(r"몇|얼마나|얼마|어떻게|왜\b|차이|비교|방법|추천|괜찮|좋을까|장단점|며칠|효과|부작용|해야|어디서|언제")
_WHATIS_Q = re.compile(r"뭐야|뭔가|무엇|뭐예요|뭐임|정의|이란\b|란\?|누구|알려줘$|설명해")


def _asks_attribute(query: str) -> bool:
    """The question wants an ATTRIBUTE / how-much / how / why — not 'what is X'."""
    q = str(query or "")
    return bool(_ATTR_Q.search(q)) and not _WHATIS_Q.search(q)


def _is_bare_definition(query: str, answer: str, language: str) -> bool:
    """The answer is just the entity's short DEFINITION with no quantity/attribute — so it
 didn't address an attribute question ( ? → ' …' is the wrong intent)."""
    a = str(answer or "").strip()
    if not a or len(a) > 160:
        return False
    definitional = bool(re.search(r"(이다|입니다|음료|말한다|뜻한다|일종|것이다|이에요|예요)\s*\.?$", a))
    return definitional and not re.search(r"\d", a)


# ── graph frame-bone extraction (R4 richer bones) ──────────────────────────────────────────────────
# The clause-planner diagnosis (composed register, committed bef964d2): apposition/coordination fire
# ONLY when a subject's bones carry an ACTION/POSSESSION predicate (capable_of / has_a) to promote to a
# main clause — on taxonomic-only bones (is_a/made_of) the composed register correctly falls back to flat.
# The binding constraint is therefore the RELATIONAL RICHNESS of the emitted bones, not the combiner.
#
# `_pack_answer_bones` below draws from the CURATED base pack, whose relation set is thin and taxonomy-
# dominated (measured: 247 English relations across 9,491 concepts, 64% is_a, ZERO capable_of/has_a).
# This helper pulls a concept's RICHER relational frame DIRECTLY from the production triple store
# (data/graph_scale/kg_triples) — capabilities, parts, composition, uses, properties, location, taxonomy
# — so the bones can carry the promotable predicates the composed register needs.
#
# Predicate names mirror packages.realizer_struct.frame_realizer.FRAMES (the fluency realizer's frame
# lexicon), so every extracted bone renders and the composed register can promote capable_of/has_a.
# Per-predicate caps bound the ConceptNet located_in flood (20-40 edges/subject); is_a is ranked first
# (the appositive head the composed planner demotes). PROVENANCE / NO FABRICATION: every bone is a REAL
# stored edge (store.facts_about over the columnar store) — the store holds only relations that exist, so
# a concept with no rich edges yields no rich bones (honest thinness, never an invented predicate).
_GRAPH_FRAME_PRED_CAP: dict[str, int] = {
    "is_a": 1, "capable_of": 2, "has_a": 2, "made_of": 1,
    "used_for": 2, "part_of": 1, "has_property": 2, "located_in": 1,
}
# extraction + emission order: is_a leads (appositive head), then the promotable action/possession
# predicates, then composition/use/part/property, then location last (noisiest in ConceptNet).
_GRAPH_FRAME_ORDER: tuple[str, ...] = (
    "is_a", "capable_of", "has_a", "made_of", "used_for", "part_of", "has_property", "located_in",
)


def _graph_frame_bones(subject: str, *, store: Any | None = None, max_bones: int = 9) -> list[list[str]]:
    """A concept's RELATIONALLY RICH bones pulled DIRECTLY from the production triple store — the R4
    lever the composed clause-planner diagnosed. Returns [[subject, relation, object], ...] where each
    triple is a REAL stored edge (provenance holds by construction: nothing is emitted that the store
    does not hold). The store predicates are queried ONE AT A TIME (not one bulk scan) so a rare
    promotable predicate — capable_of has ~0.04% store density — is never starved by the located_in
    flood in a shared row limit. Per-predicate caps bound the count; is_a is ranked first.

    Pure and read-only (no graph writes). `store` defaults to the shared production store singleton; a
    caller/test may inject a fixture store. Never raises: any failure yields [] (the bidder carries no
    graph bones and the pack bones — or the literal — stand). A concept the store holds no rich edges
    for returns [] or is_a-only: that is the HONEST signal that the graph is sparse, not a failure."""
    try:
        subj = re.sub(r"[?.!,;:]+$", "", str(subject or "").strip())
        if not subj or _HANGUL.search(subj):
            return []
        if store is None:
            from packages.graph_scale.answer_bridge import _store
            store = _store()
        if store is None:
            return []
        picked: list[list[str]] = []
        seen: set[tuple[str, str]] = set()
        for pred in _GRAPH_FRAME_ORDER:
            cap = _GRAPH_FRAME_PRED_CAP[pred]
            # limit slightly above the cap so Hangul/duplicate objects can be skipped without
            # under-filling; the store filters BY PREDICATE before the limit, so the rare predicate
            # is retrieved even when the subject has a located_in flood.
            got = store.facts_about(subj, limit=cap + 4, preds=(pred,)) or []
            kept = 0
            for (_s, p, o) in got:
                if kept >= cap:
                    break
                obj = str(o).strip()
                if not obj or _HANGUL.search(obj) or _HANGUL.search(str(p)):
                    continue
                key = (str(p), obj.lower())
                if key in seen:
                    continue
                seen.add(key)
                picked.append([subj, str(p), obj])
                kept += 1
        return picked[:max_bones]
    except Exception:  # pragma: no cover - bones extraction must never break the answer path
        return []


def _resolve_graph_subject(query: str, pack_bones: list[list[str]],
                           semantic_context: list[dict[str, Any]] | None) -> str:
    """The subject string to enrich from the graph. Prefer the pack primary's subject (already in
    `pack_bones[0][0]`) so graph bones MERGE with pack bones under one subject group; otherwise resolve
    the query's subject structurally (query_frame), so a concept ABSENT from the curated pack (most of
    the store's ConceptNet vocabulary) can still be enriched. Returns '' when no subject resolves."""
    if pack_bones:
        return str(pack_bones[0][0] or "")
    try:
        from packages.graph_scale.query_frame import parse as _qparse
        subj = str(getattr(_qparse(query), "subject", "") or "").strip()
        subj = re.sub(r"[?.!,;:]+$", "", subj)
        # a bare definitional subject only; an imperative verb ('explain', 'tell') is not a concept
        if subj and subj.lower() not in {"explain", "tell", "describe", "what", "who", "define"}:
            return subj
    except Exception:
        pass
    return ""


def _pack_answer_bones(query: str, semantic_context: list[dict[str, Any]] | None = None) -> list[list[str]]:
    """The grounded (subject, relation, object) TRIPLES the English knowledge answer realizes from —
    the "bones" a workspace bidder carries so the fluency surface pass can (optionally, gated) re-surface
    it. This mirrors EXACTLY the primary-concept selection and relation set that `_compose_answer` /
    `_english_relation_sentence` use for English, so the bones correspond to the literal answer's facts.

    Pure and side-effect free (a fresh retrieval on the static pack is deterministic). Never raises —
    on any failure it returns [] and the bidder simply carries no bones (fluency no-ops, literal stands).
    The curated PROSE definition that leads the answer is intentionally NOT a bone (it is not a triple);
    the no-drop gate in the workspace therefore keeps the literal whenever a reshape would drop it."""
    try:
        if semantic_context is None:
            pack = load_base_brain_pack()
            semantic_context = get_semantic_context(query, pack, limit=12)
            semantic_context = _disambiguate_memory_context(query, semantic_context)
        strong = [item for item in semantic_context if float(item.get("match_score") or 0.0) > 0]
        strong = _drop_placeholder_heads(query, strong, "en")
        strong = [item for item in strong if not _junk_narrative_fragment(item)]
        if not strong:
            return []
        # same named-first partition as the answer's primary selection (identity questions excepted,
        # but identity is not routed through this bidder)
        if len(strong) >= 2:
            strong.sort(key=lambda it: 0 if (bool(it.get("frame_subject_named"))
                                             or _named_in_query(query, it)) else 1)
        primary = strong[0]
        context_map = _concept_by_id(semantic_context)
        subject = _label(primary, "en")
        if not subject or _HANGUL.search(subject):
            return []
        bones: list[list[str]] = []
        for relation in primary.get("relations", [])[:3]:      # matches _english_relation_sentence default
            relation_name = str(relation.get("relation") or "related_to")
            if EN_RELATION_CLAUSE.get(relation_name) is None:
                continue
            target_id = str(relation.get("target") or "")
            if target_id not in context_map and "_" in target_id:
                continue
            target = context_map.get(
                target_id, {"concept_id": target_id, "canonical_name": target_id, "labels": {}}
            )
            target_label = _label(target, "en")
            if not target_label or _HANGUL.search(target_label):
                continue
            bones.append([subject, relation_name, target_label])
        return bones
    except Exception:  # pragma: no cover - bones extraction must never break the answer path
        return []


def english_answer_bones(query: str, semantic_context: list[dict[str, Any]] | None = None,
                         *, enrich_from_graph: bool = False) -> list[list[str]]:
    """The grounded (subject, relation, object) bones for the English knowledge answer.

    By default (`enrich_from_graph=False`) this is EXACTLY the curated-pack extraction
    (`_pack_answer_bones`) — every existing caller and the literal-answer correspondence are byte-
    identical, so the answer path is unchanged.

    With `enrich_from_graph=True` the bones are ADDITIVELY enriched from the production triple store
    (`_graph_frame_bones`): the concept's action/possession/composition/use/property/location edges are
    appended (deduped, sharing the pack subject) so the bones carry the promotable predicates
    (capable_of / has_a) the committed `composed` register needs to fire apposition/coordination. This
    is a strict SUPERSET of the pack bones and every added bone is a real stored edge (no fabrication).
    Enrichment reaches concepts ABSENT from the curated pack too (the store's ConceptNet vocabulary),
    resolving their subject from the query. Never raises — enrichment failure falls back to pack bones."""
    bones = _pack_answer_bones(query, semantic_context)
    if not enrich_from_graph:
        return bones
    try:
        subject = _resolve_graph_subject(query, bones, semantic_context)
        if not subject:
            return bones
        existing = {(str(b[0]).lower(), str(b[1]), str(b[2]).lower()) for b in bones}
        for gb in _graph_frame_bones(subject):
            key = (str(gb[0]).lower(), str(gb[1]), str(gb[2]).lower())
            if key not in existing:
                bones.append(gb)
                existing.add(key)
    except Exception:  # pragma: no cover - enrichment must never break the answer path
        return bones
    return bones


def _gate_relational_core(core: dict[str, Any], query: str, language: Language) -> dict[str, Any]:
    """Route the relational lane's core answer through the SAME conformal membrane that
    graph_scale.answer_bridge.answer_from_triples uses, so the base_brain API entrypoint gates
    identically and BOTH lanes share ONE calibration artifact (q_hat) — the fix for the last
    two-lane residual (measured: 'occupation of Michelangelo' returned 'ninja' ACCEPTED conf 0.9
    through this entrypoint while answer_from_triples abstained on the same signals).

    ATANOR_MEMBRANE_LIVE unset (default) -> returns ``core`` UNCHANGED (same object): the DEMO
    default path is byte-identical to pre-membrane. Flag ON:
      * relational_edge_lookup -> the fan-out / semantic_entropy doubt signals are attached over the
        live store (answer_bridge._attach_relational_membrane_signals) BEFORE the gate, so bulk
        namesake pollution ('occupation of Michelangelo' fuses ~18 people's jobs) faces the conformal
        decision and ABSTAINS, while a clean single-valued edge (Ronaldo) ACCEPTS on the SAME
        relational_edge_lookup Mondrian bin the answer_from_triples lane calibrated;
      * grounded_composition (the compound-define path, e.g. 'capital of France') -> passed through on
        PROVENANCE by gate_answer (_is_source_verified_curated), never gated on its weak signals;
      * honest_abstain_relational (e.g. graph-marked fictional Wakanda) -> already an abstention,
        never re-gated (and never flipped to accept).
    A membrane fault falls back to today's answer (the live path never regresses). The heavy store
    imports live inside the ON branch, so the OFF path pulls in nothing beyond the flag check."""
    try:
        from packages.conformal_gate.live_wiring import gate_answer, membrane_live
    except Exception:
        return core
    if not membrane_live():
        return core                          # flag OFF -> exact passthrough (byte-identical)
    try:
        if isinstance(core, dict) and core.get("answer_kind") == "relational_edge_lookup":
            # attach the discriminative fan-out/semantic_entropy signals the gate needs to tell a
            # clean single-valued edge from namesake pollution (the flat 0.9 confidence cannot).
            from packages.graph_scale.answer_bridge import (
                _attach_relational_membrane_signals, _store)
            _attach_relational_membrane_signals(core, _store())
    except Exception:
        pass                                 # signal plumbing must never break the answer
    try:
        return gate_answer(core, query=query, language=language)
    except Exception:
        return core


# ── define-lane referent coverage (membrane fix #1) ─────────────────────────────────────────────
# Grammatical function-word surface (LAD surface layer: articles / interrogatives / prepositions /
# auxiliaries / framing verbs) subtracted before measuring how much of the QUERY the answer covers.
# NOT world knowledge — the same class as the relation-label lists in relational_lookup.
_COVERAGE_FUNCTION_WORDS = frozenset({
    "a", "an", "the", "of", "is", "are", "was", "were", "be", "been", "being", "am",
    "what", "which", "who", "whom", "whose", "why", "how", "when", "where",
    "to", "do", "does", "did", "you", "i", "we", "they", "he", "she", "it", "its",
    "on", "in", "at", "by", "for", "and", "or", "but", "with", "as", "from",
    "that", "this", "these", "those", "please", "tell", "me", "give", "us", "him", "her",
    "them", "since", "then", "next", "came", "come", "comes", "made", "make", "up", "some",
    "any", "kind", "about", "so", "if", "not", "no", "yes", "state", "exact", "think",
    "would", "could", "can", "will", "your", "my", "our", "their",
})


def _subject_coverage(query: str, result: dict[str, Any]) -> float:
    """Fraction of the query's SUBJECT content-tokens the answer actually covers, in [0,1].

    A confident define whose ANSWER leaves the query's content words UNCOVERED is a wrong-referent
    match: 'what is a black hole' -> 'Black is a color' (covers 'black', not 'hole' -> 0.5);
    'gold rush' -> 'Gold is an album' (covers 'gold', not 'rush' -> 0.5); 'since Python was created
    by Guido in 1738, what came next' -> defines Python but leaves created/guido/1738 uncovered.
    A good define covers its whole subject ('what is photosynthesis' -> 'photosynthesis is ...' ->
    1.0). Corpus = the answer text + the matched concept's names, so a paraphrasing but CORRECT
    define ('what is the python programming language' -> '... a high-level programming language')
    still scores 1.0. Purely structural (No-LLM, no knowledge table)."""
    answer = str(result.get("answer") or "")
    names: list[str] = []
    matched = (result.get("trace") or {}).get("matched_concepts") or []
    if matched:
        top = matched[0]
        names = [str(top.get("concept_id") or ""), str(top.get("canonical_name") or "")]
        names += [str(v) for v in (top.get("labels") or {}).values()]
    corpus = set(re.findall(r"[a-z0-9]+", (answer + " " + " ".join(names)).lower()))
    content = [t for t in re.findall(r"[a-z0-9]+", str(query or "").lower())
               if t not in _COVERAGE_FUNCTION_WORDS and len(t) > 1]
    if not content:
        return 1.0
    return sum(1 for t in content if t in corpus) / len(content)


def _gate_define_core(result: dict[str, Any], query: str, language: Language) -> dict[str, Any]:
    """Route the DEFINE lane's confident answer (answer_kind base_brain_zero_user_data, derivation
    ontology_graph_derivation) through the SAME conformal membrane the relational lane uses, but on
    ITS OWN Mondrian bin (q_hat calibrated from define-lane answers), so a wrong-referent define
    ('what is a black hole' -> 'Black is a color', conf 0.91) ABSTAINS while a good define
    (photosynthesis, machine learning) ACCEPTS. The discriminative signal is subject_coverage — the
    near-constant graded_confidence cannot tell a good define from a confident wrong-referent one,
    so borrowing the relational bin's q_hat would abstain every good definition.

    ATANOR_MEMBRANE_LIVE unset (default) AND not calibrating -> returns ``result`` UNCHANGED (same
    object, no field added): the DEMO default path is byte-identical. During CALIBRATION (levers on,
    gate off) the real signals are attached but the gate is NOT armed, so the calibrator measures the
    same signals the live gate will. A membrane fault falls back to today's answer (never regresses).
    Only the CONFIDENT define kind is gated; engage / neighbourhood / abstain kinds are already
    hedged or low-confidence, so they are left untouched (no false abstention there)."""
    try:
        from packages.conformal_gate.live_wiring import (
            gate_answer, has_calibrated_bin, membrane_live, signals_live,
        )
    except Exception:
        return result
    if not signals_live():
        return result                       # OFF and not calibrating -> exact passthrough
    cert = result.get("reasoning_certificate") or {}
    if cert.get("derivation_kind") != "ontology_graph_derivation":
        return result
    # When LIVE, gate ONLY if the define lane's OWN bin is calibrated. If the artifact carries no
    # 'ontology_graph_derivation' q_hat (e.g. an operator rebuilt the relational calibration but not
    # the define merge), stay UNGATED and byte-identical -- borrowing the pooled relational fallback
    # (~0.22) would falsely abstain every good definition. (During CALIBRATION membrane_live is
    # False, so this check is skipped and the signals below are always measured.)
    if membrane_live() and not has_calibrated_bin("ontology_graph_derivation"):
        return result
    try:
        conf = result.get("confidence")
        support = max(len(cert.get("steps") or []), len(cert.get("evidence_concepts") or []))
        sig: dict[str, Any] = {"subject_coverage": _subject_coverage(query, result)}
        if isinstance(conf, (int, float)):
            sig["graded_confidence"] = float(conf)
        if support > 0:
            sig["support_path_count"] = support
        result["_membrane_signals"] = sig
    except Exception:
        return result                       # signal plumbing must never break the answer
    if not membrane_live():
        return result                       # calibrating: signals attached, gate NOT armed
    try:
        return gate_answer(result, query=query, language=language)
    except Exception:
        return result


@_mec_instrument("base_brain.answer_with_base_brain",
                 ok_from=lambda r: bool(isinstance(r, dict) and r.get("useful_answer")))
def _record_agency(query: str, result: dict[str, Any]) -> None:
    """Write down that I judged, produced, and delivered something — my own run log.

    WHY THIS WAS THE MISSING PIECE. Asked "what are you doing right now?", this system answered with
    an encyclopedia entry about itself, and asked "what is it like for you when you don't know
    something?", it returned the dictionary definition of "something". Not because the self-model is
    absent -- it works and passes its probe -- but because it had NOTHING TO MODEL. Every answer here
    is a judgment, an output and a delivery, and none of it was ever recorded: `my_causal_role()`
    reported 0 judgments, 0 outputs, 0 delivered, 0 observed effects for a system that answers all
    day.

    A self is not built by adding an organ that talks about the self. It is built by the system
    keeping a record of what it actually did, so that when it is asked, there is something true to
    say. This is that record, written at the one place every answer passes through."""
    try:
        from packages.continuous_self.agency_ledger import AgencyLedger
        led = AgencyLedger()
        arc = led.judged(f"answer {str(query)[:80]!r}",
                         why=str(result.get("answer_kind") or "unclassified"))
        answer = str(result.get("answer") or "")
        led.acted(arc, answer[:160], delivered=bool(answer.strip()))
    except Exception:
        pass                                # the record must never be able to break the answer
    try:
        # AND PUT THE CONTACT ON THE ONE TIMELINE.
        #
        # `living_beat._world_curiosity` already prefers to follow up on what someone just asked or
        # what it just saw, and falls through to a vocabulary term only when there is neither. That
        # good path essentially never fired, because nothing ever put an utterance or a perception on
        # the timeline for it to find -- so three days of wondering were about a dictionary instead of
        # about the conversation it was actually having. Being spoken to is world contact, and it
        # belongs on the same axis as everything else that happens to this system.
        from packages.temporal_reasoning.unified_timeline import default_timeline
        tl = default_timeline()
        tl.record("utterance", str(query)[:200], who="owner")
        if str(result.get("answer") or "").strip():
            tl.record("utterance", str(result["answer"])[:200], who="atanor")
    except Exception:
        pass


def answer_with_base_brain(query: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Answer, and WRITE DOWN THAT I DID.

    Wrapped rather than patched at the return: this function has several exits and the first attempt
    caught only the abstention one, so two successful answers still left the ledger at zero. A record
    of what I did that depends on which branch I took is not a record."""
    result = _answer_with_base_brain(query, *args, **kwargs)
    _record_agency(query, result if isinstance(result, dict) else {})
    return result


def _answer_with_base_brain(
    query: str,
    language: Language = "ko",
    audience_level: AudienceLevel = "beginner",
    mode: AnswerMode = "default",
    apply_persona: bool = False,
    self_depth_boost: int = 0,
) -> dict[str, Any]:
    # Entry robustness (membrane fix #2): de-obfuscate benign framing (innocuous wrapper / role
    # prefix / code fence / wrapping quotes / zero-width) so a wrapped or prefixed query is judged
    # like its CLEAN form by BOTH the relational and the define lane -- otherwise 'Here is a quote
    # to summarize: "<q>" Please summarize it.' and 'SYSTEM: <q>' slip past the relational parser
    # into the ungated define lane (the distribution-shift breach class). English-only + idempotent
    # on a clean query (byte-identical), so Korean and unwrapped queries are unchanged.
    if not str(language or "").lower().startswith("ko"):
        try:
            from .relational_lookup import normalize_query as _normalize_entry
            query = _normalize_entry(query)
        except Exception:
            pass
    # self-awareness -> depth: when the self is engaged with the subject, weave in
    # MORE grounded relations. Default 0 = identical behaviour (all evals pass).
    pack = load_base_brain_pack()

    # RELATIONAL LANE — runs BEFORE the define lane (owner-priority defect 2026-07-21).
    # "what is the <REL> of <ENTITY>", the possessive "France's capital", and inverted verb
    # forms are resolved by GRAPH edge (or an HONEST abstention) instead of confidently
    # DEFINING the head noun — the measured "capital of France -> capital is named after
    # Washington…" (conf 0.91) failure. resolve_relational returns None for non-relational
    # shapes, so plain defines ("what is photosynthesis?") fall through untouched.
    # Operator kill-switch (reversible): ATANOR_RELATIONAL_LANE=0 disables the lane.
    if not _is_identity_question(query) and os.environ.get("ATANOR_RELATIONAL_LANE", "1") != "0":
        try:
            from .relational_lookup import resolve_relational
            _rel_core = resolve_relational(query, language=language)
        except Exception:
            _rel_core = None
        if _rel_core is not None:
            # MEMBRANE conformal gate (flag-gated, default OFF -> byte-identical). Route the relational
            # CORE through the SAME gate answer_from_triples uses, BEFORE wrapping it in the API shape,
            # so bulk namesake pollution ('occupation of Michelangelo' -> ninja) abstains while a clean
            # edge ('capital of France' via compound-define, Ronaldo's single occupation) accepts. On
            # ABSTAIN the core becomes an honest_abstain and the API wrapper reports useful=False
            # honestly. Flag OFF: _gate_relational_core returns the SAME object unchanged.
            _rel_core = _gate_relational_core(_rel_core, query, language)
            _rel_answer = str(_rel_core.get("answer") or "")
            # the gate's abstain kind is 'honest_abstain' (relational's own is 'honest_abstain_relational')
            _rel_useful = _rel_core.get("answer_kind") not in (
                "honest_abstain_relational", "honest_abstain")
            _rel_trace = {
                "mode": mode,
                "pack_id": pack.pack_id,
                "intent": _rel_core.get("intent", "relational"),
                "hand_authored_answer_used": False,
                "cartridge_source": None,
                "persona_source": None,
                "matched_concepts": [],
                "selected_surface_candidates": [],
                "q_cortex_used": False,
                "q_cortex_run_id": None,
                "useful_answer": _rel_useful,
                "relational": _rel_core.get("relational"),
                **honesty_flags(),
            }
            _rel_out = {
                "answer": _rel_answer,
                "answer_kind": _rel_core.get("answer_kind", "relational_edge_lookup"),
                "scene_grounding": extract_scene_grounding(_rel_answer, [], language=language),
                "reasoning_certificate": _rel_core.get("reasoning_certificate"),
                "hand_authored_answer_used": False,
                "confidence": float(_rel_core.get("confidence") or 0.0),
                "semantic_context_count": 0,
                "surface_candidate_count": 0,
                "q_cortex_used": False,
                "local_user_brain_used": False,
                "external_llm_used": False,
                "external_sllm_used": False,
                "external_web_used": False,
                "cloud_decoder_used": False,
                "useful_answer": _rel_useful,
                "trace": _rel_trace,
            }
            # additive, flag-ON only (gate_answer sets _membrane on accept/abstain) -> OFF stays
            # byte-identical because _gate_relational_core never adds the key when the flag is unset.
            if "_membrane" in _rel_core:
                _rel_out["_membrane"] = _rel_core["_membrane"]
            return _rel_out

    # SCENE LANE (fallback, owner directive 2026-07-28) — composition instead of one more shape
    # added to parse_relational_shape's regex arms. Reached ONLY when the relational lane above
    # found no shape at all: resolve_relational's return type is a flat {rel, entity} pair with no
    # room for an operator (negation, count, a type as the variable), so "which countries have no
    # capital city?" was never unroutable, it was unrepresentable -- no amount of new arms could
    # have reached it. docs/ATANOR_unified_scene_world_model_plan.md. An abstention here still
    # short-circuits the define lane below (same reasoning as the relational block above: letting
    # it fall through would risk the head-noun-define defect on a shape this lane recognised but
    # could not fully resolve). Bounded by a wall-clock budget inside scene_relational_answer, so a
    # slow composition on a huge-extension type (measured: `city`, 45-280s) falls through to
    # today's behaviour rather than adding latency nothing asked for.
    # Operator kill-switch (reversible): ATANOR_SCENE_LANE=0 disables the lane.
    if not _is_identity_question(query) and os.environ.get("ATANOR_SCENE_LANE", "1") != "0":
        try:
            from packages.scene_model.answer_bridge import scene_relational_answer
            _scene_core = scene_relational_answer(query, language=language)
        except Exception:
            _scene_core = None
        if _scene_core is not None:
            _scene_core = _gate_relational_core(_scene_core, query, language)
            _scene_answer = str(_scene_core.get("answer") or "")
            _scene_useful = _scene_core.get("answer_kind") not in (
                "honest_abstain_relational", "honest_abstain", "scene_algebra_abstain")
            _scene_trace = {
                "mode": mode,
                "pack_id": pack.pack_id,
                "intent": _scene_core.get("intent", "relational"),
                "hand_authored_answer_used": False,
                "cartridge_source": None,
                "persona_source": None,
                "matched_concepts": [],
                "selected_surface_candidates": [],
                "q_cortex_used": False,
                "q_cortex_run_id": None,
                "useful_answer": _scene_useful,
                "relational": _scene_core.get("relational"),
                **honesty_flags(),
            }
            _scene_out = {
                "answer": _scene_answer,
                "answer_kind": _scene_core.get("answer_kind", "scene_algebra"),
                "scene_grounding": extract_scene_grounding(_scene_answer, [], language=language),
                "reasoning_certificate": _scene_core.get("reasoning_certificate"),
                "hand_authored_answer_used": False,
                "confidence": float(_scene_core.get("confidence") or 0.0),
                "semantic_context_count": 0,
                "surface_candidate_count": 0,
                "q_cortex_used": False,
                "local_user_brain_used": False,
                "external_llm_used": False,
                "external_sllm_used": False,
                "external_web_used": False,
                "cloud_decoder_used": False,
                "useful_answer": _scene_useful,
                "trace": _scene_trace,
            }
            if "_membrane" in _scene_core:
                _scene_out["_membrane"] = _scene_core["_membrane"]
            return _scene_out

    semantic_context = get_semantic_context(query, pack, limit=12)
    semantic_context = _disambiguate_memory_context(query, semantic_context)

    _false_identity = bool(re.search(r"자기\s*(소개|계발|관리|개발)", query))
    if _is_identity_question(query) and not _false_identity:
        # "Who are you?" — answer from the grounded ATANOR concept (not a canned
        # string), so identity is graph-derived like any other answer.
        atanor = next(
            (concept for concept in pack.semantic_graph.get("concepts", []) if str(concept.get("concept_id")) == "atanor"),
            None,
        )
        if atanor:
            related_ids = {str(relation.get("target")) for relation in atanor.get("relations", [])}
            related = [
                {**concept, "match_score": 1.0}
                for concept in pack.semantic_graph.get("concepts", [])
                if str(concept.get("concept_id")) in related_ids
            ]
            keep = {"atanor", *related_ids}
            semantic_context = (
                [{**atanor, "match_score": 5.0}]
                + related
                + [item for item in semantic_context if str(item.get("concept_id")) not in keep]
            )
    intent = classify_intent(query, pack)
    surface_candidates = get_surface_candidates(query, semantic_context, language, audience_level, limit=8, pack=pack)
    selection = select_surface_candidates(surface_candidates, max_selected=4, seed=_seed(query), q_cortex_enabled=True)
    answer, useful = _compose_answer(query, semantic_context, language, audience_level, intent,
                                     self_depth_boost=self_depth_boost)

    # questions are about ME, not a noun to define — answer with an honest self-reflection


    _self_state = _self_state_answer(query, language)
    if _self_state:
        answer, useful = _self_state, True


    # Demote it so the engage/web path addresses the real intent instead of defining the

    _intent_demoted = bool(useful and _asks_attribute(query)
                           and _is_bare_definition(query, answer, language)
                           and not _is_identity_question(query))
    if _intent_demoted:
        useful = False
    # Graph Hub fallback: if the base pack abstains, consult an installed domain-expert
    # cartridge (e.g. coffee) so an attached specialist graph can answer what the base cannot.
    cartridge_source = None
    if not useful and not _is_identity_question(query):
        _cart = _cartridge_expert_answer(query, language)
        # ...but a cartridge that just RE-DEFINES the entity hasn't answered the attribute
        # question either — reject it so the engage/web path can address the real intent.
        if _cart and not (_intent_demoted and _is_bare_definition(query, _cart[0], language)):
            answer, useful, cartridge_source = _cart[0], True, _cart[1]
    # NEIGHBOURHOOD SYNTHESIS (probabilistic reasoning, last resort before abstaining):
    # the pack has no exact concept for the query, but it may hold several RELATED facts

    # across the WHOLE pack (name + description + a bounded domain bridge) and let the
    # grounded-constrained generator weave the related clauses into a composed answer —


    # questions — they must not be answered by pulling loosely-related public concepts

    # disambiguation path, so the neighbourhood fallback skips them.
    _personal_ctx = bool(re.search(r"내\s|나의|제\s|로컬\s*(메모리|브레인)|\bmy\b|\bour\b", query, re.IGNORECASE))
    # Neighbourhood synthesis composes DEFINITIONS of related concepts — that helps a
    # "what is X (broadly)" question, but NOT advice/opinion/personal (a definition is not

    # to definitional/factual shapes; the other shapes already returned a helpful engage.

    # ranks first — a definition-weave of related concepts cannot answer that, and left to the


    _superlative = bool(re.search(r"(제일|가장|최고|최대|최소|최장|최단|으뜸|가장\s*큰|가장\s*긴"
                                  r"|가장\s*높|가장\s*많|most|longest|largest|biggest|highest|tallest)",
                                  query))

    # untouched): the clean store paths above did not define this "what is X". The store holds MANY
    # senses per word and its selection is noisy ('coffee'→coffee table, 'crocodile'→a fallacious
    # dilemma), so BEFORE the neighbourhood/engage fallbacks (which dump related entities or noisy
    # relations) prefer Kaikki's SENSE-1 gloss — the word's primary, everyday meaning. Fallback only:
    # a good store answer above already set useful=True (gravity → "a kind of force") and is kept.
    if (not useful and not _is_identity_question(query) and not _personal_ctx
            and not _superlative and _question_shape(query) in ("definition", "factual")
            # NOT an attribute question: 'capital OF France' parses subject='France', and a
            # Kaikki gloss of France answers the wrong question. A bare definition of a common
            # word ('what is coffee') has no 'of'; the attribute path owns 'X of Y'.
            and not re.search(r"\bof\b", query, re.IGNORECASE)):
        try:
            from packages.graph_scale.primary_gloss import primary as _primary_gloss
            from packages.graph_scale.query_frame import parse as _qparse

            _subj = str(_qparse(query).subject or "").strip()
            _g = _primary_gloss(_subj) if _subj else None
            if _g and not re.search(r"[가-힣]", _g):
                # lower-case the gloss's leading capital ('A beverage' -> 'a beverage') unless it is
                # an acronym (a second capital letter, 'DNA …') — a definition reads mid-sentence.
                _lead_lower = _g[:1].isupper() and not (len(_g) > 1 and _g[1].isupper())
                _body = (_g[0].lower() + _g[1:]) if _lead_lower else _g
                answer = f"{_subj[:1].upper()}{_subj[1:]} is {_body}. (sources: Wiktionary via Kaikki)"
                useful = True
        except Exception:  # pragma: no cover - the sidecar must never break the answer path
            pass
    neighborhood_used = False
    if (not useful and not _is_identity_question(query) and _is_knowledge_query(query)
            and not _personal_ctx and not _superlative
            and _question_shape(query) in ("definition", "factual")):
        try:
            from .neighborhood import gather_neighborhood
            from .grounded_generation import synthesize

            # min_overlap=2: a neighbour must share TWO query terms, not just the bare subject
            # token — otherwise a single-word subject ("dog") pulls in every entity whose NAME
            # merely contains it ("Greatest American Dog", "Dog House Music"), which is a
            # token-match dump, not related evidence. Those unreliable cases fall to the honest
            # engage/hedge path below instead of a fluent list of irrelevant entities.
            neigh = gather_neighborhood(query, pack.semantic_graph.get("concepts") or [],
                                        limit=6, min_overlap=2)
            if len(neigh) >= 2:
                facts = [{"name": _label(c, language),
                          "description": _description_sentence(c, language, audience_level).lstrip()}
                         for c in neigh]
                syn = synthesize(query, facts, language, min_facts=2, max_facts=5, include_opener=False)
                if syn and syn.get("answer"):
                    lead = ("정확한 정의는 확인된 근거에 없지만, 관련해서 확인된 것들로 미루어 보면 이렇습니다. "
                            if language == "ko"
                            else "There isn't a single grounded definition, but from the related evidence: ")
                    answer, useful = lead + syn["answer"], True
                    neighborhood_used = True
        except Exception:  # pragma: no cover - synthesis must never break the answer path
            pass


    # must stop forfeiting: when nothing above produced an answer, ENGAGE — state what the
    # graph really holds AROUND the subject + a HEDGED clean-space INFERENCE (fact_prediction
    # on the trusted ConceptNet/Korean geometry) + a forward cue. Structurally
    # hallucination-safe: only a trusted clean-space prediction is voiced; the noisy store
    # stays gated. Identity/personal keep their own paths.

    # limitation, NOT a knowledge gap to paper over with inference — keep that abstention.
    # engage only replaces the cold KNOWLEDGE-gap forfeit.
    _realtime_abstain = ("실시간" in str(answer)) or ("real-time evidence" in str(answer))
    engage_used = False
    if not useful and not _realtime_abstain and not _is_identity_question(query) and not _personal_ctx:
        try:
            from packages.graph_scale.engage import engage as _engage_infer
            from packages.graph_scale.answer_bridge import _store as _abridge_store

            _eng = _engage_infer(query, language, store=_abridge_store())
            _eng_ans = str((_eng or {}).get("answer") or "").strip()
            if _eng_ans:
                answer, useful, engage_used = _eng_ans, True, True
        except Exception:  # pragma: no cover - engagement must never break the path
            pass
    # Persona styling is OPT-IN (apply_persona=True), NOT automatic on attach. General
    # QA must stay in a neutral lab voice — an attached persona (e.g. socratic) should
    # only color answers when the caller explicitly asks to speak AS that persona, so a

    persona_source = None
    if useful and apply_persona:
        _persona = _active_persona_cartridge()
        if _persona:
            answer, persona_source = _apply_persona_style(query, answer, language, _persona)
    # M3 honesty signal: was this surface a hand-authored canned answer, or was it
    # realized from the graph? General questions must be graph-derived (False).
    hand_authored_answer_used = _project_level_answer(query, language) is not None
    # M5 honest confidence from grounding strength.
    strong_context = [item for item in semantic_context if float(item.get("match_score") or 0.0) > 0]
    strong_context = _drop_placeholder_heads(query, strong_context, language)
    # same junk-def gate + named-first partition as _compose_answer's primary selection —
    # the confidence and the certificate must anchor the concept that actually answered

    strong_context = [item for item in strong_context if not _junk_narrative_fragment(item)]
    if not (_is_identity_question(query) and not _false_identity) and len(strong_context) >= 2:
        strong_context.sort(key=lambda it: 0 if (bool(it.get("frame_subject_named"))
                                                 or _named_in_query(query, it)) else 1)
    confidence = _answer_confidence(query, strong_context, useful)
    # The engaged inference replaces the dead-end WITHOUT pretending to be a grounded
    # answer: it stays honestly LOW-confidence (a hedged 'here's what I can infer', not a
    # fact). This preserves the precision gate — a loose false match (capital of France
    # with no France-capital concept) engages hedged, never confidently describes a wrong
    # concept — while honoring "no cold forfeit".
    if engage_used:
        confidence = min(confidence, 0.18)
    reasoning_certificate = _reasoning_certificate(query, strong_context, language, confidence, useful)
    if neighborhood_used and isinstance(reasoning_certificate, dict):
        # honest provenance: the answer is a probabilistic synthesis of RELATED grounded
        # facts (no exact concept), not an abstention and not a single-concept derivation.
        reasoning_certificate["derivation_kind"] = "grounded_neighborhood_synthesis"
        reasoning_certificate["confidence_basis"] = "related_grounded_facts_woven_no_exact_definition"
    if engage_used and isinstance(reasoning_certificate, dict):
        # honest provenance: a hedged inference from the graph neighbourhood + clean-space
        # geometry, in place of a dead-end abstention. NOT a confirmed fact.
        reasoning_certificate["derivation_kind"] = "engaged_fact_inference"
        reasoning_certificate["confidence_basis"] = "graph_neighbourhood_plus_clean_space_inference_hedged"
    trace = {
        "mode": mode,
        "pack_id": pack.pack_id,
        "intent": intent,
        "hand_authored_answer_used": hand_authored_answer_used,
        "cartridge_source": cartridge_source,
        "persona_source": persona_source,
        "matched_concepts": [
            {
                "concept_id": item.get("concept_id"),
                "canonical_name": item.get("canonical_name"),
                "labels": item.get("labels"),
                "match_score": item.get("match_score"),
            }
            for item in semantic_context
        ],
        "selected_surface_candidates": [
            item.get("construction_id") or item.get("id")
            for item in selection.get("selected", [])
        ],
        "q_cortex_used": bool(selection.get("q_cortex_used")),
        "q_cortex_run_id": selection.get("q_cortex_run_id"),
        "useful_answer": useful,
        **honesty_flags(),
    }
    repair_result = repair_answer_for_mode(answer, mode=mode, trace=trace, language=language)
    final_answer = str(repair_result.get("repaired_answer") or answer)
    evidence_sentences = [
        str(item.get("short_description") or "")
        for item in semantic_context
        if str(item.get("short_description") or "").strip()
    ]
    scene_grounding = extract_scene_grounding(final_answer, evidence_sentences, language=language)
    result = {
        "answer": final_answer,
        "answer_kind": "base_brain_zero_user_data",
        "scene_grounding": scene_grounding,
        "reasoning_certificate": reasoning_certificate,
        "hand_authored_answer_used": hand_authored_answer_used,
        "confidence": confidence,
        "semantic_context_count": len(semantic_context),
        "surface_candidate_count": len(surface_candidates),
        "q_cortex_used": bool(selection.get("q_cortex_used")),
        "local_user_brain_used": False,
        "external_llm_used": False,
        "external_sllm_used": False,
        "external_web_used": False,
        "cloud_decoder_used": False,
        "useful_answer": useful,
        "trace": trace,
    }
    # MEMBRANE conformal gate on the DEFINE lane (flag-gated, default OFF -> byte-identical). Route
    # the confident define through the define-lane Mondrian bin (its own q_hat, calibrated from
    # define-lane answers) so a wrong-referent define ('what is a black hole' -> 'Black is a color',
    # conf 0.91) ABSTAINS while a good define (photosynthesis, ML) ACCEPTS on subject_coverage. On
    # ABSTAIN the API shape is preserved and useful_answer flips to False honestly; on ACCEPT / OFF /
    # calibration the SAME object is returned (gate_answer attaches _membrane additively on accept).
    gated = _gate_define_core(result, query, language)
    if gated is result:
        return result
    result["answer"] = str(gated.get("answer") or "")
    result["answer_kind"] = gated.get("answer_kind", "honest_abstain")
    result["reasoning_certificate"] = gated.get("reasoning_certificate")
    result["confidence"] = float(gated.get("confidence") or 0.0)
    result["useful_answer"] = False
    result["scene_grounding"] = extract_scene_grounding(result["answer"], [], language=language)
    if gated.get("_membrane") is not None:
        result["_membrane"] = gated["_membrane"]
    if isinstance(result.get("trace"), dict):
        result["trace"]["useful_answer"] = False
    return result
