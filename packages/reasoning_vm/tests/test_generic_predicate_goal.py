from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
from pathlib import Path
from typing import Any

import pytest

from packages.cognitive_core.canonical import canonical_digest
from packages.graph_scale.triple_store import TripleStore
from packages.reasoning_vm.deliberator.generic_predicate_goal import (
    GenericPredicateCompilation,
    compile_generic_predicate_goal,
    verify_generic_predicate_compilation,
)
from packages.reasoning_vm.deliberator.generic_predicate_socket import (
    CompositePredicateSocket,
    GenericPredicateContext,
    PREDICATE_NAMESPACE,
    PredicateStageSpec,
)
from packages.reasoning_vm.deliberator.relation_role_extractor import (
    SpacyRelationRoleExtractor,
)


@pytest.fixture(scope="module")
def extractor() -> SpacyRelationRoleExtractor:
    return SpacyRelationRoleExtractor()


def _tree_snapshot(root: Path) -> tuple[tuple[str, int, int, str], ...]:
    rows = []
    for path in sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: item.as_posix(),
    ):
        raw = path.read_bytes()
        stat = path.stat()
        rows.append(
            (
                path.relative_to(root).as_posix(),
                stat.st_size,
                stat.st_mtime_ns,
                hashlib.sha256(raw).hexdigest(),
            )
        )
    return tuple(rows)


def _context(
    tmp_path: Path,
    rows: tuple[tuple[str, str, str], ...],
    subject: str,
    *,
    max_facts: int = 16,
    max_rows: int = 32,
) -> tuple[GenericPredicateContext, Path]:
    root = tmp_path / "predicate_stage"
    store = TripleStore(root)
    source_id = store.intern_source("fixture", "")
    for row_subject, predicate, object_value in rows:
        assert store.add(
            row_subject,
            predicate,
            object_value,
            source=source_id,
        )
    store.flush()
    store.rebuild_index()
    store.close()
    with CompositePredicateSocket.open(
        (
            PredicateStageSpec(
                stage_id="generic-goal-fixture",
                role="generic",
                root=root,
            ),
        ),
        max_facts_per_stage=max_facts,
        max_rows_examined_per_stage=max_rows,
    ) as socket:
        result = socket.context_for_subject(subject)
    return result, root


def _compile(
    extractor: SpacyRelationRoleExtractor,
    stem: str,
    choices: tuple[tuple[str, str], ...],
    context: GenericPredicateContext,
) -> GenericPredicateCompilation:
    return compile_generic_predicate_goal(
        stem,
        choices,
        role_receipt=extractor.extract(stem),
        context=context,
    )


def test_dynamic_predicate_compiles_without_enum_and_does_not_write(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, root = _context(
        tmp_path,
        (("Zephyr", "catalyst_signature", "amber"),),
        "Zephyr",
    )
    before = _tree_snapshot(root)
    stem = "What catalyst_signature is Zephyr?"
    choice_items = (("A", "amber"), ("B", "violet"))

    first = _compile(extractor, stem, choice_items, context)
    second = _compile(extractor, stem, choice_items, context)

    assert _tree_snapshot(root) == before
    assert first == second
    assert first.compiled is True
    assert first.status == "compiled"
    assert first.reason == "compiled_internal_predicate_goal"
    assert first.goal is not None
    assert first.goal.subject == "Zephyr"
    assert first.goal.predicate.name == "catalyst_signature"
    assert first.goal.predicate.namespace == PREDICATE_NAMESPACE
    assert first.goal.predicate.wikidata_property_id is None
    assert first.goal.linkage.source == "relation_raw"
    assert first.goal.linkage.predicate_tokens == (
        "catalyst",
        "signature",
    )
    assert tuple(fact.object_value for fact in first.goal.facts) == (
        "amber",
    )
    assert first.goal.fact_bundle_digest_sha256
    assert all(value is False for value in first.claims.values())
    assert first.required_evidence["wikidata_pid_required"] is False
    expected_choices_digest = canonical_digest(
        [["A", "amber"], ["B", "violet"]]
    )
    assert first.choices_digest_sha256 == expected_choices_digest
    assert first.input_digest_sha256 == canonical_digest(
        {
            "stem": stem,
            "choices_digest_sha256": expected_choices_digest,
        }
    )
    assert canonical_digest(first.to_dict()) == canonical_digest(
        second.to_dict()
    )
    assert verify_generic_predicate_compilation(
        stem,
        first,
        role_receipt=extractor.extract(stem),
        context=context,
    )
    with pytest.raises(FrozenInstanceError):
        first.status = "abstain"  # type: ignore[misc]
    with pytest.raises(ValueError, match="evidence does not derive"):
        replace(
            first.goal,
            fact_bundle_digest_sha256="0" * 64,
        )
    tampered_choice = replace(
        first.choices[0],
        original_text="tampered",
        normalized_value="tampered",
        value_digest_sha256=hashlib.sha256(
            b"tampered"
        ).hexdigest(),
    )
    with pytest.raises(ValueError, match="choices digest does not derive"):
        replace(
            first,
            choices=(tampered_choice, *first.choices[1:]),
        )
    with pytest.raises(ValueError, match="incomplete"):
        replace(first, reason="predicate_surface_not_grounded")
    forged_goal = replace(
        first.goal,
        role_receipt_digest_sha256="0" * 64,
    )
    forged_compilation = replace(
        first,
        role_receipt_digest_sha256="0" * 64,
        goal=forged_goal,
    )
    assert not verify_generic_predicate_compilation(
        stem,
        forged_compilation,
        role_receipt=extractor.extract(stem),
        context=context,
    )


@pytest.mark.parametrize(
    (
        "rows",
        "subject",
        "stem",
        "choices",
        "predicate",
        "linkage_source",
    ),
    (
        (
            (("hydrogen", "atomic_number", "1"),),
            "hydrogen",
            "What is hydrogen's atomic number?",
            (("A", "1"), ("B", "2")),
            "atomic_number",
            "relation_raw",
        ),
        (
            (("water", "chemical_formula", "H2O"),),
            "water",
            "What is the chemical formula of water?",
            (("A", "H2O"), ("B", "CO2")),
            "chemical_formula",
            "relation_raw",
        ),
        (
            (("Dune", "genre", "science fiction"),),
            "Dune",
            "What genre is Dune?",
            (("A", "science fiction"), ("B", "fantasy")),
            "genre",
            "relation_raw",
        ),
        (
            (("Athens", "country", "Greece"),),
            "Athens",
            "Which country is Athens in?",
            (("A", "Greece"), ("B", "Italy")),
            "country",
            "wh_object_raw",
        ),
    ),
)
def test_graph_existing_predicates_share_one_general_matching_rule(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
    rows: tuple[tuple[str, str, str], ...],
    subject: str,
    stem: str,
    choices: tuple[tuple[str, str], ...],
    predicate: str,
    linkage_source: str,
) -> None:
    context, _root = _context(tmp_path, rows, subject)

    compilation = _compile(extractor, stem, choices, context)

    assert compilation.compiled is True
    assert compilation.goal is not None
    assert compilation.goal.predicate.name == predicate
    assert compilation.goal.linkage.source == linkage_source


def test_parser_lemma_can_bind_an_inflected_relation_without_alias_table(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, _root = _context(
        tmp_path,
        (("Project Lantern", "associate_with", "#aurora"),),
        "Project Lantern",
    )
    stem = (
        "Which social media hashtag is Project Lantern associated with?"
    )

    compilation = _compile(
        extractor,
        stem,
        (("A", "#aurora"), ("B", "#sol")),
        context,
    )

    assert compilation.compiled is True
    assert compilation.goal is not None
    assert compilation.goal.predicate.name == "associate_with"
    assert compilation.goal.linkage.source == "relation_lemma"
    assert compilation.goal.linkage.predicate_tokens == (
        "associate",
        "with",
    )


def test_internal_p31_text_never_becomes_a_wikidata_predicate_claim(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, _root = _context(
        tmp_path,
        (("water", "P31", "compound"),),
        "water",
    )

    compilation = _compile(
        extractor,
        "What is water's P31?",
        (("A", "compound"), ("B", "element")),
        context,
    )

    assert compilation.compiled is True
    assert compilation.goal is not None
    assert compilation.goal.predicate.canonical_id == "stage:P31"
    assert compilation.goal.predicate.wikidata_property_id is None
    assert compilation.claims["wikidata_pid_binding_established"] is False
    assert all(
        fact.source_property_id is None
        for fact in compilation.goal.facts
    )


def test_strict_partial_predicate_cannot_create_ambiguity(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, _root = _context(
        tmp_path,
        (
            ("hydrogen", "atomic", "element"),
            ("hydrogen", "atomic_number", "1"),
        ),
        "hydrogen",
    )

    compilation = _compile(
        extractor,
        "What is hydrogen's atomic number?",
        (("A", "1"), ("B", "2")),
        context,
    )

    assert compilation.compiled is True
    assert compilation.goal is not None
    assert compilation.goal.predicate.name == "atomic_number"


@pytest.mark.parametrize("unsafe_predicate", ("is", "be", "what", "which", "atomic"))
def test_function_only_and_strict_partial_predicates_never_ground(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
    unsafe_predicate: str,
) -> None:
    context, _root = _context(
        tmp_path,
        (("hydrogen", unsafe_predicate, "wrong"),),
        "hydrogen",
    )

    compilation = _compile(
        extractor,
        "What is hydrogen's atomic number?",
        (("A", "1"), ("B", "2")),
        context,
    )

    assert compilation.status == "abstain"
    assert compilation.reason == "predicate_surface_not_grounded"
    assert compilation.goal is None


def test_paraphrase_without_graph_owned_surface_abstains(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, _root = _context(
        tmp_path,
        (("Athens", "home_nation", "Greece"),),
        "Athens",
    )

    compilation = _compile(
        extractor,
        "Which country is Athens in?",
        (("A", "Greece"), ("B", "Italy")),
        context,
    )

    assert compilation.status == "abstain"
    assert compilation.reason == "predicate_surface_not_grounded"
    assert compilation.goal is None


@pytest.mark.parametrize(
    ("stem", "expected_reason"),
    (
        (
            "Which country does Athens not belong to?",
            "role_receipt_not_safe",
        ),
        (
            "Which country contains Athens?",
            "forward_query_not_established",
        ),
    ),
)
def test_hazard_and_inverse_queries_abstain_before_context_use(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
    stem: str,
    expected_reason: str,
) -> None:
    context, _root = _context(
        tmp_path,
        (("Athens", "country", "Greece"),),
        "Athens",
    )

    compilation = _compile(
        extractor,
        stem,
        (("A", "Greece"), ("B", "Italy")),
        context,
    )

    assert compilation.status == "abstain"
    assert compilation.reason == expected_reason
    assert compilation.context_digest_sha256 is None


def test_context_mismatch_not_found_and_overflow_fail_closed(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    stem = "What is hydrogen's atomic number?"
    receipt = extractor.extract(stem)
    choices = (("A", "1"), ("B", "2"))

    mismatch, _root = _context(
        tmp_path / "mismatch",
        (("water", "atomic_number", "8"),),
        "water",
    )
    mismatch_result = compile_generic_predicate_goal(
        stem,
        choices,
        role_receipt=receipt,
        context=mismatch,
    )

    not_found, _root = _context(
        tmp_path / "not_found",
        (("water", "atomic_number", "8"),),
        "hydrogen",
    )
    not_found_result = compile_generic_predicate_goal(
        stem,
        choices,
        role_receipt=receipt,
        context=not_found,
    )

    overflow, _root = _context(
        tmp_path / "overflow",
        (
            ("hydrogen", "atomic_number", "1"),
            ("hydrogen", "chemical_formula", "H"),
        ),
        "hydrogen",
        max_facts=1,
        max_rows=2,
    )
    overflow_result = compile_generic_predicate_goal(
        stem,
        choices,
        role_receipt=receipt,
        context=overflow,
    )

    assert mismatch_result.reason == "predicate_context_subject_mismatch"
    assert not_found.status == "not_found"
    assert not_found_result.reason == "predicate_context_not_ready"
    assert overflow.status == "overflow"
    assert overflow.facts == ()
    assert overflow.predicate_vocabulary == ()
    assert overflow_result.reason == "predicate_context_not_ready"


def test_receipt_input_mismatch_and_non_tuple_choices_are_invalid_without_reads(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, _root = _context(
        tmp_path,
        (("hydrogen", "atomic_number", "1"),),
        "hydrogen",
    )
    stem = "What is hydrogen's atomic number?"
    wrong_receipt = extractor.extract(
        "What is water's atomic number?"
    )

    mismatch = compile_generic_predicate_goal(
        stem,
        (("A", "1"), ("B", "2")),
        role_receipt=wrong_receipt,
        context=context,
    )

    class PoisonChoices:
        def __iter__(self) -> Any:
            raise AssertionError("non-tuple choices were enumerated")

    invalid_choices = compile_generic_predicate_goal(
        stem,
        PoisonChoices(),
        role_receipt=extractor.extract(stem),
        context=context,
    )

    assert mismatch.status == "invalid"
    assert mismatch.reason == "role_receipt_input_mismatch"
    assert invalid_choices.status == "invalid"
    assert invalid_choices.reason == "choice_items_not_tuple"
    assert invalid_choices.choices == ()
