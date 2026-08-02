from __future__ import annotations

import hashlib
from pathlib import Path
from types import MappingProxyType

import pytest

from packages.reasoning_vm.deliberator.graph_relation_goal import (
    GraphEntity,
    GraphPropertyFact,
    build_graph_relation_context,
    compile_graph_relation_goal,
)
from packages.reasoning_vm.deliberator.graph_relation_staging import (
    GraphRelationProofReceipt,
    consume_graph_relation_compilation,
    verify_graph_relation_proof_receipt,
)
from packages.reasoning_vm.deliberator.wikidata_property_catalog import (
    load_wikidata_property_catalog,
)


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures/wikidata_property_catalog_v1"
)
HASHTAG_STEM = (
    "Which social media hashtag is Project Lantern associated with?"
)
HASHTAG_CHOICES = {
    "A": "#LocalAI",
    "B": "#Atanor",
    "C": "#Other",
}
COUNTRY_STEM = "Which country is Project Lantern located in?"
COUNTRY_CHOICES = {
    "A": "France",
    "B": "Greece",
    "C": "Italy",
}


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _context(
    *,
    duplicate_hashtag_fact: bool = False,
    ambiguous_greece: bool = False,
    hashtag_kind: str = "literal",
):
    entities = [
        GraphEntity(
            entity_id="Q41",
            label="Greece",
            aliases=("Hellenic Republic",),
            evidence_digest_sha256=_digest("greece-binding"),
        ),
        GraphEntity(
            entity_id="Q9001",
            label="Project Lantern",
            aliases=("Lantern",),
            evidence_digest_sha256=_digest("lantern-binding"),
        ),
    ]
    if ambiguous_greece:
        entities.append(
            GraphEntity(
                entity_id="Q9999",
                label="Greece",
                aliases=(),
                evidence_digest_sha256=_digest(
                    "ambiguous-greece-binding"
                ),
            )
        )
    hashtag_value = "#Atanor" if hashtag_kind == "literal" else "Q41"
    facts = [
        GraphPropertyFact(
            subject_entity_id="Q9001",
            property_id="P17",
            object_kind="entity",
            object_value="Q41",
            evidence_digest_sha256=_digest("country-row"),
        ),
        GraphPropertyFact(
            subject_entity_id="Q9001",
            property_id="P2572",
            object_kind=hashtag_kind,
            object_value=hashtag_value,
            evidence_digest_sha256=_digest("hashtag-row"),
        ),
    ]
    if duplicate_hashtag_fact:
        facts.append(
            GraphPropertyFact(
                subject_entity_id="Q9001",
                property_id="P2572",
                object_kind="literal",
                object_value="#Atanor",
                evidence_digest_sha256=_digest(
                    "second-hashtag-row"
                ),
            )
        )
    return build_graph_relation_context(
        stage_id="graph-relation-proof-fixture-v1",
        source_digest_sha256=_digest("graph-source"),
        entities=tuple(entities),
        facts=tuple(facts),
    )


def _compile_hashtag(context=None, choices=None):
    graph = _context() if context is None else context
    catalog = load_wikidata_property_catalog(FIXTURE)
    compilation = compile_graph_relation_goal(
        HASHTAG_STEM,
        HASHTAG_CHOICES if choices is None else choices,
        context=graph,
        catalog=catalog,
    )
    return graph, catalog, compilation


def test_withheld_property_off_on_control_is_proof_carrying() -> None:
    context, catalog, compilation = _compile_hashtag()

    off = consume_graph_relation_compilation(
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
        enabled=False,
    )
    on = consume_graph_relation_compilation(
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
        enabled=True,
    )

    assert off.status == "abstain"
    assert off.reason == "proof_membrane_disabled"
    assert off.engine_fired is False
    assert off.receipt is None
    assert on.status == "proved"
    assert on.reason == "exactly_one_provable_choice"
    assert on.engine_fired is True
    assert on.choice_key == "B"
    assert type(on.receipt) is GraphRelationProofReceipt
    assert on.receipt.property_id == "P2572"
    assert on.receipt.fact_object_kind == "literal"
    assert on.receipt.fact_object_value == "#Atanor"
    assert on.receipt.choice_normalized_value == "#Atanor"
    assert verify_graph_relation_proof_receipt(
        on.receipt,
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
    )
    assert not any(off.claims.values())
    assert not any(on.claims.values())
    assert not any(on.receipt.claims.values())

    module_text = (
        Path(__file__).resolve().parents[1]
        / "deliberator/graph_relation_staging.py"
    ).read_text(encoding="utf-8")
    assert "P2572" not in module_text


def test_receipt_binds_input_stage_fact_catalog_and_choice() -> None:
    context, catalog, compilation = _compile_hashtag()
    decision = consume_graph_relation_compilation(
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
        enabled=True,
    )
    receipt = decision.receipt
    assert receipt is not None
    entry = catalog.property_by_id("P2572")
    assert entry is not None

    assert (
        receipt.compilation_input_digest_sha256
        == compilation.input_digest_sha256
    )
    assert receipt.stage_id == context.stage_id
    assert receipt.stage_digest_sha256 == context.stage_digest_sha256
    assert (
        receipt.stage_source_digest_sha256
        == context.source_digest_sha256
    )
    assert (
        receipt.catalog_digest_sha256
        == catalog.catalog_digest_sha256
    )
    assert (
        receipt.catalog_manifest_checksum_sha256
        == catalog.manifest_checksum_sha256
    )
    assert (
        receipt.catalog_source_artifact_sha256
        == entry.evidence.source_file_sha256
    )
    assert (
        receipt.catalog_source_record_sha256
        == entry.evidence.source_record_sha256
    )
    assert (
        receipt.catalog_source_revision
        == entry.evidence.source_revision
    )
    assert (
        receipt.fact_bundle_digest_sha256
        == compilation.goal.fact_bundle_digest_sha256
    )
    assert receipt.selected_fact_count == 1
    assert (
        receipt.fact_evidence_digest_sha256
        == _digest("hashtag-row")
    )
    assert len(receipt.proof_digest_sha256) == 64


def test_choice_insertion_order_does_not_rank_or_change_proof() -> None:
    context = _context()
    catalog = load_wikidata_property_catalog(FIXTURE)
    first = compile_graph_relation_goal(
        HASHTAG_STEM,
        HASHTAG_CHOICES,
        context=context,
        catalog=catalog,
    )
    reordered = compile_graph_relation_goal(
        HASHTAG_STEM,
        {
            "C": "#Other",
            "B": "#Atanor",
            "A": "#LocalAI",
        },
        context=context,
        catalog=catalog,
    )
    first_decision = consume_graph_relation_compilation(
        HASHTAG_STEM,
        first,
        context=context,
        catalog=catalog,
        enabled=True,
    )
    reordered_decision = consume_graph_relation_compilation(
        HASHTAG_STEM,
        reordered,
        context=context,
        catalog=catalog,
        enabled=True,
    )

    assert first.input_digest_sha256 == reordered.input_digest_sha256
    assert first_decision.choice_key == "B"
    assert reordered_decision.choice_key == "B"
    assert (
        first_decision.receipt.to_dict()
        == reordered_decision.receipt.to_dict()
    )


def test_answer_removal_abstains_without_guessing() -> None:
    context, catalog, compilation = _compile_hashtag(
        choices={
            "A": "#LocalAI",
            "B": "#Absent",
            "C": "#Other",
        }
    )

    decision = consume_graph_relation_compilation(
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
        enabled=True,
    )

    assert decision.status == "abstain"
    assert decision.reason == "no_provable_choice"
    assert decision.engine_fired is False
    assert decision.choice_key is None
    assert decision.receipt is None


def test_duplicate_fact_proofs_abstain_on_cardinality() -> None:
    context = _context(duplicate_hashtag_fact=True)
    context, catalog, compilation = _compile_hashtag(context=context)

    assert compilation.goal.selected_fact_count == 2
    decision = consume_graph_relation_compilation(
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
        enabled=True,
    )

    assert decision.status == "abstain"
    assert decision.reason == "proof_cardinality_not_one"
    assert decision.receipt is None


def test_two_choice_aliases_for_one_entity_are_not_ranked() -> None:
    context = _context()
    catalog = load_wikidata_property_catalog(FIXTURE)
    compilation = compile_graph_relation_goal(
        COUNTRY_STEM,
        {
            "A": "France",
            "B": "Greece",
            "C": "Hellenic Republic",
        },
        context=context,
        catalog=catalog,
    )

    decision = consume_graph_relation_compilation(
        COUNTRY_STEM,
        compilation,
        context=context,
        catalog=catalog,
        enabled=True,
    )

    assert decision.status == "abstain"
    assert decision.reason == "proof_cardinality_not_one"
    assert decision.receipt is None


def test_entity_choice_requires_one_unique_staged_entity() -> None:
    context = _context()
    catalog = load_wikidata_property_catalog(FIXTURE)
    compilation = compile_graph_relation_goal(
        COUNTRY_STEM,
        COUNTRY_CHOICES,
        context=context,
        catalog=catalog,
    )
    decision = consume_graph_relation_compilation(
        COUNTRY_STEM,
        compilation,
        context=context,
        catalog=catalog,
        enabled=True,
    )

    assert decision.status == "proved"
    assert decision.choice_key == "B"
    assert decision.receipt.fact_object_kind == "entity"
    assert decision.receipt.fact_object_value == "Q41"
    assert verify_graph_relation_proof_receipt(
        decision.receipt,
        COUNTRY_STEM,
        compilation,
        context=context,
        catalog=catalog,
    )

    ambiguous = _context(ambiguous_greece=True)
    ambiguous_compilation = compile_graph_relation_goal(
        COUNTRY_STEM,
        COUNTRY_CHOICES,
        context=ambiguous,
        catalog=catalog,
    )
    ambiguous_decision = consume_graph_relation_compilation(
        COUNTRY_STEM,
        ambiguous_compilation,
        context=ambiguous,
        catalog=catalog,
        enabled=True,
    )
    assert ambiguous_decision.reason == "no_provable_choice"


def test_property_datatype_and_fact_kind_mismatch_never_fires() -> None:
    context = _context(hashtag_kind="entity")
    catalog = load_wikidata_property_catalog(FIXTURE)
    compilation = compile_graph_relation_goal(
        HASHTAG_STEM,
        HASHTAG_CHOICES,
        context=context,
        catalog=catalog,
    )

    assert not compilation.compiled
    assert (
        compilation.reason
        == "property_datatype_fact_kind_mismatch"
    )
    decision = consume_graph_relation_compilation(
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
        enabled=True,
    )
    assert decision.reason == "compilation_not_compiled"
    assert decision.engine_fired is False


def test_independent_verifier_rejects_receipt_and_stem_tamper() -> None:
    context, catalog, compilation = _compile_hashtag()
    decision = consume_graph_relation_compilation(
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
        enabled=True,
    )
    receipt = decision.receipt
    assert receipt is not None

    assert not verify_graph_relation_proof_receipt(
        receipt,
        HASHTAG_STEM.replace("Which", "What"),
        compilation,
        context=context,
        catalog=catalog,
    )
    object.__setattr__(receipt, "choice_key", "A")
    assert not verify_graph_relation_proof_receipt(
        receipt,
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
    )


def test_independent_verifier_rejects_stage_and_compiler_tamper() -> None:
    context, catalog, compilation = _compile_hashtag()
    decision = consume_graph_relation_compilation(
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
        enabled=True,
    )
    receipt = decision.receipt
    assert receipt is not None

    object.__setattr__(
        compilation.goal,
        "fact_bundle_digest_sha256",
        "0" * 64,
    )
    assert not verify_graph_relation_proof_receipt(
        receipt,
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
    )

    context, catalog, compilation = _compile_hashtag()
    decision = consume_graph_relation_compilation(
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
        enabled=True,
    )
    receipt = decision.receipt
    assert receipt is not None
    selected_fact = next(
        row for row in context.facts if row.property_id == "P2572"
    )
    object.__setattr__(
        selected_fact,
        "evidence_digest_sha256",
        "0" * 64,
    )
    assert not verify_graph_relation_proof_receipt(
        receipt,
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
    )


def test_independent_verifier_rejects_catalog_and_claim_tamper() -> None:
    context, catalog, compilation = _compile_hashtag()
    decision = consume_graph_relation_compilation(
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
        enabled=True,
    )
    receipt = decision.receipt
    assert receipt is not None

    forged_claims = dict(receipt.claims)
    forged_claims["capability_improvement_established"] = True
    object.__setattr__(
        receipt,
        "claims",
        MappingProxyType(forged_claims),
    )
    assert not verify_graph_relation_proof_receipt(
        receipt,
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
    )

    context, catalog, compilation = _compile_hashtag()
    decision = consume_graph_relation_compilation(
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
        enabled=True,
    )
    receipt = decision.receipt
    assert receipt is not None
    entry = catalog.property_by_id("P2572")
    assert entry is not None
    object.__setattr__(
        entry.evidence,
        "source_revision",
        entry.evidence.source_revision + 1,
    )
    assert not verify_graph_relation_proof_receipt(
        receipt,
        HASHTAG_STEM,
        compilation,
        context=context,
        catalog=catalog,
    )


def test_exact_runtime_types_are_required() -> None:
    context, catalog, compilation = _compile_hashtag()

    with pytest.raises(TypeError, match="bool"):
        consume_graph_relation_compilation(
            HASHTAG_STEM,
            compilation,
            context=context,
            catalog=catalog,
            enabled=1,
        )
    with pytest.raises(TypeError, match="receipt"):
        verify_graph_relation_proof_receipt(
            object(),
            HASHTAG_STEM,
            compilation,
            context=context,
            catalog=catalog,
        )
