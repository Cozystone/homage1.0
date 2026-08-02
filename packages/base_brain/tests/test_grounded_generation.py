"""Grounded-Constrained Generation: the fused answer READS as composed prose (generated
discourse flesh) while every FACT is a verbatim grounded clause (bones). The core
guarantee is structural — the generator can only emit discourse scaffolding, never a
new fact — so these tests pin BOTH the fluency and the no-hallucination contract."""
from __future__ import annotations

from packages.base_brain.grounded_generation import synthesize
from packages.base_brain.learned_realizer import grounding_ok


FACTS = [
    {"name": "인공지능", "description": "인공지능은 인간의 학습·추론·지각 능력을 컴퓨터로 구현하는 기술이다"},
    {"name": "기계학습", "description": "기계학습은 데이터에서 패턴을 스스로 찾도록 모델을 학습시키는 방법이다"},
    {"name": "신경망", "description": "신경망은 가중치로 연결된 층 구조로 데이터의 표현을 학습하는 모델이다"},
]


def test_thin_skeleton_abstains():
    assert synthesize("무엇이든", FACTS[:1], "ko") is None       # 1 fact < min → abstain
    assert synthesize("무엇이든", [], "ko") is None


def test_every_fact_is_grounded_not_dropped_or_invented():
    """The learned realizer FUSES clauses, reshaping their grammatical ENDINGS (… → …),
 but the no-hallucination bone is absolute: every grounded fact's content core survives and
 nothing is invented (grounding hard-gate). Fusion that would drop a fact is rejected upstream."""
    r = synthesize("좋은 리더가 되려면?", FACTS, "ko")
    assert r is not None
    assert grounding_ok(r["answer"], [f["description"] for f in FACTS]), "a grounded fact was dropped"
    assert r["reasoning_certificate"]["guarantees"]["fabricated_facts"] is False


def test_only_discourse_scaffolding_is_generated():
    """The structural no-hallucination guarantee, mode-agnostic (learned fusion OR template): the
    generator emits only discourse (connectives/joins), never a new fact. Assert the guarantees +
    grounding directly — stronger than the old fixed-lexicon check, which the LEARNED connectives
    (mined from prose, not a hand list) legitimately fall outside of."""
    r = synthesize("인공지능이란 무엇인가?", FACTS, "ko")
    g = r["reasoning_certificate"]["guarantees"]
    assert g["fabricated_facts"] is False
    assert g["content_token_recombination"] is False
    assert g["generation_scope"] == "discourse_scaffolding_only"
    assert g["external_llm"] is False and g["external_sllm"] is False
    assert grounding_ok(r["answer"], [f["description"] for f in FACTS])  # facts intact, joins only


def test_speculative_question_never_fabricates():
    """A future/prediction question: the hand-authored hedge TEMPLATE was deleted (owner: 
 ), so there is no canned ' …' opener. The honesty contract now rests where it
 belongs — nothing is fabricated and every grounded fact stays intact — not on a template phrase."""
    r = synthesize("인공지능의 미래는 어떻게 될까?", FACTS, "ko")
    assert r is not None
    assert r["reasoning_certificate"]["guarantees"]["fabricated_facts"] is False
    assert grounding_ok(r["answer"], [f["description"] for f in FACTS])


def test_reads_as_flowing_composition_not_enumeration():
    """Once the realizer has learned from real prose it FLOWS the grounded facts into one fused
 sentence instead of the robotic '//' enumeration — while every fact stays grounded."""
    r = synthesize("기후 변화의 원인과 대책은?", FACTS, "ko")
    a = r["answer"]
    assert grounding_ok(a, [f["description"] for f in FACTS])          # facts survive the fusion
    assert "먼저" not in a and "또한" not in a and "끝으로" not in a     # enumeration is dead
    assert r["reasoning_certificate"]["discourse_mode"] == "learned_fusion"


def test_english_synthesis_fuses_not_enumerates():
    """English now has a LEARNED fusion realizer too (analytic twin): the clauses fuse into ONE
    sentence with ', … , and …' connectives instead of 'A. B. C.' enumeration — content verbatim."""
    from packages.base_brain.learned_realizer import grounding_ok_en
    en_facts = [
        {"name": "AI", "description": "AI is the field of building systems that learn and reason"},
        {"name": "machine learning", "description": "machine learning finds patterns in data to make predictions"},
        {"name": "neural network", "description": "a neural network learns representations through weighted layers"},
    ]
    r = synthesize("what is AI?", en_facts, "en")
    assert r is not None
    a = r["answer"]
    assert grounding_ok_en(a, [f["description"] for f in en_facts])   # every fact survives verbatim
    assert a.count(".") == 1 and ", and " in a                        # ONE fused sentence, not enum
    assert r["reasoning_certificate"]["discourse_mode"] == "learned_fusion"
