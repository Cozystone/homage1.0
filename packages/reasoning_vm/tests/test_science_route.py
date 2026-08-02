from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import inspect

import pytest

from packages.cognitive_core.canonical import canonical_digest
from packages.reasoning_vm.deliberator.science_goal import (
    SCIENCE_GOAL_FAMILY,
    SCIENCE_GOAL_SCHEMA,
    _SURFACES,
    compile_science_question,
)
from packages.reasoning_vm.deliberator.science_quantity_goal import (
    compile_neutralization_question,
)
from packages.reasoning_vm.deliberator.science_relation_goal import (
    MAX_STEM_CHARS as RELATION_MAX_STEM_CHARS,
    compile_typed_relation_select,
)
from packages.reasoning_vm.science_route import (
    ATOMIC_SURFACE_ADAPTER_CONTRACT_DIGEST_SHA256,
    ATOMIC_SURFACE_ADAPTER_SCHEMA,
    MAX_STEM_CHARS,
    RELATION_STEM_ADAPTER_SCHEMA,
    SCIENCE_ROUTE_CONTRACT_DIGEST_SHA256,
    SCIENCE_ROUTE_SCHEMA,
    ScienceRouteDecision,
    _reduce_profile_matches,
    classify_science_stem,
)


ATOMIC_STEM = "What is the atomic number of oxygen?"
ATOMIC_CHOICES = {"A": "1", "B": "2", "C": "8", "D": "10"}
SCALAR_STEM = (
    "What volume of 0.200 M NaOH is required to completely neutralize "
    "25.0 mL of 0.100 M HCl?"
)
SCALAR_CHOICES = {
    "A": "6.25 mL",
    "B": "12.5 mL",
    "C": "25.0 mL",
    "D": "50.0 mL",
}
RELATION_STEM = "Which country is Athens located in?"
RELATION_CHOICES = {
    "A": "France",
    "B": "Greece",
    "C": "Italy",
}


def test_public_api_is_structurally_stem_only():
    signature = inspect.signature(classify_science_stem)
    assert tuple(signature.parameters) == ("stem",)
    assert "choices" not in ScienceRouteDecision.__dataclass_fields__

    with pytest.raises(TypeError):
        classify_science_stem(ATOMIC_STEM, choices=ATOMIC_CHOICES)


def test_all_four_atomic_surfaces_select_only_the_atomic_lane():
    surfaces = (
        "What is the atomic number of oxygen?",
        "Which number is the atomic number of oxygen?",
        "Oxygen has which atomic number?",
        "Select the atomic number of oxygen.",
    )
    assert len(_SURFACES) == 4

    for stem in surfaces:
        decision = classify_science_stem(stem)
        assert decision.status == "selected"
        assert decision.lane == "atomic"
        assert decision.matched_profiles == ("atomic",)
        assert decision.reason == "atomic_profile_selected"
        assert compile_science_question(stem, ATOMIC_CHOICES).compiled is True


def test_scalar_predicate_selects_only_scalar_and_full_compiler_is_unchanged():
    decision = classify_science_stem(SCALAR_STEM)

    assert decision.status == "selected"
    assert decision.lane == "scalar"
    assert decision.matched_profiles == ("scalar",)
    assert decision.reason == "scalar_profile_selected"
    assert (
        compile_neutralization_question(SCALAR_STEM, SCALAR_CHOICES).compiled
        is True
    )


def test_all_four_diagnostic_relation_surfaces_select_only_relation():
    surfaces = (
        "Which country is Athens located in?",
        "In which country is Athens located?",
        "Athens is located in which country?",
        "Select the country in which Athens is located.",
    )

    for stem in surfaces:
        decision = classify_science_stem(stem)
        assert decision.status == "selected"
        assert decision.lane == "relation"
        assert decision.matched_profiles == ("relation",)
        assert decision.reason == "relation_profile_selected"
        assert compile_typed_relation_select(
            stem,
            RELATION_CHOICES,
        ).compiled is True


def test_narrow_relation_envelope_does_not_shrink_existing_router_envelope():
    assert RELATION_STEM_ADAPTER_SCHEMA.endswith(
        "relation_stem_adapter.v1"
    )
    assert MAX_STEM_CHARS > RELATION_MAX_STEM_CHARS
    decision = classify_science_stem("x" * (RELATION_MAX_STEM_CHARS + 1))
    assert decision.status == "unsupported"
    assert decision.reason == "unsupported_science_profile"


def test_well_formed_unsupported_stem_abstains_without_a_lane():
    decision = classify_science_stem("What is the boiling point of iron?")

    assert decision.status == "unsupported"
    assert decision.lane is None
    assert decision.matched_profiles == ()
    assert decision.reason == "unsupported_science_profile"


@pytest.mark.parametrize(
    ("stem", "reason"),
    [
        (None, "stem_not_string"),
        ("", "stem_out_of_bounds"),
        (" leading space", "stem_out_of_bounds"),
        ("trailing space ", "stem_out_of_bounds"),
        ("embedded\x00nul", "stem_out_of_bounds"),
        ("x" * 4097, "stem_out_of_bounds"),
    ],
)
def test_invalid_stems_fail_closed_deterministically(stem, reason):
    first = classify_science_stem(stem)
    second = classify_science_stem(stem)

    assert first == second
    assert first.status == "invalid"
    assert first.lane is None
    assert first.matched_profiles == ()
    assert first.reason == reason
    assert len(first.stem_digest_sha256) == 64


def test_private_reducer_makes_synthetic_ambiguity_fail_closed():
    decision = _reduce_profile_matches(
        ATOMIC_STEM,
        ("scalar", "atomic"),
    )

    assert decision.status == "ambiguous"
    assert decision.lane is None
    assert decision.matched_profiles == ("atomic", "scalar")
    assert decision.reason == "ambiguous_science_profile"


@pytest.mark.parametrize(
    "matches",
    [
        ("atomic", "atomic"),
        ("unknown",),
        ["atomic"],
    ],
)
def test_private_reducer_rejects_malformed_match_sets(matches):
    decision = _reduce_profile_matches(ATOMIC_STEM, matches)

    assert decision.status == "invalid"
    assert decision.lane is None
    assert decision.matched_profiles == ()
    assert decision.reason == "invalid_router_match_set"


def test_decision_has_exact_schema_types_and_is_frozen_with_slots():
    decision = classify_science_stem(ATOMIC_STEM)

    assert tuple(field.name for field in fields(ScienceRouteDecision)) == (
        "schema_version",
        "status",
        "lane",
        "matched_profiles",
        "reason",
        "stem_digest_sha256",
        "route_contract_digest_sha256",
    )
    assert not hasattr(decision, "__dict__")
    assert type(decision.schema_version) is str
    assert type(decision.status) is str
    assert type(decision.lane) is str
    assert type(decision.matched_profiles) is tuple
    assert type(decision.reason) is str
    assert type(decision.stem_digest_sha256) is str
    assert type(decision.route_contract_digest_sha256) is str
    assert decision.schema_version == SCIENCE_ROUTE_SCHEMA
    assert (
        decision.route_contract_digest_sha256
        == SCIENCE_ROUTE_CONTRACT_DIGEST_SHA256
    )
    assert decision.to_dict() == {
        "schema_version": SCIENCE_ROUTE_SCHEMA,
        "status": "selected",
        "lane": "atomic",
        "matched_profiles": ["atomic"],
        "reason": "atomic_profile_selected",
        "stem_digest_sha256": decision.stem_digest_sha256,
        "route_contract_digest_sha256": (
            SCIENCE_ROUTE_CONTRACT_DIGEST_SHA256
        ),
    }
    with pytest.raises(FrozenInstanceError):
        decision.status = "unsupported"


def test_atomic_adapter_digest_binds_the_exact_four_upstream_surfaces():
    expected = canonical_digest(
        {
            "schema_version": ATOMIC_SURFACE_ADAPTER_SCHEMA,
            "upstream_schema_version": SCIENCE_GOAL_SCHEMA,
            "goal_family": SCIENCE_GOAL_FAMILY,
            "surface_count": 4,
            "surfaces": [
                {
                    "family": family,
                    "rule": rule,
                    "pattern": pattern.pattern,
                    "flags": pattern.flags,
                }
                for family, rule, pattern in _SURFACES
            ],
        }
    )

    assert len(_SURFACES) == 4
    assert ATOMIC_SURFACE_ADAPTER_CONTRACT_DIGEST_SHA256 == expected
    assert len(expected) == 64


def test_replay_is_exact_and_stem_changes_are_digest_bound():
    first = classify_science_stem(ATOMIC_STEM)
    replay = classify_science_stem(ATOMIC_STEM)
    changed = classify_science_stem(
        "What is the atomic number of hydrogen?"
    )

    assert first == replay
    assert first.to_dict() == replay.to_dict()
    assert changed.status == "selected"
    assert changed.lane == "atomic"
    assert changed.stem_digest_sha256 != first.stem_digest_sha256
