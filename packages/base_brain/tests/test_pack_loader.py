from packages.base_brain.pack_builder import build_base_brain_pack_v0
from packages.base_brain.pack_loader import get_semantic_context, get_surface_candidates, load_base_brain_pack


def test_pack_loader_matches_kubernetes() -> None:
    build_base_brain_pack_v0()
    pack = load_base_brain_pack()
    context = get_semantic_context("쿠버네티스가 뭐야?", pack)
    assert context
    assert context[0]["concept_id"] == "kubernetes"
    candidates = get_surface_candidates("쿠버네티스가 뭐야?", context, "ko", "beginner", pack=pack)
    assert candidates
    assert all(item["language"] == "ko" for item in candidates)


def test_substring_wrong_referent_blocked():
    """Maximal-match boundary rule: a concept name INSIDE a longer word must not match.
 Measured live bug: ' ' confidently answered about (carbon), and
 '' about (the electron) — the chronic wrong-referent class."""
    from packages.base_brain.pack_loader import _named_with_boundary, _norm

    # interior-of-word matches are rejected...
    assert not _named_with_boundary(_norm("방탄소년단이 뭐야"), _norm("탄소"))
    assert not _named_with_boundary(_norm("삼성전자란?"), _norm("전자"))
    assert not _named_with_boundary(_norm("탄소나노튜브가 뭐야"), _norm("탄소"))
    # ...while legitimate name+particle forms still match
    assert _named_with_boundary(_norm("탄소란?"), _norm("탄소"))
    assert _named_with_boundary(_norm("그럼 전자는?"), _norm("전자"))
    assert _named_with_boundary(_norm("인공지능이 뭐야"), _norm("인공지능"))
    assert _named_with_boundary(_norm("docker가 뭐야"), _norm("docker"))


def test_function_word_overlap_is_not_a_concept_match():
    """Overlap on a grammatical word is coincidence, not evidence of the topic. Measured
    2026-07-17: "What does a polar bear look like?" anchored on the concept "Like his father"
    (match=loose_token_overlap, score 1.5) because both contain 'like', and answered
    "like is a kind of kind. like relates to unlike." The real subject must win."""
    from packages.base_brain.pack_loader import _concept_score

    query = "What does a polar bear look like?"
    coincidence = {"concept_id": "vsc_x", "canonical_name": "Like his father",
                   "labels": {"en": "Like his father"}, "aliases": []}
    real = {"concept_id": "vsc_pb", "canonical_name": "polar bear",
            "labels": {"en": "polar bear"}, "aliases": []}
    assert _concept_score(query, coincidence) == 0.0
    assert _concept_score(query, real) > _concept_score(query, coincidence)

    # Korean is unaffected — particles are handled by _norm/_JOSA_TAILS, not this list
    ko = {"concept_id": "vsc_c", "canonical_name": "커피", "labels": {"ko": "커피"}, "aliases": []}
    assert _concept_score("커피가 뭐야", ko) > 0


def test_pack_language_containment_is_field_level_not_concept_level():
    """The answer pack is a SECOND store and needed the store's lang_gate twin (2026-07-17).

 Measured on the seal holdout: kg_triples was contained but the pack was not, and 45% of it
 is Korean. Subjects the graph cannot answer fall to base_brain, which composed from Korean
 short_descriptions; the chat exit gate then replaced the whole answer with a refusal. No
 Korean ever reached a user — but five holdout turns scored as refusals that should have
 engaged.

 FIELD-level is the load-bearing detail. The naive filter (drop any concept touching Hangul)
 kills 4,347 of 9,491 concepts, because the Hangul is mostly in labels.ko (4,170 — a proper
 i18n field) and aliases (198): Kubernetes carries the alias and an entirely English
 description. That filter costs recall and fixes nothing. Only ANSWER TEXT leaks —
 canonical_name and short_description, i.e. concepts that ARE Korean (//).
 """
    import os
    import re

    from packages.base_brain.pack_loader import load_base_brain_pack

    if os.environ.get("ATANOR_ENGLISH_ONLY", "1") == "0":
        import pytest
        pytest.skip("Korean lane explicitly enabled")

    han = re.compile(r"[가-힣]")
    pack = load_base_brain_pack()
    concepts = pack.semantic_graph.get("concepts") or []
    assert concepts, "containment must not empty the pack"

    for c in concepts:
        assert not han.search(str(c.get("canonical_name") or "")), c.get("concept_id")
        assert not han.search(str(c.get("short_description") or "")), c.get("concept_id")

    # a concept whose ONLY Hangul is an alias/label is real English knowledge and must survive
    names = {str(c.get("canonical_name") or "") for c in concepts}
    assert "Kubernetes" in names, "field-level filter must keep alias-only-Hangul concepts"
