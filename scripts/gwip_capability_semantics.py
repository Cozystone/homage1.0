"""Evaluator-owned semantic verification for the GWIP capability pilot.

This module deliberately does not import the capability candidate, its policy
memory class, or any candidate verifier.  Its inputs are evaluator-owned
observations/actions plus candidate-carried JSON evidence.  Consequently every
digest, feature edge, rule execution, rule chronology, counterfactual score,
and transfer-memory binding below is reconstructed on the evaluator side.

The public functions return plain JSON-shaped dictionaries.  Parsers raise
``SemanticEvidenceError`` for malformed evidence; the composite verification
functions catch those errors and return fail-closed findings.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import json
from typing import Any

from packages.cognitive_core.canonical import (
    canonical_digest as _canonical_digest,
    canonical_id as _canonical_id,
    canonical_json as _canonical_json,
)


RULE_IR_SCHEMA = "atanor.gwip-feature-rule.v1"
MEMORY_SCHEMA = "atanor.gwip-policy-memory.v2"
LEDGER_SCHEMA = "atanor.gwip-capability-edge-ledger.v1"
RULE_EVENT_SCHEMA = "atanor.gwip-capability-rule-events.v1"
SUPPORT_BINDING_SCHEMA = "atanor.gwip-capability-support-binding.v1"
TARGET_BINDING_SCHEMA = "atanor.gwip-capability-target-binding.v1"

MAX_FEATURE_LEAVES = 64
MAX_RULE_AST_DEPTH = 6
COEFFICIENT_MINIMUM = -6
COEFFICIENT_MAXIMUM = 6
MINIMUM_DISTINCT_INPUTS = 3
COUNTERFACTUAL_MODULUS = 19

_MEMORY_FIELDS = {
    "action_sets",
    "attempts",
    "concepts_by_state",
    "feature_edges",
    "rule_records",
    "schema_version",
    "semantic_attempts",
    "target_state_digest",
    "transitions",
}
_RULE_FIELDS = {
    "schema_version",
    "action_signature",
    "input_path",
    "output_path",
    "context_path",
    "expression",
    "support_edge_refs",
    "hypothesis",
}
_RULE_RECORD_FIELDS = {
    "confirmation_edge_refs",
    "emitted_ordinal",
    "rule",
    "rule_key",
    "status",
}
class SemanticEvidenceError(ValueError):
    """Raised when untrusted semantic evidence violates the frozen contract."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the repository's canonical JSON encoding as UTF-8 bytes."""

    return _canonical_json(value).encode("utf-8")


def digest(value: Any) -> str:
    """Return a canonical SHA-256 digest without trusting a supplied digest."""

    return _canonical_digest(value)


def _plain(value: Any) -> Any:
    """Detach and normalize one JSON-shaped value using the canonical primitive."""

    try:
        return json.loads(_canonical_json(value))
    except (TypeError, ValueError) as exc:
        raise SemanticEvidenceError("value is not canonical JSON") from exc


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _pointer_tokens(path: Any) -> tuple[str, ...]:
    if not isinstance(path, str) or not path.startswith("/") or path == "/":
        raise SemanticEvidenceError("JSON pointer must be a non-root absolute path")
    tokens: list[str] = []
    for encoded in path[1:].split("/"):
        decoded: list[str] = []
        cursor = 0
        while cursor < len(encoded):
            if encoded[cursor] != "~":
                decoded.append(encoded[cursor])
                cursor += 1
                continue
            if cursor + 1 >= len(encoded) or encoded[cursor + 1] not in {"0", "1"}:
                raise SemanticEvidenceError("JSON pointer has a non-canonical escape")
            decoded.append("~" if encoded[cursor + 1] == "0" else "/")
            cursor += 2
        token = "".join(decoded)
        if _pointer_escape(token) != encoded:
            raise SemanticEvidenceError("JSON pointer is not canonically encoded")
        if token.isdigit() and len(token) > 1 and token.startswith("0"):
            raise SemanticEvidenceError("JSON pointer numeric token is not canonical")
        tokens.append(token)
    return tuple(tokens)


def _require_feature_path(path: Any) -> str:
    tokens = _pointer_tokens(path)
    if not tokens or tokens[0] != "features":
        raise SemanticEvidenceError("rule path is outside evaluator-owned /features")
    return str(path)


def _pointer_get(value: Mapping[str, Any], path: str) -> Any:
    current: Any = value
    for token in _pointer_tokens(path):
        if isinstance(current, Mapping):
            if token not in current:
                raise SemanticEvidenceError(f"JSON pointer is absent: {path}")
            current = current[token]
        elif isinstance(current, (list, tuple)):
            if not token.isdigit():
                raise SemanticEvidenceError(f"JSON pointer does not index a sequence: {path}")
            index = int(token)
            if index >= len(current):
                raise SemanticEvidenceError(f"JSON pointer index is out of range: {path}")
            current = current[index]
        else:
            raise SemanticEvidenceError(f"JSON pointer crosses a scalar: {path}")
    return current


def strict_feature_projection(
    observation: Mapping[str, Any],
    *,
    maximum_leaves: int = MAX_FEATURE_LEAVES,
) -> dict[str, int]:
    """Project exact integer leaves strictly below top-level ``/features``.

    Integers elsewhere in the observation, booleans, floats, strings, and
    caller status/truth fields are never eligible.  This is intentionally
    stricter than asking the candidate which projection root it used.
    """

    if not isinstance(observation, Mapping):
        raise SemanticEvidenceError("observation must be a mapping")
    raw = _plain(observation)
    if "features" not in raw:
        raise SemanticEvidenceError("final observation has no /features root")
    root = raw["features"]
    if not isinstance(root, (Mapping, list, tuple)):
        raise SemanticEvidenceError("/features must contain structured JSON")
    if type(maximum_leaves) is not int or maximum_leaves <= 0:
        raise SemanticEvidenceError("maximum_leaves must be a positive exact integer")

    leaves: dict[str, int] = {}

    def visit(item: Any, path: str) -> None:
        if type(item) is int:
            if len(leaves) >= maximum_leaves:
                raise SemanticEvidenceError("numeric feature projection exceeds its bound")
            leaves[path] = item
            return
        if isinstance(item, Mapping):
            for key in sorted(item):
                if not isinstance(key, str) or not key:
                    raise SemanticEvidenceError("feature mapping keys must be non-empty strings")
                visit(item[key], f"{path}/{_pointer_escape(key)}")
            return
        if isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                visit(child, f"{path}/{index}")

    visit(root, "/features")
    return dict(sorted(leaves.items()))


def payload_signature(payload: Mapping[str, Any]) -> str:
    """Digest the complete, non-empty evaluator-owned action payload."""

    if not isinstance(payload, Mapping) or not payload:
        raise SemanticEvidenceError("semantic action payload must be a non-empty mapping")
    raw = _plain(payload)
    if not raw:
        raise SemanticEvidenceError("semantic action payload must not canonicalize to empty")
    return digest(raw)


def _parse_expression(value: Any, *, depth: int = 1) -> dict[str, Any]:
    if depth > MAX_RULE_AST_DEPTH:
        raise SemanticEvidenceError("rule expression exceeds maximum AST depth")
    if not isinstance(value, Mapping):
        raise SemanticEvidenceError("rule expression must be a mapping")
    raw = _plain(value)
    op = raw.get("op")
    if op in {"var", "copy"}:
        if set(raw) != {"op", "path"}:
            raise SemanticEvidenceError(f"{op} expression fields mismatch")
        raw["path"] = _require_feature_path(raw["path"])
        return raw
    if op == "const":
        if set(raw) != {"op", "value"} or type(raw["value"]) is not int:
            raise SemanticEvidenceError("const expression requires one exact integer")
        return raw
    if op in {"add", "mul", "mod"}:
        if set(raw) != {"args", "op"}:
            raise SemanticEvidenceError(f"{op} expression fields mismatch")
        args = raw["args"]
        if not isinstance(args, list) or len(args) != 2:
            raise SemanticEvidenceError(f"{op} expression requires exactly two args")
        return {
            "op": op,
            "args": [
                _parse_expression(args[0], depth=depth + 1),
                _parse_expression(args[1], depth=depth + 1),
            ],
        }
    raise SemanticEvidenceError("unsupported rule expression operator")


def parse_rule_ir(value: Mapping[str, Any]) -> dict[str, Any]:
    """Parse the exact frozen Rule IR without candidate code."""

    if not isinstance(value, Mapping):
        raise SemanticEvidenceError("rule IR must be a mapping")
    raw = _plain(value)
    if set(raw) != _RULE_FIELDS:
        raise SemanticEvidenceError("rule IR fields mismatch")
    if raw["schema_version"] != RULE_IR_SCHEMA:
        raise SemanticEvidenceError("rule IR schema mismatch")
    if not _is_sha256(raw["action_signature"]):
        raise SemanticEvidenceError("rule action signature is not lowercase SHA-256")
    for field in ("input_path", "output_path", "context_path"):
        raw[field] = _require_feature_path(raw[field])
    if raw["context_path"] in {raw["input_path"], raw["output_path"]}:
        raise SemanticEvidenceError("context path must be distinct from input/output")
    if raw["hypothesis"] is not True:
        raise SemanticEvidenceError("rule must remain explicitly hypothetical")
    refs = raw["support_edge_refs"]
    if (
        not isinstance(refs, list)
        or len(refs) < MINIMUM_DISTINCT_INPUTS
        or len(refs) != len(set(refs))
        or any(not isinstance(item, str) or not item for item in refs)
        or refs != sorted(refs)
    ):
        raise SemanticEvidenceError("support edge refs are invalid or non-canonical")
    raw["expression"] = _parse_expression(raw["expression"])
    return raw


def _evaluate_expression(expression: Mapping[str, Any], projection: Mapping[str, int]) -> int:
    op = expression["op"]
    if op in {"var", "copy"}:
        value = projection.get(expression["path"])
        if type(value) is not int:
            raise SemanticEvidenceError("rule variable is absent or not an exact integer")
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
        raise SemanticEvidenceError("modulus must be greater than one")
    return left % right


def execute_rule_ir(
    rule: Mapping[str, Any],
    projection: Mapping[str, int],
) -> dict[str, int]:
    """Execute parsed Rule IR over an evaluator-owned strict projection."""

    normalized = parse_rule_ir(rule)
    if not isinstance(projection, Mapping):
        raise SemanticEvidenceError("feature projection must be a mapping")
    features = dict(projection)
    if any(
        not isinstance(path, str)
        or not path.startswith("/features/")
        or type(value) is not int
        for path, value in features.items()
    ):
        raise SemanticEvidenceError("projection contains a non-feature or noninteger leaf")
    for path in (
        normalized["input_path"],
        normalized["output_path"],
        normalized["context_path"],
    ):
        if type(features.get(path)) is not int:
            raise SemanticEvidenceError("rule path is absent from strict projection")
    result = dict(features)
    result[normalized["output_path"]] = _evaluate_expression(
        normalized["expression"], features
    )
    return dict(sorted(result.items()))


def affine_coefficients(rule: Mapping[str, Any]) -> tuple[int, int]:
    """Extract ``a,b`` only from the exact frozen affine/mod expression."""

    normalized = parse_rule_ir(rule)
    expression = normalized["expression"]
    expected_input = normalized["input_path"]
    expected_context = normalized["context_path"]
    try:
        if expression["op"] != "mod":
            raise SemanticEvidenceError("rule expression is not outer mod")
        numerator, modulus = expression["args"]
        if modulus != {"op": "var", "path": expected_context}:
            raise SemanticEvidenceError("rule modulus is not its declared context path")
        if numerator["op"] != "add":
            raise SemanticEvidenceError("rule numerator is not affine add")
        product, offset = numerator["args"]
        if product["op"] != "mul":
            raise SemanticEvidenceError("rule numerator has no affine multiply")
        variable, multiplier = product["args"]
        if variable != {"op": "var", "path": expected_input}:
            raise SemanticEvidenceError("rule multiply does not use declared input")
        if multiplier.get("op") != "const" or set(multiplier) != {"op", "value"}:
            raise SemanticEvidenceError("rule multiplier is not an exact const")
        if offset.get("op") != "const" or set(offset) != {"op", "value"}:
            raise SemanticEvidenceError("rule offset is not an exact const")
        a, b = multiplier["value"], offset["value"]
    except (KeyError, TypeError) as exc:
        raise SemanticEvidenceError("malformed affine expression") from exc
    if (
        type(a) is not int
        or type(b) is not int
        or not COEFFICIENT_MINIMUM <= a <= COEFFICIENT_MAXIMUM
        or not COEFFICIENT_MINIMUM <= b <= COEFFICIENT_MAXIMUM
    ):
        raise SemanticEvidenceError("affine coefficients exceed frozen search bounds")
    return a, b


def _affine_expression(
    input_path: str,
    context_path: str,
    multiplier: int,
    offset: int,
) -> dict[str, Any]:
    return {
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
    }


def _selected_payload(step: Mapping[str, Any]) -> tuple[str, dict[str, Any], list[str]]:
    action_id = step.get("action_id")
    if action_id is None:
        action_id = step.get("selected_action")
    if not isinstance(action_id, str) or not action_id:
        raise SemanticEvidenceError("evaluator step has no selected action ID")

    actions = step.get("valid_actions")
    valid_ids: list[str] = []
    payload_from_set: dict[str, Any] | None = None
    if actions is not None:
        if not isinstance(actions, list):
            raise SemanticEvidenceError("valid_actions must be a list")
        matches: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for raw_action in actions:
            if not isinstance(raw_action, Mapping):
                raise SemanticEvidenceError("valid action must be a mapping")
            item = _plain(raw_action)
            if set(item) != {"action_id", "payload"}:
                raise SemanticEvidenceError("valid action fields mismatch")
            item_id = item["action_id"]
            if not isinstance(item_id, str) or not item_id or item_id in seen_ids:
                raise SemanticEvidenceError("valid action IDs are invalid or duplicated")
            seen_ids.add(item_id)
            valid_ids.append(item_id)
            if item_id == action_id:
                matches.append(item)
        if len(matches) != 1:
            raise SemanticEvidenceError("selected action is not unique in actual valid set")
        payload_from_set = matches[0]["payload"]

    supplied_payload = step.get("action_payload")
    if payload_from_set is None:
        if not isinstance(supplied_payload, Mapping):
            raise SemanticEvidenceError("evaluator step has no bound action payload")
        payload = _plain(supplied_payload)
    else:
        payload = _plain(payload_from_set)
        if supplied_payload is not None and _plain(supplied_payload) != payload:
            raise SemanticEvidenceError("supplied payload disagrees with actual valid action")
    payload_signature(payload)
    return action_id, payload, sorted(valid_ids)


def _observation_field(step: Mapping[str, Any], primary: str, alternate: str) -> dict[str, Any]:
    primary_value = step.get(primary)
    alternate_value = step.get(alternate)
    if primary_value is not None and alternate_value is not None:
        if _plain(primary_value) != _plain(alternate_value):
            raise SemanticEvidenceError(f"{primary} and {alternate} disagree")
    value = primary_value if primary_value is not None else alternate_value
    if not isinstance(value, Mapping):
        raise SemanticEvidenceError(f"evaluator step lacks {primary}")
    return _plain(value)


def normalize_evaluator_step(
    value: Mapping[str, Any],
    *,
    ordinal: int,
    default_episode_ref: str = "episode:0",
) -> dict[str, Any]:
    """Normalize one evaluator-owned action record, never candidate metadata."""

    if not isinstance(value, Mapping):
        raise SemanticEvidenceError("evaluator step must be a mapping")
    raw = _plain(value)
    before = _observation_field(raw, "before_observation", "pre_observation")
    after = _observation_field(raw, "after_observation", "post_observation")
    action_id, payload, valid_ids = _selected_payload(raw)
    step_index = raw.get("step_index", ordinal)
    if type(step_index) is not int or step_index < 0:
        raise SemanticEvidenceError("step_index must be a nonnegative exact integer")
    episode_ref = raw.get("episode_ref", default_episode_ref)
    if not isinstance(episode_ref, str) or not episode_ref:
        raise SemanticEvidenceError("episode_ref must be non-empty")
    success = raw.get("success")
    if success is not None and type(success) is not bool:
        raise SemanticEvidenceError("success must be an exact boolean when supplied")
    return {
        "action_id": action_id,
        "action_payload": payload,
        "after_observation": after,
        "before_observation": before,
        "episode_ref": episode_ref,
        "learned_edge_ref": raw.get("learned_edge_ref"),
        "step_index": step_index,
        "success": success,
        "valid_action_ids": valid_ids,
    }


def reconstruct_edge_ledger(
    steps: Sequence[Mapping[str, Any]],
    *,
    start_ordinal: int = 0,
    default_episode_ref: str = "episode:0",
) -> dict[str, Any]:
    """Rebuild typed edges solely from actual observations and valid actions."""

    if isinstance(steps, (str, bytes)) or not isinstance(steps, Sequence):
        raise SemanticEvidenceError("steps must be a sequence")
    if type(start_ordinal) is not int or start_ordinal < 0:
        raise SemanticEvidenceError("start_ordinal must be nonnegative")
    rows: list[dict[str, Any]] = []
    prior_by_episode: dict[str, dict[str, Any]] = {}
    expected_step_by_episode: dict[str, int] = {}
    for local_index, step in enumerate(steps):
        normalized = normalize_evaluator_step(
            step,
            ordinal=local_index,
            default_episode_ref=default_episode_ref,
        )
        episode_ref = normalized["episode_ref"]
        expected_index = expected_step_by_episode.get(episode_ref, 0)
        if normalized["step_index"] != expected_index:
            raise SemanticEvidenceError("episode step indexes are not contiguous")
        prior = prior_by_episode.get(episode_ref)
        if (
            prior is not None
            and prior["after_observation"] != normalized["before_observation"]
        ):
            raise SemanticEvidenceError("actual observations do not form an episode chain")
        before_digest = digest(normalized["before_observation"])
        after_digest = digest(normalized["after_observation"])
        edge_ref = _canonical_id(
            "transition_edge",
            {
                "action_id": normalized["action_id"],
                "from": before_digest,
                "to": after_digest,
            },
        )[0]
        supplied_ref = normalized["learned_edge_ref"]
        if supplied_ref is not None and supplied_ref != edge_ref:
            raise SemanticEvidenceError("candidate learned_edge_ref is not reconstructed")
        row = {
            "action_id": normalized["action_id"],
            "action_payload": normalized["action_payload"],
            "action_signature": payload_signature(normalized["action_payload"]),
            "after": strict_feature_projection(normalized["after_observation"]),
            "after_observation": normalized["after_observation"],
            "after_observation_digest": after_digest,
            "before": strict_feature_projection(normalized["before_observation"]),
            "before_observation": normalized["before_observation"],
            "before_observation_digest": before_digest,
            "edge_ref": edge_ref,
            "episode_ref": episode_ref,
            "ordinal": start_ordinal + local_index,
            "step_index": normalized["step_index"],
            "success": normalized["success"],
            "valid_action_ids": normalized["valid_action_ids"],
        }
        rows.append(row)
        prior_by_episode[episode_ref] = normalized
        expected_step_by_episode[episode_ref] = expected_index + 1
    body = {"rows": rows, "schema_version": LEDGER_SCHEMA}
    return {**body, "ledger_digest": digest(body)}


def _ledger_rows(ledger: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(ledger, Mapping):
        raw = _plain(ledger)
        if raw.get("schema_version") != LEDGER_SCHEMA or not isinstance(raw.get("rows"), list):
            raise SemanticEvidenceError("edge ledger schema mismatch")
        body = {"rows": raw["rows"], "schema_version": LEDGER_SCHEMA}
        if raw.get("ledger_digest") != digest(body):
            raise SemanticEvidenceError("edge ledger digest mismatch")
        rows = raw["rows"]
    elif isinstance(ledger, Sequence) and not isinstance(ledger, (str, bytes)):
        rows = [_plain(item) for item in ledger]
    else:
        raise SemanticEvidenceError("edge ledger must be a ledger or row sequence")
    ordinals = [row.get("ordinal") for row in rows]
    if ordinals != list(range(len(rows))):
        raise SemanticEvidenceError("edge ledger ordinals must start at zero and be contiguous")
    return rows


def _feature_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated action events exactly as candidate feature memory does."""

    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for action_row in rows:
        edge_ref = action_row["edge_ref"]
        if edge_ref in seen:
            continue
        seen.add(edge_ref)
        row = _plain(action_row)
        row["action_ordinal"] = action_row["ordinal"]
        row["ordinal"] = len(output)
        output.append(row)
    return output


def _rule_key(rule: Mapping[str, Any]) -> str:
    raw = parse_rule_ir(rule)
    raw.pop("support_edge_refs")
    return digest(raw)


def verify_rule_support(
    rule: Mapping[str, Any],
    ledger: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    emission_ordinal: int | None = None,
) -> dict[str, Any]:
    """Independently verify support fit and frozen bounded-search uniqueness."""

    findings: list[str] = []
    coefficient: list[int] | None = None
    expected_rule: dict[str, Any] | None = None
    try:
        normalized = parse_rule_ir(rule)
        action_rows = _ledger_rows(ledger)
        rows = _feature_rows(action_rows)
        by_ref = {row["edge_ref"]: row for row in rows}
        if emission_ordinal is None:
            support_ordinals = [
                by_ref[edge_ref]["ordinal"]
                for edge_ref in normalized["support_edge_refs"]
                if edge_ref in by_ref
            ]
            emission_ordinal = max(support_ordinals, default=-1) + 1
        if (
            type(emission_ordinal) is not int
            or emission_ordinal < MINIMUM_DISTINCT_INPUTS
            or emission_ordinal > len(rows)
        ):
            findings.append("emission_ordinal_invalid")
            emission_ordinal = max(0, min(len(rows), int(emission_ordinal or 0)))
        preceding = [
            row
            for row in rows
            if row["ordinal"] < emission_ordinal
            and row["action_signature"] == normalized["action_signature"]
        ]
        expected_refs = sorted(row["edge_ref"] for row in preceding)
        if normalized["support_edge_refs"] != expected_refs:
            findings.append("support_refs_not_complete_pre_emission_signature_ledger")
        support: list[dict[str, Any]] = []
        for edge_ref in normalized["support_edge_refs"]:
            edge = by_ref.get(edge_ref)
            if edge is None:
                findings.append("support_edge_absent_from_evaluator_ledger")
                continue
            if edge["ordinal"] >= emission_ordinal:
                findings.append("support_edge_does_not_precede_emission")
            if edge["action_signature"] != normalized["action_signature"]:
                findings.append("support_action_signature_mismatch")
            support.append(edge)
        input_path = normalized["input_path"]
        output_path = normalized["output_path"]
        context_path = normalized["context_path"]
        for edge in support:
            for projection_name in ("before", "after"):
                projection = edge[projection_name]
                for path in (input_path, output_path, context_path):
                    if type(projection.get(path)) is not int:
                        findings.append(f"support_{projection_name}_path_missing")
            if findings:
                continue
            if edge["before"][context_path] != edge["after"][context_path]:
                findings.append("support_context_changed")
            try:
                predicted = execute_rule_ir(normalized, edge["before"])
            except SemanticEvidenceError:
                findings.append("support_rule_execution_failed")
            else:
                if predicted[output_path] != edge["after"][output_path]:
                    findings.append("support_rule_does_not_fit")
        distinct_inputs = {
            edge["before"].get(input_path)
            for edge in support
            if type(edge["before"].get(input_path)) is int
        }
        if len(distinct_inputs) < MINIMUM_DISTINCT_INPUTS:
            findings.append("fewer_than_three_distinct_support_inputs")
        moduli = {
            edge["before"].get(context_path)
            for edge in support
            if type(edge["before"].get(context_path)) is int
            and edge["before"].get(context_path) == edge["after"].get(context_path)
            and edge["before"].get(context_path) > 1
        }
        if len(moduli) != 1:
            findings.append("support_modulus_not_unique_and_stable")
        if not any(
            edge["before"].get(output_path) != edge["after"].get(output_path)
            for edge in support
        ):
            findings.append("support_output_never_changes")

        fitting: list[tuple[int, int, tuple[int, int]]] = []
        if len(moduli) == 1 and support:
            modulus = next(iter(moduli))
            for a in range(COEFFICIENT_MINIMUM, COEFFICIENT_MAXIMUM + 1):
                for b in range(COEFFICIENT_MINIMUM, COEFFICIENT_MAXIMUM + 1):
                    if all(
                        type(edge["before"].get(input_path)) is int
                        and type(edge["after"].get(output_path)) is int
                        and (a * edge["before"][input_path] + b) % modulus
                        == edge["after"][output_path]
                        for edge in support
                    ):
                        fitting.append((a, b, (a % modulus, b % modulus)))
            identities = {item[2] for item in fitting}
            if not fitting:
                findings.append("no_bounded_affine_prediction_fits")
            elif len(identities) != 1:
                findings.append("bounded_affine_prediction_not_unique")
            else:
                a, b, _identity = min(
                    fitting,
                    key=lambda item: (
                        abs(item[0]) + abs(item[1]),
                        abs(item[0]),
                        abs(item[1]),
                        item[0],
                        item[1],
                    ),
                )
                coefficient = [a, b]
                expected_rule = {
                    **normalized,
                    "expression": _affine_expression(
                        input_path, context_path, a, b
                    ),
                }
                if normalized != expected_rule:
                    findings.append("rule_is_not_canonical_unique_bounded_prediction")
                try:
                    supplied = affine_coefficients(normalized)
                except SemanticEvidenceError:
                    findings.append("rule_expression_is_not_frozen_affine_shape")
                else:
                    if supplied != (a, b):
                        findings.append("rule_coefficients_do_not_match_unique_prediction")
    except (KeyError, TypeError, SemanticEvidenceError) as exc:
        findings.append(f"semantic_error:{type(exc).__name__}:{exc}")
        emission_ordinal = None
        distinct_inputs = set()
    return {
        "coefficient": coefficient,
        "distinct_input_count": len(distinct_inputs),
        "emission_ordinal": emission_ordinal,
        "expected_rule": expected_rule,
        "findings": sorted(set(findings)),
        "passed": not findings,
    }


def verify_rule_record(
    record: Mapping[str, Any],
    ledger: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Verify a final record, including prequential confirmation and invalidation."""

    findings: list[str] = []
    support_report: dict[str, Any] | None = None
    try:
        if not isinstance(record, Mapping):
            raise SemanticEvidenceError("rule record must be a mapping")
        raw = _plain(record)
        if set(raw) != _RULE_RECORD_FIELDS:
            raise SemanticEvidenceError("rule record fields mismatch")
        rule = parse_rule_ir(raw["rule"])
        if raw["rule_key"] != _rule_key(rule):
            findings.append("rule_key_not_reconstructed")
        if raw["status"] not in {"provisional", "usable"}:
            findings.append("rule_status_invalid")
        emitted = raw["emitted_ordinal"]
        support_report = verify_rule_support(rule, ledger, emission_ordinal=emitted)
        findings.extend(support_report["findings"])
        rows = _ledger_rows(ledger)
        rows = _feature_rows(rows)
        later = [
            row
            for row in rows
            if row["ordinal"] >= emitted
            and row["action_signature"] == rule["action_signature"]
        ]
        matching_later: list[dict[str, Any]] = []
        contradiction_ordinals: list[int] = []
        for edge in later:
            try:
                predicted = execute_rule_ir(rule, edge["before"])
                matches = (
                    predicted[rule["output_path"]]
                    == edge["after"][rule["output_path"]]
                )
            except (KeyError, SemanticEvidenceError):
                matches = False
            if matches:
                matching_later.append(edge)
            else:
                contradiction_ordinals.append(edge["ordinal"])
        if contradiction_ordinals:
            findings.append("later_contradiction_was_not_invalidated")
        expected_confirmation = (
            [later[0]["edge_ref"]]
            if later and not contradiction_ordinals
            else []
        )
        expected_status = (
            "usable" if later and not contradiction_ordinals else "provisional"
        )
        confirmations = raw["confirmation_edge_refs"]
        if (
            not isinstance(confirmations, list)
            or confirmations != expected_confirmation
            or len(confirmations) != len(set(confirmations))
        ):
            findings.append("confirmation_not_first_distinct_later_edge")
        if raw["status"] != expected_status:
            findings.append("status_not_reconstructed_from_chronology")
        if set(confirmations) & set(rule["support_edge_refs"]):
            findings.append("confirmation_reuses_fitting_support")
        if raw["status"] == "usable" and not matching_later:
            findings.append("usable_rule_has_no_later_confirmation")
    except (KeyError, TypeError, SemanticEvidenceError) as exc:
        findings.append(f"semantic_error:{type(exc).__name__}:{exc}")
        contradiction_ordinals = []
        matching_later = []
    return {
        "confirmation_count": len(matching_later),
        "contradiction_ordinals": contradiction_ordinals,
        "findings": sorted(set(findings)),
        "passed": not findings,
        "support": support_report,
    }


def _trace_projection(trace: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(trace, Mapping):
        raise SemanticEvidenceError("trace must be a mapping")
    semantic = trace.get("semantic_trace")
    if semantic is not None:
        if not isinstance(semantic, Mapping):
            raise SemanticEvidenceError("semantic_trace must be a mapping")
        return semantic
    return trace


def evaluator_steps_from_trace(
    trace: Mapping[str, Any],
    *,
    episode_ref: str,
) -> list[dict[str, Any]]:
    """Extract evaluator-owned step inputs from a serialized InteractiveTrace."""

    semantic = _trace_projection(trace)
    steps = semantic.get("steps")
    if not isinstance(steps, list):
        raise SemanticEvidenceError("trace has no semantic step list")
    output: list[dict[str, Any]] = []
    for expected_index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            raise SemanticEvidenceError("trace step must be a mapping")
        raw = _plain(step)
        result = raw.get("step_result")
        if not isinstance(result, Mapping):
            raise SemanticEvidenceError("trace step_result is missing")
        if raw.get("post_observation") != result.get("observation"):
            raise SemanticEvidenceError("post_observation disagrees with step_result")
        output.append(
            {
                "before_observation": raw.get("pre_observation"),
                "after_observation": result.get("observation"),
                "episode_ref": episode_ref,
                "learned_edge_ref": raw.get("learned_edge_ref"),
                "selected_action": raw.get("selected_action"),
                "step_index": raw.get("step_index", expected_index),
                "success": result.get("success"),
                "valid_actions": raw.get("valid_actions"),
            }
        )
    return output


def _metadata_rules(container: Any, path: str) -> list[Mapping[str, Any]] | None:
    current = container
    for token in path.split("."):
        if not isinstance(current, Mapping) or token not in current:
            return None
        current = current[token]
    if current is None:
        return None
    if not isinstance(current, list):
        raise SemanticEvidenceError(f"{path} must be a rule list")
    return current


def extract_candidate_rule_events(
    traces: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Extract candidate-carried Rule IR at proposal/learning chronology points."""

    sequence = [traces] if isinstance(traces, Mapping) else list(traces)
    findings: list[str] = []
    events: list[dict[str, Any]] = []
    edge_count = 0
    sources = (
        ("proposal", "proposal.deliberator_proof.transition_rule_hypotheses"),
        ("proposal_proof", "proposal_proof.metadata.transition_rule_hypotheses"),
        ("learning", "learning_proof.metadata.transition_rule_hypotheses"),
    )
    for trace_index, trace in enumerate(sequence):
        try:
            semantic = _trace_projection(trace)
            steps = semantic.get("steps")
            if not isinstance(steps, list):
                raise SemanticEvidenceError("trace has no semantic step list")
            for step_index, step in enumerate(steps):
                for phase, path in sources[:2]:
                    raw_rules = _metadata_rules(step, path)
                    if raw_rules is None:
                        continue
                    parsed: list[dict[str, Any]] = []
                    seen: set[str] = set()
                    for raw_rule in raw_rules:
                        rule = parse_rule_ir(raw_rule)
                        rule_digest = digest(rule)
                        if rule_digest in seen:
                            findings.append(
                                f"trace_{trace_index}_step_{step_index}_{phase}:duplicate_rule"
                            )
                        seen.add(rule_digest)
                        parsed.append(rule)
                    events.append(
                        {
                            "action_count": edge_count,
                            "phase": phase,
                            "rule_digests": sorted(seen),
                            "rules": sorted(parsed, key=digest),
                            "step_index": step_index,
                            "trace_index": trace_index,
                        }
                    )
                edge_count += 1
                phase, path = sources[2]
                raw_rules = _metadata_rules(step, path)
                if raw_rules is not None:
                    parsed = [parse_rule_ir(item) for item in raw_rules]
                    rule_digests = [digest(item) for item in parsed]
                    if len(rule_digests) != len(set(rule_digests)):
                        findings.append(
                            f"trace_{trace_index}_step_{step_index}_{phase}:duplicate_rule"
                        )
                    events.append(
                        {
                            "action_count": edge_count,
                            "phase": phase,
                            "rule_digests": sorted(set(rule_digests)),
                            "rules": sorted(parsed, key=digest),
                            "step_index": step_index,
                            "trace_index": trace_index,
                        }
                    )
        except (KeyError, TypeError, SemanticEvidenceError) as exc:
            findings.append(f"trace_{trace_index}:semantic_error:{type(exc).__name__}:{exc}")
    body = {
        "events": events,
        "schema_version": RULE_EVENT_SCHEMA,
        "total_edge_count": edge_count,
    }
    return {
        **body,
        "event_digest": digest(body),
        "findings": findings,
        "passed": not findings,
    }


def verify_rule_timeline(
    ledger: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    rule_events: Mapping[str, Any],
    final_memory: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify actual first emission and fail-closed contradiction invalidation."""

    findings: list[str] = []
    rule_reports: dict[str, dict[str, Any]] = {}
    try:
        rows = _ledger_rows(ledger)
        event_evidence = _plain(rule_events)
        events = event_evidence.get("events")
        if not isinstance(events, list):
            raise SemanticEvidenceError("rule event list missing")
        event_body = {
            "events": events,
            "schema_version": event_evidence.get("schema_version"),
            "total_edge_count": event_evidence.get("total_edge_count"),
        }
        if event_body["schema_version"] != RULE_EVENT_SCHEMA:
            findings.append("rule_event_schema_mismatch")
        if event_body["total_edge_count"] != len(rows):
            findings.append("rule_event_total_action_count_mismatch")
        if event_evidence.get("event_digest") != digest(event_body):
            findings.append("rule_event_digest_mismatch")
        if event_evidence.get("passed") is False or event_evidence.get("findings"):
            findings.append("rule_event_extraction_was_not_clean")
        memory = _plain(final_memory)
        records = memory.get("rule_records")
        if not isinstance(records, list):
            raise SemanticEvidenceError("final memory rule_records missing")
        final_by_digest: dict[str, dict[str, Any]] = {}
        for record in records:
            rule = parse_rule_ir(record["rule"])
            rule_digest = digest(rule)
            if rule_digest in final_by_digest:
                findings.append("final_memory_duplicate_rule")
            final_by_digest[rule_digest] = record

        appearances: dict[str, list[dict[str, Any]]] = {}
        rule_values: dict[str, dict[str, Any]] = {}
        for event in events:
            action_count = event.get("action_count")
            if (
                type(action_count) is not int
                or not 0 <= action_count <= len(rows)
            ):
                findings.append("rule_event_action_count_invalid")
                continue
            for rule in event.get("rules", []):
                parsed = parse_rule_ir(rule)
                rule_digest = digest(parsed)
                rule_values[rule_digest] = parsed
                appearances.setdefault(rule_digest, []).append(event)

        for rule_digest, appearances_for_rule in appearances.items():
            rule = rule_values[rule_digest]
            first_action_count = min(
                item["action_count"] for item in appearances_for_rule
            )
            first_edge_count = len(_feature_rows(rows[:first_action_count]))
            support = verify_rule_support(
                rule, rows, emission_ordinal=first_edge_count
            )
            local_findings = list(support["findings"])
            signature_edges = [
                row
                for row in rows
                if row["action_signature"] == rule["action_signature"]
                and row["ordinal"] >= first_action_count
                and row["edge_ref"] not in set(rule["support_edge_refs"])
            ]
            contradiction_ordinal: int | None = None
            confirmation_ordinal: int | None = None
            for edge in signature_edges:
                predicted = execute_rule_ir(rule, edge["before"])
                if predicted[rule["output_path"]] == edge["after"][rule["output_path"]]:
                    if confirmation_ordinal is None:
                        confirmation_ordinal = edge["ordinal"]
                else:
                    contradiction_ordinal = edge["ordinal"]
                    break
            if contradiction_ordinal is not None:
                for event in appearances_for_rule:
                    # A proposal at edge_count n occurs before edge ordinal n;
                    # learning at n+1 has already observed edge n.
                    if event["action_count"] > contradiction_ordinal:
                        local_findings.append("rule_carried_after_contradiction")
                        break
                if rule_digest in final_by_digest:
                    local_findings.append("contradicted_rule_retained_in_final_memory")
            elif confirmation_ordinal is None:
                if rule_digest in final_by_digest:
                    record = final_by_digest[rule_digest]
                    if record.get("status") != "provisional":
                        local_findings.append("unconfirmed_rule_not_provisional")
            else:
                later_appearance = any(
                    event["action_count"] > confirmation_ordinal
                    for event in appearances_for_rule
                )
                if not later_appearance:
                    local_findings.append("prequential_confirmation_not_carried_later")
                if rule_digest not in final_by_digest:
                    local_findings.append("confirmed_rule_absent_from_final_memory")
            rule_reports[rule_digest] = {
                "confirmation_ordinal": confirmation_ordinal,
                "contradiction_ordinal": contradiction_ordinal,
                "findings": sorted(set(local_findings)),
                "first_emission_edge_count": first_edge_count,
                "first_emission_action_count": first_action_count,
                "passed": not local_findings,
            }
            findings.extend(f"{rule_digest}:{item}" for item in local_findings)

        for rule_digest in final_by_digest:
            if rule_digest not in appearances:
                findings.append(f"{rule_digest}:final_rule_was_never_carried")
        for rule_digest, record in final_by_digest.items():
            report = verify_rule_record(record, rows)
            if not report["passed"]:
                findings.extend(
                    f"{rule_digest}:final_record:{item}" for item in report["findings"]
                )
    except (KeyError, TypeError, SemanticEvidenceError) as exc:
        findings.append(f"semantic_error:{type(exc).__name__}:{exc}")
    return {
        "findings": sorted(set(findings)),
        "passed": not findings,
        "rule_reports": rule_reports,
    }


def _evaluator_concepts(value: Any, *, limit: int = 64) -> list[str]:
    """Independently reconstruct the bounded lexical perception projection."""

    output: list[str] = []

    def visit(item: Any) -> None:
        if len(output) >= limit:
            return
        if isinstance(item, Mapping):
            for key in sorted(item):
                text = " ".join(str(key).split())
                if text:
                    output.append(text)
                visit(item[key])
                if len(output) >= limit:
                    break
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)
                if len(output) >= limit:
                    break
        elif isinstance(item, str):
            text = " ".join(item.split())
            if text:
                output.append(text[:160])

    visit(value)
    # Candidate perception retains first occurrence order.
    return list(dict.fromkeys(output))


def _expected_memory_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    transitions: Counter[tuple[str, str, str]] = Counter()
    attempts: Counter[tuple[str, str]] = Counter()
    semantic_attempts: Counter[tuple[str, str]] = Counter()
    action_sets: dict[str, set[str]] = {}
    target_state_digest: str | None = None
    concepts_by_state: dict[str, list[str]] = {}
    feature_rows = _feature_rows(rows)
    for row in rows:
        transitions[
            (
                row["before_observation_digest"],
                row["action_id"],
                row["after_observation_digest"],
            )
        ] += 1
        attempts[(row["before_observation_digest"], row["action_id"])] += 1
        if row.get("valid_action_ids"):
            action_sets.setdefault(row["before_observation_digest"], set()).update(
                row["valid_action_ids"]
            )
        concepts_by_state[row["before_observation_digest"]] = _evaluator_concepts(
            row["before_observation"]
        )
        if row.get("success") is True:
            target_state_digest = row["after_observation_digest"]
    for row in feature_rows:
        semantic_attempts[(digest(row["before"]), row["action_signature"])] += 1
    return {
        "action_sets": [
            {"state": state, "actions": sorted(actions)}
            for state, actions in sorted(action_sets.items())
        ],
        "attempts": [
            {"state": state, "action": action, "count": count}
            for (state, action), count in sorted(attempts.items())
        ],
        "concepts_by_state": [
            {"state": state, "concepts": concepts}
            for state, concepts in sorted(concepts_by_state.items())
        ],
        "feature_edges": [
            {
                "action_signature": row["action_signature"],
                "after": row["after"],
                "before": row["before"],
                "edge_ref": row["edge_ref"],
                "ordinal": row["ordinal"],
            }
            for row in feature_rows
        ],
        "semantic_attempts": [
            {
                "feature_state": state,
                "action_signature": signature,
                "count": count,
            }
            for (state, signature), count in sorted(semantic_attempts.items())
        ],
        "target_state_digest": target_state_digest,
        "transitions": [
            {"from": before, "action": action, "to": after, "count": count}
            for (before, action, after), count in sorted(transitions.items())
        ],
    }


def verify_memory_against_ledger(
    memory: Mapping[str, Any],
    ledger: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Verify all evaluator-reconstructable memory surfaces and final rules."""

    findings: list[str] = []
    rule_reports: list[dict[str, Any]] = []
    memory_digest: str | None = None
    try:
        if not isinstance(memory, Mapping):
            raise SemanticEvidenceError("candidate memory must be a mapping")
        raw = _plain(memory)
        memory_digest = digest(raw)
        if set(raw) != _MEMORY_FIELDS:
            raise SemanticEvidenceError("candidate memory fields mismatch")
        if raw["schema_version"] != MEMORY_SCHEMA:
            findings.append("candidate_memory_schema_mismatch")
        rows = _ledger_rows(ledger)
        expected = _expected_memory_rows(rows)
        for field in (
            "action_sets",
            "attempts",
            "concepts_by_state",
            "feature_edges",
            "semantic_attempts",
            "target_state_digest",
            "transitions",
        ):
            if raw.get(field) != expected[field]:
                findings.append(f"memory_{field}_not_reconstructed")
        records = raw.get("rule_records")
        if not isinstance(records, list):
            findings.append("memory_rule_records_not_list")
        else:
            seen_keys: set[str] = set()
            for record in records:
                report = verify_rule_record(record, rows)
                rule_reports.append(report)
                key = record.get("rule_key") if isinstance(record, Mapping) else None
                if not isinstance(key, str) or key in seen_keys:
                    findings.append("memory_rule_record_key_invalid_or_duplicate")
                seen_keys.add(key)
                findings.extend(f"rule_record:{item}" for item in report["findings"])
            if [item.get("rule_key") for item in records] != sorted(seen_keys):
                findings.append("memory_rule_records_noncanonical_order")
    except (KeyError, TypeError, SemanticEvidenceError) as exc:
        findings.append(f"semantic_error:{type(exc).__name__}:{exc}")
    return {
        "findings": sorted(set(findings)),
        "memory_digest": memory_digest,
        "passed": not findings,
        "rule_reports": rule_reports,
    }


def canonical_empty_memory() -> dict[str, Any]:
    """Return the exact cold-start v2 memory, evaluator-owned."""

    return {
        "action_sets": [],
        "attempts": [],
        "concepts_by_state": [],
        "feature_edges": [],
        "rule_records": [],
        "schema_version": MEMORY_SCHEMA,
        "semantic_attempts": [],
        "target_state_digest": None,
        "transitions": [],
    }


def verify_support_memory_chain(
    traces: Sequence[Mapping[str, Any]],
    *,
    pair_index: int,
    expected_episode_count: int = 4,
) -> dict[str, Any]:
    """Verify sequential support memory and rebuild its cumulative edge ledger."""

    findings: list[str] = []
    all_steps: list[dict[str, Any]] = []
    final_memory: dict[str, Any] | None = None
    try:
        if len(traces) != expected_episode_count:
            findings.append("support_episode_count_mismatch")
        prior_memory = canonical_empty_memory()
        for episode_index, trace in enumerate(traces):
            semantic = _trace_projection(trace)
            memory_before = semantic.get("memory_before")
            memory_after = semantic.get("memory_after")
            if not isinstance(memory_before, Mapping) or not isinstance(
                memory_after, Mapping
            ):
                raise SemanticEvidenceError("support trace memory binding is absent")
            if _plain(memory_before) != prior_memory:
                findings.append(f"episode_{episode_index}:memory_before_chain_mismatch")
            episode_steps = evaluator_steps_from_trace(
                trace,
                episode_ref=f"pair:{pair_index}:support:{episode_index}",
            )
            all_steps.extend(episode_steps)
            prefix_ledger = reconstruct_edge_ledger(all_steps)
            memory_report = verify_memory_against_ledger(memory_after, prefix_ledger)
            if not memory_report["passed"]:
                findings.extend(
                    f"episode_{episode_index}:{item}"
                    for item in memory_report["findings"]
                )
            prior_memory = _plain(memory_after)
            final_memory = prior_memory
        ledger = reconstruct_edge_ledger(all_steps)
    except (KeyError, TypeError, SemanticEvidenceError) as exc:
        findings.append(f"semantic_error:{type(exc).__name__}:{exc}")
        ledger = None
    return {
        "final_memory": final_memory,
        "findings": sorted(set(findings)),
        "ledger": ledger,
        "pair_index": pair_index,
        "passed": not findings,
    }


def build_support_memory_binding(
    *,
    pair_index: int,
    traces: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a support binding only from a fully verified evaluator chain."""

    verification = verify_support_memory_chain(traces, pair_index=pair_index)
    if not verification["passed"]:
        return {
            "binding": None,
            "findings": verification["findings"],
            "passed": False,
            "verification": verification,
        }
    memory = verification["final_memory"]
    ledger = verification["ledger"]
    body = {
        "ledger": ledger,
        "ledger_digest": ledger["ledger_digest"],
        "memory": memory,
        "memory_digest": digest(memory),
        "pair_index": pair_index,
        "schema_version": SUPPORT_BINDING_SCHEMA,
    }
    return {
        "binding": {**body, "binding_digest": digest(body)},
        "findings": [],
        "passed": True,
        "verification": verification,
    }


def _validated_support_binding(value: Mapping[str, Any], pair_index: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticEvidenceError("support binding must be a mapping")
    raw = _plain(value)
    body = {
        "ledger": raw.get("ledger"),
        "ledger_digest": raw.get("ledger_digest"),
        "memory": raw.get("memory"),
        "memory_digest": raw.get("memory_digest"),
        "pair_index": raw.get("pair_index"),
        "schema_version": raw.get("schema_version"),
    }
    if (
        set(raw) != set(body) | {"binding_digest"}
        or body["schema_version"] != SUPPORT_BINDING_SCHEMA
        or body["pair_index"] != pair_index
        or not isinstance(body["ledger"], Mapping)
        or not _is_sha256(body["ledger_digest"])
        or body["ledger"].get("ledger_digest") != body["ledger_digest"]
        or not isinstance(body["memory"], Mapping)
        or body["memory_digest"] != digest(body["memory"])
        or raw["binding_digest"] != digest(body)
    ):
        raise SemanticEvidenceError("support binding does not reconstruct")
    memory_report = verify_memory_against_ledger(body["memory"], body["ledger"])
    if not memory_report["passed"]:
        raise SemanticEvidenceError(
            "support binding memory does not reconstruct from its edge ledger"
        )
    return raw


def bind_target_memory(
    *,
    arm: str,
    pair_index: int,
    support_bindings: Mapping[int, Mapping[str, Any]],
    pair_count: int,
) -> dict[str, Any]:
    """Derive matched/cold/mismatch memory; caller labels never select bytes."""

    if type(pair_index) is not int or not 0 <= pair_index < pair_count:
        raise SemanticEvidenceError("target pair index is out of range")
    if type(pair_count) is not int or pair_count <= 1:
        raise SemanticEvidenceError("pair_count must exceed one")
    if arm == "cold":
        source_pair_index: int | None = None
        memory = canonical_empty_memory()
        support_binding_digest: str | None = None
    elif arm in {"matched_warm", "mismatched_warm"}:
        source_pair_index = (
            pair_index if arm == "matched_warm" else (pair_index + 1) % pair_count
        )
        if source_pair_index not in support_bindings:
            raise SemanticEvidenceError("required evaluator support binding is absent")
        binding = _validated_support_binding(
            support_bindings[source_pair_index], source_pair_index
        )
        memory = _plain(binding["memory"])
        support_binding_digest = binding["binding_digest"]
    else:
        raise SemanticEvidenceError("unsupported target arm")
    body = {
        "arm": arm,
        "memory": memory,
        "memory_digest": digest(memory),
        "pair_index": pair_index,
        "schema_version": TARGET_BINDING_SCHEMA,
        "source_pair_index": source_pair_index,
        "support_binding_digest": support_binding_digest,
    }
    return {**body, "binding_digest": digest(body)}


def verify_target_memory_binding(
    *,
    actual_memory_before: Mapping[str, Any],
    arm: str,
    pair_index: int,
    support_bindings: Mapping[int, Mapping[str, Any]],
    pair_count: int,
    claimed_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute the target binding and compare actual bytes.

    ``claimed_binding`` is optional candidate evidence and never selects the
    expected memory.  Even a canonically re-sealed caller claim is compared
    with a fresh evaluator derivation from the verified support-binding map.
    """

    findings: list[str] = []
    try:
        expected = bind_target_memory(
            arm=arm,
            pair_index=pair_index,
            support_bindings=support_bindings,
            pair_count=pair_count,
        )
        raw = _plain(expected)
        expected_fields = {
            "arm",
            "binding_digest",
            "memory",
            "memory_digest",
            "pair_index",
            "schema_version",
            "source_pair_index",
            "support_binding_digest",
        }
        if set(raw) != expected_fields:
            raise SemanticEvidenceError("target binding fields mismatch")
        body = {key: raw[key] for key in raw if key != "binding_digest"}
        if raw.get("schema_version") != TARGET_BINDING_SCHEMA:
            findings.append("target_binding_schema_mismatch")
        if raw.get("binding_digest") != digest(body):
            findings.append("target_binding_digest_mismatch")
        if raw.get("memory_digest") != digest(raw.get("memory")):
            findings.append("target_binding_memory_digest_mismatch")
        if claimed_binding is not None and _plain(claimed_binding) != raw:
            findings.append("caller_target_binding_claim_mismatch")
        if _plain(actual_memory_before) != raw.get("memory"):
            findings.append("target_memory_before_not_evaluator_bound")
    except (KeyError, TypeError, SemanticEvidenceError) as exc:
        findings.append(f"semantic_error:{type(exc).__name__}:{exc}")
    return {"findings": findings, "passed": not findings}


def score_counterfactuals(
    rules: Sequence[Mapping[str, Any]],
    action_programs: Mapping[str, Sequence[int]],
    *,
    modulus: int = COUNTERFACTUAL_MODULUS,
    expected_action_count: int = 4,
) -> dict[str, Any]:
    """Execute candidate-carried rules on every hidden state/action cell."""

    findings: list[str] = []
    cells: list[dict[str, Any]] = []
    if (
        type(modulus) is not int
        or modulus <= 1
        or type(expected_action_count) is not int
        or expected_action_count <= 0
    ):
        raise SemanticEvidenceError("counterfactual dimensions are invalid")
    try:
        if len(action_programs) != expected_action_count:
            findings.append("counterfactual_action_count_mismatch")
        parsed_rules = [parse_rule_ir(rule) for rule in rules]
        rules_by_signature: dict[str, list[dict[str, Any]]] = {}
        for rule in parsed_rules:
            affine_coefficients(rule)
            rules_by_signature.setdefault(rule["action_signature"], []).append(rule)
        if set(rules_by_signature) != set(action_programs):
            findings.append("counterfactual_rule_signature_set_mismatch")
        correct = 0
        predicted = 0
        total = expected_action_count * modulus
        for signature, raw_program in sorted(action_programs.items()):
            if not _is_sha256(signature):
                findings.append("counterfactual_program_signature_invalid")
                continue
            if (
                not isinstance(raw_program, (list, tuple))
                or len(raw_program) != 2
                or any(type(item) is not int for item in raw_program)
            ):
                findings.append("counterfactual_program_invalid")
                continue
            a, b = raw_program
            candidates = rules_by_signature.get(signature, [])
            if len(candidates) != 1:
                findings.append(
                    f"counterfactual_rule_multiplicity:{signature}:{len(candidates)}"
                )
                continue
            rule = candidates[0]
            for state in range(modulus):
                projection = {
                    rule["input_path"]: state,
                    rule["output_path"]: state,
                    rule["context_path"]: modulus,
                }
                result = execute_rule_ir(rule, projection)
                prediction = result[rule["output_path"]]
                expected = (a * state + b) % modulus
                is_correct = prediction == expected
                predicted += 1
                correct += int(is_correct)
                cells.append(
                    {
                        "action_signature": signature,
                        "correct": is_correct,
                        "expected": expected,
                        "prediction": prediction,
                        "state": state,
                    }
                )
        coverage = predicted / total if total else 0.0
        precision = correct / predicted if predicted else 0.0
    except (KeyError, TypeError, SemanticEvidenceError) as exc:
        findings.append(f"semantic_error:{type(exc).__name__}:{exc}")
        correct = 0
        predicted = 0
        total = expected_action_count * modulus
        coverage = 0.0
        precision = 0.0
    return {
        "cells": cells,
        "correct_predictions": correct,
        "coverage": coverage,
        "findings": sorted(set(findings)),
        "passed": not findings and precision == 1.0 and coverage >= 0.9 and predicted >= 8,
        "precision": precision,
        "predicted_cells": predicted,
        "total_cells": total,
    }


__all__ = [
    "COEFFICIENT_MAXIMUM",
    "COEFFICIENT_MINIMUM",
    "COUNTERFACTUAL_MODULUS",
    "LEDGER_SCHEMA",
    "MEMORY_SCHEMA",
    "MINIMUM_DISTINCT_INPUTS",
    "RULE_IR_SCHEMA",
    "SemanticEvidenceError",
    "affine_coefficients",
    "bind_target_memory",
    "build_support_memory_binding",
    "canonical_empty_memory",
    "canonical_json_bytes",
    "digest",
    "evaluator_steps_from_trace",
    "execute_rule_ir",
    "extract_candidate_rule_events",
    "normalize_evaluator_step",
    "parse_rule_ir",
    "payload_signature",
    "reconstruct_edge_ledger",
    "score_counterfactuals",
    "strict_feature_projection",
    "verify_memory_against_ledger",
    "verify_rule_record",
    "verify_rule_support",
    "verify_rule_timeline",
    "verify_support_memory_chain",
    "verify_target_memory_binding",
]
