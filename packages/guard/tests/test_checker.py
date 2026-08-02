from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from guard import check_guard


def test_guard_detects_overclaim_and_support():
    evidence = {"evidence_docs": [{"snippet": "GraphRAG uses KnowledgeGraph and Evidence to ground answers."}]}
    ontology = {"nodes": [{"label": "GraphRAG"}, {"label": "KnowledgeGraph"}]}

    report = check_guard("GraphRAG always guarantees perfect answers.", evidence, ontology)

    assert report["claims"][0]["support"] in {"lexical_match", "lexical_match_weak"}
    assert report["claims"][0]["support_authority"] == "none"
    assert report["claims"][0]["basis"] == "unverified_token_overlap"
    assert report["warnings"]
    assert report["overall_guard_score"] < 100


def test_contradictory_token_overlap_has_no_support_authority():
    report = check_guard(
        "Paris is the capital of Germany.",
        {"evidence_docs": [{"snippet": "Berlin is the capital of Germany."}]},
        {},
    )

    claim = report["claims"][0]
    assert claim["support"] == "lexical_match"
    assert claim["support_authority"] == "none"
    assert claim["basis"] == "unverified_token_overlap"
    assert report["support_authority"] == "none"
    assert report["basis"] == "unverified_token_overlap"


def test_legitimate_overlap_remains_a_non_authoritative_lexical_diagnostic():
    evidence = {"evidence_docs": [{"snippet": "Berlin is the capital of Germany."}]}
    legitimate = check_guard("Berlin is the capital of Germany.", evidence, {})
    contradictory = check_guard("Paris is the capital of Germany.", evidence, {})

    claim = legitimate["claims"][0]
    assert claim["support"] == "lexical_match"
    assert claim["support_authority"] == "none"
    assert claim["basis"] == "unverified_token_overlap"
    assert legitimate["overall_guard_score"] == contradictory["overall_guard_score"] == 100
