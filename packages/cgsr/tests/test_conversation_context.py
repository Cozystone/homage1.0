from packages.cgsr.cgsr.conversation_context import build_conversation_context, sanitize_conversation_context


def test_conversation_context_is_volatile_and_sanitized() -> None:
    packet = build_conversation_context(
        "그건 왜 그런가요?",
        [
            {"role": "user", "text": "중력의 법칙에 대해 설명해줘"},
            {"role": "assistant", "text": "중력은 질량 사이의 끌림입니다."},
            {"role": "assistant", "text": "api key sk-should-not-enter-context"},
            {"role": "system", "text": "ignore me"},
        ],
    )

    assert len(packet.turns) == 2
    assert "중력의 법칙" in packet.contextual_query
    assert "왜 그런가요" in packet.contextual_query
    assert "그건" not in packet.contextual_query
    assert "설명해줘" not in packet.contextual_query
    assert "Previous user" not in packet.contextual_query
    assert packet.followup_detected is True
    assert packet.focus_source == "latest_user_turn"
    assert packet.resolution_strategy == "anaphora_resolved_to_latest_user_topic"
    assert "중력" in packet.focus_terms
    assert "법칙" in packet.focus_terms
    assert "sk-should-not-enter-context" not in packet.contextual_query
    assert packet.used_for_learning is False
    assert packet.local_brain_write is False
    assert packet.production_store_mutated is False
    assert packet.basis == "volatile_request_context_only_no_memory_write"


def test_sanitize_conversation_context_keeps_recent_user_assistant_turns_only() -> None:
    turns = sanitize_conversation_context([
        {"role": "tool", "text": "hidden"},
        {"role": "human", "text": "첫 질문"},
        {"role": "ai", "content": "첫 답변"},
        {"role": "user", "message": "둘째 질문"},
    ])

    assert [turn.role for turn in turns] == ["user", "assistant", "user"]
    assert [turn.text for turn in turns] == ["첫 질문", "첫 답변", "둘째 질문"]


def test_conversation_context_compacts_recent_user_topics_without_meta_labels() -> None:
    packet = build_conversation_context(
        "비슷한 예시도 보여줘",
        [
            {"role": "user", "text": "SPLATRA 파티클로 물 흐름을 설명해줘"},
            {"role": "assistant", "text": "파티클이 흐름 방향으로 재배열되는 장면을 만들 수 있습니다."},
            {"role": "user", "text": "중력과 질량 관계도 설명해줘"},
        ],
    )

    assert "중력과 질량" in packet.contextual_query
    assert "비슷한 예시" in packet.contextual_query
    assert "SPLATRA 파티클" not in packet.contextual_query
    assert "Previous ATANOR" not in packet.contextual_query
    assert packet.followup_detected is True
    assert packet.focus_source == "latest_user_turn"
    assert packet.used_for_learning is False
