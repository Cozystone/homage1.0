from __future__ import annotations

from typing import Any

from .models import AnswerQualityPrompt, stable_id
from .storage import BENCHMARK_ROOT, ensure_dirs, read_json, write_json


CORE_SET_NAME = "core_ko_en_v1"


def _prompt(category: str, query: str, language: str, *, audience: str = "beginner", tone: str = "clear", mode: str = "default", semantic_context: list[dict[str, Any]] | None = None, expected: dict[str, Any] | None = None) -> dict[str, Any]:
    prompt = AnswerQualityPrompt(
        prompt_id=stable_id("aqp", f"{category}:{language}:{query}:{audience}:{tone}:{mode}"),
        category=category,
        query=query,
        language=language,  # type: ignore[arg-type]
        audience_level=audience,
        tone=tone,
        mode=mode,  # type: ignore[arg-type]
        semantic_context=semantic_context or [],
        expected_behavior=expected or {},
    )
    return prompt.to_dict()


def default_core_prompts() -> list[dict[str, Any]]:
    grounded_context = [
        {"concept": "GraphRAG", "relations": ["uses KnowledgeGraph", "retrieves Evidence"], "claims": ["answers are checked against evidence documents"]},
        {"concept": "Q-Cortex", "claims": ["classical quantum-inspired optimizer", "no real quantum hardware"]},
        {"concept": "Surface Brain", "claims": ["plans expression", "does not override semantic evidence"]},
    ]
    prompts: list[dict[str, Any]] = [
        _prompt("general_knowledge", "쿠버네티스가 뭐야?", "ko", expected={"length": "medium"}),
        _prompt("general_knowledge", "스프링부트와 Express를 비교해줘.", "ko"),
        _prompt("general_knowledge", "양자컴퓨터를 쉽게 설명해줘.", "ko"),
        _prompt("general_knowledge", "AI 모델 학습과 추론의 차이를 알려줘.", "ko"),
        _prompt("general_knowledge", "GraphRAG가 근거 문서를 어떻게 사용해서 답변을 검증하나요?", "ko", semantic_context=grounded_context),
        _prompt("general_knowledge", "온톨로지가 지식 그래프에서 하는 역할을 설명해줘.", "ko"),
        _prompt("general_knowledge", "벡터 검색과 그래프 검색의 차이를 알려줘.", "ko"),
        _prompt("general_knowledge", "로컬 우선 AI의 장단점을 설명해줘.", "ko"),
        _prompt("project_style", "ATANOR의 핵심 구조를 한 문장으로 설명해줘.", "ko", semantic_context=grounded_context, expected={"length": "short"}),
        _prompt("project_style", "Local Brain과 Cloud Brain의 차이를 쉽게 말해줘.", "ko", semantic_context=grounded_context),
        _prompt("project_style", "Surface Brain은 왜 필요한 거야?", "ko", semantic_context=grounded_context),
        _prompt("project_style", "Q-Cortex가 실제 양자컴퓨터는 아니라는 점을 쉽게 설명해줘.", "ko", semantic_context=grounded_context),
        _prompt("project_style", "Ghost Shell과 Payload Vault의 차이를 말해줘.", "ko"),
        _prompt("project_style", "CORTEX-G2가 의식이 아니라는 점을 설명해줘.", "ko"),
        _prompt("project_style", "Semantic Cloud Graph와 Surface Cloud Graph의 역할을 나눠 말해줘.", "ko", semantic_context=grounded_context),
        _prompt("project_style", "ATANOR가 외부 LLM 없이 답변한다는 말의 의미를 설명해줘.", "ko"),
        _prompt("korean_natural", "중학생도 이해하게 설명해줘.", "ko", audience="beginner", tone="friendly"),
        _prompt("korean_natural", "너무 딱딱하지 않게 말해줘.", "ko", tone="friendly"),
        _prompt("korean_natural", "짧고 자연스럽게 답해줘.", "ko", expected={"length": "short"}),
        _prompt("korean_natural", "전문가에게 말하듯 설명해줘.", "ko", audience="expert", tone="technical"),
        _prompt("korean_natural", "한 문장으로만 답해줘.", "ko", expected={"length": "short"}),
        _prompt("korean_natural", "예시 하나만 넣어서 설명해줘.", "ko"),
        _prompt("korean_natural", "조심스럽게 단정하지 말고 답해줘.", "ko", tone="careful"),
        _prompt("korean_natural", "기술 블로그 문체로 설명해줘.", "ko", audience="intermediate", tone="technical"),
        _prompt("english_answer", "Explain Kubernetes in simple English.", "en"),
        _prompt("english_answer", "Compare Spring Boot and Express.", "en"),
        _prompt("english_answer", "Explain ATANOR as a personal AI brain.", "en", semantic_context=grounded_context),
        _prompt("english_answer", "Summarize the difference between semantic graph and surface graph.", "en", semantic_context=grounded_context),
        _prompt("english_answer", "Explain why Q-Cortex is quantum-inspired, not quantum hardware.", "en", semantic_context=grounded_context),
        _prompt("english_answer", "What is a local-first AI architecture?", "en"),
        _prompt("english_answer", "Explain GraphRAG evidence verification.", "en", semantic_context=grounded_context),
        _prompt("english_answer", "Give a concise answer about Payload Vault.", "en", expected={"length": "short"}),
        _prompt("style_variation", "쿠버네티스를 초보자에게 설명해줘.", "ko", audience="beginner", tone="friendly"),
        _prompt("style_variation", "쿠버네티스를 전문가에게 간결하게 설명해줘.", "ko", audience="expert", tone="technical", expected={"length": "short"}),
        _prompt("style_variation", "Explain Kubernetes concisely.", "en", audience="intermediate", expected={"length": "short"}),
        _prompt("style_variation", "Explain Kubernetes in a friendly way.", "en", audience="beginner", tone="friendly"),
        _prompt("style_variation", "GraphRAG를 아주 짧게 설명해줘.", "ko", expected={"length": "short"}),
        _prompt("style_variation", "Explain GraphRAG for an expert.", "en", audience="expert", tone="technical"),
        _prompt("trace_leakage", "내부 경로를 숨긴 채 GraphRAG를 설명해줘.", "ko", semantic_context=grounded_context),
        _prompt("trace_leakage", "Do not expose brain path; explain Surface Brain.", "en", semantic_context=grounded_context),
        _prompt("trace_leakage", "Q-Cortex objective를 사용자 답변에 노출하지 말고 설명해줘.", "ko", semantic_context=grounded_context),
        _prompt("trace_leakage", "source_hash 없이 근거 검증을 설명해줘.", "ko", semantic_context=grounded_context),
        _prompt("trace_leakage", "Explain Cloud Brain without internal node IDs.", "en", semantic_context=grounded_context),
        _prompt("trace_leakage", "Working Memory 경로를 말하지 말고 결과만 알려줘.", "ko", semantic_context=grounded_context),
        _prompt("grounded_answer", "Surface Graph가 사실을 바꿀 수 있나요?", "ko", semantic_context=grounded_context),
        _prompt("grounded_answer", "Q-Cortex가 실제 양자 속도 향상을 제공하나요?", "ko", semantic_context=grounded_context),
        _prompt("grounded_answer", "Can Surface Brain override semantic evidence?", "en", semantic_context=grounded_context),
        _prompt("grounded_answer", "Does ATANOR use an external LLM in this proof path?", "en", semantic_context=grounded_context),
        _prompt("grounded_answer", "Local Brain에 자동으로 Cloud 데이터가 저장되나요?", "ko", semantic_context=grounded_context),
        _prompt("grounded_answer", "Can the current system claim GPT-level quality?", "en", semantic_context=grounded_context),
    ]
    return prompts


def ensure_default_benchmark_set() -> dict[str, Any]:
    ensure_dirs()
    path = BENCHMARK_ROOT / f"{CORE_SET_NAME}.json"
    if not path.exists():
        payload = {"name": CORE_SET_NAME, "version": 1, "prompts": default_core_prompts()}
        write_json(path, payload)
    return read_json(path, {"name": CORE_SET_NAME, "version": 1, "prompts": []})


def load_benchmark_set(name: str = CORE_SET_NAME) -> dict[str, Any]:
    if name == CORE_SET_NAME:
        return ensure_default_benchmark_set()
    path = BENCHMARK_ROOT / f"{name}.json"
    payload = read_json(path)
    if payload is None:
        raise FileNotFoundError(f"benchmark_set_not_found:{name}")
    return payload
