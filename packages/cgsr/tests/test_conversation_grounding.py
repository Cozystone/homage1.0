from __future__ import annotations

import json
from pathlib import Path

from packages.cgsr.cgsr.conversation_grounding import (
    GroundedContext,
    _rank_facts_for_question,
    gather_grounded_context,
    honesty_metadata,
    realize_grounded_context,
    semantic_safety_flags,
)


def test_grounding_drops_wrong_language_snippets() -> None:
    # An English question must never surface a Korean web snippet, and vice versa.
    en_facts = (
        "react 취약점 이슈 원인 총정리 -판다랭크. 09 Dec 2025.",
        "Next.js is a React framework for production web apps.",
    )
    kept_en = [fact for fact, _ in _rank_facts_for_question("What is Next.js?", en_facts, limit=3)]
    assert kept_en == ["Next.js is a React framework for production web apps."]

    ko_facts = (
        "This is an unrelated English fact about cars.",
        "GraphRAG는 의미 그래프로 근거를 찾는 방식입니다.",
    )
    kept_ko = [fact for fact, _ in _rank_facts_for_question("GraphRAG가 뭐야?", ko_facts, limit=3)]
    assert kept_ko == ["GraphRAG는 의미 그래프로 근거를 찾는 방식입니다."]


def test_grounding_prefers_relevant_fact_as_tiebreaker() -> None:
    facts = (
        "The weather is cold today.",
        "Kubernetes orchestrates containers across machines.",
    )
    kept = [fact for fact, _ in _rank_facts_for_question("What is Kubernetes?", facts, limit=1)]
    assert kept == ["Kubernetes orchestrates containers across machines."]
from packages.cgsr.cgsr.conversation_router import route_conversation_request


def test_local_cloud_grounding_has_correct_architecture_facts() -> None:
    prompt = "로컬 브레인과 클라우드 브레인의 차이를 설명해줘"
    route = route_conversation_request(prompt)
    context = gather_grounded_context(prompt, route)
    answer = realize_grounded_context(prompt, context)

    assert route.route_type == "local_cloud_brain_explanation"
    assert context.grounding_quality == "high"
    assert context.grounding_source == "local_state"
    assert "로컬 브레인은 사용자 개인 기억" in " ".join(context.facts)
    assert "클라우드 브레인은 출처와 검증 상태" in " ".join(context.facts)
    assert answer
    # preamble openers were removed by design (answers lead with content);
    # assert the architecture facts themselves instead of the old phrasing
    assert "로컬 브레인" in answer and "클라우드 브레인" in answer
    assert "로컬 브레인" in answer
    assert "클라우드 브레인" in answer
    assert context.safety_flags["local_brain_write"] is False
    assert context.safety_flags["production_store_mutated"] is False


def test_memory_grounding_never_claims_direct_write() -> None:
    prompt = "이거 기억해줘"
    route = route_conversation_request(prompt)
    context = gather_grounded_context(prompt, route)
    answer = realize_grounded_context(prompt, context)

    assert route.route_type == "memory_request"
    assert context.safety_flags["local_brain_write"] is False
    assert answer
    assert "직접 쓰지 않는다" in answer
    assert "명시적 승인" in answer


def test_honesty_metadata_is_explicit() -> None:
    prompt = "규칙기반 답변 쓰고 있는 거 아냐?"
    route = route_conversation_request(prompt)
    context = gather_grounded_context(prompt, route)
    metadata = honesty_metadata(route=route, grounded_context=context, semantic_grounding_used=True, answer_mode="grounded_explanation")

    assert route.route_type == "limitation_question"
    assert metadata["external_llm_used"] is False
    assert metadata["external_sllm_used"] is False
    assert metadata["direct_prompt_answer_table_used"] is False
    assert metadata["hand_authored_construction_used"] is True
    assert metadata["heuristic_act_inference_used"] is True
    assert metadata["semantic_grounding_metadata_present"] is True
    assert metadata["honesty_metadata_present"] is True


def test_splatra_direct_generation_answer_mentions_candidate_cartridge_not_ui_patch() -> None:
    prompt = "사실적인 빨간 사과 3D 모델을 SPLATRA 파티클로 직접 생성해서 보여줘"
    route = route_conversation_request(prompt)
    context = gather_grounded_context(prompt, route)
    answer = realize_grounded_context(prompt, context)

    assert route.route_type == "splatra_request"
    assert answer
    assert "SPLATRA" in answer
    assert "UI-local 후보" in answer
    assert "코드 패치를 적용" not in answer
    assert context.safety_flags["local_brain_write"] is False
    assert context.safety_flags["production_store_mutated"] is False


def test_general_knowledge_can_use_readonly_verified_store(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "text": "Gravity is a force of attraction between masses. Isaac Newton formulated the law of universal gravitation.",
                "verification": {"status": "verified"},
                "provenance": {
                    "source_name": "licensed_fixture",
                    "title": "Gravity",
                    "url": "https://example.test/gravity",
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    prompt = "What is the law of gravity?"
    route = route_conversation_request(prompt)
    context = gather_grounded_context(prompt, route, runtime={"verified_store_path": str(tmp_path)})
    answer = realize_grounded_context(prompt, context)

    assert route.route_type == "general_knowledge_question"
    assert context.grounding_source == "verified_store_v0_readonly"
    assert context.grounding_quality == "medium"
    assert context.safety_flags["production_store_mutated"] is False
    assert context.safety_flags["local_brain_write"] is False
    assert "Isaac Newton" in " ".join(context.facts)
    assert answer
    assert "universal gravitation" in answer


def test_grounded_discourse_prioritizes_causal_fact_for_why_followup() -> None:
    prompt = "그건 왜 그런가요?"
    route = route_conversation_request(prompt)
    grounded = GroundedContext(
        route_type=route.route_type,
        facts=(
            "만유인력의 법칙은 질량을 가진 물체 사이의 중력 끌림을 기술하는 물리학 법칙이다.",
            "중력의 크기는 두 물체의 질량이 클수록 커지고 거리의 제곱에 반비례한다.",
            "이 법칙은 아이작 뉴턴의 1687년 발표 논문을 통해 소개되었다.",
        ),
        constraints=("검색된 근거만 사용한다.",),
        unknowns=(),
        source_refs=("fixture",),
        grounding_source="semantic_cloud_graph_web_evidence_readonly",
        grounding_quality="high",
        safety_flags=semantic_safety_flags(),
    )

    answer = realize_grounded_context(prompt, grounded)

    assert answer

    # the CAUSAL fact leads the discourse for a why-follow-up
    assert answer.startswith("중력의 크기는")
    assert "질량이 클수록" in answer
    assert "아이작 뉴턴" not in answer


def test_web_grounded_discourse_uses_one_ranked_standalone_fact_for_why_context() -> None:
    prompt = "그건 왜 그런가요?"
    route = route_conversation_request(prompt)
    grounded = GroundedContext(
        route_type=route.route_type,
        facts=(
            "만유인력의 법칙은 질량을 가진 물체 사이의 중력 끌림을 기술하는 물리학 법칙이다.",
            "이 법칙에서 힘의 크기는 두 물체의 질량에 비례하고 거리의 제곱에 반비례한다.",
            "아이작 뉴턴은 1687년에 이 법칙을 소개했다.",
        ),
        constraints=("검색된 근거만 사용한다.",),
        unknowns=(),
        source_refs=("fixture-a", "fixture-b"),
        grounding_source="semantic_cloud_graph_web_evidence_readonly",
        grounding_quality="high",
        safety_flags=semantic_safety_flags(),
    )

    answer = realize_grounded_context(prompt, grounded)

    assert answer
    assert "거리의 제곱에 반비례" in answer
    assert "만유인력의 법칙은" not in answer
    assert "1687년" not in answer


def test_grounded_discourse_repairs_spacing_without_inventing_content() -> None:
    prompt = "중력의 법칙에 대해 설명해줘"
    route = route_conversation_request(prompt)
    grounded = GroundedContext(
        route_type=route.route_type,
        facts=(
            "만유인력의 법칙 (萬有引力- 法則 , 영어: law of universal gravity)이란 질량을 가진 물체사이의 중력 끌림을 기술하는 물리학 법칙 이다.",
        ),
        constraints=("검색된 근거만 사용한다.",),
        unknowns=(),
        source_refs=("fixture",),
        grounding_source="semantic_cloud_graph_web_evidence_readonly",
        grounding_quality="high",
        safety_flags=semantic_safety_flags(),
    )

    answer = realize_grounded_context(prompt, grounded)

    assert answer
    assert "법칙(萬有引力-法則, 영어" in answer
    assert "법칙 이다" not in answer
    assert "법칙이다" in answer


def test_grounded_discourse_keeps_long_korean_sentence_boundary() -> None:
    prompt = "중력의 법칙에 대해 설명해줘"
    route = route_conversation_request(prompt)
    grounded = GroundedContext(
        route_type=route.route_type,
        facts=(
            "만유인력의 법칙(萬有引力-法則, 영어: law of universal gravity)이란 질량을 가진 물체사이의 중력 끌림을 기술하는 물리학 법칙이다. "
            "이 법칙은 아이작 뉴턴의 1687년 발표 논문 〈자연철학의 수학적 원리, 혹은 프린키피아(Principia)〉를 통해 처음 소개되었다. "
            "현대의 용어를 사용하여 이 법칙을 기술할 수 있다.",
        ),
        constraints=("검색된 근거만 사용한다.",),
        unknowns=(),
        source_refs=("fixture",),
        grounding_source="semantic_cloud_graph_web_evidence_readonly",
        grounding_quality="high",
        safety_flags=semantic_safety_flags(),
    )

    answer = realize_grounded_context(prompt, grounded)

    assert answer
    assert "처음 소개되었다" in answer
    assert "처음." not in answer


def test_grounded_discourse_keeps_space_after_sentence_boundary() -> None:
    prompt = "중력은 왜 그런가요?"
    route = route_conversation_request(prompt)
    grounded = GroundedContext(
        route_type=route.route_type,
        facts=(
            "역제곱 법칙은 어떤 힘의 크기가 거리의 제곱에 반비례하는 것이다. 이 규칙에는 중력이 해당한다.",
        ),
        constraints=("검색된 근거만 사용한다.",),
        unknowns=(),
        source_refs=("fixture",),
        grounding_source="semantic_cloud_graph_web_evidence_readonly",
        grounding_quality="high",
        safety_flags=semantic_safety_flags(),
    )

    answer = realize_grounded_context(prompt, grounded)

    assert answer
    assert "것이다. 이 규칙" in answer
    assert "것이다.이 규칙" not in answer


def test_grounded_discourse_drops_incomplete_particle_tail_sentence() -> None:
    prompt = "중력은 왜 그런가요?"
    route = route_conversation_request(prompt)
    grounded = GroundedContext(
        route_type=route.route_type,
        facts=(
            "역제곱 법칙은 힘의 크기가 거리의 제곱에 반비례하는 것이다. 이 규칙에는 중력이 해당한다. 뉴턴의 중력 법칙은 다음과 같은 방정식으로.",
        ),
        constraints=("검색된 근거만 사용한다.",),
        unknowns=(),
        source_refs=("fixture",),
        grounding_source="semantic_cloud_graph_web_evidence_readonly",
        grounding_quality="high",
        safety_flags=semantic_safety_flags(),
    )

    answer = realize_grounded_context(prompt, grounded)

    assert answer
    assert "거리의 제곱에 반비례" in answer
    assert "다음과 같은 방정식으로" not in answer


def test_grounded_discourse_drops_already_clipped_first_tail_sentence() -> None:
    prompt = "중력의 법칙에 대해 설명해줘"
    route = route_conversation_request(prompt)
    grounded = GroundedContext(
        route_type=route.route_type,
        facts=(
            "만유인력의 법칙은 질량을 가진 물체 사이의 중력 끌림을 기술하는 법칙이다. 이 법칙은 아이작 뉴턴의 발표 논문을 통해 처음.",
        ),
        constraints=("검색된 근거만 사용한다.",),
        unknowns=(),
        source_refs=("fixture",),
        grounding_source="semantic_cloud_graph_web_evidence_readonly",
        grounding_quality="high",
        safety_flags=semantic_safety_flags(),
    )

    answer = realize_grounded_context(prompt, grounded)

    assert answer
    assert "중력 끌림을 기술하는 법칙" in answer
    assert "처음." not in answer


def test_general_knowledge_does_not_ground_on_english_function_words(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "text": "The Second Law of Thermodynamics explains entropy in closed systems.",
                "verification": {"status": "verified"},
                "provenance": {
                    "source_name": "licensed_fixture",
                    "title": "Thermodynamics",
                    "url": "https://example.test/thermodynamics",
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    prompt = "What is the law of gravity?"
    route = route_conversation_request(prompt)
    context = gather_grounded_context(prompt, route, runtime={"verified_store_path": str(tmp_path)})
    answer = realize_grounded_context(prompt, context)

    assert route.route_type == "general_knowledge_question"
    assert context.grounding_source == "none"
    assert context.grounding_quality == "none"
    assert not context.facts
    assert answer is None


def test_general_knowledge_adds_same_document_motion_evidence_without_topic_template(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.jsonl"
    rows = [
        {
            "text": "Gravity is a force of attraction between masses. Isaac Newton formulated the law of universal gravitation.",
            "verification": {"status": "verified"},
            "provenance": {
                "document_id": "licensed_gravity_doc",
                "source_id": "licensed:gravity:1",
                "source_name": "licensed_fixture",
                "title": "Gravity",
            },
        },
        {
            "text": "Universal gravitation described free fall near Earth and orbital motion of planets as connected motion.",
            "verification": {"status": "verified"},
            "provenance": {
                "document_id": "licensed_gravity_doc",
                "source_id": "licensed:gravity:2",
                "source_name": "licensed_fixture",
                "title": "Gravity",
            },
        },
    ]
    evidence_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    prompt = "What is the law of gravity?"
    route = route_conversation_request(prompt)
    context = gather_grounded_context(prompt, route, runtime={"verified_store_path": str(tmp_path)})

    facts = " ".join(context.facts)
    assert context.grounding_source == "verified_store_v0_readonly"
    assert "universal gravitation" in facts
    assert "free fall near Earth" in facts
    assert "orbital motion" in facts


def test_general_knowledge_does_not_add_unrelated_adjacent_scene_words(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.jsonl"
    rows = [
        {
            "text": "Gravity is a force of attraction between masses. Isaac Newton formulated the law of universal gravitation.",
            "verification": {"status": "verified"},
            "provenance": {
                "document_id": "licensed_gravity_doc",
                "source_id": "licensed:gravity:1",
                "source_name": "licensed_fixture",
                "title": "Gravity",
            },
        },
        {
            "text": "An apple fell from a tree in an unrelated orchard story.",
            "verification": {"status": "verified"},
            "provenance": {
                "document_id": "licensed_orchard_doc",
                "source_id": "licensed:orchard:1",
                "source_name": "licensed_fixture",
                "title": "Orchard",
            },
        },
    ]
    evidence_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    prompt = "What is the law of gravity?"
    route = route_conversation_request(prompt)
    context = gather_grounded_context(prompt, route, runtime={"verified_store_path": str(tmp_path)})

    facts = " ".join(context.facts)
    assert context.grounding_source == "verified_store_v0_readonly"
    assert "universal gravitation" in facts
    assert "apple" not in facts.casefold()
    assert "orchard" not in facts.casefold()


def test_korean_general_knowledge_uses_utf8_verified_store_tokens(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "text": "아이작 뉴턴은 중력, 즉 만유인력 법칙을 수학적으로 정식화했다.",
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "만유인력"},
            },
            ensure_ascii=False,
        )
        + "\n"
        + json.dumps(
            {
                "text": "각운동량 보존 법칙은 각운동량이 시간에 따라 일정하다는 것을 말한다.",
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "각운동량"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    prompt = "중력의 법칙에 대해 설명해줘"
    route = route_conversation_request(prompt)
    context = gather_grounded_context(prompt, route, runtime={"verified_store_path": str(tmp_path)})
    answer = realize_grounded_context(prompt, context)

    assert route.route_type == "general_knowledge_question"
    assert context.grounding_source == "verified_store_v0_readonly"
    assert context.grounding_quality == "medium"
    assert "아이작 뉴턴" in " ".join(context.facts)
    assert "각운동량" not in " ".join(context.facts)
    assert answer
    assert "만유인력" in answer
