from __future__ import annotations

from cgsr.ingestion.decomposer import (
    ENGLISH_GENERIC_HEADS,
    _english_definition_subject,
    extract_english_case_roles,
)


def test_definition_subject_keeps_real_multiword_subject():
    assert _english_definition_subject("Marie Curie was a physicist and chemist.") == "Marie Curie"
    assert _english_definition_subject("Electricity is the set of physical phenomena.") == "Electricity"
    assert _english_definition_subject("Photosynthesis is a system of biological processes.") == "Photosynthesis"


def test_definition_subject_drops_leading_article():
    assert _english_definition_subject("The telephone is a device.") == "telephone"
    assert _english_definition_subject("A telephone, shortened to phone, is a device.") == "telephone"


def test_definition_subject_skips_introductory_phrase():
    # The real subject follows the introductory prepositional phrase.
    assert _english_definition_subject("In physics, gravity is a fundamental interaction.") == "gravity"


def test_definition_subject_returns_empty_without_copula_or_clean_subject():
    assert _english_definition_subject("Plants convert sunlight into energy.") == ""
    # An over-long leading clause is not a clean subject.
    assert _english_definition_subject(
        "The very large and complicated multinational corporate entity is old."
    ) == ""


def test_case_roles_use_definition_subject_for_copula():
    roles, predicate = extract_english_case_roles("Marie Curie was a physicist.")
    assert predicate == "be"
    subjects = [role["head"] for role in roles if role["role"] == "SUBJ"]
    assert subjects == ["Marie Curie"]


def test_generic_heads_are_recognised():
    for head in ("other", "such", "various", "things"):
        assert head in ENGLISH_GENERIC_HEADS
