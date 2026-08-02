from __future__ import annotations

from packages.local_memory_operator_confirmation.phrase import generate_required_phrase, normalize_phrase, phrase_matches


def test_required_phrase_is_deterministic() -> None:
    first = generate_required_phrase("manifest-1", "plan-1")
    second = generate_required_phrase("manifest-1", "plan-1")

    assert first == second
    assert first.startswith("I UNDERSTAND LOCAL BRAIN WRITE PREPARATION")


def test_phrase_requires_exact_normalized_match() -> None:
    required = generate_required_phrase("manifest-1", "plan-1")

    assert phrase_matches(required, f"  {required}  ")
    assert not phrase_matches(required, required.lower())
    assert not phrase_matches(required, "I UNDERSTAND LOCAL BRAIN WRITE")
    assert not phrase_matches(required, "")


def test_normalize_phrase_collapses_whitespace() -> None:
    assert normalize_phrase("  A   B\nC  ") == "A B C"
