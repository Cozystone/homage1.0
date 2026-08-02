from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
from types import MappingProxyType
from collections.abc import Mapping
from typing import Iterator

import pytest

from packages.reasoning_vm.deliberator.graph_relation_goal import (
    GraphEntity,
    GraphPropertyFact,
    GraphRelationContext,
    build_graph_relation_context,
    compile_graph_relation_goal,
)
from packages.reasoning_vm.deliberator.wikidata_property_catalog import (
    WikidataPropertyCatalogSnapshot,
    load_wikidata_property_catalog,
)


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures/wikidata_property_catalog_v1"
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _context(*, include_hashtag: bool = True):
    facts = [
        GraphPropertyFact(
            subject_entity_id="Q9001",
            property_id="P17",
            object_kind="entity",
            object_value="Q41",
            evidence_digest_sha256=_digest("project-country-row"),
        ),
        GraphPropertyFact(
            subject_entity_id="Q1524",
            property_id="P17",
            object_kind="entity",
            object_value="Q41",
            evidence_digest_sha256=_digest("athens-country-row"),
        ),
    ]
    if include_hashtag:
        facts.append(
            GraphPropertyFact(
                subject_entity_id="Q9001",
                property_id="P2572",
                object_kind="literal",
                object_value="#Atanor",
                evidence_digest_sha256=_digest("project-hashtag-row"),
            )
        )
    return build_graph_relation_context(
        stage_id="withheld-property-fixture-v1",
        source_digest_sha256=_digest("fixture-source"),
        entities=(
            GraphEntity(
                entity_id="Q1524",
                label="Athens",
                aliases=(),
                evidence_digest_sha256=_digest("athens-binding"),
            ),
            GraphEntity(
                entity_id="Q9001",
                label="Project Lantern",
                aliases=("Lantern",),
                evidence_digest_sha256=_digest("lantern-binding"),
            ),
        ),
        facts=tuple(facts),
    )


CHOICES = {
    "A": "#LocalAI",
    "B": "#Atanor",
    "C": "#Other",
}


def test_withheld_property_compiles_from_graph_and_catalog_only() -> None:
    catalog = load_wikidata_property_catalog(FIXTURE)
    context = _context()

    result = compile_graph_relation_goal(
        (
            "Which social media hashtag is Project Lantern "
            "associated with?"
        ),
        CHOICES,
        context=context,
        catalog=catalog,
    )

    assert result.compiled
    assert result.goal is not None
    assert result.goal.subject_entity_id == "Q9001"
    assert result.goal.subject_surface == "Project Lantern"
    assert result.goal.property_id == "P2572"
    assert result.goal.property_label == "hashtag"
    assert result.goal.matched_property_surface == "social media hashtag"
    assert result.goal.property_datatype == "string"
    assert result.goal.expected_object_kind == "literal"
    assert result.goal.selected_fact_count == 1
    assert result.goal.linkage_method == (
        "relation_before_subject_aux_gap"
    )
    assert result.goal.linkage_score >= 2.0
    assert result.goal.linkage_margin >= 0.25
    assert (
        result.goal.relation_span_sha256
        == _digest("social media hashtag")
    )
    assert result.required_evidence["fact_bundle_digest_sha256"] == (
        result.goal.fact_bundle_digest_sha256
    )
    assert result.required_evidence["subject_entity_id"] == "Q9001"
    assert result.required_evidence["catalog_source_revision"] > 0
    assert [row.key for row in result.choices] == ["A", "B", "C"]
    assert "choice_key" not in result.to_dict()
    assert result.required_evidence["original_property_id"] == "P2572"
    assert not any(result.claims.values())

    module_text = (
        Path(__file__).resolve().parents[1]
        / "deliberator/graph_relation_goal.py"
    ).read_text(encoding="utf-8")
    assert "P2572" not in module_text
    assert "RELATION_VOCAB" not in module_text
    assert "REL_SYNONYMS" not in module_text


def test_catalog_presence_without_subject_edge_cannot_compile() -> None:
    result = compile_graph_relation_goal(
        (
            "Which social media hashtag is Project Lantern "
            "associated with?"
        ),
        CHOICES,
        context=_context(include_hashtag=False),
        catalog=load_wikidata_property_catalog(FIXTURE),
    )

    assert not result.compiled
    assert result.reason == "property_surface_not_grounded"


def test_property_tie_and_multiple_subjects_abstain() -> None:
    catalog = load_wikidata_property_catalog(FIXTURE)
    context = _context()

    tie = compile_graph_relation_goal(
        "Which country hashtag is Project Lantern associated with?",
        CHOICES,
        context=context,
        catalog=catalog,
    )
    assert tie.reason == "property_surface_ambiguous"

    subjects = compile_graph_relation_goal(
        (
            "Which social media hashtag links Project Lantern "
            "and Athens?"
        ),
        CHOICES,
        context=context,
        catalog=catalog,
    )
    assert subjects.reason == "subject_ambiguous"


@pytest.mark.parametrize(
    ("stem", "reason"),
    [
        (
            "Which social media hashtag is Project Lantern not associated with?",
            "negation_not_supported",
        ),
        (
            "Which social media hashtag was Project Lantern associated with?",
            "temporal_semantics_not_supported",
        ),
        (
            "Which social media hashtag is Project Lantern most associated with?",
            "comparison_not_supported",
        ),
    ],
)
def test_semantic_hazards_abstain(stem: str, reason: str) -> None:
    result = compile_graph_relation_goal(
        stem,
        CHOICES,
        context=_context(),
        catalog=load_wikidata_property_catalog(FIXTURE),
    )

    assert not result.compiled
    assert result.reason == reason


def test_context_and_catalog_digests_bind_compilation() -> None:
    catalog = load_wikidata_property_catalog(FIXTURE)
    context = _context()
    first = compile_graph_relation_goal(
        (
            "Which social media hashtag is Project Lantern "
            "associated with?"
        ),
        CHOICES,
        context=context,
        catalog=catalog,
    )
    changed = compile_graph_relation_goal(
        (
            "Which social media hashtag is Project Lantern "
            "associated with?"
        ),
        {**CHOICES, "C": "#Different"},
        context=context,
        catalog=catalog,
    )
    assert first.input_digest_sha256 != changed.input_digest_sha256
    assert first.stage_digest_sha256 == context.stage_digest_sha256
    assert first.catalog_digest_sha256 == catalog.catalog_digest_sha256
    with pytest.raises(ValueError, match="evidence is not bound"):
        replace(
            first,
            required_evidence=MappingProxyType(
                {
                    **dict(first.required_evidence),
                    "original_property_id": "P17",
                }
            ),
        )

    object.__setattr__(context, "stage_digest_sha256", "0" * 64)
    with pytest.raises(ValueError, match="validation bound"):
        context.assert_validated()


def test_invalid_inputs_fail_closed() -> None:
    catalog = load_wikidata_property_catalog(FIXTURE)
    context = _context()
    duplicate = compile_graph_relation_goal(
        "Which hashtag is Project Lantern associated with?",
        {"A": "#Same", "B": "#Same"},
        context=context,
        catalog=catalog,
    )
    assert duplicate.status == "invalid"
    assert duplicate.reason == "duplicate_choice"

    unknown = compile_graph_relation_goal(
        "Which hashtag is Unknown Project associated with?",
        CHOICES,
        context=context,
        catalog=catalog,
    )
    assert unknown.status == "abstain"
    assert unknown.reason == "subject_not_grounded"


@pytest.mark.parametrize(
    ("stem", "reason"),
    [
        (
            "Which country criticized Project Lantern?",
            "property_role_not_grounded",
        ),
        (
            (
                "Which project is in the same country as "
                "Project Lantern?"
            ),
            "comparison_not_supported",
        ),
        (
            "Which entity has country Project Lantern?",
            "property_role_not_grounded",
        ),
        (
            (
                "Which social media hashtag doesn't Project "
                "Lantern use?"
            ),
            "negation_not_supported",
        ),
    ],
)
def test_false_syntactic_roles_fail_closed(
    stem: str,
    reason: str,
) -> None:
    result = compile_graph_relation_goal(
        stem,
        CHOICES,
        context=_context(),
        catalog=load_wikidata_property_catalog(FIXTURE),
    )

    assert not result.compiled
    assert result.reason == reason


@pytest.mark.parametrize(
    "stem",
    [
        "Which country is Project Lantern located in?",
        "What is the country of Project Lantern?",
        "Project Lantern has which social media hashtag?",
    ],
)
def test_generic_structural_frames_compile_without_relation_templates(
    stem: str,
) -> None:
    result = compile_graph_relation_goal(
        stem,
        CHOICES,
        context=_context(),
        catalog=load_wikidata_property_catalog(FIXTURE),
    )

    assert result.compiled
    assert result.goal is not None
    assert result.goal.property_id in {"P17", "P2572"}


def test_choice_content_cannot_select_or_change_the_goal() -> None:
    catalog = load_wikidata_property_catalog(FIXTURE)
    context = _context()
    stem = (
        "Which social media hashtag is Project Lantern "
        "associated with?"
    )
    variants = (
        CHOICES,
        {"C": "#Other", "A": "#LocalAI", "B": "#Atanor"},
        {"A": "#WrongOne", "B": "#WrongTwo"},
        {"X": "unrelated", "Y": "also unrelated"},
    )
    results = tuple(
        compile_graph_relation_goal(
            stem,
            choices,
            context=context,
            catalog=catalog,
        )
        for choices in variants
    )

    assert all(result.compiled for result in results)
    assert all(result.goal == results[0].goal for result in results)
    assert (
        results[0].input_digest_sha256
        == results[1].input_digest_sha256
    )
    assert len(
        {result.input_digest_sha256 for result in results}
    ) == len(results) - 1


def test_fact_order_is_canonical_and_full_evidence_is_bound() -> None:
    entities = (
        GraphEntity(
            entity_id="Q9001",
            label="Project Lantern",
            aliases=(),
            evidence_digest_sha256=_digest("subject"),
        ),
    )
    facts = (
        GraphPropertyFact(
            subject_entity_id="Q9001",
            property_id="P2572",
            object_kind="literal",
            object_value="#Atanor",
            evidence_digest_sha256=_digest("source-b"),
        ),
        GraphPropertyFact(
            subject_entity_id="Q9001",
            property_id="P2572",
            object_kind="literal",
            object_value="#Atanor",
            evidence_digest_sha256=_digest("source-a"),
        ),
    )
    first = build_graph_relation_context(
        stage_id="canonical-fact-order-v1",
        source_digest_sha256=_digest("source"),
        entities=entities,
        facts=facts,
    )
    second = build_graph_relation_context(
        stage_id="canonical-fact-order-v1",
        source_digest_sha256=_digest("source"),
        entities=entities,
        facts=tuple(reversed(facts)),
    )
    assert first.stage_digest_sha256 == second.stage_digest_sha256

    result = compile_graph_relation_goal(
        (
            "Which social media hashtag is Project Lantern "
            "associated with?"
        ),
        CHOICES,
        context=first,
        catalog=load_wikidata_property_catalog(FIXTURE),
    )
    assert result.compiled
    assert result.goal is not None
    assert result.goal.selected_fact_count == 2
    assert result.required_evidence["selected_fact_count"] == 2

    with pytest.raises(ValueError, match="duplicate exact graph fact"):
        build_graph_relation_context(
            stage_id="duplicate-fact-v1",
            source_digest_sha256=_digest("source"),
            entities=entities,
            facts=(facts[0], facts[0]),
        )


def test_catalog_datatype_and_staged_object_kind_must_agree() -> None:
    context = build_graph_relation_context(
        stage_id="kind-mismatch-v1",
        source_digest_sha256=_digest("source"),
        entities=(
            GraphEntity(
                entity_id="Q9001",
                label="Project Lantern",
                aliases=(),
                evidence_digest_sha256=_digest("subject"),
            ),
        ),
        facts=(
            GraphPropertyFact(
                subject_entity_id="Q9001",
                property_id="P2572",
                object_kind="entity",
                object_value="Q41",
                evidence_digest_sha256=_digest("wrong-kind"),
            ),
        ),
    )
    result = compile_graph_relation_goal(
        (
            "Which social media hashtag is Project Lantern "
            "associated with?"
        ),
        CHOICES,
        context=context,
        catalog=load_wikidata_property_catalog(FIXTURE),
    )
    assert not result.compiled
    assert result.reason == "property_datatype_fact_kind_mismatch"


def test_validation_runs_once_per_snapshot_not_once_per_entity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    catalog = load_wikidata_property_catalog(FIXTURE)
    context_calls = 0
    catalog_calls = 0
    original_context = GraphRelationContext.assert_validated
    original_catalog = WikidataPropertyCatalogSnapshot.assert_validated

    def count_context(self: GraphRelationContext) -> None:
        nonlocal context_calls
        context_calls += 1
        original_context(self)

    def count_catalog(
        self: WikidataPropertyCatalogSnapshot,
    ) -> None:
        nonlocal catalog_calls
        catalog_calls += 1
        original_catalog(self)

    monkeypatch.setattr(
        GraphRelationContext,
        "assert_validated",
        count_context,
    )
    monkeypatch.setattr(
        WikidataPropertyCatalogSnapshot,
        "assert_validated",
        count_catalog,
    )
    result = compile_graph_relation_goal(
        (
            "Which social media hashtag is Project Lantern "
            "associated with?"
        ),
        CHOICES,
        context=context,
        catalog=catalog,
    )
    assert result.compiled
    assert context_calls == 1
    assert catalog_calls == 1


class _LyingChoices(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        return f"value-{key}"

    def __iter__(self) -> Iterator[str]:
        return iter(str(index) for index in range(10_000))

    def __len__(self) -> int:
        return 2


def test_bounded_choice_snapshot_ignores_a_lying_length() -> None:
    result = compile_graph_relation_goal(
        (
            "Which social media hashtag is Project Lantern "
            "associated with?"
        ),
        _LyingChoices(),
        context=_context(),
        catalog=load_wikidata_property_catalog(FIXTURE),
    )
    assert result.status == "invalid"
    assert result.reason == "choice_count_out_of_bounds"


def test_exact_false_authority_values_are_required() -> None:
    context = _context()
    object.__setattr__(
        context,
        "authority_claims",
        MappingProxyType(
            {
                "capability_established": 0,
                "e4_established": 0,
                "e5_established": 0,
                "external_authenticity_established": 0,
                "independent_evaluation_established": 0,
            }
        ),
    )
    with pytest.raises(ValueError, match="validation bound"):
        context.assert_validated()
