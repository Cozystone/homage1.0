from __future__ import annotations

import ast
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable

import pytest

from packages.eval_evidence.receipt import canonical_json_bytes
from packages.reasoning_vm.deliberator.relational_object_compiler import (
    compile_explicit_relational_object_mcq,
)
from packages.reasoning_vm.deliberator.science_goal import (
    compile_science_question,
)
from packages.reasoning_vm.deliberator.science_quantity_goal import (
    compile_neutralization_question,
)
from packages.reasoning_vm.science_route import classify_science_stem


REPO = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    REPO
    / "scripts/tests/fixtures/"
    "science_mmlu_pro_typed_family_contract_v1.json"
)
DATASET_PATH = REPO / "data/benchmarks/mmlu_pro/slice_5.jsonl"

SCHEMA_VERSION = "atanor.science-mmlu-pro-typed-family-contract.v1"
EXPECTED_DATASET_PATH = "data/benchmarks/mmlu_pro/slice_5.jsonl"
EXPECTED_DATASET_SHA256 = (
    "a1325092eabfb8dc394ef37f64fe63d79c002678b9d9d3b580605d41690e8b36"
)
EXPECTED_DATASET_BYTES = 31014
EXPECTED_ITEM_COUNT = 40
EXPECTED_ORDERED_ITEM_DIGESTS_SHA256 = (
    "ee61ae23f76dbe21632107f45da2c5852e92c65e1d2909c9a873e2509de6dda1"
)
EXPECTED_CONTRACT_SHA256 = (
    "ec98f4da3150ed0ae315e72dece96b660102608f2ff1886d369cce678278a900"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CATEGORIES = frozenset(
    {
        "biology",
        "chemistry",
        "physics",
        "history",
        "economics",
        "psychology",
        "health",
        "law",
    }
)
_TYPED_FAMILIES = frozenset(
    {
        "finite_predicate_extension",
        "scalar_quantity_resolve",
        "typed_relation_select",
        "unsupported",
    }
)
_GROUNDABILITY = frozenset(
    {"blocked", "groundable", "not_assessed", "uncertain"}
)


class ContractError(ValueError):
    """The evaluator-only taxonomy contract is malformed or not bound."""


def _fail(message: str) -> None:
    raise ContractError(message)


def _require_exact_keys(
    value: Any,
    expected: set[str],
    *,
    label: str,
) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        _fail(
            f"{label} keys differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    return value


def _require_nonempty_string(value: Any, *, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail(f"{label} must be a trimmed non-empty string")
    return value


def _require_sha256(value: Any, *, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _fail(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_exact_bool(value: Any, expected: bool, *, label: str) -> None:
    if type(value) is not bool or value is not expected:
        _fail(f"{label} must be {expected!r}")


def _require_exact_count_map(
    value: Any,
    expected: dict[str, int],
    *,
    label: str,
) -> dict[str, int]:
    counts = _require_exact_keys(value, set(expected), label=label)
    for key, expected_count in expected.items():
        actual = counts[key]
        if type(actual) is not int or actual != expected_count:
            _fail(f"{label}.{key} must be exact integer {expected_count}")
    return counts


def _load_dataset() -> tuple[bytes, list[dict[str, Any]]]:
    payload = DATASET_PATH.read_bytes()
    try:
        lines = payload.decode("utf-8").splitlines()
        rows = [json.loads(line) for line in lines]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssertionError("the bound dataset is not UTF-8 JSONL") from exc
    assert all(type(row) is dict for row in rows)
    return payload, rows


def _replay_current_executable_snapshot(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    route_counts: Counter[str] = Counter()
    compiler_counts: Counter[str] = Counter()
    relation_reason_counts: Counter[str] = Counter()

    for row in rows:
        question = row["question"]
        choices = row["choices"]

        route = classify_science_stem(question)
        if route.status == "selected":
            assert route.lane is not None
            route_counts[
                {
                    "atomic": "atomic_number_lookup",
                    "scalar": "scalar_quantity_resolve",
                }[route.lane]
            ] += 1
        else:
            route_counts[route.status] += 1

        if compile_science_question(question, choices).compiled:
            compiler_counts["atomic_number_lookup"] += 1
        if compile_neutralization_question(question, choices).compiled:
            compiler_counts["scalar_quantity_resolve"] += 1

        relation = compile_explicit_relational_object_mcq(
            question,
            choices,
        )
        if relation.compiled:
            compiler_counts["explicit_located_in_object_choice"] += 1
        else:
            relation_reason_counts[relation.reason] += 1

    for key in (
        "atomic_number_lookup",
        "scalar_quantity_resolve",
        "explicit_located_in_object_choice",
    ):
        compiler_counts[key] += 0
    return {
        "route_counts": dict(route_counts),
        "compiler_counts": dict(compiler_counts),
        "relation_probe_reason_counts": dict(relation_reason_counts),
    }


def _validate_scope(
    scope_value: Any,
    *,
    dataset_payload: bytes,
    dataset_rows: list[dict[str, Any]],
) -> None:
    scope = _require_exact_keys(
        scope_value,
        {
            "dataset_path",
            "dataset_sha256",
            "dataset_bytes",
            "item_count",
            "order_contract",
            "item_digest_contract",
            "ordered_item_digests_sha256",
        },
        label="scope",
    )
    if scope["dataset_path"] != EXPECTED_DATASET_PATH:
        _fail("scope.dataset_path does not bind the exposed slice")
    if scope["dataset_sha256"] != EXPECTED_DATASET_SHA256:
        _fail("scope.dataset_sha256 differs from the frozen digest")
    if type(scope["dataset_bytes"]) is not int or (
        scope["dataset_bytes"] != EXPECTED_DATASET_BYTES
    ):
        _fail("scope.dataset_bytes differs from the frozen byte count")
    if type(scope["item_count"]) is not int or (
        scope["item_count"] != EXPECTED_ITEM_COUNT
    ):
        _fail("scope.item_count differs from the frozen item count")
    if (
        scope["order_contract"]
        != "physical_jsonl_order_zero_based_ordinal"
    ):
        _fail("scope.order_contract is not the declared physical order")
    if (
        scope["item_digest_contract"]
        != "sha256_of_canonical_json_full_source_row"
    ):
        _fail("scope.item_digest_contract is unsupported")
    if (
        scope["ordered_item_digests_sha256"]
        != EXPECTED_ORDERED_ITEM_DIGESTS_SHA256
    ):
        _fail("scope.ordered_item_digests_sha256 differs from the freeze")

    if hashlib.sha256(dataset_payload).hexdigest() != scope["dataset_sha256"]:
        _fail("dataset bytes do not match scope.dataset_sha256")
    if len(dataset_payload) != scope["dataset_bytes"]:
        _fail("dataset byte length does not match scope.dataset_bytes")
    if len(dataset_rows) != scope["item_count"]:
        _fail("dataset row count does not match scope.item_count")


def _validate_separation(value: Any) -> None:
    separation = _require_exact_keys(
        value,
        {
            "owner",
            "candidate_access_allowed",
            "stage_access_allowed",
            "inventory_contains_question_text",
            "inventory_contains_choice_text",
            "inventory_contains_answer_labels",
            "public_slice_exposed",
            "classification_is_hidden_holdout",
            "capability_claim",
            "benchmark_improvement_claim",
            "independent_evaluation_claim",
            "promotion_gate_claim",
        },
        label="separation",
    )
    if separation["owner"] != "evaluator":
        _fail("separation.owner must be evaluator")
    for key in (
        "candidate_access_allowed",
        "stage_access_allowed",
        "inventory_contains_question_text",
        "inventory_contains_choice_text",
        "inventory_contains_answer_labels",
        "classification_is_hidden_holdout",
        "capability_claim",
        "benchmark_improvement_claim",
        "independent_evaluation_claim",
        "promotion_gate_claim",
    ):
        _require_exact_bool(separation[key], False, label=f"separation.{key}")
    _require_exact_bool(
        separation["public_slice_exposed"],
        True,
        label="separation.public_slice_exposed",
    )


def _validate_documented_estimate(value: Any) -> None:
    estimate = _require_exact_keys(
        value,
        {
            "classification_kind",
            "source_document",
            "item_membership",
            "family_reach_counts",
            "non_overlapping_total",
            "source_groundable_total",
            "accuracy_forecast",
        },
        label="documented_reach_estimate",
    )
    if (
        estimate["classification_kind"]
        != "non_executable_documented_aggregate_estimate"
    ):
        _fail("documented estimate must remain explicitly non-executable")
    if (
        estimate["source_document"]
        != "docs/ATANOR_A_TRACK_EVIDENCE_2026-07-25.md"
    ):
        _fail("documented estimate source differs")
    if estimate["item_membership"] != "unmapped":
        _fail("aggregate estimate must not invent per-item membership")
    _require_exact_count_map(
        estimate["family_reach_counts"],
        {
            "scalar_quantity_resolve": 4,
            "typed_relation_select": 12,
            "finite_predicate_extension": 4,
        },
        label="documented_reach_estimate.family_reach_counts",
    )
    if (
        type(estimate["non_overlapping_total"]) is not int
        or estimate["non_overlapping_total"] != 20
        or type(estimate["source_groundable_total"]) is not int
        or estimate["source_groundable_total"] != 19
    ):
        _fail("documented aggregate totals differ")
    _require_exact_bool(
        estimate["accuracy_forecast"],
        False,
        label="documented_reach_estimate.accuracy_forecast",
    )


def _validate_current_snapshot(value: Any) -> None:
    snapshot = _require_exact_keys(
        value,
        {
            "classification_kind",
            "router_schema_version",
            "router_profile_order",
            "route_counts",
            "compiler_counts",
            "relation_probe_reason_counts",
            "finite_predicate_extension_implemented",
        },
        label="current_executable_snapshot",
    )
    if snapshot["classification_kind"] != "executable_current_at_precommit":
        _fail("current executable classification kind differs")
    if (
        snapshot["router_schema_version"]
        != "atanor.reasoning_vm.science_route.v1"
    ):
        _fail("current router schema differs")
    if snapshot["router_profile_order"] != ["atomic", "scalar"]:
        _fail("current router profile order differs")
    _require_exact_count_map(
        snapshot["route_counts"],
        {
            "scalar_quantity_resolve": 1,
            "unsupported": 39,
        },
        label="current_executable_snapshot.route_counts",
    )
    _require_exact_count_map(
        snapshot["compiler_counts"],
        {
            "atomic_number_lookup": 0,
            "scalar_quantity_resolve": 1,
            "explicit_located_in_object_choice": 0,
        },
        label="current_executable_snapshot.compiler_counts",
    )
    _require_exact_count_map(
        snapshot["relation_probe_reason_counts"],
        {
            "ambiguous_or_unsupported_semantics": 10,
            "stem_out_of_bounds": 6,
            "unsupported_surface_family": 24,
        },
        label="current_executable_snapshot.relation_probe_reason_counts",
    )
    _require_exact_bool(
        snapshot["finite_predicate_extension_implemented"],
        False,
        label=(
            "current_executable_snapshot."
            "finite_predicate_extension_implemented"
        ),
    )


def _validate_inventory(
    inventory_value: Any,
    *,
    dataset_rows: list[dict[str, Any]],
) -> tuple[Counter[str], Counter[str], Counter[str]]:
    if type(inventory_value) is not list or (
        len(inventory_value) != EXPECTED_ITEM_COUNT
    ):
        _fail("inventory must contain exactly 40 ordered items")

    family_counts: Counter[str] = Counter()
    groundability_counts: Counter[str] = Counter()
    executable_counts: Counter[str] = Counter()
    digests: list[str] = []
    seen_digests: set[str] = set()

    for expected_ordinal, (item_value, source_row) in enumerate(
        zip(inventory_value, dataset_rows, strict=True)
    ):
        label = f"inventory[{expected_ordinal}]"
        item = _require_exact_keys(
            item_value,
            {
                "ordinal",
                "category",
                "canonical_item_digest_sha256",
                "typed_family",
                "typed_goal_signature",
                "rationale",
                "source_groundability",
                "current_executable_classification",
                "documented_estimate_membership",
            },
            label=label,
        )
        if type(item["ordinal"]) is not int or (
            item["ordinal"] != expected_ordinal
        ):
            _fail(f"{label}.ordinal breaks physical dataset order")
        if type(item["category"]) is not str or (
            item["category"] not in _CATEGORIES
            or item["category"] != source_row.get("category")
        ):
            _fail(f"{label}.category differs from the source row")

        item_digest = _require_sha256(
            item["canonical_item_digest_sha256"],
            label=f"{label}.canonical_item_digest_sha256",
        )
        expected_digest = hashlib.sha256(
            canonical_json_bytes(source_row)
        ).hexdigest()
        if item_digest != expected_digest:
            _fail(f"{label} does not bind the full canonical source row")
        if item_digest in seen_digests:
            _fail("inventory canonical item digests must be unique")
        seen_digests.add(item_digest)
        digests.append(item_digest)

        family = item["typed_family"]
        if type(family) is not str or family not in _TYPED_FAMILIES:
            _fail(f"{label}.typed_family is invalid")
        signature = _require_nonempty_string(
            item["typed_goal_signature"],
            label=f"{label}.typed_goal_signature",
        )
        rationale = _require_nonempty_string(
            item["rationale"],
            label=f"{label}.rationale",
        )
        if len(signature) > 180 or len(rationale) > 400:
            _fail(f"{label} taxonomy text exceeds its bound")
        if family == "unsupported" and not signature.startswith(
            "unsupported:"
        ):
            _fail(f"{label} unsupported signature is not fail-closed")
        if family == "typed_relation_select" and not signature.startswith(
            "select_choice_object("
        ):
            _fail(f"{label} relation signature is not normalized")
        if family == "scalar_quantity_resolve" and not signature.startswith(
            ("derive_quantity(", "lookup_quantity(", "lookup_quantity_pair(")
        ):
            _fail(f"{label} scalar signature is not normalized")
        if family == "finite_predicate_extension" and not signature.startswith(
            ("finite_existential(", "finite_predicate(", "finite_subset(", "finite_universal(")
        ):
            _fail(f"{label} finite signature is not normalized")

        groundability = _require_exact_keys(
            item["source_groundability"],
            {"status", "rationale"},
            label=f"{label}.source_groundability",
        )
        ground_status = groundability["status"]
        if (
            type(ground_status) is not str
            or ground_status not in _GROUNDABILITY
        ):
            _fail(f"{label}.source_groundability.status is invalid")
        _require_nonempty_string(
            groundability["rationale"],
            label=f"{label}.source_groundability.rationale",
        )
        if family == "unsupported" and ground_status not in {
            "blocked",
            "not_assessed",
        }:
            _fail(f"{label} unsupported item has admitted groundability")
        if family != "unsupported" and ground_status not in {
            "groundable",
            "uncertain",
        }:
            _fail(f"{label} admitted family lacks a sourcing disposition")

        current = _require_exact_keys(
            item["current_executable_classification"],
            {"status", "typed_family", "reason"},
            label=f"{label}.current_executable_classification",
        )
        if current["status"] == "unsupported":
            if (
                current["typed_family"] is not None
                or current["reason"] != "unsupported_science_profile"
            ):
                _fail(f"{label} unsupported executable result is inconsistent")
            executable_counts["unsupported"] += 1
        elif current["status"] == "selected_and_compiled":
            if (
                current["typed_family"] != "scalar_quantity_resolve"
                or current["reason"]
                != "typed_neutralization_volume_goal_emitted"
                or expected_ordinal != 7
            ):
                _fail(f"{label} compiled executable result is inconsistent")
            executable_counts["scalar_quantity_resolve"] += 1
        else:
            _fail(f"{label} executable status is invalid")

        if item["documented_estimate_membership"] != "unmapped":
            _fail(f"{label} invents documented estimate membership")
        family_counts[family] += 1
        groundability_counts[ground_status] += 1

    if hashlib.sha256(canonical_json_bytes(digests)).hexdigest() != (
        EXPECTED_ORDERED_ITEM_DIGESTS_SHA256
    ):
        _fail("ordered inventory digest differs from the frozen order")
    return family_counts, groundability_counts, executable_counts


def _validate_summary(
    summary_value: Any,
    *,
    family_counts: Counter[str],
    groundability_counts: Counter[str],
) -> None:
    summary = _require_exact_keys(
        summary_value,
        {
            "classification_kind",
            "typed_family_counts",
            "source_groundability_counts",
        },
        label="taxonomy_summary",
    )
    if (
        summary["classification_kind"]
        != "evaluator_authored_conservative_structural_taxonomy"
    ):
        _fail("taxonomy summary classification kind differs")
    expected_families = {
        "finite_predicate_extension": 4,
        "scalar_quantity_resolve": 4,
        "typed_relation_select": 10,
        "unsupported": 22,
    }
    expected_groundability = {
        "blocked": 2,
        "groundable": 15,
        "not_assessed": 20,
        "uncertain": 3,
    }
    _require_exact_count_map(
        summary["typed_family_counts"],
        expected_families,
        label="taxonomy_summary.typed_family_counts",
    )
    if dict(family_counts) != expected_families:
        _fail("inventory family counts do not match taxonomy summary")
    _require_exact_count_map(
        summary["source_groundability_counts"],
        expected_groundability,
        label="taxonomy_summary.source_groundability_counts",
    )
    if dict(groundability_counts) != expected_groundability:
        _fail("inventory groundability counts do not match summary")


def _validate_contract(
    value: Any,
    *,
    dataset_payload: bytes,
    dataset_rows: list[dict[str, Any]],
) -> None:
    contract = _require_exact_keys(
        value,
        {
            "schema_version",
            "evidence_kind",
            "scope",
            "separation",
            "documented_reach_estimate",
            "current_executable_snapshot",
            "taxonomy_summary",
            "inventory",
        },
        label="contract",
    )
    if contract["schema_version"] != SCHEMA_VERSION:
        _fail("contract schema version differs")
    if (
        contract["evidence_kind"]
        != "evaluator_only_exposed_development_taxonomy_precommit"
    ):
        _fail("contract evidence kind differs")

    _validate_scope(
        contract["scope"],
        dataset_payload=dataset_payload,
        dataset_rows=dataset_rows,
    )
    _validate_separation(contract["separation"])
    _validate_documented_estimate(contract["documented_reach_estimate"])
    _validate_current_snapshot(contract["current_executable_snapshot"])
    family_counts, groundability_counts, executable_counts = (
        _validate_inventory(
            contract["inventory"],
            dataset_rows=dataset_rows,
        )
    )
    if executable_counts != Counter(
        {"unsupported": 39, "scalar_quantity_resolve": 1}
    ):
        _fail("per-item executable counts differ from the frozen snapshot")
    _validate_summary(
        contract["taxonomy_summary"],
        family_counts=family_counts,
        groundability_counts=groundability_counts,
    )


def _load_contract(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    payload = path.read_bytes()
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("contract is not one UTF-8 JSON value") from exc
    if payload != canonical_json_bytes(value) + b"\n":
        _fail("contract must be canonical JSON with one trailing newline")
    dataset_payload, dataset_rows = _load_dataset()
    _validate_contract(
        value,
        dataset_payload=dataset_payload,
        dataset_rows=dataset_rows,
    )
    return value


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return _load_contract()


def test_contract_is_exact_canonical_and_digest_frozen(
    contract: dict[str, Any],
) -> None:
    payload = FIXTURE_PATH.read_bytes()
    assert payload == canonical_json_bytes(contract) + b"\n"
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_CONTRACT_SHA256


def test_contract_binds_exact_exposed_slice_order_and_full_rows(
    contract: dict[str, Any],
) -> None:
    payload, rows = _load_dataset()
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_DATASET_SHA256
    assert len(payload) == EXPECTED_DATASET_BYTES
    assert len(rows) == EXPECTED_ITEM_COUNT
    assert [row["ordinal"] for row in contract["inventory"]] == list(
        range(EXPECTED_ITEM_COUNT)
    )
    expected_digests = [
        hashlib.sha256(canonical_json_bytes(row)).hexdigest() for row in rows
    ]
    assert [
        row["canonical_item_digest_sha256"]
        for row in contract["inventory"]
    ] == expected_digests
    assert len(set(expected_digests)) == EXPECTED_ITEM_COUNT


def test_estimate_taxonomy_and_current_execution_are_not_conflated(
    contract: dict[str, Any],
) -> None:
    estimate = contract["documented_reach_estimate"]
    taxonomy = contract["taxonomy_summary"]
    current = contract["current_executable_snapshot"]

    assert estimate["classification_kind"].startswith("non_executable_")
    assert estimate["item_membership"] == "unmapped"
    assert estimate["family_reach_counts"]["typed_relation_select"] == 12
    assert taxonomy["typed_family_counts"]["typed_relation_select"] == 10
    assert current["compiler_counts"][
        "explicit_located_in_object_choice"
    ] == 0
    assert current["route_counts"] == {
        "scalar_quantity_resolve": 1,
        "unsupported": 39,
    }
    assert all(
        row["documented_estimate_membership"] == "unmapped"
        for row in contract["inventory"]
    )


def test_current_executable_snapshot_replays_live_production_code(
    contract: dict[str, Any],
) -> None:
    _payload, rows = _load_dataset()
    replay = _replay_current_executable_snapshot(rows)
    current = contract["current_executable_snapshot"]

    assert replay["route_counts"] == current["route_counts"]
    assert replay["compiler_counts"] == current["compiler_counts"]
    assert (
        replay["relation_probe_reason_counts"]
        == current["relation_probe_reason_counts"]
    )


def test_taxonomy_is_conservative_and_contains_no_direct_answer_payload(
    contract: dict[str, Any],
) -> None:
    assert contract["taxonomy_summary"]["typed_family_counts"] == {
        "finite_predicate_extension": 4,
        "scalar_quantity_resolve": 4,
        "typed_relation_select": 10,
        "unsupported": 22,
    }
    assert contract["taxonomy_summary"]["source_groundability_counts"] == {
        "blocked": 2,
        "groundable": 15,
        "not_assessed": 20,
        "uncertain": 3,
    }
    forbidden_item_keys = {
        "answer",
        "answer_label",
        "choice_key",
        "choices",
        "gold",
        "question",
        "stem",
    }
    for item in contract["inventory"]:
        assert not (set(item) & forbidden_item_keys)

    serialized_inventory = canonical_json_bytes(contract["inventory"]).decode(
        "utf-8"
    )
    _payload, rows = _load_dataset()
    assert all(row["question"] not in serialized_inventory for row in rows)
    for row in rows:
        for choice in row["choices"].values():
            if len(choice) >= 24:
                assert choice not in serialized_inventory


def test_disputed_items_remain_fail_closed_and_surface_exact(
    contract: dict[str, Any],
) -> None:
    polio = contract["inventory"][30]
    virus = contract["inventory"][34]

    assert polio["typed_family"] == "unsupported"
    assert polio["source_groundability"]["status"] == "blocked"
    assert polio["typed_goal_signature"] == (
        "unsupported:typed_relation_candidate_without_"
        "answer_bearing_option"
    )
    assert virus["typed_family"] == "typed_relation_select"
    assert virus["source_groundability"]["status"] == "uncertain"
    assert virus["typed_goal_signature"] == (
        "select_choice_object(subject=calcivirus_family,"
        "predicate=replication_class)"
    )
    assert "calicivirus" not in virus["typed_goal_signature"]


def _mutate_extra_top_level(value: dict[str, Any]) -> None:
    value["unexpected"] = True


def _mutate_schema_type(value: dict[str, Any]) -> None:
    value["schema_version"] = 1


def _mutate_dataset_digest(value: dict[str, Any]) -> None:
    value["scope"]["dataset_sha256"] = "0" * 64


def _mutate_item_order(value: dict[str, Any]) -> None:
    value["inventory"][0], value["inventory"][1] = (
        value["inventory"][1],
        value["inventory"][0],
    )


def _mutate_item_digest(value: dict[str, Any]) -> None:
    value["inventory"][0]["canonical_item_digest_sha256"] = "0" * 64


def _mutate_family_without_signature(value: dict[str, Any]) -> None:
    value["inventory"][0]["typed_family"] = "typed_relation_select"


def _mutate_groundability(value: dict[str, Any]) -> None:
    value["inventory"][1]["source_groundability"]["status"] = "maybe"


def _mutate_summary(value: dict[str, Any]) -> None:
    value["taxonomy_summary"]["typed_family_counts"]["unsupported"] = 20


def _mutate_estimate_count_to_bool(value: dict[str, Any]) -> None:
    value["documented_reach_estimate"]["family_reach_counts"][
        "scalar_quantity_resolve"
    ] = True


def _mutate_current_count_to_bool(value: dict[str, Any]) -> None:
    value["current_executable_snapshot"]["compiler_counts"][
        "atomic_number_lookup"
    ] = False


def _mutate_summary_count_to_bool(value: dict[str, Any]) -> None:
    value["taxonomy_summary"]["source_groundability_counts"][
        "blocked"
    ] = True


def _mutate_estimate_membership(value: dict[str, Any]) -> None:
    value["inventory"][0]["documented_estimate_membership"] = "estimated"


_MUTATIONS: tuple[
    tuple[str, Callable[[dict[str, Any]], None]],
    ...,
] = (
    ("extra_top_level", _mutate_extra_top_level),
    ("schema_type", _mutate_schema_type),
    ("dataset_digest", _mutate_dataset_digest),
    ("item_order", _mutate_item_order),
    ("item_digest", _mutate_item_digest),
    ("family_without_signature", _mutate_family_without_signature),
    ("groundability", _mutate_groundability),
    ("summary", _mutate_summary),
    ("estimate_count_bool", _mutate_estimate_count_to_bool),
    ("current_count_bool", _mutate_current_count_to_bool),
    ("summary_count_bool", _mutate_summary_count_to_bool),
    ("estimate_membership", _mutate_estimate_membership),
)


@pytest.mark.parametrize(
    ("_name", "mutate"),
    _MUTATIONS,
    ids=[name for name, _mutate in _MUTATIONS],
)
def test_schema_and_binding_mutations_fail_closed(
    contract: dict[str, Any],
    _name: str,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    mutant = deepcopy(contract)
    mutate(mutant)
    dataset_payload, dataset_rows = _load_dataset()
    with pytest.raises(ContractError):
        _validate_contract(
            mutant,
            dataset_payload=dataset_payload,
            dataset_rows=dataset_rows,
        )


def test_noncanonical_or_nonterminated_contract_is_rejected(
    contract: dict[str, Any],
    tmp_path: Path,
) -> None:
    pretty = tmp_path / "pretty.json"
    pretty.write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ContractError, match="canonical JSON"):
        _load_contract(pretty)

    unterminated = tmp_path / "unterminated.json"
    unterminated.write_bytes(canonical_json_bytes(contract))
    with pytest.raises(ContractError, match="canonical JSON"):
        _load_contract(unterminated)


def test_no_production_package_imports_or_names_evaluator_fixture() -> None:
    fixture_name = FIXTURE_PATH.name
    fixture_repo_path = FIXTURE_PATH.relative_to(REPO).as_posix()
    violations: list[str] = []

    for path in sorted((REPO / "packages").rglob("*.py")):
        source = path.read_text(encoding="utf-8-sig")
        relative = path.relative_to(REPO).as_posix()
        try:
            tree = ast.parse(source, filename=relative)
        except SyntaxError as exc:
            raise AssertionError(f"cannot audit production source {relative}") from exc

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("scripts.tests"):
                    violations.append(f"{relative}:imports:{module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("scripts.tests"):
                        violations.append(
                            f"{relative}:imports:{alias.name}"
                        )
            elif isinstance(node, ast.Constant) and isinstance(
                node.value, str
            ):
                normalized = node.value.replace("\\", "/")
                if (
                    fixture_name in normalized
                    or fixture_repo_path in normalized
                ):
                    violations.append(f"{relative}:names-evaluator-fixture")

    assert violations == []
