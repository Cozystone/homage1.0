from __future__ import annotations

from packages.surface_brain.realization_planner import plan_speech, realize_answer


def test_default_answer_hides_internal_graph_path(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    context = {
        "concepts": ["GraphRAG", "KnowledgeGraph", "Evidence"],
        "relations": [{"source": "GraphRAG", "relation": "uses", "target": "KnowledgeGraph"}],
        "evidence": [{"chunk_id": "demo-001", "snippet": "GraphRAG uses a KnowledgeGraph to retrieve Evidence."}],
    }

    plan = plan_speech("GraphRAG가 근거 문서를 어떻게 사용해서 답변을 검증하나요?", context, language="ko")
    answer = realize_answer(plan, context, query="GraphRAG가 근거 문서를 어떻게 사용해서 답변을 검증하나요?")

    assert "Local Brain" not in answer["answer"]
    assert "Cloud Brain" not in answer["answer"]
    assert "근거" in answer["answer"] or "Evidence" in answer["answer"]
    assert answer["trace_summary"]["trace_hidden_by_default"] is True
    assert answer["honesty"]["external_llm_used"] is False

