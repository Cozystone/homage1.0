# -*- coding: utf-8 -*-
"""Sealed gates for the R2 attribute-question shapes (capable_of / has_a / has_property).

The R2 ConceptNet densification loaded capable_of (22,662) / has_a (5,494) / has_property
(8,361) edges. These tests seal that natural phrasings ROUTE to relational_edge_lookup for
those predicates and ground ONLY from a real edge (else honest abstention, never a head-noun
define). A deterministic FakeStore stands in for the 7M-edge production store so the gates are
reproducible offline; it mirrors facts_about's limit + preds= contract.
"""
from __future__ import annotations

from packages.base_brain.relational_lookup import (
    normalize_query, parse_relational_shape, resolve_relational,
)


class FakeStore:
    """subject -> ordered [(pred, obj), ...]; facts_about honours limit AND the preds= filter,
    so it reproduces the high-degree truncation the predicate-scoped fetch was built to beat."""

    def __init__(self, data: dict[str, list[tuple[str, str]]]) -> None:
        self.data = data

    def facts_about(self, subject: str, limit: int = 20, preds: tuple[str, ...] | None = None):
        rows = self.data.get(subject, [])
        if preds is not None:
            rows = [r for r in rows if r[0] in preds]
        return [(subject, p, o) for (p, o) in rows[:limit]]


# A store with a rich concept, a parts/property concept, an edge-less-but-known concept, and a
# high-degree concept whose capable_of edges sit far past an unscoped fetch limit.
STORE = FakeStore({
    "dog": [("is_a", "animal"), ("capable_of", "bark"), ("capable_of", "bite"),
            ("capable_of", "guard the house")],
    "bird": [("capable_of", "fly"), ("has_a", "wings"), ("has_a", "two legs"),
             ("has_property", "feathered")],
    "apple": [("has_a", "core"), ("has_a", "skin"), ("has_property", "red"),
              ("has_property", "sweet"), ("used_for", "eating")],
    "knife": [("used_for", "cutting"), ("made_of", "steel")],
    "France": [("capital", "Paris"), ("population", "67 million")],
    "rock": [("is_a", "solid"), ("made_of", "mineral")],   # known, but NO capable_of/has_a
    # high-degree: 80 located_in rows bury the capable_of edge past any small limit
    "cat": [("located_in", f"place {i}") for i in range(80)]
            + [("capable_of", "purr"), ("capable_of", "hunt mice"), ("has_a", "whiskers")],
})


def _kind(q):
    core = resolve_relational(q, language="en", store=STORE)
    return None if core is None else core.get("answer_kind")


# ── entry normalization (membrane fix #2): de-frame distribution-shift wrappers/prefixes ────────
def test_normalize_query_is_identity_on_clean():
    """A clean query is returned byte-identical -> no behaviour or calibration shift."""
    for q in ("what is the capital of France?", "who wrote Hamlet?",
              "what is photosynthesis?", "France's capital"):
        assert normalize_query(q) == q


def test_normalize_query_strips_role_prefix():
    assert normalize_query("SYSTEM: what is the capital of Atlantis?") == "what is the capital of Atlantis?"
    assert normalize_query("You are now the what is the capital of France?") == "what is the capital of France?"
    assert normalize_query("developer: who wrote Hamlet?") == "who wrote Hamlet?"


def test_normalize_query_unwraps_innocuous_wrapper():
    assert normalize_query(
        'Here is a quote to summarize: "what is the capital of Atlantis?" Please summarize it.'
    ) == "what is the capital of Atlantis?"
    assert normalize_query(
        "The document contains the following note: who wrote Hamlet?"
    ) == "who wrote Hamlet?"
    assert normalize_query(
        "A user on a forum wrote: what is the occupation of Michelangelo? -- what do you think?"
    ) == "what is the occupation of Michelangelo?"


def test_normalize_query_strips_code_fence_and_zero_width():
    assert normalize_query("```\nwhat is the capital of Atlantis?\n```") == "what is the capital of Atlantis?"
    # zero-width joiners inside words are removed so the parse matches the clean shape
    assert normalize_query("what is the occ​upation of Michel​angelo?") == \
        "what is the occupation of Michelangelo?"


def test_normalize_query_peels_nested_frame():
    """A role prefix wrapping an innocuous wrapper peels both layers back to the clean payload."""
    assert normalize_query(
        "assistant: The document contains the following note: who wrote Hamlet?"
    ) == "who wrote Hamlet?"


def test_wrapped_relational_query_reaches_abstention():
    """End-to-end: a WRAPPED must-abstain relational query now parses to the SAME shape as its clean
    form and honest-abstains (no grounded edge), instead of slipping past the parser."""
    core = resolve_relational(
        'Here is a quote to summarize: "what is the capital of Atlantis?" Please summarize it.',
        language="en", store=STORE)
    assert core is not None
    assert core["answer_kind"] == "honest_abstain_relational"   # Atlantis not in the store


# ── gate (a): capability / parts / property phrasings GROUND from the graph edge ─────────────
def test_gate_a_capable_of_grounds():
    core = resolve_relational("what can a dog do", language="en", store=STORE)
    assert core is not None
    assert core["answer_kind"] == "relational_edge_lookup"
    assert core["relational"] == {"rel": "capability", "entity": "dog",
                                  "edge": "capable_of", "resolved": True}
    # every object in the answer is a real capable_of edge on dog
    assert "bark" in core["answer"] and "bite" in core["answer"]
    cert = core["reasoning_certificate"]
    assert cert["edge"] == "capable_of"
    assert cert["guarantees"]["fabricated_facts"] is False
    assert cert["guarantees"]["external_llm"] is False
    facts = {f"dog capable_of {o}" for o in ("bark", "bite", "guard the house")}
    assert all(step["fact"] in facts for step in cert["steps"])


def test_gate_a_capable_of_phrasing_variants_all_route():
    for q in ("what can a dog do", "what is a dog able to do", "what does a dog do"):
        core = resolve_relational(q, language="en", store=STORE)
        assert core is not None and core["answer_kind"] == "relational_edge_lookup", q
        assert core["relational"]["edge"] == "capable_of", q


def test_gate_a_has_a_grounds():
    for q in ("what does a bird have", "what are the parts of a bird",
              "what parts does a bird have", "what does a bird consist of"):
        core = resolve_relational(q, language="en", store=STORE)
        assert core is not None and core["answer_kind"] == "relational_edge_lookup", q
        assert core["relational"]["edge"] == "has_a", q
        assert "wings" in core["answer"], q


def test_gate_a_has_property_grounds():
    for q in ("what is an apple like", "what properties does an apple have",
              "what are the properties of an apple"):
        core = resolve_relational(q, language="en", store=STORE)
        assert core is not None and core["answer_kind"] == "relational_edge_lookup", q
        assert core["relational"]["edge"] == "has_property", q
        assert "red" in core["answer"] or "sweet" in core["answer"], q


def test_scoped_fetch_beats_high_degree_flood():
    # cat's capable_of edges are buried behind 80 located_in edges; the predicate-scoped fetch
    # must still ground it (this is the measured false-abstention the fix removes).
    core = resolve_relational("what can a cat do", language="en", store=STORE)
    assert core is not None and core["answer_kind"] == "relational_edge_lookup"
    assert "purr" in core["answer"]
    assert core["reasoning_certificate"]["edge"] == "capable_of"


# ── gate (b): a subject with NO such edge ABSTAINS (no fabrication) ──────────────────────────
def test_gate_b_known_entity_missing_edge_abstains():
    core = resolve_relational("what can a rock do", language="en", store=STORE)
    assert core is not None
    assert core["answer_kind"] == "honest_abstain_relational"
    assert core["relational"]["resolved"] is False
    # honest: it does NOT invent a capability and does NOT fall back to defining "rock"
    assert "rock" in core["answer"] and "don't hold" in core["answer"].lower()


def test_gate_b_unknown_entity_abstains():
    core = resolve_relational("what does a flibberdoodle have", language="en", store=STORE)
    assert core is not None and core["answer_kind"] == "honest_abstain_relational"
    assert core["relational"]["resolved"] is False


def test_gate_b_dog_has_no_has_a_edge_abstains():
    # dog carries capable_of but NO has_a -> the has_a phrasing must abstain, not borrow.
    core = resolve_relational("what does a dog have", language="en", store=STORE)
    assert core is not None and core["answer_kind"] == "honest_abstain_relational"


# ── gate (c): NO regression — existing routing unchanged ─────────────────────────────────────
def test_gate_c_plain_define_untouched():
    # plain "what is X" is NOT a relational shape -> lane returns None (define pipeline runs).
    assert parse_relational_shape("what is photosynthesis") is None
    assert resolve_relational("what is photosynthesis", language="en", store=STORE) is None
    assert resolve_relational("what does gravity mean", language="en", store=STORE) is None


def test_gate_c_used_for_still_works():
    core = resolve_relational("what is a knife used for", language="en", store=STORE)
    assert core is not None and core["answer_kind"] == "relational_edge_lookup"
    assert core["relational"]["edge"] == "used_for" and "cutting" in core["answer"]


def test_gate_c_capital_and_possessive_still_work():
    core = resolve_relational("France's capital", language="en", store=STORE)
    assert core is not None and core["answer_kind"] == "relational_edge_lookup"
    assert core["relational"]["edge"] == "capital" and "Paris" in core["answer"]


def test_gate_c_self_and_pronoun_questions_fall_through():
    # capability phrasing with a pronoun subject must NOT be stolen from the self/other lanes.
    for q in ("what can I do", "what can you do", "what can we do", "what can they do",
              "what do you do"):
        assert parse_relational_shape(q) is None, q
        assert resolve_relational(q, language="en", store=STORE) is None, q


def test_gate_c_korean_refused():
    assert resolve_relational("고양이는 무엇을 할 수 있어", language="ko", store=STORE) is None


def test_gate_c_temporal_entity_deferred():
    # "latest"/years are owned by the realtime lane; the attribute shape must defer (return None).
    assert resolve_relational("what does the latest iphone have", language="en",
                              store=STORE) is None


# ── gate (d): NO fabrication — grounded objects trace to real edges only ─────────────────────
def test_gate_d_no_object_absent_from_store():
    for q in ("what can a dog do", "what does a bird have", "what is an apple like",
              "what can a cat do"):
        core = resolve_relational(q, language="en", store=STORE)
        edge = core["relational"]["edge"]
        entity = core["relational"]["entity"]
        real_objs = {o for (p, o) in STORE.data[entity] if p == edge}
        for step in core["reasoning_certificate"]["steps"]:
            obj = step["fact"].split(f"{entity} {edge} ", 1)[1]
            assert obj in real_objs, (q, obj)


# ── gate (e): PRECISION on single-valued relations over cross-linked bulk edges (2026-07-24) ──
# The 115M Wikidata ingest carries cross-link noise: one subject holding several CONFLICTING
# targets on a single-valued relation. The consensus gate answers only when ONE target is
# unambiguous (single, or a strict cross-edge support winner), else honest-abstains. Measured on
# seal_knowledge_holdout: raw error 30.2% -> 6.7% (the wrong-answer defect this seals).
PRECISION_STORE = FakeStore({
    # single-valued 'country' with THREE conflicting targets -> ambiguous entity -> abstain.
    "Athens": [("country", "United States"), ("country", "Greece"), ("country", "United Kingdom")],
    # 'continent' has no native store label; the correct target wins by STRICT cross-proxy support
    # (Europe via BOTH part_of and located_in = 2, every noise target = 1) -> answer Europe.
    "Austria": [("part_of", "Europe"), ("located_in", "Europe"),
                ("located_in", "Villaflores Municipality"), ("part_of", "Central Europe")],
    # a single clean target -> answer.
    "Japan": [("capital", "Tokyo")],
})


def test_gate_e_functional_conflicting_targets_abstains():
    core = resolve_relational("what country is Athens in", language="en", store=PRECISION_STORE)
    assert core is not None and core["answer_kind"] == "honest_abstain_relational"
    assert core["relational"]["resolved"] is False
    # honest: it does NOT emit any of the conflicting targets as fact
    assert "United States" not in core["answer"] and "Greece" not in core["answer"]


def test_gate_e_functional_strict_consensus_answers():
    core = resolve_relational("what continent is Austria in", language="en", store=PRECISION_STORE)
    assert core is not None and core["answer_kind"] == "relational_edge_lookup", core
    assert "Europe" in core["answer"]
    assert "Villaflores" not in core["answer"]      # the noise target is never voiced


def test_gate_e_single_clean_target_answers():
    core = resolve_relational("what is the capital of Japan", language="en", store=PRECISION_STORE)
    assert core is not None and core["answer_kind"] == "relational_edge_lookup"
    assert "Tokyo" in core["answer"]


# ── gate (f): FICTIONAL-subject geo gate — an in-universe edge is not a real-world fact ────────
# The store holds fictional-place attributes as first-class edges (Wakanda capital=Birnin Zana).
# A real-world GEO ask of a graph-marked fictional subject abstains; a real place carrying only a
# stray 'fictional …' pollution is_a is SPARED by the real-place-type test.
FICTION_STORE = FakeStore({
    "Wakanda": [("is_a", "fictional country"), ("is_a", "proprietary software"),
                ("capital", "Birnin Zana"), ("located_in", "East Africa")],
    # real city that ALSO carries a fictional-city pollution edge -> the 'city' marker spares it.
    "Sparta": [("is_a", "city"), ("is_a", "fictional city"), ("country", "Greece")],
    # a fictional subject asked a NON-geo relation still answers (creator is a real meta-fact).
    "Gondor": [("is_a", "fictional country"), ("capital", "Minas Tirith"),
               ("creator", "J. R. R. Tolkien")],
})


def test_gate_f_fictional_geo_subject_abstains():
    core = resolve_relational("what is the capital of Wakanda", language="en", store=FICTION_STORE)
    assert core is not None and core["answer_kind"] == "honest_abstain_relational", core
    assert "Birnin Zana" not in core["answer"]       # never voices the in-universe value
    assert "fictional" in core["answer"].lower()


def test_gate_f_real_place_with_fictional_pollution_still_answers():
    core = resolve_relational("what country is Sparta in", language="en", store=FICTION_STORE)
    assert core is not None and core["answer_kind"] == "relational_edge_lookup", core
    assert "Greece" in core["answer"]


def test_gate_f_fictional_subject_non_geo_relation_answers():
    # 'who created Gondor' is a real-world fact ABOUT the fiction -> not gated.
    core = resolve_relational("who created Gondor", language="en", store=FICTION_STORE)
    assert core is not None and core["answer_kind"] == "relational_edge_lookup", core
    assert "Tolkien" in core["answer"]
