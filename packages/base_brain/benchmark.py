from __future__ import annotations

import json
from typing import Any

from .models import BENCHMARK_PATH, ensure_base_dirs, utc_now_iso


def _prompt(
    prompt_id: str,
    query: str,
    language: str,
    expected_intent: str,
    expected_key_concepts: list[str],
    audience_level: str = "beginner",
) -> dict[str, Any]:
    return {
        "prompt_id": prompt_id,
        "query": query,
        "language": language,
        "audience_level": audience_level,
        "mode": "default",
        "expected_intent": expected_intent,
        "expected_key_concepts": expected_key_concepts,
        "forbidden_leakage_terms": [
            "Local Brain",
            "Cloud Brain",
            "Working Memory",
            "Q-Cortex",
            "source_hash",
            "node_id",
        ],
    }


def build_zero_user_benchmark_v0() -> dict[str, Any]:
    ensure_base_dirs()
    prompts = [
        _prompt("ko_001", "쿠버네티스가 뭐야?", "ko", "define", ["kubernetes", "container"]),
        _prompt("ko_002", "스프링부트와 Express의 차이를 알려줘.", "ko", "compare", ["spring_boot", "express_js"], "intermediate"),
        _prompt("ko_003", "AI 모델 학습과 추론의 차이를 설명해줘.", "ko", "compare", ["ai_training", "ai_inference"]),
        _prompt("ko_004", "양자컴퓨터를 쉽게 설명해줘.", "ko", "explain", ["quantum_computer"]),
        _prompt("ko_005", "GraphRAG와 일반 RAG의 차이가 뭐야?", "ko", "compare", ["graphrag", "semantic_graph"]),
        _prompt("ko_006", "SQLite가 로컬 앱에 좋은 이유는?", "ko", "explain", ["sqlite", "local_first_ai"]),
        _prompt("ko_007", "CPU와 GPU의 차이를 알려줘.", "ko", "compare", ["cpu", "gpu"]),
        _prompt("ko_008", "전압과 전류의 차이를 쉽게 말해줘.", "ko", "compare", ["voltage", "current"]),
        _prompt("ko_009", "로컬 AI와 클라우드 AI의 차이점은?", "ko", "compare", ["local_first_ai", "cloud_ai"]),
        _prompt("ko_010", "Tauri 앱 배포가 뭐가 달라?", "ko", "explain", ["tauri", "desktop_app"]),
        _prompt("ko_011", "온톨로지 그래프가 뭐야?", "ko", "define", ["ontology", "semantic_graph"]),
        _prompt("ko_012", "환각을 줄이려면 왜 근거가 필요해?", "ko", "explain", ["hallucination_reduction", "evidence"]),
        _prompt("ko_013", "Surface Graph는 왜 필요한 거야?", "ko", "explain", ["surface_graph", "semantic_graph"]),
        _prompt("ko_014", "컨테이너와 Docker 관계를 설명해줘.", "ko", "explain", ["container", "docker"]),
        _prompt("ko_015", "API가 뭔지 짧게 알려줘.", "ko", "define", ["api"]),
        _prompt("en_001", "What is Kubernetes?", "en", "define", ["kubernetes", "container"]),
        _prompt("en_002", "Compare Spring Boot and Express.", "en", "compare", ["spring_boot", "express_js"], "intermediate"),
        _prompt("en_003", "Explain AI training versus inference.", "en", "compare", ["ai_training", "ai_inference"]),
        _prompt("en_004", "What is an ontology graph?", "en", "define", ["ontology", "semantic_graph"]),
        _prompt("en_005", "What is the difference between local AI and cloud AI?", "en", "compare", ["local_first_ai", "cloud_ai"]),
        _prompt("en_006", "Explain SQLite for local-first apps.", "en", "explain", ["sqlite", "local_first_ai"]),
        _prompt("en_007", "What is GraphRAG?", "en", "define", ["graphrag"]),
        _prompt("en_008", "Explain CPU versus GPU.", "en", "compare", ["cpu", "gpu"]),
        _prompt("en_009", "What does Tauri do for desktop apps?", "en", "explain", ["tauri", "desktop_app"]),
        _prompt("en_010", "Why does evidence matter for reducing hallucination?", "en", "explain", ["evidence", "hallucination_reduction"]),
        _prompt("style_001", "쿠버네티스를 중학생도 이해하게 설명해줘.", "ko", "explain", ["kubernetes"], "beginner"),
        _prompt("style_002", "쿠버네티스를 전문가에게 말하듯 설명해줘.", "ko", "explain", ["kubernetes"], "expert"),
        _prompt("style_003", "Explain Kubernetes in simple English.", "en", "explain", ["kubernetes"], "beginner"),
        _prompt("style_004", "Explain Kubernetes concisely for an engineer.", "en", "explain", ["kubernetes"], "expert"),
        _prompt("unsupported_001", "오늘 우리 동네 비가 오는지 알려줘.", "ko", "unknown", ["needs_external_context"]),
    ]
    benchmark = {
        "benchmark_id": "zero_user_general_v0",
        "version": "0.1.1",
        "created_at": utc_now_iso(),
        "prompts": prompts,
        "honesty": {
            "external_llm_used": False,
            "external_web_used": False,
            "user_data_used": False,
        },
    }
    BENCHMARK_PATH.write_text(json.dumps(benchmark, ensure_ascii=False, indent=2), encoding="utf-8")
    return benchmark
