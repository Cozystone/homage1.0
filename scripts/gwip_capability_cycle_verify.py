"""Independent verifier for serialized GWIP capability ``InteractiveTrace`` values.

This evaluator-side module intentionally uses only the Python standard
library.  It does not import the candidate package, candidate constructors, or
the candidate's verifier.  Every identity and lineage check below is rebuilt
from JSON, an evaluator-owned request, the parent environment call log, and
the parent authority transcript.

The verifier is specific to the sealed candidate-C trace contract:

* ``atanor.gwip-interactive-trace.v2``;
* canonical M1 cognitive contracts;
* the ``retain_policy_updates``-aware ``_build_cycle_receipt`` layout; and
* typed affine Rule IR carried by candidate-C policy memory.

It is an integrity verifier, not a capability scorer.  A passing result says
that the submitted trace is bound to the supplied parent witnesses; it does
not make a benchmark or production-authority claim.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
import hashlib
import json
import math
from typing import Any


TRACE_SCHEMA = "atanor.gwip-interactive-trace.v2"
COGNITIVE_SCHEMA = "atanor.cognitive_core.m1.v1"
MEMORY_V1_SCHEMA = "atanor.gwip-policy-memory.v1"
MEMORY_V2_SCHEMA = "atanor.gwip-policy-memory.v2"
RULE_IR_SCHEMA = "atanor.gwip-feature-rule.v1"

MAX_RULE_AST_DEPTH = 6
MAX_RULE_PLAN_DEPTH = 64
MAX_RULE_ROWS = 64
MAX_FEATURE_ROWS = 4_096
COEFFICIENT_SEARCH_BOUND = 6
MIN_DISTINCT_RULE_INPUTS = 3

_SURFACES = (
    "trace_schema",
    "request_binding",
    "goal_binding",
    "semantic_digest",
    "semantic_lineage",
    "environment_binding",
    "action_binding",
    "authority_binding",
    "contract_identity",
    "world_lineage",
    "decision_lineage",
    "proposal_lineage",
    "learning_lineage",
    "memory_binding",
    "rule_ir",
    "cycle_receipt",
)

_CONTRACT_PREFIXES = {
    "CognitiveEnvelope": "cenv",
    "GoalIR": "goal",
    "ProofCandidate": "proofc",
    "WorldSnapshot": "world",
    "CognitiveMoment": "moment",
    "DecisionReceipt": "decision",
}

_CONTRACT_FIELDS = {
    "GoalIR": {
        "can_authorize_actions",
        "can_override_safety",
        "constraints",
        "content_hash",
        "contract_id",
        "contract_type",
        "metadata",
        "origin",
        "parent_goal_ids",
        "priority",
        "schema_version",
        "statement",
    },
    "ClaimEnvelope": {
        "accepted_as_observed_fact",
        "confidence",
        "content_hash",
        "contract_id",
        "contract_type",
        "lineage_tiers",
        "metadata",
        "schema_version",
        "source_claim_ids",
        "source_refs",
        "statement",
        "tier",
    },
    "ProofCandidate": {
        "accepted_as_proof",
        "claim_id",
        "confidence",
        "content_hash",
        "contract_id",
        "contract_type",
        "derivation_steps",
        "metadata",
        "method",
        "premise_claim_ids",
        "schema_version",
        "truth_mutation_allowed",
        "verifier_refs",
    },
    "WorldSnapshot": {
        "content_hash",
        "contract_id",
        "contract_type",
        "inferred_claim_ids",
        "metadata",
        "observed_claim_ids",
        "parent_snapshot_id",
        "predicted_claim_ids",
        "read_only",
        "recorded_claim_ids",
        "retrodicted_claim_ids",
        "schema_version",
        "snapshot_index",
        "world_time",
    },
    "CognitiveEnvelope": {
        "autonomy_authority",
        "cognition_only",
        "content_hash",
        "context",
        "contract_id",
        "contract_type",
        "explicit_user_goal_ids",
        "hormone_signals",
        "intrinsic_goal_ids",
        "intrinsic_override_allowed",
        "permission_mutation_allowed",
        "read_only",
        "resource_limits",
        "safety_mutation_allowed",
        "schema_version",
        "session_id",
        "truth_mutation_allowed",
        "world_snapshot_id",
    },
    "CognitiveMoment": {
        "action_authority",
        "active_goal_ids",
        "attention_targets",
        "claim_ids",
        "content_hash",
        "contract_id",
        "contract_type",
        "envelope_id",
        "hormone_signals",
        "metadata",
        "moment_index",
        "permission_mutation_allowed",
        "proof_candidate_ids",
        "resource_state",
        "safety_mutation_allowed",
        "schema_version",
        "selected_goal_id",
        "truth_mutation_allowed",
        "world_snapshot_id",
    },
    "DecisionReceipt": {
        "action_executed",
        "authoritative",
        "content_hash",
        "contract_id",
        "contract_type",
        "decision_kind",
        "input_claim_ids",
        "metadata",
        "mode",
        "moment_id",
        "proof_candidate_ids",
        "proposed_action",
        "rationale",
        "read_only",
        "schema_version",
        "selected_goal_id",
        "shadow",
    },
}

_TRACE_FIELDS = {
    "authority_finish",
    "cycle_receipt",
    "lineage_steps",
    "mechanism_only",
    "production_default_on",
    "schema_version",
    "semantic_trace",
    "semantic_trace_digest",
    "structural_receipt_authenticates_action",
}

_SEMANTIC_FIELDS = {
    "denied_attempt",
    "environment_seed",
    "goal",
    "memory_after",
    "memory_before",
    "policy_seed",
    "reset_result",
    "retain_policy_updates",
    "step_budget",
    "steps",
    "stop_reason",
    "stop_result",
    "success",
}

_SEMANTIC_STEP_FIELDS = {
    "authorization",
    "decision_receipt",
    "learned_edge_ref",
    "learning_proof",
    "post_observation",
    "pre_observation",
    "proposal",
    "proposal_proof",
    "selected_action",
    "step_index",
    "step_result",
    "valid_actions",
    "valid_actions_digest",
    "world_snapshot",
}

_LINEAGE_STEP_FIELDS = _SEMANTIC_STEP_FIELDS | {
    "cognitive_envelope",
    "cognitive_moment",
    "perception",
}


class _Report:
    def __init__(self) -> None:
        self.surface_findings: dict[str, list[str]] = {
            name: [] for name in _SURFACES
        }

    def fail(self, surface: str, message: str) -> None:
        if surface not in self.surface_findings:
            raise AssertionError(f"unknown verification surface: {surface}")
        if message not in self.surface_findings[surface]:
            self.surface_findings[surface].append(message)

    def result(self) -> dict[str, Any]:
        for findings in self.surface_findings.values():
            findings.sort()
        surfaces = {
            name: not findings
            for name, findings in self.surface_findings.items()
        }
        flat = [
            f"{surface}:{message}"
            for surface in _SURFACES
            for message in self.surface_findings[surface]
        ]
        return {
            "passed": all(surfaces.values()),
            "findings": flat,
            "surfaces": surfaces,
            "surface_findings": copy.deepcopy(self.surface_findings),
            "candidate_verifier_imported": False,
            "production_authority_claim": False,
        }


def _plain_json(value: Any) -> Any:
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("canonical JSON cannot contain NaN or infinity")
        return value
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key in sorted(value):
            if type(key) is not str or not key:
                raise ValueError("canonical JSON keys must be non-empty strings")
            output[key] = _plain_json(value[key])
        return output
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    raise TypeError(f"unsupported canonical JSON type: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _plain_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_id(prefix: str, value: Any) -> tuple[str, str]:
    if type(prefix) is not str or not prefix or any(char.isspace() for char in prefix):
        raise ValueError("canonical ID prefix is invalid")
    digest = _canonical_digest(value)
    return f"{prefix}_{digest[:32]}", digest


def _normalized_text(value: Any, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be a string")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"{label} must be non-empty")
    return normalized


def _sorted_ids(value: Any, label: str, *, ordered: bool = False) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be an array")
    items = [_normalized_text(item, label) for item in value]
    if len(items) != len(set(items)):
        raise ValueError(f"{label} contains duplicate IDs")
    return items if ordered else sorted(items)


def _sealed_contract(
    contract_type: str,
    prefix: str,
    fields: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        **_plain_json(fields),
        "contract_type": contract_type,
        "schema_version": COGNITIVE_SCHEMA,
    }
    contract_id, content_hash = _canonical_id(prefix, payload)
    return {
        **payload,
        "contract_id": contract_id,
        "content_hash": content_hash,
    }


def _verify_contract_identity(
    value: Any,
    contract_type: str,
    report: _Report,
    *,
    surface: str = "contract_identity",
) -> bool:
    if type(value) is not dict:
        report.fail(surface, f"{contract_type}:not_an_object")
        return False
    if set(value) != _CONTRACT_FIELDS[contract_type]:
        report.fail(surface, f"{contract_type}:field_set_mismatch")
        return False
    if (
        value.get("contract_type") != contract_type
        or value.get("schema_version") != COGNITIVE_SCHEMA
    ):
        report.fail(surface, f"{contract_type}:type_or_schema_mismatch")
        return False
    payload = {
        key: copy.deepcopy(item)
        for key, item in value.items()
        if key not in {"contract_id", "content_hash"}
    }
    if contract_type == "ClaimEnvelope":
        tier = payload.get("tier")
        if type(tier) is not str or not tier:
            report.fail(surface, "ClaimEnvelope:tier_invalid")
            return False
        prefix = f"claim_{tier}"
    else:
        prefix = _CONTRACT_PREFIXES[contract_type]
    expected_id, expected_hash = _canonical_id(prefix, payload)
    if (
        value.get("contract_id") != expected_id
        or value.get("content_hash") != expected_hash
    ):
        report.fail(surface, f"{contract_type}:canonical_identity_mismatch")
        return False
    return True


def _materialize_request_goal(raw: Any, report: _Report) -> dict[str, Any] | None:
    if type(raw) is not dict:
        report.fail("request_binding", "goal_ir_not_an_object")
        return None
    if set(raw) == _CONTRACT_FIELDS["GoalIR"]:
        if not _verify_contract_identity(raw, "GoalIR", report, surface="goal_binding"):
            return None
        return copy.deepcopy(raw)
    allowed = {
        "statement",
        "origin",
        "priority",
        "parent_goal_ids",
        "constraints",
        "metadata",
    }
    if not {"statement", "origin", "metadata"} <= set(raw) <= allowed:
        report.fail("request_binding", "goal_ir_initializer_fields_mismatch")
        return None
    try:
        statement = _normalized_text(raw["statement"], "goal statement")
        origin = raw["origin"]
        if origin not in {
            "explicit_user",
            "delegated_user",
            "system_maintenance",
            "intrinsic",
        }:
            raise ValueError("goal origin invalid")
        priority = raw.get("priority", 50)
        if type(priority) is not int or not 0 <= priority <= 100:
            raise ValueError("goal priority invalid")
        parent_goal_ids = _sorted_ids(
            raw.get("parent_goal_ids", []),
            "parent_goal_ids",
        )
        constraints = [
            _normalized_text(item, "goal constraint")
            for item in raw.get("constraints", [])
        ]
        if type(raw["metadata"]) is not dict:
            raise TypeError("goal metadata must be an object")
        return _sealed_contract(
            "GoalIR",
            "goal",
            {
                "can_authorize_actions": False,
                "can_override_safety": False,
                "constraints": constraints,
                "metadata": copy.deepcopy(raw["metadata"]),
                "origin": origin,
                "parent_goal_ids": parent_goal_ids,
                "priority": priority,
                "statement": statement,
            },
        )
    except (KeyError, TypeError, ValueError) as exc:
        report.fail("request_binding", f"goal_ir_materialization:{type(exc).__name__}:{exc}")
        return None


def _normalize_action_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError("valid actions must be an array")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if type(item) is str:
            action_id = _normalized_text(item, "action_id")
            payload: dict[str, Any] = {}
        elif type(item) is dict and set(item) <= {"action_id", "payload"}:
            action_id = _normalized_text(item.get("action_id"), "action_id")
            payload_raw = item.get("payload", {})
            if type(payload_raw) is not dict:
                raise TypeError("action payload must be an object")
            payload = copy.deepcopy(payload_raw)
        else:
            raise ValueError("action row fields mismatch")
        if action_id in seen:
            raise ValueError("valid action IDs cannot repeat")
        seen.add(action_id)
        output.append({"action_id": action_id, "payload": payload})
    return output


def _log_result(row: Mapping[str, Any], operation: str) -> Any:
    if "result" in row:
        return copy.deepcopy(row["result"])
    if operation == "observe" and "observation" in row:
        return copy.deepcopy(row["observation"])
    if operation == "valid_actions" and "actions" in row:
        return copy.deepcopy(row["actions"])
    raise KeyError(f"{operation} log row has no parent result")


def _expected_operations(semantic: Mapping[str, Any]) -> list[str]:
    operations = ["reset"]
    steps = semantic.get("steps", [])
    for _step in steps:
        operations.extend(("observe", "valid_actions", "step"))
    denied = semantic.get("denied_attempt")
    if denied is not None:
        operations.extend(("observe", "valid_actions"))
    elif semantic.get("stop_reason") in {
        "no_valid_actions",
        "policy_abstained",
    }:
        operations.extend(("observe", "valid_actions"))
    elif semantic.get("stop_reason") in {
        "operator_stop_requested",
        "post_observation_mismatch",
    }:
        operations.append("observe")
    operations.append("stop")
    return operations


def _verify_environment_log(
    semantic: Mapping[str, Any],
    environment_log: Any,
    report: _Report,
) -> list[dict[str, Any]]:
    if not isinstance(environment_log, Sequence) or isinstance(
        environment_log, (str, bytes)
    ):
        report.fail("environment_binding", "parent_environment_log_not_an_array")
        return []
    rows = [copy.deepcopy(item) for item in environment_log]
    if any(type(item) is not dict for item in rows):
        report.fail("environment_binding", "parent_environment_log_row_not_an_object")
        return []
    operations = [item.get("operation") for item in rows]
    expected_operations = _expected_operations(semantic)
    if operations != expected_operations:
        report.fail(
            "environment_binding",
            "call_order_mismatch:"
            + ",".join(str(item) for item in operations),
        )
    if not rows:
        return []
    try:
        reset = rows[0]
        if reset.get("seed", semantic.get("environment_seed")) != semantic.get(
            "environment_seed"
        ):
            report.fail("environment_binding", "reset_seed_mismatch")
        reset_result = _log_result(reset, "reset")
        if reset_result != semantic.get("reset_result"):
            report.fail("environment_binding", "reset_result_mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        report.fail("environment_binding", f"reset_witness:{type(exc).__name__}:{exc}")

    witnessed: list[dict[str, Any]] = []
    cursor = 1
    semantic_steps = semantic.get("steps")
    if type(semantic_steps) is not list:
        return witnessed
    for index, _step in enumerate(semantic_steps):
        if cursor + 2 >= len(rows):
            report.fail("environment_binding", f"step_{index}:parent_log_incomplete")
            break
        observe_row, valid_row, step_row = rows[cursor : cursor + 3]
        cursor += 3
        try:
            observation = _log_result(observe_row, "observe")
            actions = _normalize_action_rows(
                _log_result(valid_row, "valid_actions")
            )
            result = _log_result(step_row, "step")
            if type(observation) is not dict or type(result) is not dict:
                raise TypeError("parent observation/result must be objects")
            if set(result) != {
                "observation",
                "terminal",
                "success",
                "stop_reason",
            }:
                raise ValueError("parent step result fields mismatch")
            if step_row.get("step_index", index) != index:
                report.fail("environment_binding", f"step_{index}:log_index_mismatch")
            for row, value, label in (
                (observe_row, observation, "observation"),
                (valid_row, _log_result(valid_row, "valid_actions"), "valid_actions"),
            ):
                supplied_digest = row.get(
                    "result_sha256",
                    row.get("result_digest", _canonical_digest(value)),
                )
                if supplied_digest != _canonical_digest(value):
                    report.fail(
                        "environment_binding",
                        f"step_{index}:parent_{label}_digest_mismatch",
                    )
            action_id = step_row.get("action_id")
            if type(action_id) is not str or not action_id:
                raise ValueError("parent step action_id missing")
            result_digest = step_row.get(
                "result_sha256",
                step_row.get("result_digest", _canonical_digest(result)),
            )
            if result_digest != _canonical_digest(result):
                report.fail(
                    "environment_binding",
                    f"step_{index}:parent_result_digest_mismatch",
                )
            witnessed.append(
                {
                    "observation": observation,
                    "actions": actions,
                    "action_id": action_id,
                    "result": result,
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            report.fail(
                "environment_binding",
                f"step_{index}:parent_witness:{type(exc).__name__}:{exc}",
            )
    try:
        if rows and rows[-1].get("operation") == "stop":
            stop_result = _log_result(rows[-1], "stop")
            if stop_result != semantic.get("stop_result"):
                report.fail("environment_binding", "stop_result_mismatch")
            if (
                type(stop_result) is dict
                and stop_result.get("reason", semantic.get("stop_reason"))
                != semantic.get("stop_reason")
            ):
                report.fail("environment_binding", "stop_reason_mismatch")
            digest = rows[-1].get(
                "result_sha256",
                rows[-1].get("result_digest", _canonical_digest(stop_result)),
            )
            if digest != _canonical_digest(stop_result):
                report.fail("environment_binding", "stop_result_digest_mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        report.fail("environment_binding", f"stop_witness:{type(exc).__name__}:{exc}")
    return witnessed


def _materialize_authorization(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise TypeError("parent authorization must be an object")
    base_fields = {
        "action_id",
        "step_index",
        "granted",
        "reason",
        "authority_kind",
        "operational_evidence",
    }
    if not base_fields <= set(raw) <= base_fields | {
        "bearer_capability",
        "witness_id",
    }:
        raise ValueError("parent authorization fields mismatch")
    action_id = _normalized_text(raw["action_id"], "authorization action_id")
    step_index = raw["step_index"]
    if type(step_index) is not int or step_index < 0:
        raise ValueError("authorization step_index invalid")
    if type(raw["granted"]) is not bool:
        raise TypeError("authorization granted must be boolean")
    reason = _normalized_text(raw["reason"], "authorization reason")
    authority_kind = _normalized_text(
        raw["authority_kind"],
        "authorization authority_kind",
    )
    if type(raw["operational_evidence"]) is not dict:
        raise TypeError("authorization operational evidence must be an object")
    identity = {
        "action_id": action_id,
        "authority_kind": authority_kind,
        "granted": raw["granted"],
        "operational_evidence": copy.deepcopy(raw["operational_evidence"]),
        "reason": reason,
        "step_index": step_index,
    }
    witness_id = _canonical_id("authorization_witness", identity)[0]
    materialized = {
        "action_id": action_id,
        "authority_kind": authority_kind,
        "bearer_capability": False,
        "granted": raw["granted"],
        "operational_evidence": copy.deepcopy(raw["operational_evidence"]),
        "reason": reason,
        "step_index": step_index,
        "witness_id": witness_id,
    }
    if "bearer_capability" in raw and raw["bearer_capability"] is not False:
        raise ValueError("authorization bearer_capability must be false")
    if "witness_id" in raw and raw["witness_id"] != witness_id:
        raise ValueError("authorization witness identity mismatch")
    return materialized


def _authorization_semantic(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "action_id": raw["action_id"],
        "authority_kind": raw["authority_kind"],
        "granted": raw["granted"],
        "reason": raw["reason"],
        "step_index": raw["step_index"],
    }


def _pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _pointer_tokens(path: Any) -> list[str]:
    if type(path) is not str or not path.startswith("/") or path == "/":
        raise ValueError("JSON pointer must be a non-root absolute path")
    output: list[str] = []
    for encoded in path[1:].split("/"):
        index = 0
        decoded: list[str] = []
        while index < len(encoded):
            if encoded[index] != "~":
                decoded.append(encoded[index])
                index += 1
            else:
                if index + 1 >= len(encoded) or encoded[index + 1] not in {"0", "1"}:
                    raise ValueError("JSON pointer escape invalid")
                decoded.append("~" if encoded[index + 1] == "0" else "/")
                index += 2
        token = "".join(decoded)
        if _pointer_escape(token) != encoded:
            raise ValueError("JSON pointer is not canonical")
        if token.isdigit() and len(token) > 1 and token.startswith("0"):
            raise ValueError("JSON pointer numeric token is not canonical")
        output.append(token)
    return output


def _pointer_get(value: Any, path: str) -> Any:
    current = value
    for token in _pointer_tokens(path):
        if type(current) is dict:
            current = current[token]
        elif type(current) is list and token.isdigit():
            current = current[int(token)]
        else:
            raise KeyError(path)
    return current


def _goal_constraints(goal: Mapping[str, Any]) -> list[dict[str, Any]]:
    metadata = goal.get("metadata")
    if type(metadata) is not dict:
        raise ValueError("GoalIR metadata missing")
    raw = metadata.get("target_constraints")
    if raw is None:
        return []
    if type(raw) is not list or len(raw) > 16:
        raise ValueError("goal target constraints invalid")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in raw:
        if (
            type(row) is not dict
            or set(row) != {"path", "op", "value"}
            or row.get("op") != "eq"
            or type(row.get("value")) is not int
        ):
            raise ValueError("goal target constraint row invalid")
        path = row["path"]
        _pointer_tokens(path)
        if path in seen:
            raise ValueError("goal target constraint path repeated")
        seen.add(path)
        output.append(copy.deepcopy(row))
    return sorted(output, key=lambda item: item["path"])


def _numeric_projection(value: Mapping[str, Any], root_path: str) -> dict[str, int]:
    tokens = _pointer_tokens(root_path)
    if len(tokens) != 1:
        raise ValueError("numeric projection root must be one top-level path")
    root = _pointer_get(value, root_path)
    if not isinstance(root, (Mapping, list, tuple)):
        raise ValueError("numeric projection root must contain structured data")
    leaves: dict[str, int] = {}

    def visit(item: Any, path: str) -> None:
        if len(leaves) >= 64:
            raise ValueError("numeric projection exceeds bounded leaves")
        if type(item) is int:
            leaves[path] = item
        elif isinstance(item, Mapping):
            for key in sorted(item, key=str):
                visit(item[key], f"{path}/{_pointer_escape(str(key))}")
        elif isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                visit(child, f"{path}/{index}")

    visit(root, root_path)
    return leaves


def _expression_depth(value: Mapping[str, Any]) -> int:
    args = value.get("args", [])
    if not args:
        return 1
    return 1 + max(_expression_depth(item) for item in args)


def _validate_expression(value: Any) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("rule expression must be an object")
    raw = copy.deepcopy(value)
    op = raw.get("op")
    if op in {"var", "copy"}:
        if set(raw) != {"op", "path"}:
            raise ValueError("rule variable expression fields mismatch")
        _pointer_tokens(raw["path"])
    elif op == "const":
        if set(raw) != {"op", "value"} or type(raw["value"]) is not int:
            raise ValueError("rule constant expression invalid")
    elif op in {"add", "mul", "mod"}:
        if set(raw) != {"args", "op"} or type(raw["args"]) is not list:
            raise ValueError("binary rule expression fields mismatch")
        if len(raw["args"]) != 2:
            raise ValueError("binary rule expression arity mismatch")
        raw["args"] = [
            _validate_expression(raw["args"][0]),
            _validate_expression(raw["args"][1]),
        ]
    else:
        raise ValueError("unsupported rule expression operator")
    if _expression_depth(raw) > MAX_RULE_AST_DEPTH:
        raise ValueError("rule expression depth exceeded")
    return raw


def _validate_rule(value: Any) -> dict[str, Any]:
    required = {
        "schema_version",
        "action_signature",
        "input_path",
        "output_path",
        "context_path",
        "expression",
        "support_edge_refs",
        "hypothesis",
    }
    if type(value) is not dict or set(value) != required:
        raise ValueError("Rule IR fields mismatch")
    rule = copy.deepcopy(value)
    if rule["schema_version"] != RULE_IR_SCHEMA or rule["hypothesis"] is not True:
        raise ValueError("Rule IR schema/hypothesis mismatch")
    signature = rule["action_signature"]
    if (
        type(signature) is not str
        or len(signature) != 64
        or any(char not in "0123456789abcdef" for char in signature)
    ):
        raise ValueError("Rule IR action signature invalid")
    for name in ("input_path", "output_path", "context_path"):
        _pointer_tokens(rule[name])
    refs = rule["support_edge_refs"]
    if (
        type(refs) is not list
        or len(refs) < MIN_DISTINCT_RULE_INPUTS
        or len(refs) != len(set(refs))
        or any(type(item) is not str or not item for item in refs)
    ):
        raise ValueError("Rule IR support references invalid")
    rule["support_edge_refs"] = sorted(refs)
    rule["expression"] = _validate_expression(rule["expression"])
    return rule


def _evaluate_expression(expression: Mapping[str, Any], projection: Mapping[str, Any]) -> int:
    op = expression["op"]
    if op in {"var", "copy"}:
        value = projection.get(expression["path"])
        if type(value) is not int:
            raise ValueError("rule variable is not an exact integer")
        return value
    if op == "const":
        return expression["value"]
    left = _evaluate_expression(expression["args"][0], projection)
    right = _evaluate_expression(expression["args"][1], projection)
    if op == "add":
        return left + right
    if op == "mul":
        return left * right
    if right <= 1:
        raise ValueError("rule modulus must be greater than one")
    return left % right


def _evaluate_rule(rule: Mapping[str, Any], projection: Mapping[str, Any]) -> dict[str, int]:
    normalized = _validate_rule(rule)
    for path in (
        normalized["input_path"],
        normalized["output_path"],
        normalized["context_path"],
    ):
        if type(projection.get(path)) is not int:
            raise ValueError("Rule IR path missing from projection")
    output = copy.deepcopy(dict(projection))
    output[normalized["output_path"]] = _evaluate_expression(
        normalized["expression"],
        projection,
    )
    return output


def _canonical_affine_rule(
    *,
    action_signature: str,
    input_path: str,
    output_path: str,
    context_path: str,
    edges: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    ordered = sorted(edges, key=lambda item: item["ordinal"])
    if len(ordered) < MIN_DISTINCT_RULE_INPUTS:
        return None
    if any(item["action_signature"] != action_signature for item in ordered):
        return None
    required = {input_path, output_path, context_path}
    if any(
        any(
            type(edge["before"].get(path)) is not int
            or type(edge["after"].get(path)) is not int
            for path in required
        )
        for edge in ordered
    ):
        return None
    if (
        len({edge["before"][input_path] for edge in ordered})
        < MIN_DISTINCT_RULE_INPUTS
        or not any(
            edge["before"][output_path] != edge["after"][output_path]
            for edge in ordered
        )
    ):
        return None
    moduli = {
        edge["before"][context_path]
        for edge in ordered
        if edge["before"][context_path] == edge["after"][context_path]
        and edge["before"][context_path] > 1
    }
    if len(moduli) != 1 or any(
        edge["before"][context_path] != edge["after"][context_path]
        for edge in ordered
    ):
        return None
    modulus = next(iter(moduli))
    fits: list[tuple[int, int, tuple[int, int]]] = []
    for multiplier in range(
        -COEFFICIENT_SEARCH_BOUND,
        COEFFICIENT_SEARCH_BOUND + 1,
    ):
        for offset in range(
            -COEFFICIENT_SEARCH_BOUND,
            COEFFICIENT_SEARCH_BOUND + 1,
        ):
            if all(
                (
                    multiplier * edge["before"][input_path] + offset
                )
                % modulus
                == edge["after"][output_path]
                for edge in ordered
            ):
                fits.append(
                    (
                        multiplier,
                        offset,
                        (multiplier % modulus, offset % modulus),
                    )
                )
    if not fits or len({item[2] for item in fits}) != 1:
        return None
    multiplier, offset, _equivalence = min(
        fits,
        key=lambda item: (
            abs(item[0]) + abs(item[1]),
            abs(item[0]),
            abs(item[1]),
            item[0],
            item[1],
        ),
    )
    return _validate_rule(
        {
            "schema_version": RULE_IR_SCHEMA,
            "action_signature": action_signature,
            "input_path": input_path,
            "output_path": output_path,
            "context_path": context_path,
            "expression": {
                "op": "mod",
                "args": [
                    {
                        "op": "add",
                        "args": [
                            {
                                "op": "mul",
                                "args": [
                                    {"op": "var", "path": input_path},
                                    {"op": "const", "value": multiplier},
                                ],
                            },
                            {"op": "const", "value": offset},
                        ],
                    },
                    {"op": "var", "path": context_path},
                ],
            },
            "support_edge_refs": [item["edge_ref"] for item in ordered],
            "hypothesis": True,
        }
    )


def _rule_key(rule: Mapping[str, Any]) -> str:
    value = _validate_rule(rule)
    value.pop("support_edge_refs")
    return _canonical_digest(value)


def _verify_memory(value: Any, report: _Report, label: str) -> dict[str, Any] | None:
    if type(value) is not dict:
        report.fail("memory_binding", f"{label}:not_an_object")
        return None
    schema = value.get("schema_version")
    base_fields = {
        "action_sets",
        "attempts",
        "concepts_by_state",
        "schema_version",
        "target_state_digest",
        "transitions",
    }
    expected_fields = (
        base_fields
        if schema == MEMORY_V1_SCHEMA
        else base_fields | {"feature_edges", "rule_records", "semantic_attempts"}
    )
    if schema not in {MEMORY_V1_SCHEMA, MEMORY_V2_SCHEMA} or set(value) != expected_fields:
        report.fail("memory_binding", f"{label}:schema_or_fields_mismatch")
        return None
    try:
        transitions = value["transitions"]
        attempts = value["attempts"]
        action_sets = value["action_sets"]
        concepts = value["concepts_by_state"]
        if any(type(rows) is not list for rows in (transitions, attempts, action_sets, concepts)):
            raise TypeError("memory core rows must be arrays")
        transition_keys: list[tuple[str, str, str]] = []
        for row in transitions:
            if (
                type(row) is not dict
                or set(row) != {"from", "action", "to", "count"}
                or type(row["count"]) is not int
                or row["count"] <= 0
            ):
                raise ValueError("memory transition row invalid")
            transition_keys.append((row["from"], row["action"], row["to"]))
        if transition_keys != sorted(transition_keys) or len(transition_keys) != len(
            set(transition_keys)
        ):
            raise ValueError("memory transition rows are not canonical")
        attempt_keys: list[tuple[str, str]] = []
        for row in attempts:
            if (
                type(row) is not dict
                or set(row) != {"state", "action", "count"}
                or type(row["count"]) is not int
                or row["count"] <= 0
            ):
                raise ValueError("memory attempt row invalid")
            attempt_keys.append((row["state"], row["action"]))
        if attempt_keys != sorted(attempt_keys) or len(attempt_keys) != len(
            set(attempt_keys)
        ):
            raise ValueError("memory attempt rows are not canonical")
        action_states: list[str] = []
        for row in action_sets:
            if (
                type(row) is not dict
                or set(row) != {"state", "actions"}
                or type(row["actions"]) is not list
                or row["actions"] != sorted(set(row["actions"]))
            ):
                raise ValueError("memory action-set row invalid")
            action_states.append(row["state"])
        if action_states != sorted(action_states) or len(action_states) != len(
            set(action_states)
        ):
            raise ValueError("memory action-set rows are not canonical")
        concept_states: list[str] = []
        for row in concepts:
            if (
                type(row) is not dict
                or set(row) != {"state", "concepts"}
                or type(row["concepts"]) is not list
            ):
                raise ValueError("memory concept row invalid")
            concept_states.append(row["state"])
        if concept_states != sorted(concept_states) or len(concept_states) != len(
            set(concept_states)
        ):
            raise ValueError("memory concept rows are not canonical")
        if schema == MEMORY_V1_SCHEMA:
            return copy.deepcopy(value)

        feature_edges = value["feature_edges"]
        rule_records = value["rule_records"]
        semantic_attempts = value["semantic_attempts"]
        if (
            type(feature_edges) is not list
            or len(feature_edges) > MAX_FEATURE_ROWS
            or type(rule_records) is not list
            or len(rule_records) > MAX_RULE_ROWS
            or type(semantic_attempts) is not list
            or len(semantic_attempts) > MAX_FEATURE_ROWS
        ):
            raise ValueError("memory typed row bound exceeded")
        valid_edge_refs = {
            _canonical_id(
                "transition_edge",
                {"action_id": action, "from": before, "to": after},
            )[0]
            for before, action, after in transition_keys
        }
        edges_by_ref: dict[str, dict[str, Any]] = {}
        for ordinal, edge in enumerate(feature_edges):
            if (
                type(edge) is not dict
                or set(edge)
                != {"action_signature", "after", "before", "edge_ref", "ordinal"}
                or edge.get("ordinal") != ordinal
                or edge.get("edge_ref") not in valid_edge_refs
                or edge.get("edge_ref") in edges_by_ref
                or type(edge.get("before")) is not dict
                or type(edge.get("after")) is not dict
                or not edge["before"]
                or not edge["after"]
                or any(type(item) is not int for item in edge["before"].values())
                or any(type(item) is not int for item in edge["after"].values())
            ):
                raise ValueError("memory feature edge invalid")
            signature = edge["action_signature"]
            if (
                type(signature) is not str
                or len(signature) != 64
                or any(char not in "0123456789abcdef" for char in signature)
            ):
                raise ValueError("memory feature action signature invalid")
            for path in (*edge["before"], *edge["after"]):
                _pointer_tokens(path)
            edges_by_ref[edge["edge_ref"]] = copy.deepcopy(edge)
        derived_attempts: dict[tuple[str, str], int] = {}
        for edge in feature_edges:
            key = (_canonical_digest(edge["before"]), edge["action_signature"])
            derived_attempts[key] = derived_attempts.get(key, 0) + 1
        expected_semantic = [
            {
                "feature_state": state,
                "action_signature": signature,
                "count": count,
            }
            for (state, signature), count in sorted(derived_attempts.items())
        ]
        if semantic_attempts != expected_semantic:
            raise ValueError("memory semantic attempts do not derive from feature edges")

        record_keys: list[str] = []
        for record in rule_records:
            if (
                type(record) is not dict
                or set(record)
                != {
                    "confirmation_edge_refs",
                    "emitted_ordinal",
                    "rule",
                    "rule_key",
                    "status",
                }
            ):
                raise ValueError("memory rule record fields invalid")
            rule = _validate_rule(record["rule"])
            if record["rule"] != rule:
                raise ValueError("memory Rule IR is not canonical")
            key = _rule_key(rule)
            record_keys.append(key)
            if (
                record["rule_key"] != key
                or record["status"] not in {"provisional", "usable"}
                or type(record["emitted_ordinal"]) is not int
                or not 0 <= record["emitted_ordinal"] <= len(feature_edges)
                or type(record["confirmation_edge_refs"]) is not list
                or (
                    record["status"] == "usable"
                    and len(record["confirmation_edge_refs"]) != 1
                )
                or (
                    record["status"] == "provisional"
                    and bool(record["confirmation_edge_refs"])
                )
            ):
                raise ValueError("memory rule record identity/status invalid")
            support = set(rule["support_edge_refs"])
            confirmation = set(record["confirmation_edge_refs"])
            if (
                not support <= set(edges_by_ref)
                or not confirmation <= set(edges_by_ref)
                or support & confirmation
            ):
                raise ValueError("memory rule support/confirmation lineage invalid")
            if any(
                edges_by_ref[ref]["ordinal"] >= record["emitted_ordinal"]
                for ref in support
            ) or any(
                edges_by_ref[ref]["ordinal"] < record["emitted_ordinal"]
                for ref in confirmation
            ):
                raise ValueError("memory rule chronology invalid")
            signature_edges = sorted(
                (
                    edge
                    for edge in feature_edges
                    if edge["action_signature"] == rule["action_signature"]
                ),
                key=lambda item: item["ordinal"],
            )
            fitting = [
                edge
                for edge in signature_edges
                if edge["ordinal"] < record["emitted_ordinal"]
            ]
            if (
                not fitting
                or record["emitted_ordinal"] != fitting[-1]["ordinal"] + 1
                or support != {edge["edge_ref"] for edge in fitting}
            ):
                raise ValueError("memory rule fitting support chronology invalid")
            derived = _canonical_affine_rule(
                action_signature=rule["action_signature"],
                input_path=rule["input_path"],
                output_path=rule["output_path"],
                context_path=rule["context_path"],
                edges=fitting,
            )
            if derived != rule:
                raise ValueError("memory Rule IR is not independently reconstructed")
            later = [
                edge
                for edge in signature_edges
                if edge["ordinal"] >= record["emitted_ordinal"]
            ]
            if any(
                _evaluate_rule(rule, edge["before"])[rule["output_path"]]
                != edge["after"][rule["output_path"]]
                for edge in later
            ):
                raise ValueError("memory Rule IR contradicted by later edge")
            expected_confirmation = [later[0]["edge_ref"]] if later else []
            expected_status = "usable" if later else "provisional"
            if (
                record["confirmation_edge_refs"] != expected_confirmation
                or record["status"] != expected_status
            ):
                raise ValueError("memory Rule IR status is self-attested")
        if record_keys != sorted(record_keys) or len(record_keys) != len(set(record_keys)):
            raise ValueError("memory rule records are not canonical")
        return copy.deepcopy(value)
    except (KeyError, TypeError, ValueError) as exc:
        report.fail("memory_binding", f"{label}:{type(exc).__name__}:{exc}")
        report.fail("rule_ir", f"{label}:{type(exc).__name__}:{exc}")
        return None


def _memory_rules(memory: Mapping[str, Any], statuses: set[str]) -> list[dict[str, Any]]:
    if memory.get("schema_version") != MEMORY_V2_SCHEMA:
        return []
    rules = [
        copy.deepcopy(record["rule"])
        for record in memory.get("rule_records", [])
        if record.get("status") in statuses
    ]
    return sorted(rules, key=_canonical_digest)


def _advance_verified_rule_memory(
    memory: Mapping[str, Any],
    *,
    pre_observation: Mapping[str, Any],
    post_observation: Mapping[str, Any],
    learning_metadata: Mapping[str, Any],
    selected_action: Mapping[str, Any],
    goal: Mapping[str, Any],
    report: _Report,
    index: int,
) -> dict[str, Any]:
    """Rebuild the rule-memory state after one independently witnessed step."""

    current = copy.deepcopy(dict(memory))

    def verify_metadata(
        *,
        confirmed: Sequence[str] = (),
        emitted: Sequence[str] = (),
    ) -> None:
        checks = {
            "confirmed_rule_digests": sorted(confirmed),
            "emitted_provisional_rule_digests": sorted(emitted),
            "provisional_transition_rule_hypotheses": _memory_rules(
                current,
                {"provisional"},
            ),
            "transition_rule_hypotheses": _memory_rules(
                current,
                {"provisional", "usable"},
            ),
        }
        for name, expected in checks.items():
            if learning_metadata.get(name) != expected:
                report.fail(
                    "rule_ir",
                    f"step_{index}:{name}_memory_evolution_mismatch",
                )

    if current.get("schema_version") != MEMORY_V2_SCHEMA:
        verify_metadata()
        return current
    try:
        signature = _action_signature(selected_action)
        constraints = _goal_constraints(goal)
        roots = {_pointer_tokens(row["path"])[0] for row in constraints}
        root_path = (
            "/" + _pointer_escape(next(iter(roots)))
            if len(roots) == 1
            else None
        )
        before_features: dict[str, int] = {}
        after_features: dict[str, int] = {}
        if signature is not None and root_path is not None:
            before_features = _numeric_projection(
                pre_observation,
                root_path,
            )
            after_features = _numeric_projection(
                post_observation,
                root_path,
            )
        if signature is None or not before_features or not after_features:
            verify_metadata()
            return current

        edge_ref = _canonical_id(
            "transition_edge",
            {
                "action_id": selected_action["action_id"],
                "from": _canonical_digest(pre_observation),
                "to": _canonical_digest(post_observation),
            },
        )[0]
        feature_edges = copy.deepcopy(current["feature_edges"])
        feature_by_ref = {row["edge_ref"]: row for row in feature_edges}
        records = {
            row["rule_key"]: copy.deepcopy(row)
            for row in current["rule_records"]
        }
        current_ordinal = len(feature_edges)
        confirmed: list[str] = []
        rejected: list[str] = []
        for key, record in sorted(records.items()):
            rule = _validate_rule(record["rule"])
            if rule["action_signature"] != signature:
                continue
            try:
                predicted = _evaluate_rule(rule, before_features)
                output_path = rule["output_path"]
                matched = (
                    type(after_features.get(output_path)) is int
                    and predicted[output_path] == after_features[output_path]
                )
            except (KeyError, TypeError, ValueError):
                matched = False
            if not matched:
                rejected.append(key)
                continue
            if edge_ref in rule["support_edge_refs"]:
                continue
            if record["status"] == "usable":
                continue
            if (
                record["status"] == "provisional"
                and record["emitted_ordinal"] <= current_ordinal
            ):
                record["confirmation_edge_refs"] = [edge_ref]
                record["status"] = "usable"
                confirmed.append(_canonical_digest(rule))
        for key in rejected:
            del records[key]

        expected_edge = {
            "action_signature": signature,
            "after": after_features,
            "before": before_features,
            "edge_ref": edge_ref,
            "ordinal": (
                feature_by_ref[edge_ref]["ordinal"]
                if edge_ref in feature_by_ref
                else len(feature_edges)
            ),
        }
        if edge_ref in feature_by_ref:
            if feature_by_ref[edge_ref] != expected_edge:
                raise ValueError("feature edge identity collision")
        else:
            if len(feature_edges) >= MAX_FEATURE_ROWS:
                raise ValueError("feature transition memory exceeds bounded edge count")
            feature_edges.append(expected_edge)
            feature_by_ref[edge_ref] = expected_edge

        emitted: list[str] = []
        signature_edges = [
            edge
            for edge in sorted(
                feature_edges,
                key=lambda item: item["ordinal"],
            )
            if edge["action_signature"] == signature
        ]
        if len(signature_edges) >= MIN_DISTINCT_RULE_INPUTS:
            common_paths = set(signature_edges[0]["before"]) & set(
                signature_edges[0]["after"]
            )
            for edge in signature_edges[1:]:
                common_paths &= set(edge["before"])
                common_paths &= set(edge["after"])
            common_paths = {
                path
                for path in common_paths
                if all(
                    type(edge["before"].get(path)) is int
                    and type(edge["after"].get(path)) is int
                    for edge in signature_edges
                )
            }
            capacity_reached = False
            for output_path in sorted(common_paths):
                if capacity_reached:
                    break
                for input_path in sorted(common_paths):
                    if capacity_reached:
                        break
                    for context_path in sorted(common_paths - {output_path}):
                        rule = _canonical_affine_rule(
                            action_signature=signature,
                            input_path=input_path,
                            output_path=output_path,
                            context_path=context_path,
                            edges=signature_edges,
                        )
                        if rule is None:
                            continue
                        key = _rule_key(rule)
                        if key in records and records[key]["status"] in {
                            "provisional",
                            "usable",
                        }:
                            continue
                        if len(records) >= MAX_RULE_ROWS:
                            capacity_reached = True
                            break
                        records[key] = {
                            "confirmation_edge_refs": [],
                            "emitted_ordinal": len(feature_edges),
                            "rule": rule,
                            "rule_key": key,
                            "status": "provisional",
                        }
                        emitted.append(_canonical_digest(rule))

        current["feature_edges"] = feature_edges
        current["rule_records"] = [
            records[key] for key in sorted(records)
        ]
        verify_metadata(
            confirmed=confirmed,
            emitted=emitted,
        )
        return current
    except (KeyError, TypeError, ValueError) as exc:
        report.fail(
            "rule_ir",
            f"step_{index}:rule_memory_evolution:"
            f"{type(exc).__name__}:{exc}",
        )
        return current


def _verify_memory_evolution(
    *,
    semantic: Mapping[str, Any],
    lineage_steps: Sequence[Mapping[str, Any]],
    report: _Report,
) -> None:
    """Bind retained policy memory to the independently witnessed trace steps.

    Rule induction is checked separately by :func:`_verify_memory`; this
    routine reconstructs every non-rule state mutation (action registration,
    transition/attempt counts, concepts, success target, feature edges, and
    semantic attempts).  That prevents a caller from substituting an unrelated
    but internally self-consistent memory-after object.
    """

    before = semantic.get("memory_before")
    after = semantic.get("memory_after")
    if type(before) is not dict or type(after) is not dict:
        return
    if semantic.get("retain_policy_updates") is False:
        return
    if (
        before.get("schema_version") != MEMORY_V2_SCHEMA
        or after.get("schema_version") != MEMORY_V2_SCHEMA
    ):
        report.fail(
            "memory_binding",
            "retaining_trace_requires_v2_memory_for_independent_evolution",
        )
        return
    try:
        transitions = {
            (row["from"], row["action"], row["to"]): row["count"]
            for row in before["transitions"]
        }
        attempts = {
            (row["state"], row["action"]): row["count"]
            for row in before["attempts"]
        }
        action_sets = {
            row["state"]: set(row["actions"])
            for row in before["action_sets"]
        }
        concepts = {
            row["state"]: list(row["concepts"])
            for row in before["concepts_by_state"]
        }
        feature_edges = copy.deepcopy(before["feature_edges"])
        feature_by_ref = {
            row["edge_ref"]: row for row in feature_edges
        }
        target_state_digest = before["target_state_digest"]
        constraints = _goal_constraints(semantic["goal"])
        roots = {_pointer_tokens(row["path"])[0] for row in constraints}
        root_path = (
            "/" + _pointer_escape(next(iter(roots)))
            if len(roots) == 1
            else None
        )

        for index, (step, full) in enumerate(
            zip(semantic["steps"], lineage_steps)
        ):
            pre = step["pre_observation"]
            post = step["post_observation"]
            before_digest = _canonical_digest(pre)
            after_digest = _canonical_digest(post)
            action_id = step["selected_action"]
            valid_ids = {row["action_id"] for row in step["valid_actions"]}
            action_sets.setdefault(before_digest, set()).update(valid_ids)
            transition_key = (before_digest, action_id, after_digest)
            transitions[transition_key] = transitions.get(transition_key, 0) + 1
            attempt_key = (before_digest, action_id)
            attempts[attempt_key] = attempts.get(attempt_key, 0) + 1
            concepts[before_digest] = _collect_concepts(pre)
            if step["step_result"]["success"] is True:
                target_state_digest = after_digest
            selected = [
                row
                for row in step["valid_actions"]
                if row["action_id"] == action_id
            ]
            if len(selected) != 1:
                raise ValueError(f"step_{index}:selected action is not unique")
            signature = _action_signature(selected[0])
            before_features: dict[str, int] = {}
            after_features: dict[str, int] = {}
            if signature is not None and root_path is not None:
                before_features = _numeric_projection(pre, root_path)
                after_features = _numeric_projection(post, root_path)
            if signature is not None and before_features and after_features:
                edge_ref = step["learned_edge_ref"]
                expected_edge = {
                    "action_signature": signature,
                    "after": after_features,
                    "before": before_features,
                    "edge_ref": edge_ref,
                    "ordinal": (
                        feature_by_ref[edge_ref]["ordinal"]
                        if edge_ref in feature_by_ref
                        else len(feature_edges)
                    ),
                }
                if edge_ref in feature_by_ref:
                    if feature_by_ref[edge_ref] != expected_edge:
                        raise ValueError(
                            f"step_{index}:feature edge identity collision"
                        )
                else:
                    feature_edges.append(expected_edge)
                    feature_by_ref[edge_ref] = expected_edge

        denied = semantic.get("denied_attempt")
        if type(denied) is dict:
            state = _canonical_digest(denied["pre_observation"])
            action_sets.setdefault(state, set()).update(
                row["action_id"] for row in denied["valid_actions"]
            )
        expected_core = {
            "transitions": [
                {
                    "from": source,
                    "action": action,
                    "to": target,
                    "count": count,
                }
                for (source, action, target), count in sorted(transitions.items())
            ],
            "attempts": [
                {"state": state, "action": action, "count": count}
                for (state, action), count in sorted(attempts.items())
            ],
            "action_sets": [
                {"state": state, "actions": sorted(actions)}
                for state, actions in sorted(action_sets.items())
            ],
            "concepts_by_state": [
                {"state": state, "concepts": rows}
                for state, rows in sorted(concepts.items())
            ],
            "feature_edges": feature_edges,
            "target_state_digest": target_state_digest,
        }
        for name, expected in expected_core.items():
            if after.get(name) != expected:
                report.fail(
                    "memory_binding",
                    f"retaining_memory_{name}_evolution_mismatch",
                )
        derived_attempts: dict[tuple[str, str], int] = {}
        for edge in feature_edges:
            key = (_canonical_digest(edge["before"]), edge["action_signature"])
            derived_attempts[key] = derived_attempts.get(key, 0) + 1
        expected_semantic_attempts = [
            {
                "feature_state": state,
                "action_signature": signature,
                "count": count,
            }
            for (state, signature), count in sorted(derived_attempts.items())
        ]
        if after.get("semantic_attempts") != expected_semantic_attempts:
            report.fail(
                "memory_binding",
                "retaining_memory_semantic_attempts_evolution_mismatch",
            )
        if semantic["steps"]:
            last_rules = semantic["steps"][-1]["learning_proof"].get(
                "metadata",
                {},
            )
            expected_all = _memory_rules(
                after,
                {"provisional", "usable"},
            )
            expected_provisional = _memory_rules(after, {"provisional"})
            if last_rules.get("transition_rule_hypotheses") != expected_all:
                report.fail(
                    "rule_ir",
                    "last_learning_proof_rule_set_differs_from_memory_after",
                )
            if (
                last_rules.get("provisional_transition_rule_hypotheses")
                != expected_provisional
            ):
                report.fail(
                    "rule_ir",
                    "last_learning_proof_provisional_set_differs_from_memory_after",
                )
    except (KeyError, TypeError, ValueError) as exc:
        report.fail(
            "memory_binding",
            f"memory_evolution:{type(exc).__name__}:{exc}",
        )


def _collect_concepts(value: Any, *, limit: int = 64) -> list[str]:
    output: list[str] = []

    def visit(item: Any) -> None:
        if len(output) >= limit:
            return
        if isinstance(item, Mapping):
            for key in sorted(item, key=str):
                text = " ".join(str(key).split())
                if text:
                    output.append(text)
                visit(item[key])
                if len(output) >= limit:
                    break
        elif isinstance(item, (tuple, list)):
            for child in item:
                visit(child)
                if len(output) >= limit:
                    break
        elif type(item) is str:
            text = " ".join(item.split())
            if text:
                output.append(text[:160])

    visit(value)
    return list(dict.fromkeys(output))


def _expected_perception(
    observation: Mapping[str, Any],
    report: _Report,
    index: int,
) -> dict[str, Any]:
    observation_digest = _canonical_digest(observation)
    concepts = _collect_concepts(observation)
    if "detections" in observation or "frame_size" in observation:
        report.fail(
            "environment_binding",
            f"step_{index}:scene_graph_input_outside_capability_contract",
        )
    scene_graph = {"used": False, "graph": {}}
    situation = {
        "agent_count": 0,
        "location_count": 0,
        "present_count": 0,
        "room_count": 0,
    }
    claim = _sealed_contract(
        "ClaimEnvelope",
        "claim_observed",
        {
            "accepted_as_observed_fact": True,
            "confidence": None,
            "lineage_tiers": [],
            "metadata": {
                "observation_digest": observation_digest,
                "perception": "deterministic_scene_graph_and_situation_tracker",
            },
            "source_claim_ids": [],
            "source_refs": [f"environment-observation:{observation_digest}"],
            "statement": f"Environment observation sha256 {observation_digest}.",
            "tier": "observed",
        },
    )
    organ_digest = _canonical_digest(
        {
            "claim_id": claim["contract_id"],
            "concepts": concepts,
            "scene_graph": scene_graph,
            "situation_summary": situation,
        }
    )
    return {
        "claim": claim,
        "concepts": concepts,
        "observation": copy.deepcopy(dict(observation)),
        "observation_digest": observation_digest,
        "organ_digest": organ_digest,
        "scene_graph": scene_graph,
        "situation_summary": situation,
    }


def _proposal_identity(proposal: Any, report: _Report, index: int) -> bool:
    fields = {
        "action_id",
        "affordance_grounding",
        "affordance_resonance",
        "authoritative",
        "deliberator_proof",
        "observation_digest",
        "proposal_id",
        "strategy",
        "transition_graph_path",
        "valid_actions_digest",
    }
    if type(proposal) is not dict or set(proposal) != fields:
        report.fail("proposal_lineage", f"step_{index}:proposal_fields_mismatch")
        return False
    if proposal.get("authoritative") is not False:
        report.fail("proposal_lineage", f"step_{index}:proposal_authoritative")
    try:
        payload = {
            "action_id": proposal["action_id"],
            "affordance_grounding": proposal["affordance_grounding"],
            "affordance_resonance": float(proposal["affordance_resonance"]),
            "deliberator_proof": proposal["deliberator_proof"],
            "observation_digest": proposal["observation_digest"],
            "strategy": proposal["strategy"],
            "transition_graph_path": proposal["transition_graph_path"],
            "valid_actions_digest": proposal["valid_actions_digest"],
        }
        expected = _canonical_id("proposal", payload)[0]
        if proposal["proposal_id"] != expected:
            report.fail(
                "proposal_lineage",
                f"step_{index}:proposal_identity_mismatch",
            )
            return False
    except (KeyError, TypeError, ValueError) as exc:
        report.fail(
            "proposal_lineage",
            f"step_{index}:proposal_identity:{type(exc).__name__}:{exc}",
        )
        return False
    return True


def _action_signature(action: Mapping[str, Any]) -> str | None:
    payload = action["payload"]
    return _canonical_digest(payload) if payload else None


def _verify_rule_plan(
    proposal: Mapping[str, Any],
    goal: Mapping[str, Any],
    observation: Mapping[str, Any],
    selected_action: Mapping[str, Any],
    memory_before: Mapping[str, Any],
    report: _Report,
    index: int,
) -> None:
    proof = proposal.get("deliberator_proof")
    if type(proof) is not dict:
        report.fail("rule_ir", f"step_{index}:deliberator_proof_missing")
        return
    expected_hypotheses = _memory_rules(
        memory_before,
        {"provisional", "usable"},
    )
    supplied = proof.get("transition_rule_hypotheses")
    if proposal.get("strategy") != "typed_rule_goal_plan":
        if supplied != expected_hypotheses:
            report.fail("rule_ir", f"step_{index}:hypothesis_set_memory_mismatch")
        return
    try:
        usable_rules = _memory_rules(memory_before, {"usable"})
        if supplied != usable_rules:
            raise ValueError("usable_rule_set_mismatch")
        constraints = _goal_constraints(goal)
        roots = {_pointer_tokens(row["path"])[0] for row in constraints}
        if len(roots) != 1:
            raise ValueError("goal_constraints_root_mismatch")
        root_path = "/" + _pointer_escape(next(iter(roots)))
        if proof.get("goal_constraints") != constraints:
            raise ValueError("goal_constraints_mismatch")
        if proof.get("goal_constraint_digest") != _canonical_digest(constraints):
            raise ValueError("goal_constraint_digest_mismatch")
        if (
            proof.get("selector") != "reasoning_vm.deliberator"
            or proof.get("grounded") is not True
        ):
            raise ValueError("rule_plan_selector_mismatch")
        plan = proof.get("selected_plan")
        if type(plan) is not list or not plan or len(plan) > MAX_RULE_PLAN_DEPTH:
            raise ValueError("selected_plan_invalid")
        current = _numeric_projection(observation, root_path)
        rules_by_signature: dict[str, list[dict[str, Any]]] = {}
        for rule in usable_rules:
            normalized = _validate_rule(rule)
            rules_by_signature.setdefault(
                normalized["action_signature"],
                [],
            ).append(normalized)
        for plan_index, row in enumerate(plan):
            if (
                type(row) is not dict
                or set(row)
                != {"action_signature", "after", "before", "rule_digests"}
                or row["before"] != current
            ):
                raise ValueError(f"plan_{plan_index}:shape_or_before_mismatch")
            rules = sorted(
                rules_by_signature.get(row["action_signature"], []),
                key=_canonical_digest,
            )
            if not rules:
                raise ValueError(f"plan_{plan_index}:rule_missing")
            if row["rule_digests"] != sorted(_canonical_digest(rule) for rule in rules):
                raise ValueError(f"plan_{plan_index}:rule_digest_mismatch")
            output_paths = [rule["output_path"] for rule in rules]
            if len(output_paths) != len(set(output_paths)):
                raise ValueError(f"plan_{plan_index}:ambiguous_output")
            after = copy.deepcopy(current)
            for rule in rules:
                evaluated = _evaluate_rule(rule, current)
                after[rule["output_path"]] = evaluated[rule["output_path"]]
            if row["after"] != after:
                raise ValueError(f"plan_{plan_index}:after_mismatch")
            current = after
        if plan[0]["action_signature"] != _action_signature(selected_action):
            raise ValueError("selected_action_signature_mismatch")
        if not constraints or not all(
            current.get(row["path"]) == row["value"] for row in constraints
        ):
            raise ValueError("plan_does_not_satisfy_goal")
        expected_path: list[str] = [
            f"feature:{_canonical_digest(plan[0]['before'])}"
        ]
        for row in plan:
            expected_path.extend(
                (
                    "feature_action:"
                    + _canonical_digest(
                        {
                            "from": row["before"],
                            "action_signature": row["action_signature"],
                        }
                    ),
                    f"feature:{_canonical_digest(row['after'])}",
                )
            )
        if proposal.get("transition_graph_path") != expected_path:
            raise ValueError("rule_transition_graph_path_mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        report.fail("rule_ir", f"step_{index}:{type(exc).__name__}:{exc}")


def _expected_proposal_proof(
    *,
    proposal: Mapping[str, Any],
    perception: Mapping[str, Any],
    goal: Mapping[str, Any],
    selected_action: Mapping[str, Any],
) -> dict[str, Any]:
    route_proof = proposal["deliberator_proof"]
    grounded = route_proof.get("grounded") is True
    hypotheses = route_proof.get("transition_rule_hypotheses", [])
    if type(hypotheses) is not list:
        hypotheses = []
    selected_plan = route_proof.get("selected_plan")
    return _sealed_contract(
        "ProofCandidate",
        "proofc",
        {
            "accepted_as_proof": False,
            "claim_id": perception["claim"]["contract_id"],
            "confidence": None,
            "derivation_steps": (
                ["DELIBERATOR re-verified the learned route."]
                if grounded
                else ["Systematic exploration selected an evaluator-returned action."]
            ),
            "metadata": {
                "action_payload_signature": _action_signature(selected_action),
                "goal_digest": _canonical_digest(goal),
                "proposal_id": proposal["proposal_id"],
                "route_proof": copy.deepcopy(route_proof),
                "selected_action_id": selected_action["action_id"],
                "selected_plan": copy.deepcopy(selected_plan),
                "transition_rule_hypotheses": copy.deepcopy(hypotheses),
            },
            "method": (
                "deliberator_verified_transition_route"
                if grounded
                else "bounded_systematic_exploration"
            ),
            "premise_claim_ids": [perception["claim"]["contract_id"]],
            "truth_mutation_allowed": False,
            "verifier_refs": [proposal["proposal_id"]],
        },
    )


def _expected_decision_records(
    *,
    index: int,
    goal: Mapping[str, Any],
    perception: Mapping[str, Any],
    valid_actions_digest: str,
    parent_snapshot_id: str | None,
    proposal: Mapping[str, Any],
    selected_action: Mapping[str, Any],
    step_budget: int,
    session_id: str,
) -> tuple[dict[str, Any], ...]:
    snapshot = _sealed_contract(
        "WorldSnapshot",
        "world",
        {
            "inferred_claim_ids": [],
            "metadata": {
                "observation_digest": perception["observation_digest"],
                "organ_digest": perception["organ_digest"],
                "valid_actions_digest": valid_actions_digest,
            },
            "observed_claim_ids": [perception["claim"]["contract_id"]],
            "parent_snapshot_id": parent_snapshot_id,
            "predicted_claim_ids": [],
            "read_only": True,
            "recorded_claim_ids": [],
            "retrodicted_claim_ids": [],
            "snapshot_index": index,
            "world_time": f"logical:{index}",
        },
    )
    proof = _expected_proposal_proof(
        proposal=proposal,
        perception=perception,
        goal=goal,
        selected_action=selected_action,
    )
    envelope = _sealed_contract(
        "CognitiveEnvelope",
        "cenv",
        {
            "autonomy_authority": False,
            "cognition_only": True,
            "context": {"loop": "generic_world_interaction"},
            "explicit_user_goal_ids": [goal["contract_id"]],
            "hormone_signals": {},
            "intrinsic_goal_ids": [],
            "intrinsic_override_allowed": False,
            "permission_mutation_allowed": False,
            "read_only": True,
            "resource_limits": {
                "step_budget": float(step_budget),
                "steps_remaining": float(max(0, step_budget - index)),
            },
            "safety_mutation_allowed": False,
            "session_id": session_id,
            "truth_mutation_allowed": False,
            "world_snapshot_id": snapshot["contract_id"],
        },
    )
    moment = _sealed_contract(
        "CognitiveMoment",
        "moment",
        {
            "action_authority": False,
            "active_goal_ids": [goal["contract_id"]],
            "attention_targets": [
                perception["claim"]["contract_id"],
                proposal["proposal_id"],
            ],
            "claim_ids": [perception["claim"]["contract_id"]],
            "envelope_id": envelope["contract_id"],
            "hormone_signals": {},
            "metadata": {"valid_actions_digest": valid_actions_digest},
            "moment_index": index,
            "permission_mutation_allowed": False,
            "proof_candidate_ids": [proof["contract_id"]],
            "resource_state": {
                "step_budget": float(step_budget),
                "steps_remaining": float(max(0, step_budget - index)),
            },
            "safety_mutation_allowed": False,
            "selected_goal_id": goal["contract_id"],
            "truth_mutation_allowed": False,
            "world_snapshot_id": snapshot["contract_id"],
        },
    )
    metadata = proof["metadata"]
    decision = _sealed_contract(
        "DecisionReceipt",
        "decision",
        {
            "action_executed": False,
            "authoritative": False,
            "decision_kind": "interactive_action_proposal",
            "input_claim_ids": [perception["claim"]["contract_id"]],
            "metadata": {
                "action_payload_signature": metadata["action_payload_signature"],
                "goal_digest": metadata["goal_digest"],
                "observation_digest": perception["observation_digest"],
                "proposal_id": proposal["proposal_id"],
                "selected_plan_digest": _canonical_digest(
                    metadata.get("selected_plan")
                ),
                "snapshot_id": snapshot["contract_id"],
                "transition_rule_hypotheses_digest": _canonical_digest(
                    metadata["transition_rule_hypotheses"]
                ),
                "valid_actions_digest": valid_actions_digest,
            },
            "mode": "read_only",
            "moment_id": moment["contract_id"],
            "proof_candidate_ids": [proof["contract_id"]],
            "proposed_action": {
                "action_id": selected_action["action_id"],
                "payload_digest": _canonical_digest(selected_action["payload"]),
            },
            "rationale": (
                f"{proposal['strategy']}; action is a proposal pending "
                "independent RunLease."
            ),
            "read_only": True,
            "selected_goal_id": goal["contract_id"],
            "shadow": False,
        },
    )
    return snapshot, envelope, moment, proof, decision


def _expected_target_claim(
    *,
    action_id: str,
    action_signature: str | None,
    before_digest: str,
    after_digest: str,
    edge_ref: str,
    source_claim_id: str,
) -> dict[str, Any]:
    return _sealed_contract(
        "ClaimEnvelope",
        "claim_inferred",
        {
            "accepted_as_observed_fact": False,
            "confidence": None,
            "lineage_tiers": ["observed"],
            "metadata": {
                "action_id": action_id,
                "action_signature": action_signature,
                "from_observation_digest": before_digest,
                "to_observation_digest": after_digest,
            },
            "source_claim_ids": [source_claim_id],
            "source_refs": [],
            "statement": f"Observed transition edge {edge_ref}.",
            "tier": "inferred",
        },
    )


def _verify_learning_lineage(
    *,
    step: Mapping[str, Any],
    full: Mapping[str, Any],
    selected_action: Mapping[str, Any],
    goal: Mapping[str, Any],
    report: _Report,
    index: int,
) -> None:
    try:
        before = step["pre_observation"]
        after = step["post_observation"]
        before_digest = _canonical_digest(before)
        after_digest = _canonical_digest(after)
        edge_ref = _canonical_id(
            "transition_edge",
            {
                "action_id": selected_action["action_id"],
                "from": before_digest,
                "to": after_digest,
            },
        )[0]
        if step.get("learned_edge_ref") != edge_ref:
            report.fail("learning_lineage", f"step_{index}:edge_ref_mismatch")
        proof = full.get("learning_proof")
        if not _verify_contract_identity(
            proof,
            "ProofCandidate",
            report,
            surface="contract_identity",
        ):
            report.fail("learning_lineage", f"step_{index}:proof_identity_invalid")
            return
        metadata = proof.get("metadata")
        if type(metadata) is not dict:
            raise ValueError("learning proof metadata missing")
        signature = _action_signature(selected_action)
        constraints = _goal_constraints(goal)
        roots = {_pointer_tokens(row["path"])[0] for row in constraints}
        before_features: dict[str, int] = {}
        after_features: dict[str, int] = {}
        if len(roots) == 1:
            root_path = "/" + _pointer_escape(next(iter(roots)))
            before_features = _numeric_projection(before, root_path)
            after_features = _numeric_projection(after, root_path)
        target_claim = _expected_target_claim(
            action_id=selected_action["action_id"],
            action_signature=signature,
            before_digest=before_digest,
            after_digest=after_digest,
            edge_ref=edge_ref,
            source_claim_id=full["perception"]["claim"]["contract_id"],
        )
        checks = {
            "action_signature": signature,
            "after_features": after_features,
            "before_features": before_features,
            "edge_id": edge_ref,
            "target_claim": target_claim,
        }
        for name, expected in checks.items():
            if metadata.get(name) != expected:
                report.fail(
                    "learning_lineage",
                    f"step_{index}:{name}_mismatch",
                )
        if (
            proof.get("claim_id") != target_claim["contract_id"]
            or proof.get("method") != "environment_transition_witness"
            or proof.get("premise_claim_ids")
            != [full["perception"]["claim"]["contract_id"]]
            or proof.get("derivation_steps")
            != [
                "Bind the selected action to the evaluator-owned valid set.",
                "Observe the evaluator-owned post-step state.",
            ]
            or proof.get("verifier_refs") != [edge_ref]
        ):
            report.fail("learning_lineage", f"step_{index}:proof_binding_mismatch")
        for key in (
            "transition_rule_hypotheses",
            "provisional_transition_rule_hypotheses",
        ):
            rules = metadata.get(key)
            if type(rules) is not list:
                report.fail("rule_ir", f"step_{index}:{key}_not_an_array")
            else:
                for rule_index, rule in enumerate(rules):
                    try:
                        _validate_rule(rule)
                    except (KeyError, TypeError, ValueError) as exc:
                        report.fail(
                            "rule_ir",
                            f"step_{index}:{key}_{rule_index}:"
                            f"{type(exc).__name__}:{exc}",
                        )
    except (KeyError, TypeError, ValueError) as exc:
        report.fail(
            "learning_lineage",
            f"step_{index}:{type(exc).__name__}:{exc}",
        )


def _semantic_from_lineage(full: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "authorization": _authorization_semantic(full["authorization"]),
        "decision_receipt": copy.deepcopy(full["decision_receipt"]),
        "learned_edge_ref": full["learned_edge_ref"],
        "learning_proof": copy.deepcopy(full["learning_proof"]),
        "post_observation": copy.deepcopy(full["post_observation"]),
        "pre_observation": copy.deepcopy(full["pre_observation"]),
        "proposal": copy.deepcopy(full["proposal"]),
        "proposal_proof": copy.deepcopy(full["proposal_proof"]),
        "selected_action": full["selected_action"],
        "step_index": full["step_index"],
        "step_result": copy.deepcopy(full["step_result"]),
        "valid_actions": copy.deepcopy(full["valid_actions"]),
        "valid_actions_digest": full["valid_actions_digest"],
        "world_snapshot": copy.deepcopy(full["world_snapshot"]),
    }


def _cycle_status(stop_reason: str, success: bool) -> str:
    if success:
        return "completed"
    if stop_reason in {"no_valid_actions", "policy_abstained"}:
        return "abstained"
    if stop_reason.startswith(("step_budget", "run_lease", "operator_stop")):
        return "cancelled"
    return "failed"


def _entity(
    *,
    kind: str,
    cycle_id: str,
    ordinal: int,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    payload_copy = copy.deepcopy(dict(payload))
    payload_hash = _canonical_digest(payload_copy)
    semantic_id = _canonical_id(
        f"sem_{kind}",
        {"kind": kind, "payload_hash": payload_hash},
    )[0]
    occurrence_id = _canonical_id(
        f"occ_{kind}",
        {
            "cycle_id": cycle_id,
            "kind": kind,
            "ordinal": ordinal,
            "payload_hash": payload_hash,
        },
    )[0]
    return {
        "authoritative": False,
        "contract_type": "CanonicalEntityRef",
        "cycle_id": cycle_id,
        "kind": kind,
        "legacy_ref": None,
        "observer_only": True,
        "occurrence_id": occurrence_id,
        "ordinal": ordinal,
        "payload": payload_copy,
        "payload_hash": payload_hash,
        "schema_version": COGNITIVE_SCHEMA,
        "semantic_id": semantic_id,
    }


def _apply_state_patch(state: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    if type(state) is not dict or type(patch) is not dict:
        raise TypeError("cycle state and patch must be objects")
    if set(patch) - {"set", "delete"}:
        raise ValueError("cycle state patch fields invalid")
    setters = patch.get("set", {})
    deleters = patch.get("delete", [])
    if type(setters) is not dict or type(deleters) is not list:
        raise TypeError("cycle state patch shape invalid")
    if len(deleters) != len(set(deleters)) or set(setters) & set(deleters):
        raise ValueError("cycle state patch conflict")
    output = copy.deepcopy(dict(state))
    for key in deleters:
        if type(key) is not str or not key:
            raise ValueError("cycle state delete key invalid")
        output.pop(key, None)
    for key, value in setters.items():
        if type(key) is not str or not key:
            raise ValueError("cycle state set key invalid")
        output[key] = copy.deepcopy(value)
    _canonical_json(output)
    return output


def _event(
    *,
    cycle_id: str,
    sequence: int,
    phase: str,
    parent_event_id: str | None,
    refs: Sequence[str],
    state_before: Mapping[str, Any],
    patch: Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state_after = _apply_state_patch(state_before, patch)
    payload = {
        "cycle_id": cycle_id,
        "entity_occurrence_ids": list(refs),
        "metadata": copy.deepcopy(dict(metadata or {})),
        "parent_event_id": parent_event_id,
        "phase": phase,
        "sequence": sequence,
        "state_after_hash": _canonical_digest(state_after),
        "state_before_hash": _canonical_digest(state_before),
        "state_patch": copy.deepcopy(dict(patch)),
    }
    event_id = _canonical_id("cevent", payload)[0]
    return (
        {
            "authoritative": False,
            "contract_type": "CycleEvent",
            **payload,
            "event_id": event_id,
            "observer_only": True,
            "permission_mutated": False,
            "promotion_mutated": False,
            "schema_version": COGNITIVE_SCHEMA,
            "truth_mutated": False,
        },
        state_after,
    )


def _build_cycle_receipt(
    semantic: Mapping[str, Any],
    lineage_steps: Sequence[Mapping[str, Any]],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    goal = semantic["goal"]
    identity = {
        "environment_seed": semantic["environment_seed"],
        "goal_id": goal["contract_id"],
        "memory_before_digest": _canonical_digest(semantic["memory_before"]),
        "policy_seed": semantic["policy_seed"],
        "reset_digest": _canonical_digest(semantic["reset_result"]),
        "retain_policy_updates": semantic["retain_policy_updates"],
        "step_budget": semantic["step_budget"],
    }
    request_id = request.get("request_id") or _canonical_id(
        "gwip_request",
        identity,
    )[0]
    cycle_id = request.get("cycle_id") or _canonical_id(
        "gwip_cycle",
        identity,
    )[0]
    steps = semantic["steps"]
    first_observation_id = (
        f"environment-observation:{_canonical_digest(steps[0]['pre_observation'])}"
        if steps
        else f"environment-reset:{_canonical_digest(semantic['reset_result'])}"
    )
    request_cycle = {
        "authoritative": False,
        "contract_type": "RequestCycle",
        "cycle_id": cycle_id,
        "input_observation_id": first_observation_id,
        "observer_only": True,
        "parent_cycle_id": None,
        "request_id": request_id,
        "schema_version": COGNITIVE_SCHEMA,
        "seed": semantic["policy_seed"],
        "session_id": request["session_id"],
    }
    entities: list[dict[str, Any]] = []

    def add_entity(kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        item = _entity(
            kind=kind,
            cycle_id=cycle_id,
            ordinal=len(entities),
            payload=payload,
        )
        entities.append(item)
        return item

    events: list[dict[str, Any]] = []
    state: dict[str, Any] = {"status": "running", "step_count": 0}
    initial_state = copy.deepcopy(state)

    def transition(
        phase: str,
        refs: Sequence[Mapping[str, Any]],
        patch: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        nonlocal state
        event, state = _event(
            cycle_id=cycle_id,
            sequence=len(events),
            phase=phase,
            parent_event_id=events[-1]["event_id"] if events else None,
            refs=[item["occurrence_id"] for item in refs],
            state_before=state,
            patch=patch,
            metadata=metadata,
        )
        events.append(event)

    goal_entity = add_entity("goal", goal)
    transition(
        "ingress",
        (goal_entity,),
        {
            "set": {
                "goal_id": goal["contract_id"],
                "reset_digest": _canonical_digest(semantic["reset_result"]),
                "retain_policy_updates": semantic["retain_policy_updates"],
            },
            "delete": [],
        },
    )
    for step, full in zip(steps, lineage_steps):
        proposal_metadata = step["proposal_proof"]["metadata"]
        learning_metadata = step["learning_proof"]["metadata"]
        observation = add_entity(
            "observation",
            {
                "claim_id": full["perception"]["claim"]["contract_id"],
                "observation_digest": full["perception"]["observation_digest"],
                "snapshot_id": step["world_snapshot"]["contract_id"],
                "valid_actions_digest": step["valid_actions_digest"],
            },
        )
        plan = add_entity(
            "plan",
            {
                **copy.deepcopy(step["proposal"]),
                "goal_digest": proposal_metadata.get("goal_digest"),
                "proposal_proof_id": step["proposal_proof"]["contract_id"],
                "selected_plan_digest": _canonical_digest(
                    proposal_metadata.get("selected_plan")
                ),
                "transition_rule_hypotheses_digest": _canonical_digest(
                    proposal_metadata.get("transition_rule_hypotheses", [])
                ),
            },
        )
        action = add_entity(
            "action",
            {
                "action_id": step["selected_action"],
                "action_payload_signature": proposal_metadata.get(
                    "action_payload_signature"
                ),
                "decision_receipt_id": step["decision_receipt"]["contract_id"],
                "proposal_id": step["proposal"]["proposal_id"],
                "valid_actions_digest": step["valid_actions_digest"],
            },
        )
        authorization = add_entity(
            "evaluation",
            {
                "action_occurrence_id": action["occurrence_id"],
                "authorization_witness_id": full["authorization"]["witness_id"],
                "granted": full["authorization"]["granted"],
            },
        )
        learning = add_entity(
            "learning_candidate",
            {
                "action_occurrence_id": action["occurrence_id"],
                "edge_ref": step["learned_edge_ref"],
                "from_observation_digest": full["perception"][
                    "observation_digest"
                ],
                "learning_proof_id": step["learning_proof"]["contract_id"],
                "to_observation_digest": _canonical_digest(
                    step["post_observation"]
                ),
                "transition_rule_hypotheses_digest": _canonical_digest(
                    learning_metadata.get("transition_rule_hypotheses", [])
                ),
            },
        )
        transition(
            "perception",
            (observation,),
            {
                "set": {
                    "current_observation_digest": full["perception"][
                        "observation_digest"
                    ],
                    "current_snapshot_id": step["world_snapshot"]["contract_id"],
                    "valid_actions_digest": step["valid_actions_digest"],
                },
                "delete": [],
            },
        )
        transition(
            "selection",
            (plan, action),
            {
                "set": {
                    "decision_receipt_id": step["decision_receipt"]["contract_id"],
                    "proposed_action_occurrence_id": action["occurrence_id"],
                    "proposal_id": step["proposal"]["proposal_id"],
                },
                "delete": [],
            },
        )
        transition(
            "authorization_observation",
            (authorization,),
            {
                "set": {
                    "authorization_witness_id": full["authorization"][
                        "witness_id"
                    ],
                },
                "delete": [],
            },
            metadata={"structural_receipt_authenticates_action": False},
        )
        transition(
            "effect_observation",
            (action, learning),
            {
                "set": {
                    "last_action_occurrence_id": action["occurrence_id"],
                    "post_observation_digest": _canonical_digest(
                        step["post_observation"]
                    ),
                    "step_count": step["step_index"] + 1,
                },
                "delete": [],
            },
        )
        transition(
            "learning_proposal",
            (learning,),
            {
                "set": {
                    "latest_learning_edge_ref": step["learned_edge_ref"],
                },
                "delete": [],
            },
            metadata={"promotion_mutated": False},
        )

    denied_refs: tuple[dict[str, Any], ...] = ()
    denied = semantic["denied_attempt"]
    if denied is not None:
        denied_entity = add_entity(
            "evaluation",
            {
                "action_id": denied["proposal"]["action_id"],
                "executed": False,
                "reason": denied["reason"],
                "valid_actions_digest": denied["valid_actions_digest"],
            },
        )
        denied_refs = (denied_entity,)
        transition(
            "evaluation",
            denied_refs,
            {
                "set": {
                    "denied_action_id": denied["proposal"]["action_id"],
                    "denial_reason": denied["reason"],
                },
                "delete": [],
            },
        )
    status = _cycle_status(semantic["stop_reason"], semantic["success"])
    terminal = add_entity(
        "episode",
        {
            "status": status,
            "step_count": len(steps),
            "stop_reason": semantic["stop_reason"],
            "success": semantic["success"],
        },
    )
    transition(
        "terminal",
        (*denied_refs, terminal),
        {
            "set": {
                "status": status,
                "stop_reason": semantic["stop_reason"],
                "success": semantic["success"],
            },
            "delete": [],
        },
    )
    output = {
        "status": status,
        "step_count": len(steps),
        "stop_reason": semantic["stop_reason"],
        "success": semantic["success"],
    }
    body = {
        "declared_effects": ["environment_step_observed"] if steps else [],
        "entities": entities,
        "events": events,
        "initial_state": initial_state,
        "input_hash": _canonical_digest(identity),
        "limitations": [
            "decision_receipts_are_non_authoritative",
            "mechanism_only",
            "structural_replay_does_not_reexecute_environment",
        ],
        "output_hash": _canonical_digest(output),
        "request_cycle": request_cycle,
        "selected_route": "generic_world_interaction",
        "status": status,
        "terminal_state_hash": events[-1]["state_after_hash"],
    }
    receipt_id = _canonical_id("cycle", body)[0]
    return {
        "action_authorized": False,
        "authoritative": False,
        "contract_type": "CycleReceipt",
        **body,
        "observer_only": True,
        "permission_mutated": False,
        "promotion_mutated": False,
        "receipt_id": receipt_id,
        "schema_version": COGNITIVE_SCHEMA,
        "truth_mutated": False,
    }


def _verify_request(
    semantic: Mapping[str, Any],
    request: Any,
    report: _Report,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if type(request) is not dict:
        report.fail("request_binding", "request_not_an_object")
        return None, None
    required = {
        "goal_ir",
        "environment_seed",
        "policy_seed",
        "step_budget",
        "retain_policy_updates",
        "session_id",
        "policy_memory",
    }
    if not required <= set(request):
        report.fail("request_binding", "request_required_fields_missing")
        return request, None
    expected_goal = _materialize_request_goal(request["goal_ir"], report)
    checks = (
        ("environment_seed", "environment_seed"),
        ("policy_seed", "policy_seed"),
        ("step_budget", "step_budget"),
        ("retain_policy_updates", "retain_policy_updates"),
    )
    for request_name, semantic_name in checks:
        if request.get(request_name) != semantic.get(semantic_name):
            report.fail("request_binding", f"{request_name}_mismatch")
    if (
        type(request.get("session_id")) is not str
        or not request["session_id"].strip()
    ):
        report.fail("request_binding", "session_id_invalid")
    if expected_goal is not None and semantic.get("goal") != expected_goal:
        report.fail("goal_binding", "trace_goal_differs_from_request_goal")
    if semantic.get("memory_before") != request.get("policy_memory"):
        report.fail("memory_binding", "memory_before_differs_from_request")
    if "policy_memory_sha256" in request and request.get(
        "policy_memory_sha256"
    ) != _canonical_digest(request.get("policy_memory")):
        report.fail("request_binding", "request_policy_memory_digest_mismatch")
    return request, expected_goal


def _verify_trace_steps(
    *,
    semantic: Mapping[str, Any],
    lineage_steps: Sequence[Mapping[str, Any]],
    witnessed_steps: Sequence[Mapping[str, Any]],
    verified_memory_before: Mapping[str, Any],
    expected_goal: Mapping[str, Any],
    request: Mapping[str, Any],
    parent_authorizations: Any,
    report: _Report,
) -> None:
    semantic_steps = semantic["steps"]
    if not isinstance(parent_authorizations, Sequence) or isinstance(
        parent_authorizations, (str, bytes)
    ):
        report.fail("authority_binding", "parent_authorizations_not_an_array")
        parent_rows: list[Any] = []
    else:
        parent_rows = list(parent_authorizations)
    if len(parent_rows) != len(semantic_steps):
        report.fail("authority_binding", "parent_authorization_census_mismatch")
    if len(witnessed_steps) != len(semantic_steps):
        report.fail("environment_binding", "environment_step_census_mismatch")

    memory_at_step = copy.deepcopy(dict(verified_memory_before))
    parent_snapshot_id: str | None = None
    for index, (step, full) in enumerate(zip(semantic_steps, lineage_steps)):
        if type(step) is not dict or set(step) != _SEMANTIC_STEP_FIELDS:
            report.fail("trace_schema", f"step_{index}:semantic_fields_mismatch")
            continue
        if type(full) is not dict or set(full) != _LINEAGE_STEP_FIELDS:
            report.fail("trace_schema", f"step_{index}:lineage_fields_mismatch")
            continue
        try:
            reconstructed = _semantic_from_lineage(full)
            if reconstructed != step:
                report.fail(
                    "semantic_lineage",
                    f"step_{index}:semantic_lineage_projection_mismatch",
                )
        except (KeyError, TypeError, ValueError) as exc:
            report.fail(
                "semantic_lineage",
                f"step_{index}:{type(exc).__name__}:{exc}",
            )
        if step.get("step_index") != index:
            report.fail("semantic_lineage", f"step_{index}:index_mismatch")
        if index >= len(witnessed_steps):
            continue
        witnessed = witnessed_steps[index]
        expected_actions = witnessed["actions"]
        valid_digest = _canonical_digest(expected_actions)
        if (
            step.get("pre_observation") != witnessed["observation"]
            or step.get("valid_actions") != expected_actions
            or step.get("valid_actions_digest") != valid_digest
            or step.get("selected_action") != witnessed["action_id"]
            or step.get("post_observation")
            != witnessed["result"].get("observation")
        ):
            report.fail("action_binding", f"step_{index}:parent_action_binding_mismatch")
        expected_step_result = {
            **copy.deepcopy(witnessed["result"]),
            "result_digest": _canonical_digest(witnessed["result"]),
        }
        if step.get("step_result") != expected_step_result:
            report.fail(
                "environment_binding",
                f"step_{index}:step_result_mismatch",
            )
        selected = [
            item
            for item in expected_actions
            if item["action_id"] == witnessed["action_id"]
        ]
        if len(selected) != 1:
            report.fail("action_binding", f"step_{index}:selected_action_not_unique")
            continue
        selected_action = selected[0]
        proposal = step.get("proposal")
        _proposal_identity(proposal, report, index)
        if (
            type(proposal) is not dict
            or proposal.get("action_id") != witnessed["action_id"]
            or proposal.get("observation_digest")
            != _canonical_digest(witnessed["observation"])
            or proposal.get("valid_actions_digest") != valid_digest
        ):
            report.fail("proposal_lineage", f"step_{index}:proposal_input_mismatch")
            continue
        _verify_rule_plan(
            proposal,
            expected_goal,
            witnessed["observation"],
            selected_action,
            memory_at_step,
            report,
            index,
        )
        expected_perception = _expected_perception(
            witnessed["observation"],
            report,
            index,
        )
        if full.get("perception") != expected_perception:
            report.fail("world_lineage", f"step_{index}:perception_mismatch")
        _verify_contract_identity(
            full.get("perception", {}).get("claim"),
            "ClaimEnvelope",
            report,
        )
        expected_records = _expected_decision_records(
            index=index,
            goal=expected_goal,
            perception=expected_perception,
            valid_actions_digest=valid_digest,
            parent_snapshot_id=parent_snapshot_id,
            proposal=proposal,
            selected_action=selected_action,
            step_budget=request["step_budget"],
            session_id=request["session_id"],
        )
        snapshot, envelope, moment, proposal_proof, decision = expected_records
        if full.get("world_snapshot") != snapshot:
            report.fail("world_lineage", f"step_{index}:world_snapshot_mismatch")
        if full.get("cognitive_envelope") != envelope:
            report.fail("world_lineage", f"step_{index}:cognitive_envelope_mismatch")
        if full.get("cognitive_moment") != moment:
            report.fail("world_lineage", f"step_{index}:cognitive_moment_mismatch")
        if full.get("proposal_proof") != proposal_proof:
            report.fail("proposal_lineage", f"step_{index}:proposal_proof_mismatch")
        if full.get("decision_receipt") != decision:
            report.fail("decision_lineage", f"step_{index}:decision_receipt_mismatch")
        for raw, kind in (
            (full.get("world_snapshot"), "WorldSnapshot"),
            (full.get("cognitive_envelope"), "CognitiveEnvelope"),
            (full.get("cognitive_moment"), "CognitiveMoment"),
            (full.get("proposal_proof"), "ProofCandidate"),
            (full.get("decision_receipt"), "DecisionReceipt"),
        ):
            _verify_contract_identity(raw, kind, report)
        parent_snapshot_id = snapshot["contract_id"]

        try:
            expected_authorization = _materialize_authorization(
                parent_rows[index]
            )
            if full.get("authorization") != expected_authorization:
                report.fail(
                    "authority_binding",
                    f"step_{index}:parent_authorization_mismatch",
                )
            if (
                expected_authorization["action_id"] != witnessed["action_id"]
                or expected_authorization["step_index"] != index
                or expected_authorization["granted"] is not True
            ):
                report.fail(
                    "authority_binding",
                    f"step_{index}:authorization_action_or_grant_mismatch",
                )
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            report.fail(
                "authority_binding",
                f"step_{index}:{type(exc).__name__}:{exc}",
            )
        _verify_learning_lineage(
            step=step,
            full=full,
            selected_action=selected_action,
            goal=expected_goal,
            report=report,
            index=index,
        )
        if semantic["retain_policy_updates"] is True:
            learning_proof = full.get("learning_proof")
            if (
                type(learning_proof) is not dict
                or type(learning_proof.get("metadata")) is not dict
            ):
                report.fail(
                    "rule_ir",
                    f"step_{index}:learning_metadata_not_an_object",
                )
                learning_metadata = {}
            else:
                learning_metadata = learning_proof["metadata"]
            memory_at_step = _advance_verified_rule_memory(
                memory_at_step,
                pre_observation=witnessed["observation"],
                post_observation=witnessed["result"]["observation"],
                learning_metadata=learning_metadata,
                selected_action=selected_action,
                goal=expected_goal,
                report=report,
                index=index,
            )

    if (
        semantic["retain_policy_updates"] is True
        and memory_at_step.get("schema_version") == MEMORY_V2_SCHEMA
        and type(semantic.get("memory_after")) is dict
        and memory_at_step.get("rule_records")
        != semantic["memory_after"].get("rule_records")
    ):
        report.fail(
            "rule_ir",
            "retaining_rule_memory_evolution_mismatch",
        )


def verify_capability_trace(
    trace: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    environment_log: Sequence[Mapping[str, Any]],
    parent_authorizations: Sequence[Mapping[str, Any]],
    parent_finish: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify one serialized candidate-C trace against parent-owned witnesses.

    The function never accepts candidate pass flags as evidence.  It returns a
    conjunctive verdict plus per-surface findings so adversarial tests can
    demonstrate which independent binding rejected a caller-resealed forgery.
    """

    report = _Report()
    if type(trace) is not dict:
        report.fail("trace_schema", "trace_not_an_object")
        return report.result()
    try:
        _canonical_json(trace)
    except (TypeError, ValueError) as exc:
        report.fail("trace_schema", f"trace_not_canonical_json:{type(exc).__name__}:{exc}")
        return report.result()
    if set(trace) != _TRACE_FIELDS:
        report.fail("trace_schema", "trace_field_set_mismatch")
    if (
        trace.get("schema_version") != TRACE_SCHEMA
        or trace.get("mechanism_only") is not True
        or trace.get("production_default_on") is not False
        or trace.get("structural_receipt_authenticates_action") is not False
    ):
        report.fail("trace_schema", "trace_fixed_contract_mismatch")
    semantic = trace.get("semantic_trace")
    lineage_steps = trace.get("lineage_steps")
    if type(semantic) is not dict or set(semantic) != _SEMANTIC_FIELDS:
        report.fail("trace_schema", "semantic_trace_fields_mismatch")
        return report.result()
    if type(lineage_steps) is not list:
        report.fail("trace_schema", "lineage_steps_not_an_array")
        return report.result()
    steps = semantic.get("steps")
    if type(steps) is not list or len(steps) != len(lineage_steps):
        report.fail("semantic_lineage", "semantic_lineage_step_census_mismatch")
        return report.result()
    if trace.get("semantic_trace_digest") != _canonical_digest(semantic):
        report.fail("semantic_digest", "semantic_trace_digest_mismatch")
    if (
        type(semantic.get("environment_seed")) is not int
        or type(semantic.get("policy_seed")) is not int
        or type(semantic.get("step_budget")) is not int
        or not 1 <= semantic["step_budget"] <= 10_000
        or type(semantic.get("retain_policy_updates")) is not bool
        or type(semantic.get("stop_reason")) is not str
        or not semantic["stop_reason"]
        or type(semantic.get("success")) is not bool
    ):
        report.fail("trace_schema", "semantic_scalar_contract_mismatch")

    checked_request, expected_goal = _verify_request(semantic, request, report)
    _verify_contract_identity(semantic.get("goal"), "GoalIR", report)
    memory_before = _verify_memory(
        semantic.get("memory_before"),
        report,
        "memory_before",
    )
    memory_after = _verify_memory(
        semantic.get("memory_after"),
        report,
        "memory_after",
    )
    if (
        semantic.get("retain_policy_updates") is False
        and semantic.get("memory_after") != semantic.get("memory_before")
    ):
        report.fail("memory_binding", "nonretaining_trace_mutated_memory")
    if (
        memory_before is not None
        and memory_after is not None
        and semantic.get("retain_policy_updates") is True
        and memory_before.get("schema_version") != memory_after.get("schema_version")
    ):
        report.fail("memory_binding", "retaining_memory_schema_changed")
    _verify_memory_evolution(
        semantic=semantic,
        lineage_steps=lineage_steps,
        report=report,
    )

    witnessed_steps = _verify_environment_log(
        semantic,
        environment_log,
        report,
    )
    if checked_request is not None and expected_goal is not None:
        _verify_trace_steps(
            semantic=semantic,
            lineage_steps=lineage_steps,
            witnessed_steps=witnessed_steps,
            verified_memory_before=(
                memory_before if memory_before is not None else {}
            ),
            expected_goal=expected_goal,
            request=checked_request,
            parent_authorizations=parent_authorizations,
            report=report,
        )
    if type(parent_finish) is not dict:
        report.fail("authority_binding", "parent_finish_not_an_object")
    elif trace.get("authority_finish") != parent_finish:
        report.fail("authority_binding", "parent_finish_mismatch")

    if checked_request is not None:
        try:
            expected_cycle = _build_cycle_receipt(
                semantic,
                lineage_steps,
                checked_request,
            )
            if trace.get("cycle_receipt") != expected_cycle:
                report.fail(
                    "cycle_receipt",
                    "retain_aware_cycle_receipt_reconstruction_mismatch",
                )
        except (KeyError, TypeError, ValueError) as exc:
            report.fail(
                "cycle_receipt",
                f"cycle_reconstruction:{type(exc).__name__}:{exc}",
            )
    return report.result()


def reseal_worker_owned_semantic_digest(
    trace: Mapping[str, Any],
) -> dict[str, Any]:
    """Test seam: recompute only the caller-owned semantic trace digest.

    This deliberately cannot reseal parent environment, request, authority, or
    cycle bindings.  Adversarial tests use it to prove that changing a value
    and recomputing the obvious hash still fails independent verification.
    """

    if type(trace) is not dict or type(trace.get("semantic_trace")) is not dict:
        raise TypeError("trace must contain a semantic_trace object")
    output = copy.deepcopy(dict(trace))
    output["semantic_trace_digest"] = _canonical_digest(
        output["semantic_trace"]
    )
    return output


def verify_forgery_rejection(
    baseline_trace: Mapping[str, Any],
    forged_trace: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    environment_log: Sequence[Mapping[str, Any]],
    parent_authorizations: Sequence[Mapping[str, Any]],
    parent_finish: Mapping[str, Any],
) -> dict[str, Any]:
    """Return an explicit baseline-pass/forgery-rejected adversarial receipt."""

    baseline = verify_capability_trace(
        baseline_trace,
        request=request,
        environment_log=environment_log,
        parent_authorizations=parent_authorizations,
        parent_finish=parent_finish,
    )
    forged = verify_capability_trace(
        forged_trace,
        request=request,
        environment_log=environment_log,
        parent_authorizations=parent_authorizations,
        parent_finish=parent_finish,
    )
    return {
        "passed": baseline["passed"] is True and forged["passed"] is False,
        "baseline": baseline,
        "forged": forged,
        "caller_digest_reseal_is_not_authority": True,
    }


__all__ = [
    "reseal_worker_owned_semantic_digest",
    "verify_capability_trace",
    "verify_forgery_rejection",
]
