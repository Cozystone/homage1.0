from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import inspect
import json
from pathlib import Path
import struct

import pytest

from packages.cognitive_core.canonical import canonical_digest
from packages.graph_scale.triple_store import TripleStore
from packages.reasoning_vm.deliberator.generic_predicate_goal import (
    GenericPredicateCompilation,
    PredicateTokenLinkage,
    compile_generic_predicate_goal,
)
from packages.reasoning_vm.deliberator.generic_predicate_socket import (
    QID_PID_RECORD_FORMAT,
    BoundPredicateStage,
    CompositePredicateSocket,
    GenericPredicateContext,
    GenericPredicateFact,
    PredicateStageSpec,
)
from packages.reasoning_vm.deliberator.generic_predicate_staging import (
    GenericPredicateProofReceipt,
    GenericPredicateStagingError,
    consume_generic_predicate_compilation,
    verify_generic_predicate_proof_receipt,
)
from packages.reasoning_vm.deliberator.relation_role_extractor import (
    RelationRoleReceipt,
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
    role: str = "entity",
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
    sidecar_digest = None
    if role == "literal":
        predicates = {predicate for _, predicate, _ in rows}
        assert len(predicates) == 1
        sidecar_raw = b"".join(
            struct.pack("<QI", 556, 1086) for _ in rows
        )
        (root / "qid_pid.col").write_bytes(sidecar_raw)
        sidecar_digest = hashlib.sha256(sidecar_raw).hexdigest()
        (root / "S1_WIKIDATA_LITERAL_MANIFEST.json").write_text(
            json.dumps(
                {
                    "completion_state": "complete",
                    "promotion_eligible": True,
                    "property_profile": {
                        "P1086": {"predicate": next(iter(predicates))}
                    },
                    "qid_pid_sidecar": {
                        "path": "qid_pid.col",
                        "record_format": QID_PID_RECORD_FORMAT,
                        "record_bytes": 12,
                        "records": len(rows),
                        "sha256": sidecar_digest,
                    },
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    with CompositePredicateSocket.open(
        (
            PredicateStageSpec(
                stage_id="generic-proof-fixture",
                role=role,
                root=root,
                expected_qid_pid_sidecar_digest_sha256=sidecar_digest,
            ),
        ),
        max_facts_per_stage=16,
        max_rows_examined_per_stage=32,
    ) as socket:
        context = socket.context_for_subject(subject)
    return context, root


def _compile(
    extractor: SpacyRelationRoleExtractor,
    stem: str,
    choices: tuple[tuple[str, str], ...],
    context: GenericPredicateContext,
) -> tuple[RelationRoleReceipt, GenericPredicateCompilation]:
    role_receipt = extractor.extract(stem)
    compilation = compile_generic_predicate_goal(
        stem,
        choices,
        role_receipt=role_receipt,
        context=context,
    )
    return role_receipt, compilation


def _replace_fact(
    fact: GenericPredicateFact,
    **changes: object,
) -> GenericPredicateFact:
    payload = fact.to_dict()
    payload.pop("fact_digest_sha256")
    payload.update(changes)
    return replace(
        fact,
        **changes,
        fact_digest_sha256=canonical_digest(payload),
    )


def _replace_context(
    context: GenericPredicateContext,
    *,
    facts: tuple[GenericPredicateFact, ...],
    stage_bindings: tuple[BoundPredicateStage, ...] | None = None,
) -> GenericPredicateContext:
    bindings = (
        context.stage_bindings
        if stage_bindings is None
        else stage_bindings
    )
    payload = context.to_dict()
    payload.pop("context_digest_sha256")
    payload["facts"] = [fact.to_dict() for fact in facts]
    payload["stage_bindings"] = [
        binding.to_dict() for binding in bindings
    ]
    return replace(
        context,
        facts=facts,
        stage_bindings=bindings,
        context_digest_sha256=canonical_digest(payload),
    )


def test_off_on_exact_proof_is_immutable_and_read_only(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, root = _context(
        tmp_path,
        (("Zephyr", "catalyst_signature", "amber"),),
        "Zephyr",
        role="entity",
    )
    before = _tree_snapshot(root)
    stem = "What catalyst_signature is Zephyr?"
    role_receipt, compilation = _compile(
        extractor,
        stem,
        (("A", "amber"), ("B", "violet")),
        context,
    )

    off = consume_generic_predicate_compilation(
        stem,
        compilation,
        role_receipt=role_receipt,
        context=context,
        enabled=False,
    )
    on = consume_generic_predicate_compilation(
        stem,
        compilation,
        role_receipt=role_receipt,
        context=context,
        enabled=True,
    )

    assert _tree_snapshot(root) == before
    assert off.status == "abstain"
    assert off.reason == "proof_membrane_disabled"
    assert off.engine_fired is False
    assert off.receipt is None
    assert on.status == "proved"
    assert on.reason == "exactly_one_provable_choice"
    assert on.engine_fired is True
    assert on.choice_key == "A"
    assert type(on.receipt) is GenericPredicateProofReceipt
    receipt = on.receipt
    assert receipt.predicate_name == "catalyst_signature"
    assert receipt.predicate_canonical_id == "stage:catalyst_signature"
    assert receipt.predicate_wikidata_property_id is None
    assert receipt.fact_object_value == "amber"
    assert receipt.choice_normalized_value == "amber"
    assert receipt.stage_role == "entity"
    assert receipt.source_binding_kind == "none"
    assert receipt.source_subject_entity_id is None
    assert receipt.source_property_id is None
    assert receipt.source_qid_pid_sidecar_digest_sha256 is None
    assert verify_generic_predicate_proof_receipt(
        receipt,
        stem,
        compilation,
        role_receipt=role_receipt,
        context=context,
    )
    assert not any(off.claims.values())
    assert not any(on.claims.values())
    assert not any(receipt.claims.values())
    serialized = receipt.to_dict()
    proof_digest = serialized.pop("proof_digest_sha256")
    assert proof_digest == canonical_digest(serialized)
    with pytest.raises(FrozenInstanceError):
        receipt.choice_key = "B"  # type: ignore[misc]


def test_zero_fact_choice_pairs_abstain_without_guessing(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, _root = _context(
        tmp_path,
        (("Zephyr", "catalyst_signature", "amber"),),
        "Zephyr",
    )
    stem = "What catalyst_signature is Zephyr?"
    role_receipt, compilation = _compile(
        extractor,
        stem,
        (("A", "blue"), ("B", "violet")),
        context,
    )

    decision = consume_generic_predicate_compilation(
        stem,
        compilation,
        role_receipt=role_receipt,
        context=context,
        enabled=True,
    )

    assert decision.status == "abstain"
    assert decision.reason == "no_provable_choice"
    assert decision.choice_key is None
    assert decision.receipt is None


def test_two_fact_choice_pairs_abstain_but_one_of_many_facts_proves(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, _root = _context(
        tmp_path,
        (
            ("Dune", "genre", "science fiction"),
            ("Dune", "genre", "adventure"),
        ),
        "Dune",
    )
    stem = "What genre is Dune?"
    role_receipt, ambiguous = _compile(
        extractor,
        stem,
        (("A", "science fiction"), ("B", "adventure")),
        context,
    )
    _same_role, unique = _compile(
        extractor,
        stem,
        (("A", "science fiction"), ("B", "romance")),
        context,
    )

    rejected = consume_generic_predicate_compilation(
        stem,
        ambiguous,
        role_receipt=role_receipt,
        context=context,
        enabled=True,
    )
    proved = consume_generic_predicate_compilation(
        stem,
        unique,
        role_receipt=role_receipt,
        context=context,
        enabled=True,
    )

    assert rejected.status == "abstain"
    assert rejected.reason == "proof_cardinality_not_one"
    assert rejected.receipt is None
    assert proved.status == "proved"
    assert proved.choice_key == "A"
    assert proved.receipt is not None
    assert proved.receipt.selected_fact_count == 2


@pytest.mark.parametrize(
    ("rows", "choices", "status", "reason", "choice_key"),
    (
        (
            (("sample", "symbol", "Co"),),
            (("A", "CO"), ("B", "Cu")),
            "abstain",
            "no_provable_choice",
            None,
        ),
        (
            (
                ("sample", "symbol", "Co"),
                ("sample", "symbol", "CO"),
            ),
            (("A", "Co"), ("B", "Cu")),
            "proved",
            "exactly_one_provable_choice",
            "A",
        ),
    ),
)
def test_fact_choice_matching_preserves_case_as_exact_evidence(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
    rows: tuple[tuple[str, str, str], ...],
    choices: tuple[tuple[str, str], ...],
    status: str,
    reason: str,
    choice_key: str | None,
) -> None:
    context, _root = _context(tmp_path, rows, "sample")
    stem = "What symbol is sample?"
    role_receipt, compilation = _compile(
        extractor,
        stem,
        choices,
        context,
    )

    decision = consume_generic_predicate_compilation(
        stem,
        compilation,
        role_receipt=role_receipt,
        context=context,
        enabled=True,
    )

    assert decision.status == status
    assert decision.reason == reason
    assert decision.choice_key == choice_key
    if decision.receipt is not None:
        assert decision.receipt.fact_object_value == "Co"


def test_s1_qid_pid_is_separate_source_evidence(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, _root = _context(
        tmp_path,
        (("hydrogen", "atomic_number", "1"),),
        "hydrogen",
        role="literal",
    )
    stem = "What is hydrogen's atomic number?"
    role_receipt, compilation = _compile(
        extractor,
        stem,
        (("A", "1"), ("B", "2")),
        context,
    )

    decision = consume_generic_predicate_compilation(
        stem,
        compilation,
        role_receipt=role_receipt,
        context=context,
        enabled=True,
    )

    assert decision.status == "proved"
    assert decision.receipt is not None
    receipt = decision.receipt
    assert receipt.predicate_name == "atomic_number"
    assert receipt.predicate_canonical_id == "stage:atomic_number"
    assert receipt.predicate_wikidata_property_id is None
    assert receipt.stage_role == "literal"
    assert receipt.linkage_evidence_tokens == ("atomic", "number")
    assert receipt.linkage_match_start == 0
    assert receipt.linkage_match_end == 2
    assert receipt.source_binding_kind == "qid_pid_sidecar"
    assert receipt.source_subject_entity_id == "Q556"
    assert receipt.source_property_id == "P1086"
    assert (
        receipt.source_qid_pid_sidecar_digest_sha256
        == receipt.stage_qid_pid_sidecar_digest_sha256
    )
    assert verify_generic_predicate_proof_receipt(
        receipt,
        stem,
        compilation,
        role_receipt=role_receipt,
        context=context,
    )
    with pytest.raises(ValueError):
        replace(
            receipt,
            predicate_wikidata_property_id="P1086",  # type: ignore[arg-type]
        )


def test_literal_stage_without_s1_source_binding_is_rejected(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, _root = _context(
        tmp_path,
        (("hydrogen", "atomic_number", "1"),),
        "hydrogen",
    )
    literal_binding = replace(
        context.stage_bindings[0],
        role="literal",
    )
    literal_fact = _replace_fact(
        context.facts[0],
        stage_role="literal",
        object_kind="literal",
    )
    forged_context = _replace_context(
        context,
        facts=(literal_fact,),
        stage_bindings=(literal_binding,),
    )
    forged_context.assert_validated()
    stem = "What atomic_number is hydrogen?"
    role_receipt, compilation = _compile(
        extractor,
        stem,
        (("A", "1"), ("B", "2")),
        forged_context,
    )
    assert compilation.compiled

    with pytest.raises(GenericPredicateStagingError):
        consume_generic_predicate_compilation(
            stem,
            compilation,
            role_receipt=role_receipt,
            context=forged_context,
            enabled=True,
        )


def test_literal_fact_object_kind_must_replay_stage_role(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, _root = _context(
        tmp_path,
        (("hydrogen", "atomic_number", "1"),),
        "hydrogen",
        role="literal",
    )
    poisoned_fact = _replace_fact(
        context.facts[0],
        object_kind="entity",
    )
    poisoned_context = _replace_context(
        context,
        facts=(poisoned_fact,),
    )
    poisoned_context.assert_validated()
    stem = "What atomic_number is hydrogen?"
    role_receipt, compilation = _compile(
        extractor,
        stem,
        (("A", "1"), ("B", "2")),
        poisoned_context,
    )
    assert compilation.compiled

    with pytest.raises(GenericPredicateStagingError):
        consume_generic_predicate_compilation(
            stem,
            compilation,
            role_receipt=role_receipt,
            context=poisoned_context,
            enabled=True,
        )


def test_every_fact_row_replays_bound_stage_range(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, _root = _context(
        tmp_path,
        (
            ("Dune", "genre", "science fiction"),
            ("Dune", "genre", "adventure"),
        ),
        "Dune",
    )
    poisoned_facts = tuple(
        _replace_fact(fact, row_index=999_999)
        if fact.object_value == "adventure"
        else fact
        for fact in context.facts
    )
    poisoned_context = _replace_context(
        context,
        facts=poisoned_facts,
    )
    poisoned_context.assert_validated()
    stem = "What genre is Dune?"
    role_receipt, compilation = _compile(
        extractor,
        stem,
        (("A", "science fiction"), ("B", "fantasy")),
        poisoned_context,
    )
    assert compilation.compiled

    with pytest.raises(GenericPredicateStagingError):
        consume_generic_predicate_compilation(
            stem,
            compilation,
            role_receipt=role_receipt,
            context=poisoned_context,
            enabled=True,
        )


def test_noncompiled_and_wrong_types_fail_closed(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, _root = _context(
        tmp_path,
        (("Athens", "home_nation", "Greece"),),
        "Athens",
    )
    stem = "Which country is Athens in?"
    role_receipt, compilation = _compile(
        extractor,
        stem,
        (("A", "Greece"), ("B", "Italy")),
        context,
    )
    assert compilation.compiled is False

    decision = consume_generic_predicate_compilation(
        stem,
        compilation,
        role_receipt=role_receipt,
        context=context,
        enabled=True,
    )

    assert decision.reason == "compilation_not_compiled"
    assert decision.engine_fired is False
    with pytest.raises(TypeError):
        consume_generic_predicate_compilation(
            stem,
            compilation,
            role_receipt=role_receipt,
            context=context,
            enabled=1,
        )
    with pytest.raises(TypeError):
        consume_generic_predicate_compilation(
            stem,
            object(),
            role_receipt=role_receipt,
            context=context,
            enabled=True,
        )


def test_receipt_mutation_and_input_mutation_are_rejected(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, _root = _context(
        tmp_path,
        (("water", "chemical_formula", "H2O"),),
        "water",
    )
    stem = "What is the chemical formula of water?"
    role_receipt, compilation = _compile(
        extractor,
        stem,
        (("A", "H2O"), ("B", "CO2")),
        context,
    )
    decision = consume_generic_predicate_compilation(
        stem,
        compilation,
        role_receipt=role_receipt,
        context=context,
        enabled=True,
    )
    receipt = decision.receipt
    assert receipt is not None

    object.__setattr__(receipt, "choice_key", "B")
    object.__setattr__(
        receipt,
        "proof_digest_sha256",
        canonical_digest(receipt.proof_body()),
    )
    receipt.__post_init__()
    assert not verify_generic_predicate_proof_receipt(
        receipt,
        stem,
        compilation,
        role_receipt=role_receipt,
        context=context,
    )

    object.__setattr__(
        compilation.goal,
        "fact_bundle_digest_sha256",
        "0" * 64,
    )
    with pytest.raises(GenericPredicateStagingError):
        consume_generic_predicate_compilation(
            stem,
            compilation,
            role_receipt=role_receipt,
            context=context,
            enabled=True,
        )


@pytest.mark.parametrize(
    "target",
    ("role", "context", "linkage"),
)
def test_every_replay_layer_rejects_mutation(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
    target: str,
) -> None:
    context, _root = _context(
        tmp_path,
        (("Dune", "genre", "science fiction"),),
        "Dune",
    )
    stem = "What genre is Dune?"
    role_receipt, compilation = _compile(
        extractor,
        stem,
        (("A", "science fiction"), ("B", "fantasy")),
        context,
    )
    if target == "role":
        object.__setattr__(
            role_receipt,
            "receipt_digest_sha256",
            "0" * 64,
        )
    elif target == "context":
        object.__setattr__(
            context,
            "context_digest_sha256",
            "0" * 64,
        )
    else:
        object.__setattr__(
            compilation.goal.linkage,
            "match_start",
            1,
        )

    with pytest.raises(GenericPredicateStagingError):
        consume_generic_predicate_compilation(
            stem,
            compilation,
            role_receipt=role_receipt,
            context=context,
            enabled=True,
        )


def test_forged_substring_linkage_fails_full_compiler_replay(
    tmp_path: Path,
    extractor: SpacyRelationRoleExtractor,
) -> None:
    context, _root = _context(
        tmp_path,
        (("Dune", "genre", "science fiction"),),
        "Dune",
    )
    choices = (("A", "science fiction"), ("B", "fantasy"))
    valid_stem = "What genre is Dune?"
    valid_role, valid = _compile(
        extractor,
        valid_stem,
        choices,
        context,
    )
    assert valid.compiled
    assert valid.goal is not None

    substring_stem = "What literary genre is Dune?"
    substring_role, refused = _compile(
        extractor,
        substring_stem,
        choices,
        context,
    )
    assert refused.reason == "predicate_surface_not_grounded"
    forged_goal = replace(
        valid.goal,
        linkage=PredicateTokenLinkage(
            source="relation_raw",
            predicate_tokens=("genre",),
            evidence_tokens=("literary", "genre"),
            match_start=1,
            match_end=2,
        ),
        role_receipt_digest_sha256=(
            substring_role.receipt_digest_sha256
        ),
    )
    forged = replace(
        valid,
        input_digest_sha256=refused.input_digest_sha256,
        role_receipt_digest_sha256=(
            substring_role.receipt_digest_sha256
        ),
        goal=forged_goal,
    )
    forged.__post_init__()

    with pytest.raises(GenericPredicateStagingError):
        consume_generic_predicate_compilation(
            substring_stem,
            forged,
            role_receipt=substring_role,
            context=context,
            enabled=True,
        )
    assert not verify_generic_predicate_proof_receipt(
        object(),
        valid_stem,
        valid,
        role_receipt=valid_role,
        context=context,
    )


def test_public_consumer_has_no_gold_or_rank_parameter() -> None:
    signature = inspect.signature(consume_generic_predicate_compilation)

    assert tuple(signature.parameters) == (
        "stem",
        "compilation",
        "role_receipt",
        "context",
        "enabled",
    )
