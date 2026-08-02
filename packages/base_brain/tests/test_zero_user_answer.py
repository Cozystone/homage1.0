import re

from packages.base_brain.zero_user_answer import answer_with_base_brain


FORBIDDEN = ["Local Brain", "Cloud Brain", "Working Memory", "Q-Cortex", "source_hash", "node_id"]


def test_zero_user_answer_known_prompt_is_clean() -> None:
    result = answer_with_base_brain("쿠버네티스가 뭐야?", language="ko")
    assert result["answer"]
    assert "쿠버네티스" in result["answer"]
    assert result["semantic_context_count"] > 0
    assert result["surface_candidate_count"] > 0
    assert result["local_user_brain_used"] is False
    assert result["external_llm_used"] is False
    assert result["external_sllm_used"] is False
    assert result["external_web_used"] is False
    assert not any(term in result["answer"] for term in FORBIDDEN)


def test_zero_user_answer_unsupported_question_does_not_hallucinate() -> None:
    result = answer_with_base_brain("오늘 우리 동네 비가 올지 알려줘", language="ko")
    assert "근거" in result["answer"] or "부족" in result["answer"]
    assert result["external_web_used"] is False


def test_zero_user_answer_rejects_unverified_person() -> None:

    # forfeit. An unverified person now gets a HEDGED engagement — but the safety intent
    # holds: LOW confidence + NO fabricated biography (no invented birth year).
    result = answer_with_base_brain("유재석이 누구야", language="ko")
    assert result["answer"]
    assert result["confidence"] <= 0.2, f"unverified person must stay low-confidence, got {result['confidence']}"
    assert not re.search(r"\b(19|20)\d\d년\b", result["answer"]), "must not invent a birth year"
    assert result["external_llm_used"] is False


# ─────────────────────────────────────────────────────────────────────────────────────────────
# MEMBRANE: the conformal gate on the base_brain relational lane (the SECOND API entrypoint).
#
# answer_with_base_brain resolves "the <REL> of <ENTITY>" through resolve_relational and returns
# the core in an API shape. Before this wiring, ATANOR_MEMBRANE_LIVE=1 gated answer_from_triples
# but NOT this entrypoint, so 'occupation of Michelangelo' returned "ninja, ..." ACCEPTED at conf
# 0.9 while the other lane abstained on the SAME signals. These tests exercise _gate_relational_core:
#   * flag OFF is a pure passthrough (same object) -> the DEMO default path is byte-identical;
#   * flag ON attaches the REAL fan-out/semantic_entropy signals (from answer_bridge, over a store
#     double here) and runs the SAME calibrated ConformalGate, so a fused namesake abstains and a
#     clean single-valued edge accepts, on the SAME relational_edge_lookup q_hat both lanes share;
#   * grounded_composition (compound-define) is accepted on provenance; a relational abstention is
#     never re-gated.
# Hermetic: a store double supplies facts_about, so the real signal code runs without the 115M store.
import pytest

from packages.base_brain import zero_user_answer as ZUA
from packages.conformal_gate import live_wiring as LW

# the live calibration artifact's real thresholds (data/conformal_gate/membrane_calibration.json):
# relational_edge_lookup bin q_hat, grounded_composition = abstain-all (spared by the provenance
# passthrough), pooled fallback = the relational q_hat.
_REL_QHAT = 0.22381796388965472


@pytest.fixture(autouse=True)
def _membrane_reset(monkeypatch):
    monkeypatch.delenv("ATANOR_MEMBRANE_LIVE", raising=False)
    monkeypatch.delenv("ATANOR_MEMBRANE_FAILSAFE", raising=False)
    LW._calib_cache.clear()
    LW._warned_uncalibrated = False
    yield


def _live_like_gate():
    """A Mondrian gate mirroring the shipped artifact so both API lanes share ONE q_hat."""
    from packages.conformal_gate.gate import ConformalGate
    return ConformalGate(alpha=0.1, method="mondrian",
                         bin_q_hat={"relational_edge_lookup": _REL_QHAT,
                                    "grounded_composition": float("-inf")},
                         fallback_q_hat=_REL_QHAT, calibration_n=268)


class _StoreDouble:
    """Minimal store: facts_about(entity, limit=, preds=) over an in-memory {entity: [(s,p,o)]}."""
    def __init__(self, facts):
        self._facts = facts

    def facts_about(self, subject, limit=200, preds=None):
        rows = self._facts.get(subject, [])
        if preds is not None:
            rows = [r for r in rows if r[1] in preds]
        return rows[:limit]


def _relational_core(entity, edge="occupation", answer=None):
    return {
        "answer": answer or f"{entity}'s occupation is thing.",
        "answer_kind": "relational_edge_lookup",
        "confidence": 0.9,
        "intent": "relational",
        "relational": {"rel": edge, "entity": entity, "edge": edge, "resolved": True},
        "reasoning_certificate": {
            "derivation_kind": "relational_edge_lookup",
            "edge": edge, "asked_relation": edge,
            "guarantees": {"external_llm": False, "fabricated_facts": False,
                           "inferred": False, "verified": True},
            "steps": [], "evidence_concepts": [entity],
        },
    }


def test_membrane_relational_core_flag_off_is_identity() -> None:
    """Flag OFF: _gate_relational_core returns the SAME object, adds NOTHING -> byte-identical."""
    core = _relational_core("Michelangelo", answer="Michelangelo's occupation is ninja, cook.")
    out = ZUA._gate_relational_core(core, "What is the occupation of Michelangelo?", "en")
    assert out is core
    assert "_membrane" not in out and "_membrane_signals" not in out


def test_membrane_relational_namesake_abstains(monkeypatch) -> None:
    """Flag ON: a fused namesake hub (18 occupation targets) -> high fan-out entropy -> ABSTAIN."""
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    monkeypatch.setattr(LW, "_load_calibration", _live_like_gate)
    facts = {"Michelangelo": [("Michelangelo", "occupation", f"job{i}") for i in range(18)]}
    from packages.graph_scale import answer_bridge as AB
    monkeypatch.setattr(AB, "_store", lambda: _StoreDouble(facts))
    out = ZUA._gate_relational_core(
        _relational_core("Michelangelo", answer="Michelangelo's occupation is ninja, cook."),
        "What is the occupation of Michelangelo?", "en")
    assert out["answer_kind"] == "honest_abstain"
    assert out["_membrane"]["decision"] == "ABSTAIN"
    # the REAL gate certificate, not a fabricated number
    assert out["reasoning_certificate"]["membrane_certificate"]["nonconformity"] > _REL_QHAT


def test_membrane_relational_clean_edge_accepts(monkeypatch) -> None:
    """Flag ON: a clean single-valued edge (one occupation) -> low nonconformity -> ACCEPT."""
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    monkeypatch.setattr(LW, "_load_calibration", _live_like_gate)
    facts = {"Cristiano Ronaldo": [("Cristiano Ronaldo", "occupation", "association football player")]}
    from packages.graph_scale import answer_bridge as AB
    monkeypatch.setattr(AB, "_store", lambda: _StoreDouble(facts))
    core = _relational_core("Cristiano Ronaldo",
                            answer="Cristiano Ronaldo's occupation is association football player.")
    out = ZUA._gate_relational_core(core, "What is the occupation of Cristiano Ronaldo?", "en")
    assert out is core                                   # accepted -> same object, answer kept
    assert out["answer_kind"] == "relational_edge_lookup"
    assert out["_membrane"]["decision"] == "ACCEPT"
    assert out["reasoning_certificate"]["membrane_certificate"]["nonconformity"] <= _REL_QHAT


def test_membrane_grounded_composition_passthrough(monkeypatch) -> None:
    """Flag ON: a provenance-backed compound-define (capital of France) is accepted on provenance
    even under an abstain-all gate — never gated on its weak signals."""
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    monkeypatch.setattr(LW, "_load_calibration", _live_like_gate)  # grounded_composition bin = abstain-all
    core = {
        "answer": "Capital of france is a paris.",
        "answer_kind": "grounded_composition",
        "confidence": 0.88,
        "intent": "define",
        "reasoning_certificate": {
            "derivation_kind": "grounded_composition",
            "guarantees": {"external_llm": False, "fabricated_facts": False,
                           "inferred": False, "composition_vocabulary_closed": True},
            "steps": [], "evidence_concepts": ["France", "Paris"],
        },
    }
    out = ZUA._gate_relational_core(core, "What is the capital of France?", "en")
    assert out is core
    assert out["_membrane"]["reason"] == "source_verified_passthrough"


def test_membrane_never_regates_relational_abstention(monkeypatch) -> None:
    """Flag ON: honest_abstain_relational (e.g. fictional Wakanda) is already an abstention -> never
    re-gated (and never flipped to accept)."""
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    monkeypatch.setattr(LW, "_load_calibration", _live_like_gate)
    core = {"answer": "Wakanda appears to be a fictional entity, so I don't hold a real-world capital.",
            "answer_kind": "honest_abstain_relational", "confidence": 0.2,
            "reasoning_certificate": {"derivation_kind": "relational_abstention"}}
    out = ZUA._gate_relational_core(core, "What is the capital of Wakanda?", "en")
    assert out is core


def test_membrane_relational_wrapper_reports_abstention_useful_false(monkeypatch) -> None:
    """End-to-end shape: when the gate abstains, the API wrapper the base_brain router consumes must
    report useful_answer=False and carry the abstention, not the withdrawn namesake answer. Uses a
    monkeypatched resolve_relational so the assertion holds without the 115M store."""
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    monkeypatch.setattr(LW, "_load_calibration", _live_like_gate)
    facts = {"Michelangelo": [("Michelangelo", "occupation", f"job{i}") for i in range(18)]}
    from packages.graph_scale import answer_bridge as AB
    monkeypatch.setattr(AB, "_store", lambda: _StoreDouble(facts))

    def _fake_resolve(query, language="en", store=None):
        return _relational_core("Michelangelo", answer="Michelangelo's occupation is ninja, cook.")

    import packages.base_brain.relational_lookup as RL
    monkeypatch.setattr(RL, "resolve_relational", _fake_resolve)
    out = answer_with_base_brain("What is the occupation of Michelangelo?", language="en")
    assert out["answer_kind"] == "honest_abstain"
    assert out["useful_answer"] is False
    assert "ninja" not in out["answer"]                  # the polluted answer was withheld
    assert out["external_llm_used"] is False             # API-shape contract preserved
    assert "trace" in out and out["trace"]["useful_answer"] is False


# ─────────────────────────────────────────────────────────────────────────────────────────────
# MEMBRANE: the conformal gate on the base_brain DEFINE lane (base_brain_zero_user_data /
# ontology_graph_derivation) -- the ungated confident-define breach (2026-07-24, adversary loop
# surface a). Before this wiring the define lane emitted a confident (~0.91) WRONG-REFERENT answer
# on false-premise / compound queries ('what is a black hole' -> 'Black is a color'). The fix gates
# it through the SAME membrane on its OWN Mondrian bin (subject_coverage doubt), calibrated so good
# definitions PASS and wrong-referent defines ABSTAIN. Borrowing the relational q_hat is the WRONG
# scale, so an absent define bin leaves the lane UNGATED (never a false abstain).
#
# Hermetic by construction: the base_brain conftest isolates the pack to a tmp dir (no promoted
# 'black' concept), so these unit-test _gate_define_core on a SYNTHETIC define result -- the same
# dict shape answer_with_base_brain builds -- decoupled from the 5203-concept promoted pack. The
# end-to-end pack behavior (black hole abstains / photosynthesis passes) is covered by the live
# adversary loop + build_membrane_calibration report.
_DEFINE_Q_HAT = 0.39666666666666667


def _live_like_gate_with_define():
    """The shipped Mondrian gate PLUS the define-lane bin (data/conformal_gate/membrane_calibration
    .json ontology_graph_derivation q_hat), so the two lanes share the relational q_hat and the
    define lane uses its own."""
    from packages.conformal_gate.gate import ConformalGate
    return ConformalGate(alpha=0.1, method="mondrian",
                         bin_q_hat={"relational_edge_lookup": _REL_QHAT,
                                    "grounded_composition": float("-inf"),
                                    "ontology_graph_derivation": _DEFINE_Q_HAT},
                         fallback_q_hat=_REL_QHAT, calibration_n=308)


def _define_result(query_subject_words, answer, *, conf=0.91, support=1):
    """A define-lane result dict as answer_with_base_brain builds it (derivation
    ontology_graph_derivation). ``answer`` is what the define lane composed; subject_coverage is
    measured from it, so a wrong-referent answer that leaves the subject uncovered scores low."""
    label = query_subject_words[0]
    return {
        "answer": answer,
        "answer_kind": "base_brain_zero_user_data",
        "confidence": conf,
        "useful_answer": True,
        "reasoning_certificate": {
            "derivation_kind": "ontology_graph_derivation",
            "anchor_concept": {"id": label, "label": label},
            "steps": [{"step": i + 1, "type": "graph_relation"} for i in range(support)],
            "evidence_concepts": [label],
            "confidence": conf,
        },
        "trace": {"useful_answer": True,
                  "matched_concepts": [{"concept_id": label, "canonical_name": label, "labels": {}}]},
    }


def test_define_subject_coverage_separates_referents() -> None:
    """The discriminative signal: a good define covers its whole subject (1.0); a wrong-referent
    define leaves content uncovered ('black hole' -> answer only about 'black' -> 0.5)."""
    good = _define_result(["machine learning"],
                          "Machine learning builds models that find patterns in data.")
    wrong = _define_result(["black"], "Black is a color that results from the absence of light.")
    assert ZUA._subject_coverage("what is machine learning?", good) == 1.0
    assert ZUA._subject_coverage("what is a black hole?", wrong) == 0.5


def test_define_lane_flag_off_is_identity() -> None:
    """Flag OFF: _gate_define_core returns the SAME object, adds NOTHING -> byte-identical."""
    r = _define_result(["black"], "Black is a color that results from the absence of light.")
    out = ZUA._gate_define_core(r, "what is a black hole?", "en")
    assert out is r
    assert "_membrane" not in out and "_membrane_signals" not in out


def test_define_lane_wrong_referent_abstains(monkeypatch) -> None:
    """Flag ON + define bin: a confident wrong-referent define ('black hole' -> 'Black is a color',
    conf 0.91) ABSTAINS on its own bin (subject_coverage doubt pushes nonconformity above q_hat)."""
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    monkeypatch.setattr(LW, "_load_calibration", _live_like_gate_with_define)
    r = _define_result(["black"], "Black is a color that results from the absence of light.")
    out = ZUA._gate_define_core(r, "what is a black hole?", "en")
    assert out["answer_kind"] == "honest_abstain"
    assert out["_membrane"]["decision"] == "ABSTAIN"
    # the certificate is the REAL gate decision on the define bin, not a fabricated number
    cert = out["reasoning_certificate"]["membrane_certificate"]
    assert cert["bin"] == "ontology_graph_derivation"
    assert cert["nonconformity"] > cert["q_hat"] == _DEFINE_Q_HAT


def test_define_lane_good_define_accepts(monkeypatch) -> None:
    """Flag ON + define bin: a good define (machine learning) covers its subject -> low nonconformity
    -> ACCEPT on the define bin (SAME object, answer kept). NOT abstained by the coarser relational
    q_hat, which would gate every good definition."""
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    monkeypatch.setattr(LW, "_load_calibration", _live_like_gate_with_define)
    r = _define_result(["machine learning"],
                       "Machine learning builds models that find patterns in data.", support=3)
    out = ZUA._gate_define_core(r, "what is machine learning?", "en")
    assert out is r                                      # accepted -> same object, answer kept
    assert out["answer_kind"] == "base_brain_zero_user_data"
    assert out["_membrane"]["decision"] == "ACCEPT"


def test_define_lane_ungated_when_define_bin_absent(monkeypatch) -> None:
    """Flag ON but the artifact carries NO define bin (partial operator recalibration): the define
    lane stays UNGATED (pre-membrane behavior) rather than borrow the relational fallback (~0.22),
    which would falsely abstain a good definition whose nonconformity exceeds 0.22."""
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    monkeypatch.setattr(LW, "_load_calibration", _live_like_gate)   # relational + grounded only
    r = _define_result(["machine learning"],
                       "Machine learning builds models that find patterns in data.")
    out = ZUA._gate_define_core(r, "what is machine learning?", "en")
    assert out is r                                      # SAME object, stayed ungated
    assert out["answer_kind"] == "base_brain_zero_user_data"
    assert "_membrane" not in out and "_membrane_signals" not in out


def test_entry_normalization_preserves_clean_query() -> None:
    """A clean define query is byte-identical through the normalizer -> the define lane answers it
    exactly as before (no behaviour shift from fix #2). Uses a curated-pack concept so the isolated
    test pack still answers it."""
    out = answer_with_base_brain("what is machine learning?", language="en")
    assert out["useful_answer"] is True
    assert out["answer_kind"] == "base_brain_zero_user_data"
    assert "machine learning" in out["answer"].lower()
