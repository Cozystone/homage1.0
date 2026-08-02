from packages.cloud_brain.semantic_projection import project_sentence_to_semantic_candidates


def test_korean_kubernetes_sentence_projects_concepts_and_relations():
    result = project_sentence_to_semantic_candidates("쿠버네티스는 컨테이너화된 애플리케이션을 자동으로 배포하고 관리하는 오픈소스 플랫폼입니다.", "ko")
    assert result["concept_candidates"]
    assert result["relation_candidates"]
    assert any(row["relation"] == "manages" for row in result["relation_candidates"])
    assert result["limitations"]


def test_english_kubernetes_sentence_projects_concepts_and_relations():
    result = project_sentence_to_semantic_candidates("Kubernetes is an open-source platform that manages containerized applications and automates deployment.", "en")
    assert any(row["source"] == "Kubernetes" for row in result["relation_candidates"])
    assert result["extraction_confidence"] > 0.5
