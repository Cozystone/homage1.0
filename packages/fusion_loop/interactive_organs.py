"""Domain-neutral organ adapters for the general world-interaction loop.

The adapters in this module are deliberately advisory.  They turn an
evaluator-owned observation into canonical cognitive records, keep a bounded
empirical transition memory, and propose an action.  They never authorize an
action and never accept a caller-supplied truth, validity, or authority flag.

The implementation reuses the existing deterministic perception, situation,
transition-graph, affordance-resonance, and DELIBERATOR organs.  Environment
state and action payloads remain opaque canonical JSON; there are no task- or
domain-specific branches.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from packages.affordance.context_affordance import resonance
from packages.cognitive_core import (
    ClaimEnvelope,
    EpistemicTier,
    FrozenMap,
    GoalIR,
    ProofCandidate,
)
from packages.cognitive_core.canonical import canonical_digest, canonical_id, canonical_json
from packages.perception.scene_graph import build_scene_graph
from packages.reasoning_vm.deliberator.back_chain import Rule
from packages.reasoning_vm.deliberator.reasoner import Deliberator
from packages.situation_model.state_tracker import StateTracker
from packages.temporal_reasoning.transition_graph import EventTransitionGraph


MAX_OPAQUE_JSON_BYTES = 1_048_576
LEGACY_MEMORY_SCHEMA_VERSION = "atanor.gwip-policy-memory.v1"
MEMORY_SCHEMA_VERSION = "atanor.gwip-policy-memory.v2"
RULE_IR_SCHEMA_VERSION = "atanor.gwip-feature-rule.v1"
MAX_FEATURE_LEAVES = 64
MAX_GOAL_CONSTRAINTS = 16
MAX_RULE_HYPOTHESES = 64
MAX_RULE_PLAN_DEPTH = 64
MAX_RULE_PLAN_NODES = 4_096
MAX_RULE_AST_DEPTH = 6
COEFFICIENT_SEARCH_BOUND = 6
MIN_DISTINCT_RULE_INPUTS = 3


def _pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _pointer_tokens(path: str) -> tuple[str, ...]:
    if not isinstance(path, str) or not path.startswith("/") or path == "/":
        raise ValueError("JSON pointer must be a non-root absolute path")
    tokens: list[str] = []
    encoded_tokens = path[1:].split("/")
    for encoded in encoded_tokens:
        token = encoded
        if "~" in token:
            index = 0
            decoded: list[str] = []
            while index < len(token):
                if token[index] != "~":
                    decoded.append(token[index])
                    index += 1
                    continue
                if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
                    raise ValueError("JSON pointer contains an invalid escape")
                decoded.append("~" if token[index + 1] == "0" else "/")
                index += 2
            token = "".join(decoded)
        if _pointer_escape(token) != encoded:
            raise ValueError("JSON pointer is not canonically encoded")
        if token.isdigit() and len(token) > 1 and token.startswith("0"):
            raise ValueError("JSON pointer numeric token is not canonical")
        tokens.append(token)
    return tuple(tokens)


def _pointer_get(value: Mapping[str, Any] | FrozenMap, path: str) -> Any:
    current: Any = value.to_dict() if isinstance(value, FrozenMap) else value
    for token in _pointer_tokens(path):
        if isinstance(current, Mapping):
            if token not in current:
                raise KeyError(path)
            current = current[token]
        elif isinstance(current, (list, tuple)):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                raise KeyError(path)
            index = int(token)
            if index >= len(current):
                raise KeyError(path)
            current = current[index]
        else:
            raise KeyError(path)
    return current


def numeric_feature_projection(
    value: Mapping[str, Any] | FrozenMap,
    *,
    root_path: str,
) -> FrozenMap:
    """Project exact integers below one GoalIR-derived structural root.

    The root is supplied from the top-level path shared by the goal's typed
    constraints, rather than a hard-coded observation field name.  Sibling
    identifiers, statuses, truth flags, and other caller metadata therefore
    cannot enter transferable rules even when represented as integers.
    """

    observation = bounded_mapping(value, name="structured observation")
    raw = observation.to_dict()
    tokens = _pointer_tokens(root_path)
    if len(tokens) != 1:
        raise ValueError("numeric projection root must be one top-level path")
    root = _pointer_get(raw, root_path)
    if not isinstance(root, (Mapping, list, tuple)):
        raise ValueError("numeric projection root must contain structured data")
    leaves: dict[str, int] = {}

    def visit(item: Any, path: str) -> None:
        if len(leaves) >= MAX_FEATURE_LEAVES:
            raise ValueError("numeric feature projection exceeds bounded leaf count")
        if type(item) is int:
            leaves[path] = item
            return
        if isinstance(item, Mapping):
            for key in sorted(item, key=str):
                visit(item[key], f"{path}/{_pointer_escape(str(key))}")
            return
        if isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                visit(child, f"{path}/{index}")

    visit(root, root_path)
    return FrozenMap(leaves)


def action_payload_signature(
    action: "ActionOption | Mapping[str, Any] | FrozenMap",
) -> str | None:
    """Return the semantic signature of a non-empty evaluator-owned payload."""

    if isinstance(action, ActionOption):
        payload = action.payload
    elif isinstance(action, FrozenMap):
        payload = action
    elif isinstance(action, Mapping):
        payload = bounded_mapping(action, name="action signature payload")
    else:
        raise TypeError("action signature requires ActionOption or payload mapping")
    if not payload:
        return None
    return canonical_digest(payload)


def extract_goal_constraints(goal: GoalIR) -> tuple[FrozenMap, ...]:
    """Read bounded typed equality constraints from an existing GoalIR."""

    if type(goal) is not GoalIR:
        raise TypeError("goal constraints require an exact GoalIR")
    metadata = goal.metadata.to_dict()
    raw = metadata.get("target_constraints")
    if raw is None:
        return ()
    if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
        raise ValueError("goal target_constraints must be a sequence")
    if len(raw) > MAX_GOAL_CONSTRAINTS:
        raise ValueError("goal target_constraints exceed bounded count")
    constraints: list[FrozenMap] = []
    paths: set[str] = set()
    for row in raw:
        if not isinstance(row, Mapping) or set(row) != {"path", "op", "value"}:
            raise ValueError("goal constraint requires exactly path, op, and value")
        path = row["path"]
        _pointer_tokens(path)
        if path in paths:
            raise ValueError("goal constraint paths must be unique")
        if row["op"] != "eq" or type(row["value"]) is not int:
            raise ValueError("only exact integer equality goal constraints are supported")
        paths.add(path)
        constraints.append(FrozenMap({"op": "eq", "path": path, "value": row["value"]}))
    return tuple(sorted(constraints, key=lambda item: item["path"]))


def _constraint_projection_root(
    constraints: Sequence[Mapping[str, Any] | FrozenMap],
) -> str | None:
    roots = {
        _pointer_tokens(item["path"])[0]
        for item in constraints
    }
    if len(roots) != 1:
        return None
    return "/" + _pointer_escape(next(iter(roots)))


def _goal_satisfied(
    projection: Mapping[str, Any] | FrozenMap,
    constraints: Sequence[Mapping[str, Any] | FrozenMap],
) -> bool:
    return bool(constraints) and all(
        projection.get(item["path"]) == item["value"] for item in constraints
    )


def bounded_mapping(
    value: Mapping[str, Any],
    *,
    name: str,
    max_bytes: int = MAX_OPAQUE_JSON_BYTES,
) -> FrozenMap:
    """Freeze one bounded JSON mapping and reject unstable/non-JSON values."""

    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    frozen = FrozenMap(value)
    size = len(canonical_json(frozen).encode("utf-8"))
    if size > max_bytes:
        raise ValueError(f"{name} exceeds the {max_bytes}-byte canonical limit")
    return frozen


def opaque_digest(value: Mapping[str, Any] | FrozenMap) -> str:
    """Canonical state identity used by the generic transition learner."""

    return canonical_digest(value)


def _collect_concepts(value: Any, *, limit: int = 64) -> tuple[str, ...]:
    """Extract bounded lexical cues without interpreting their domain."""

    out: list[str] = []

    def visit(item: Any) -> None:
        if len(out) >= limit:
            return
        if isinstance(item, FrozenMap):
            item = item.to_dict()
        if isinstance(item, Mapping):
            for key in sorted(item, key=str):
                text = " ".join(str(key).split())
                if text:
                    out.append(text)
                visit(item[key])
                if len(out) >= limit:
                    break
        elif isinstance(item, (tuple, list)):
            for child in item:
                visit(child)
                if len(out) >= limit:
                    break
        elif isinstance(item, str):
            text = " ".join(item.split())
            if text:
                out.append(text[:160])

    visit(value)
    return tuple(dict.fromkeys(out))


def _situation_summary(concepts: Sequence[str]) -> FrozenMap:
    """Run the existing pure state tracker and expose only a stable summary."""

    tracker = StateTracker()
    for order, sentence in enumerate(concepts):
        tracker.ingest(sentence, order)
    world = tracker.w
    return FrozenMap(
        {
            "agent_count": len(world.agents),
            "location_count": len(world.loc),
            "present_count": len(world.present),
            "room_count": len(world.rooms),
        }
    )


def _scene_graph(value: FrozenMap) -> FrozenMap:
    """Use deterministic scene-graph perception when its generic shape exists."""

    raw = value.to_dict()
    detections = raw.get("detections")
    frame_size = raw.get("frame_size")
    if (
        not isinstance(detections, list)
        or not isinstance(frame_size, (list, tuple))
        or len(frame_size) != 2
        or any(type(item) is not int or item <= 0 for item in frame_size)
    ):
        return FrozenMap({"used": False, "graph": {}})
    if any(not isinstance(item, Mapping) for item in detections):
        return FrozenMap({"used": False, "graph": {}})
    try:
        graph = build_scene_graph(
            [dict(item) for item in detections],
            (int(frame_size[0]), int(frame_size[1])),
        )
    except (KeyError, TypeError, ValueError):
        return FrozenMap({"used": False, "graph": {}})
    return FrozenMap({"used": True, "graph": graph})


@dataclass(frozen=True, kw_only=True)
class PerceptionBundle:
    """Canonical, non-authoritative products derived from one actual observation."""

    observation: FrozenMap
    observation_digest: str
    claim: ClaimEnvelope
    concepts: tuple[str, ...]
    scene_graph: FrozenMap
    situation_summary: FrozenMap
    organ_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim.to_dict(),
            "concepts": list(self.concepts),
            "observation": self.observation.to_dict(),
            "observation_digest": self.observation_digest,
            "organ_digest": self.organ_digest,
            "scene_graph": self.scene_graph.to_dict(),
            "situation_summary": self.situation_summary.to_dict(),
        }


def perceive_observation(value: Mapping[str, Any]) -> PerceptionBundle:
    """Bind deterministic organ output to the exact environment observation."""

    observation = bounded_mapping(value, name="environment observation")
    digest = opaque_digest(observation)
    concepts = _collect_concepts(observation)
    scene = _scene_graph(observation)
    situation = _situation_summary(concepts)
    claim = ClaimEnvelope(
        statement=f"Environment observation sha256 {digest}.",
        tier=EpistemicTier.OBSERVED,
        source_refs=(f"environment-observation:{digest}",),
        metadata={
            "observation_digest": digest,
            "perception": "deterministic_scene_graph_and_situation_tracker",
        },
    )
    organ_digest = canonical_digest(
        {
            "claim_id": claim.contract_id,
            "concepts": concepts,
            "scene_graph": scene,
            "situation_summary": situation,
        }
    )
    return PerceptionBundle(
        observation=observation,
        observation_digest=digest,
        claim=claim,
        concepts=concepts,
        scene_graph=scene,
        situation_summary=situation,
        organ_digest=organ_digest,
    )


@dataclass(frozen=True, kw_only=True)
class ActionOption:
    """One evaluator-returned action; no field grants permission."""

    action_id: str
    payload: FrozenMap = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        if not isinstance(self.action_id, str) or not self.action_id.strip():
            raise ValueError("action_id must be a non-empty string")
        object.__setattr__(self, "action_id", " ".join(self.action_id.split()))
        object.__setattr__(
            self,
            "payload",
            bounded_mapping(self.payload, name="action payload"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"action_id": self.action_id, "payload": self.payload.to_dict()}


def normalize_valid_actions(values: Sequence[str | Mapping[str, Any]]) -> tuple[ActionOption, ...]:
    """Snapshot the evaluator-owned valid set and reject ambiguous duplicates."""

    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("valid_actions must be a sequence")
    actions: list[ActionOption] = []
    for value in values:
        if isinstance(value, str):
            action = ActionOption(action_id=value)
        elif isinstance(value, Mapping):
            if set(value) - {"action_id", "payload"}:
                raise ValueError("action mapping supports only action_id and payload")
            action = ActionOption(
                action_id=value.get("action_id"),
                payload=value.get("payload", {}),
            )
        else:
            raise TypeError("each valid action must be a string or action mapping")
        actions.append(action)
    action_ids = [item.action_id for item in actions]
    if len(action_ids) != len(set(action_ids)):
        raise ValueError("evaluator valid_actions cannot contain duplicate action IDs")
    return tuple(actions)


def _expression_depth(value: Mapping[str, Any]) -> int:
    args = value.get("args", ())
    if not args:
        return 1
    return 1 + max(_expression_depth(item) for item in args)


def _validate_expression(value: Any) -> FrozenMap:
    if not isinstance(value, Mapping):
        raise ValueError("rule expression must be a mapping")
    raw = FrozenMap(value).to_dict()
    op = raw.get("op")
    if op == "var":
        if set(raw) != {"op", "path"}:
            raise ValueError("var expression fields mismatch")
        _pointer_tokens(raw["path"])
    elif op == "const":
        if set(raw) != {"op", "value"} or type(raw["value"]) is not int:
            raise ValueError("const expression requires an exact integer")
    elif op == "copy":
        if set(raw) != {"op", "path"}:
            raise ValueError("copy expression fields mismatch")
        _pointer_tokens(raw["path"])
    elif op in {"add", "mul", "mod"}:
        if set(raw) != {"args", "op"}:
            raise ValueError(f"{op} expression fields mismatch")
        args = raw["args"]
        if not isinstance(args, list) or len(args) != 2:
            raise ValueError(f"{op} expression requires exactly two arguments")
        raw["args"] = [
            _validate_expression(args[0]).to_dict(),
            _validate_expression(args[1]).to_dict(),
        ]
    else:
        raise ValueError("unsupported rule expression operator")
    if _expression_depth(raw) > MAX_RULE_AST_DEPTH:
        raise ValueError("rule expression exceeds bounded depth")
    return FrozenMap(raw)


def _evaluate_expression(
    value: Mapping[str, Any] | FrozenMap,
    projection: Mapping[str, Any] | FrozenMap,
) -> int:
    raw = value.to_dict() if isinstance(value, FrozenMap) else dict(value)
    op = raw["op"]
    if op in {"var", "copy"}:
        result = projection.get(raw["path"])
        if type(result) is not int:
            raise ValueError("rule variable does not resolve to an exact integer")
        return result
    if op == "const":
        return raw["value"]
    left = _evaluate_expression(raw["args"][0], projection)
    right = _evaluate_expression(raw["args"][1], projection)
    if op == "add":
        return left + right
    if op == "mul":
        return left * right
    if right <= 1:
        raise ValueError("rule modulus must be greater than one")
    return left % right


def validate_rule_ir(value: Mapping[str, Any] | FrozenMap) -> FrozenMap:
    """Validate and canonicalize one non-authoritative typed rule hypothesis."""

    if not isinstance(value, (Mapping, FrozenMap)):
        raise ValueError("rule IR must be a mapping")
    raw = value.to_dict() if isinstance(value, FrozenMap) else FrozenMap(value).to_dict()
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
    if set(raw) != required:
        raise ValueError("rule IR fields mismatch")
    if raw["schema_version"] != RULE_IR_SCHEMA_VERSION:
        raise ValueError("unsupported rule IR schema")
    signature = raw["action_signature"]
    if (
        not isinstance(signature, str)
        or len(signature) != 64
        or any(character not in "0123456789abcdef" for character in signature)
    ):
        raise ValueError("rule action signature must be a lowercase SHA-256")
    for key in ("input_path", "output_path", "context_path"):
        _pointer_tokens(raw[key])
    if raw["hypothesis"] is not True:
        raise ValueError("transition rules must remain hypotheses")
    refs = raw["support_edge_refs"]
    if (
        not isinstance(refs, list)
        or len(refs) < MIN_DISTINCT_RULE_INPUTS
        or len(refs) != len(set(refs))
        or any(not isinstance(item, str) or not item for item in refs)
    ):
        raise ValueError("rule support edge references are invalid")
    raw["support_edge_refs"] = sorted(refs)
    raw["expression"] = _validate_expression(raw["expression"]).to_dict()
    return FrozenMap(raw)


def evaluate_rule_ir(
    rule: Mapping[str, Any] | FrozenMap,
    projection: Mapping[str, Any] | FrozenMap,
) -> FrozenMap:
    """Execute a validated rule against a typed feature projection."""

    normalized = validate_rule_ir(rule)
    features = FrozenMap(projection)
    for path in (
        normalized["input_path"],
        normalized["output_path"],
        normalized["context_path"],
    ):
        if type(features.get(path)) is not int:
            raise ValueError("rule path is absent from typed feature projection")
    result = features.to_dict()
    result[normalized["output_path"]] = _evaluate_expression(
        normalized["expression"],
        features,
    )
    return FrozenMap(result)


def _affine_expression(
    *,
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


def _derive_canonical_affine_rule(
    *,
    action_signature: str,
    input_path: str,
    output_path: str,
    context_path: str,
    edges: Sequence[Mapping[str, Any] | FrozenMap],
) -> FrozenMap | None:
    """Recompute one rule from observed feature edges, ignoring caller status."""

    ordered = sorted(
        (
            item if isinstance(item, FrozenMap) else FrozenMap(item)
            for item in edges
        ),
        key=lambda item: item["ordinal"],
    )
    if len(ordered) < MIN_DISTINCT_RULE_INPUTS:
        return None
    if any(item["action_signature"] != action_signature for item in ordered):
        return None
    before_rows = [FrozenMap(item["before"]) for item in ordered]
    after_rows = [FrozenMap(item["after"]) for item in ordered]
    required_paths = {input_path, output_path, context_path}
    if any(
        any(
            type(before.get(path)) is not int
            or type(after.get(path)) is not int
            for path in required_paths
        )
        for before, after in zip(before_rows, after_rows)
    ):
        return None
    if (
        len({before[input_path] for before in before_rows})
        < MIN_DISTINCT_RULE_INPUTS
        or not any(
            before[output_path] != after[output_path]
            for before, after in zip(before_rows, after_rows)
        )
    ):
        return None
    moduli = {
        before[context_path]
        for before, after in zip(before_rows, after_rows)
        if before[context_path] == after[context_path]
        and before[context_path] > 1
    }
    if len(moduli) != 1 or any(
        before[context_path] != after[context_path]
        for before, after in zip(before_rows, after_rows)
    ):
        return None
    modulus = next(iter(moduli))
    fitting: list[tuple[int, int, tuple[int, int]]] = []
    for multiplier in range(
        -COEFFICIENT_SEARCH_BOUND,
        COEFFICIENT_SEARCH_BOUND + 1,
    ):
        for offset in range(
            -COEFFICIENT_SEARCH_BOUND,
            COEFFICIENT_SEARCH_BOUND + 1,
        ):
            if all(
                (multiplier * before[input_path] + offset) % modulus
                == after[output_path]
                for before, after in zip(before_rows, after_rows)
            ):
                fitting.append(
                    (
                        multiplier,
                        offset,
                        (multiplier % modulus, offset % modulus),
                    )
                )
    if not fitting or len({item[2] for item in fitting}) != 1:
        return None
    multiplier, offset, _identity = min(
        fitting,
        key=lambda item: (
            abs(item[0]) + abs(item[1]),
            abs(item[0]),
            abs(item[1]),
            item[0],
            item[1],
        ),
    )
    return validate_rule_ir(
        {
            "schema_version": RULE_IR_SCHEMA_VERSION,
            "action_signature": action_signature,
            "input_path": input_path,
            "output_path": output_path,
            "context_path": context_path,
            "expression": _affine_expression(
                input_path=input_path,
                context_path=context_path,
                multiplier=multiplier,
                offset=offset,
            ),
            "support_edge_refs": [item["edge_ref"] for item in ordered],
            "hypothesis": True,
        }
    )


def _rule_key(rule: Mapping[str, Any] | FrozenMap) -> str:
    raw = validate_rule_ir(rule).to_dict()
    raw.pop("support_edge_refs")
    return canonical_digest(raw)


def _usable_rule_irs(records: Mapping[str, FrozenMap]) -> tuple[FrozenMap, ...]:
    values = [
        validate_rule_ir(record["rule"])
        for record in records.values()
        if record["status"] == "usable"
    ]
    return tuple(sorted(values, key=canonical_digest))


def _provisional_rule_irs(records: Mapping[str, FrozenMap]) -> tuple[FrozenMap, ...]:
    values = [
        validate_rule_ir(record["rule"])
        for record in records.values()
        if record["status"] == "provisional"
    ]
    return tuple(sorted(values, key=canonical_digest))


@dataclass(frozen=True, kw_only=True)
class ActionProposal:
    """Advisory selection evidence.  It is not an authorization."""

    action_id: str
    strategy: str
    valid_actions_digest: str
    observation_digest: str
    transition_graph_path: tuple[str, ...] = ()
    deliberator_proof: FrozenMap = field(default_factory=FrozenMap)
    affordance_resonance: float = 0.0
    affordance_grounding: tuple[str, ...] = ()
    proposal_id: str = field(init=False)
    authoritative: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.action_id, str) or not self.action_id:
            raise ValueError("action proposal requires action_id")
        payload = {
            "action_id": self.action_id,
            "affordance_grounding": self.affordance_grounding,
            "affordance_resonance": float(self.affordance_resonance),
            "deliberator_proof": self.deliberator_proof,
            "observation_digest": self.observation_digest,
            "strategy": self.strategy,
            "transition_graph_path": self.transition_graph_path,
            "valid_actions_digest": self.valid_actions_digest,
        }
        object.__setattr__(self, "proposal_id", canonical_id("proposal", payload)[0])

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "affordance_grounding": list(self.affordance_grounding),
            "affordance_resonance": self.affordance_resonance,
            "authoritative": self.authoritative,
            "deliberator_proof": self.deliberator_proof.to_dict(),
            "observation_digest": self.observation_digest,
            "proposal_id": self.proposal_id,
            "strategy": self.strategy,
            "transition_graph_path": list(self.transition_graph_path),
            "valid_actions_digest": self.valid_actions_digest,
        }


@dataclass
class InteractivePolicyMemory:
    """Portable deterministic memory scoped by the evaluator to one mechanic."""

    transitions: dict[tuple[str, str, str], int] = field(default_factory=dict)
    attempts: dict[tuple[str, str], int] = field(default_factory=dict)
    action_sets: dict[str, tuple[str, ...]] = field(default_factory=dict)
    concepts_by_state: dict[str, tuple[str, ...]] = field(default_factory=dict)
    target_state_digest: str | None = None
    feature_edges: dict[str, FrozenMap] = field(default_factory=dict)
    semantic_attempts: dict[tuple[str, str], int] = field(default_factory=dict)
    rule_records: dict[str, FrozenMap] = field(default_factory=dict)

    def register_actions(self, state_digest: str, action_ids: Sequence[str]) -> None:
        normalized = tuple(sorted(action_ids))
        prior = self.action_sets.get(state_digest)
        if prior is not None and prior != normalized:
            # A changing set is retained as its union; the trace still binds each actual set.
            normalized = tuple(sorted(set(prior) | set(normalized)))
        self.action_sets[state_digest] = normalized

    def record(
        self,
        *,
        before_digest: str,
        action_id: str,
        after_digest: str,
        concepts: Sequence[str],
        success: bool,
    ) -> None:
        key = (before_digest, action_id, after_digest)
        self.transitions[key] = self.transitions.get(key, 0) + 1
        attempt = (before_digest, action_id)
        self.attempts[attempt] = self.attempts.get(attempt, 0) + 1
        self.concepts_by_state[before_digest] = tuple(concepts)
        if success:
            self.target_state_digest = after_digest

    def confirm_provisional_rules(
        self,
        *,
        before: FrozenMap,
        action_signature: str,
        after: FrozenMap,
        confirmation_edge_ref: str,
    ) -> tuple[str, ...]:
        """Confirm only rules emitted before this independently observed edge."""

        current_ordinal = len(self.feature_edges)
        confirmed: list[str] = []
        rejected: list[str] = []
        for key, record in sorted(self.rule_records.items()):
            if record["rule"]["action_signature"] != action_signature:
                continue
            rule = validate_rule_ir(record["rule"])
            try:
                predicted = evaluate_rule_ir(rule, before)
                output_path = rule["output_path"]
                matched = (
                    type(after.get(output_path)) is int
                    and predicted[output_path] == after[output_path]
                )
            except (KeyError, TypeError, ValueError):
                matched = False
            if not matched:
                rejected.append(key)
                continue
            if confirmation_edge_ref in rule["support_edge_refs"]:
                # Repeating an edge used to fit a rule is not a new
                # prequential witness.
                continue
            if record["status"] == "usable":
                # Every later witness is a fail-closed recheck.  A prior
                # confirmation cannot keep a falsified hypothesis alive.
                continue
            if (
                record["status"] != "provisional"
                or record["emitted_ordinal"] > current_ordinal
            ):
                continue
            self.rule_records[key] = FrozenMap(
                {
                    **record.to_dict(),
                    "confirmation_edge_refs": [confirmation_edge_ref],
                    "status": "usable",
                }
            )
            confirmed.append(canonical_digest(rule))
        for key in rejected:
            del self.rule_records[key]
        return tuple(sorted(confirmed))

    def record_feature_edge(
        self,
        *,
        edge_ref: str,
        before: FrozenMap,
        action_signature: str,
        after: FrozenMap,
    ) -> None:
        if edge_ref in self.feature_edges:
            prior = self.feature_edges[edge_ref]
            expected = {
                "action_signature": action_signature,
                "after": after.to_dict(),
                "before": before.to_dict(),
                "edge_ref": edge_ref,
                "ordinal": prior["ordinal"],
            }
            if prior.to_dict() != expected:
                raise ValueError("feature edge identity collision")
            return
        if len(self.feature_edges) >= MAX_RULE_PLAN_NODES:
            raise ValueError("feature transition memory exceeds bounded edge count")
        self.feature_edges[edge_ref] = FrozenMap(
            {
                "action_signature": action_signature,
                "after": after.to_dict(),
                "before": before.to_dict(),
                "edge_ref": edge_ref,
                "ordinal": len(self.feature_edges),
            }
        )
        attempt_key = (canonical_digest(before), action_signature)
        self.semantic_attempts[attempt_key] = self.semantic_attempts.get(attempt_key, 0) + 1

    def induce_provisional_rules(self, action_signature: str) -> tuple[str, ...]:
        """Emit bounded provisional rules; a future edge must confirm them."""

        edges = [
            edge
            for edge in sorted(self.feature_edges.values(), key=lambda item: item["ordinal"])
            if edge["action_signature"] == action_signature
        ]
        if len(edges) < MIN_DISTINCT_RULE_INPUTS:
            return ()
        before_rows = [FrozenMap(edge["before"]) for edge in edges]
        after_rows = [FrozenMap(edge["after"]) for edge in edges]
        common_paths = set(before_rows[0]) & set(after_rows[0])
        for row in (*before_rows[1:], *after_rows[1:]):
            common_paths &= set(row)
        common_paths = {
            path
            for path in common_paths
            if all(
                type(before.get(path)) is int and type(after.get(path)) is int
                for before, after in zip(before_rows, after_rows)
            )
        }
        emitted: list[str] = []
        for output_path in sorted(common_paths):
            if not any(
                before[output_path] != after[output_path]
                for before, after in zip(before_rows, after_rows)
            ):
                continue
            for input_path in sorted(common_paths):
                if (
                    len({before[input_path] for before in before_rows})
                    < MIN_DISTINCT_RULE_INPUTS
                ):
                    continue
                for context_path in sorted(common_paths - {output_path}):
                    moduli = {
                        before[context_path]
                        for before, after in zip(before_rows, after_rows)
                        if before[context_path] == after[context_path]
                        and before[context_path] > 1
                    }
                    if len(moduli) != 1 or any(
                        before[context_path] != after[context_path]
                        for before, after in zip(before_rows, after_rows)
                    ):
                        continue
                    modulus = next(iter(moduli))
                    fitting: list[tuple[int, int, tuple[int, int]]] = []
                    for multiplier in range(
                        -COEFFICIENT_SEARCH_BOUND,
                        COEFFICIENT_SEARCH_BOUND + 1,
                    ):
                        for offset in range(
                            -COEFFICIENT_SEARCH_BOUND,
                            COEFFICIENT_SEARCH_BOUND + 1,
                        ):
                            if all(
                                (multiplier * before[input_path] + offset) % modulus
                                == after[output_path]
                                for before, after in zip(before_rows, after_rows)
                            ):
                                # Two affine programs have the same full-domain
                                # predictions modulo m exactly when both
                                # coefficients share their residues.  Comparing
                                # residues avoids work proportional to an
                                # untrusted observation integer.
                                prediction_identity = (
                                    multiplier % modulus,
                                    offset % modulus,
                                )
                                fitting.append(
                                    (multiplier, offset, prediction_identity)
                                )
                    if not fitting:
                        continue
                    prediction_functions = {item[2] for item in fitting}
                    if len(prediction_functions) != 1:
                        # Exact fit on observed points is not enough.
                        continue
                    multiplier, offset, _predictions = min(
                        fitting,
                        key=lambda item: (
                            abs(item[0]) + abs(item[1]),
                            abs(item[0]),
                            abs(item[1]),
                            item[0],
                            item[1],
                        ),
                    )
                    rule = validate_rule_ir(
                        {
                            "schema_version": RULE_IR_SCHEMA_VERSION,
                            "action_signature": action_signature,
                            "input_path": input_path,
                            "output_path": output_path,
                            "context_path": context_path,
                            "expression": _affine_expression(
                                input_path=input_path,
                                context_path=context_path,
                                multiplier=multiplier,
                                offset=offset,
                            ),
                            "support_edge_refs": [
                                edge["edge_ref"] for edge in edges
                            ],
                            "hypothesis": True,
                        }
                    )
                    key = _rule_key(rule)
                    existing = self.rule_records.get(key)
                    if existing is not None and existing["status"] in {
                        "provisional",
                        "usable",
                    }:
                        continue
                    if len(self.rule_records) >= MAX_RULE_HYPOTHESES:
                        return tuple(sorted(emitted))
                    self.rule_records[key] = FrozenMap(
                        {
                            "confirmation_edge_refs": [],
                            "emitted_ordinal": len(self.feature_edges),
                            "rule": rule.to_dict(),
                            "rule_key": key,
                            "status": "provisional",
                        }
                    )
                    emitted.append(canonical_digest(rule))
        return tuple(sorted(emitted))

    def usable_rules(self) -> tuple[FrozenMap, ...]:
        return _usable_rule_irs(self.rule_records)

    def provisional_rules(self) -> tuple[FrozenMap, ...]:
        return _provisional_rule_irs(self.rule_records)

    def hypothesis_rules(self) -> tuple[FrozenMap, ...]:
        """Return every currently retained hypothesis, including provisional ones."""

        values = {
            _rule_key(record["rule"]): validate_rule_ir(record["rule"])
            for record in self.rule_records.values()
            if record["status"] in {"provisional", "usable"}
        }
        return tuple(sorted(values.values(), key=canonical_digest))

    def export(self) -> dict[str, Any]:
        return {
            "action_sets": [
                {"state": state, "actions": list(actions)}
                for state, actions in sorted(self.action_sets.items())
            ],
            "attempts": [
                {"state": state, "action": action, "count": count}
                for (state, action), count in sorted(self.attempts.items())
            ],
            "concepts_by_state": [
                {"state": state, "concepts": list(concepts)}
                for state, concepts in sorted(self.concepts_by_state.items())
            ],
            "feature_edges": [
                edge.to_dict()
                for edge in sorted(
                    self.feature_edges.values(),
                    key=lambda item: (item["ordinal"], item["edge_ref"]),
                )
            ],
            "rule_records": [
                record.to_dict()
                for _key, record in sorted(self.rule_records.items())
            ],
            "schema_version": MEMORY_SCHEMA_VERSION,
            "semantic_attempts": [
                {
                    "feature_state": state,
                    "action_signature": signature,
                    "count": count,
                }
                for (state, signature), count in sorted(self.semantic_attempts.items())
            ],
            "target_state_digest": self.target_state_digest,
            "transitions": [
                {
                    "from": before,
                    "action": action,
                    "to": after,
                    "count": count,
                }
                for (before, action, after), count in sorted(self.transitions.items())
            ],
        }

    @classmethod
    def load(cls, value: Mapping[str, Any]) -> "InteractivePolicyMemory":
        frozen = bounded_mapping(value, name="policy memory")
        raw = frozen.to_dict()
        schema = raw.get("schema_version")
        if schema not in {LEGACY_MEMORY_SCHEMA_VERSION, MEMORY_SCHEMA_VERSION}:
            raise ValueError("unsupported policy memory schema")
        memory = cls(target_state_digest=raw.get("target_state_digest"))
        for item in raw.get("transitions", []):
            count = item.get("count")
            if type(count) is not int or count <= 0:
                raise ValueError("transition count must be positive")
            memory.transitions[(item["from"], item["action"], item["to"])] = count
        for item in raw.get("attempts", []):
            count = item.get("count")
            if type(count) is not int or count <= 0:
                raise ValueError("attempt count must be positive")
            memory.attempts[(item["state"], item["action"])] = count
        for item in raw.get("action_sets", []):
            memory.action_sets[item["state"]] = tuple(sorted(item["actions"]))
        for item in raw.get("concepts_by_state", []):
            memory.concepts_by_state[item["state"]] = tuple(item["concepts"])
        if schema == MEMORY_SCHEMA_VERSION:
            feature_rows = raw.get("feature_edges", [])
            rule_rows = raw.get("rule_records", [])
            semantic_rows = raw.get("semantic_attempts", [])
            if (
                not isinstance(feature_rows, list)
                or len(feature_rows) > MAX_RULE_PLAN_NODES
            ):
                raise ValueError("feature edge rows exceed bounded count")
            if (
                not isinstance(rule_rows, list)
                or len(rule_rows) > MAX_RULE_HYPOTHESES
            ):
                raise ValueError("rule record rows exceed bounded count")
            if (
                not isinstance(semantic_rows, list)
                or len(semantic_rows) > MAX_RULE_PLAN_NODES
            ):
                raise ValueError("semantic attempt rows exceed bounded count")
            valid_edge_refs = {
                canonical_id(
                    "transition_edge",
                    {"action_id": action, "from": before, "to": after},
                )[0]
                for before, action, after in memory.transitions
            }
            for item in feature_rows:
                edge = FrozenMap(item)
                if set(edge) != {
                    "action_signature",
                    "after",
                    "before",
                    "edge_ref",
                    "ordinal",
                }:
                    raise ValueError("feature edge fields mismatch")
                edge_ref = edge["edge_ref"]
                if (
                    not isinstance(edge_ref, str)
                    or edge_ref not in valid_edge_refs
                    or edge_ref in memory.feature_edges
                    or type(edge["ordinal"]) is not int
                    or edge["ordinal"] != len(memory.feature_edges)
                ):
                    raise ValueError("feature edges must have unique contiguous ordinals")
                signature = edge["action_signature"]
                if (
                    not isinstance(signature, str)
                    or len(signature) != 64
                    or any(
                        character not in "0123456789abcdef"
                        for character in signature
                    )
                ):
                    raise ValueError("feature edge action signature is invalid")
                before = FrozenMap(edge["before"])
                after = FrozenMap(edge["after"])
                if (
                    not before
                    or not after
                    or any(type(item) is not int for item in before.values())
                    or any(type(item) is not int for item in after.values())
                ):
                    raise ValueError("feature edge projections are invalid")
                for path in (*before, *after):
                    _pointer_tokens(path)
                memory.feature_edges[edge_ref] = edge
            for item in semantic_rows:
                count = item.get("count")
                key = (item.get("feature_state"), item.get("action_signature"))
                if (
                    type(count) is not int
                    or count <= 0
                    or not all(isinstance(value, str) and value for value in key)
                    or key in memory.semantic_attempts
                ):
                    raise ValueError("semantic attempt row is invalid")
                memory.semantic_attempts[key] = count
            derived_attempts: dict[tuple[str, str], int] = {}
            for edge in memory.feature_edges.values():
                key = (
                    canonical_digest(edge["before"]),
                    edge["action_signature"],
                )
                derived_attempts[key] = derived_attempts.get(key, 0) + 1
            if memory.semantic_attempts != derived_attempts:
                raise ValueError(
                    "semantic attempts do not reconstruct from feature edges"
                )
            for item in rule_rows:
                record = FrozenMap(item)
                if set(record) != {
                    "confirmation_edge_refs",
                    "emitted_ordinal",
                    "rule",
                    "rule_key",
                    "status",
                }:
                    raise ValueError("rule record fields mismatch")
                rule = validate_rule_ir(record["rule"])
                key = _rule_key(rule)
                if (
                    record["rule_key"] != key
                    or key in memory.rule_records
                    or record["status"] not in {"provisional", "usable"}
                    or type(record["emitted_ordinal"]) is not int
                    or not 0 <= record["emitted_ordinal"] <= len(memory.feature_edges)
                    or not isinstance(record["confirmation_edge_refs"], (list, tuple))
                    or (
                        record["status"] == "usable"
                        and len(record["confirmation_edge_refs"]) != 1
                    )
                    or (
                        record["status"] == "provisional"
                        and record["confirmation_edge_refs"]
                    )
                ):
                    raise ValueError("rule record is invalid")
                support = set(rule["support_edge_refs"])
                if not support <= set(memory.feature_edges):
                    raise ValueError("rule support edge is absent from memory")
                confirmation = set(record["confirmation_edge_refs"])
                if not confirmation <= set(memory.feature_edges):
                    raise ValueError("rule confirmation edge is absent from memory")
                if support & confirmation:
                    raise ValueError(
                        "rule confirmation edge must be distinct from fitting support"
                    )
                if any(
                    memory.feature_edges[edge_ref]["ordinal"]
                    >= record["emitted_ordinal"]
                    for edge_ref in support
                ):
                    raise ValueError("rule support must precede its emission")
                if any(
                    memory.feature_edges[edge_ref]["ordinal"]
                    < record["emitted_ordinal"]
                    for edge_ref in confirmation
                ):
                    raise ValueError("rule confirmation must follow its emission")
                signature = rule["action_signature"]
                signature_edges = sorted(
                    (
                        edge
                        for edge in memory.feature_edges.values()
                        if edge["action_signature"] == signature
                    ),
                    key=lambda edge: edge["ordinal"],
                )
                fitting_edges = [
                    edge
                    for edge in signature_edges
                    if edge["ordinal"] < record["emitted_ordinal"]
                ]
                if (
                    not fitting_edges
                    or record["emitted_ordinal"]
                    != fitting_edges[-1]["ordinal"] + 1
                    or support
                    != {edge["edge_ref"] for edge in fitting_edges}
                ):
                    raise ValueError(
                        "rule fitting support does not reconstruct from chronology"
                    )
                derived = _derive_canonical_affine_rule(
                    action_signature=signature,
                    input_path=rule["input_path"],
                    output_path=rule["output_path"],
                    context_path=rule["context_path"],
                    edges=fitting_edges,
                )
                if derived is None or derived.to_dict() != rule.to_dict():
                    raise ValueError(
                        "rule does not reconstruct from its observed support"
                    )
                later_edges = [
                    edge
                    for edge in signature_edges
                    if edge["ordinal"] >= record["emitted_ordinal"]
                ]
                for edge in later_edges:
                    predicted = evaluate_rule_ir(rule, FrozenMap(edge["before"]))
                    if (
                        predicted[rule["output_path"]]
                        != edge["after"][rule["output_path"]]
                    ):
                        raise ValueError("later edge contradicts retained rule")
                expected_confirmation = (
                    [later_edges[0]["edge_ref"]] if later_edges else []
                )
                expected_status = "usable" if later_edges else "provisional"
                if (
                    record["status"] != expected_status
                    or list(record["confirmation_edge_refs"])
                    != expected_confirmation
                ):
                    raise ValueError(
                        "rule status does not reconstruct from later observation"
                    )
                memory.rule_records[key] = record
            # The v2 canonical export rejects duplicate rows and loose fields.
            if memory.export() != raw:
                raise ValueError("policy memory is not canonical")
        else:
            legacy = memory.export()
            for field in ("feature_edges", "rule_records", "semantic_attempts"):
                legacy.pop(field)
            legacy["schema_version"] = LEGACY_MEMORY_SCHEMA_VERSION
            if legacy != raw:
                raise ValueError("legacy policy memory is not canonical")
        return memory

    @property
    def digest(self) -> str:
        return canonical_digest(self.export())


def _state_token(digest: str) -> str:
    return f"state:{digest}"


def _action_token(state_digest: str, action_id: str) -> str:
    return "action:" + canonical_digest({"state": state_digest, "action": action_id})


class AtanorInteractivePolicy:
    """Learn transitions, exploit verified routes, otherwise explore systematically."""

    def __init__(
        self,
        memory: InteractivePolicyMemory | Mapping[str, Any] | None = None,
    ) -> None:
        if memory is None:
            self.memory = InteractivePolicyMemory()
        elif isinstance(memory, InteractivePolicyMemory):
            self.memory = InteractivePolicyMemory.load(memory.export())
        else:
            self.memory = InteractivePolicyMemory.load(memory)

    def export_memory(self) -> dict[str, Any]:
        return self.memory.export()

    @classmethod
    def from_memory(cls, value: Mapping[str, Any]) -> "AtanorInteractivePolicy":
        return cls(InteractivePolicyMemory.load(value))

    def _graph(
        self,
    ) -> tuple[EventTransitionGraph, dict[str, tuple[str, str, str]]]:
        pairs: dict[tuple[str, str], int] = {}
        action_nodes: dict[str, tuple[str, str, str]] = {}
        for (before, action, after), count in self.memory.transitions.items():
            before_token = _state_token(before)
            action_token = _action_token(before, action)
            after_token = _state_token(after)
            pairs[(before_token, action_token)] = (
                pairs.get((before_token, action_token), 0) + count
            )
            pairs[(action_token, after_token)] = (
                pairs.get((action_token, after_token), 0) + count
            )
            action_nodes[action_token] = (before, action, after)
        return EventTransitionGraph(pairs, event_vocab=set().union(*pairs) if pairs else set()), action_nodes

    @staticmethod
    def _path(
        graph: EventTransitionGraph,
        start: str,
        *,
        target: str | None = None,
        frontier: set[str] | None = None,
    ) -> tuple[str, ...]:
        if target == start or start in (frontier or set()):
            return (start,)
        queue: deque[tuple[str, tuple[str, ...]]] = deque([(start, (start,))])
        seen = {start}
        while queue:
            node, path = queue.popleft()
            for edge in graph.successors(node, margin=0.6):
                if edge.target in seen:
                    continue
                next_path = path + (edge.target,)
                if edge.target == target or edge.target in (frontier or set()):
                    return next_path
                seen.add(edge.target)
                queue.append((edge.target, next_path))
        return ()

    def _facts_about(self, subject: str) -> list[tuple[str, str, str]]:
        facts: list[tuple[str, str, str]] = []
        for before, action, after in sorted(self.memory.transitions):
            if before != subject:
                continue
            facts.append((before, "transition", after))
            facts.append((before, f"via:{canonical_digest(action)[:16]}", after))
        return facts

    def _prove_route(
        self,
        *,
        before: str,
        action_id: str,
        after: str,
        target: str,
    ) -> FrozenMap:
        rules = [
            Rule(
                "transition_transitive",
                ("?x", "transition", "?z"),
                [("?x", "transition", "?y"), ("?y", "transition", "?z")],
            )
        ]
        deliberator = Deliberator(
            self._facts_about,
            rules=rules,
            with_kernels=False,
            max_depth=16,
            budget=4_000,
        )
        edge_relation = f"via:{canonical_digest(action_id)[:16]}"
        edge = deliberator.can_prove(before, edge_relation, after)
        route = (
            {"provable": True, "hops": 0, "trail": "target reached by selected edge"}
            if after == target
            else deliberator.can_prove(after, "transition", target)
        )
        grounded = bool(edge.get("provable") and route.get("provable"))

        def stable(item: Mapping[str, Any]) -> dict[str, Any]:
            proof = item.get("proof")
            return {
                "depth": int(item.get("depth", 0)),
                "hops": int(item.get("hops", 0)),
                "proof": proof.to_dict() if hasattr(proof, "to_dict") else None,
                "provable": bool(item.get("provable")),
                "trail": str(item.get("trail", "")),
            }

        return FrozenMap(
            {
                "edge": stable(edge),
                "grounded": grounded,
                "route": stable(route),
                "selector": "reasoning_vm.deliberator",
                "target_state_digest": target,
                "transition_rule_hypotheses": [
                    rule.to_dict() for rule in self.memory.hypothesis_rules()
                ],
            }
        )

    def _current_hypothesis_evidence(self, selector: str) -> FrozenMap:
        return FrozenMap(
            {
                "grounded": False,
                "selector": selector,
                "transition_rule_hypotheses": [
                    rule.to_dict() for rule in self.memory.hypothesis_rules()
                ],
            }
        )

    @staticmethod
    def _resonance(
        perception: PerceptionBundle,
        action: ActionOption,
    ) -> tuple[float, tuple[str, ...]]:
        cues = [action.action_id]
        cues.extend(_collect_concepts(action.payload))
        score, grounding = resonance(list(perception.concepts), cues, use_graph=False)
        return float(score), tuple(grounding)

    @staticmethod
    def _tie_key(
        *,
        policy_seed: int,
        state_digest: str,
        action_id: str,
    ) -> str:
        return canonical_digest(
            {
                "action_id": action_id,
                "policy_seed": policy_seed,
                "state_digest": state_digest,
            }
        )

    def _rule_successor(
        self,
        projection: FrozenMap,
        action_signature: str,
    ) -> tuple[FrozenMap, tuple[FrozenMap, ...]] | None:
        rules = tuple(
            rule
            for rule in self.memory.usable_rules()
            if rule["action_signature"] == action_signature
        )
        if not rules:
            return None
        output_paths = [rule["output_path"] for rule in rules]
        if len(output_paths) != len(set(output_paths)):
            return None
        result = projection.to_dict()
        try:
            for rule in rules:
                predicted = evaluate_rule_ir(rule, projection)
                result[rule["output_path"]] = predicted[rule["output_path"]]
        except (KeyError, TypeError, ValueError):
            return None
        return FrozenMap(result), rules

    def _select_rule_plan(
        self,
        *,
        perception: PerceptionBundle,
        valid_actions: Sequence[ActionOption],
        valid_actions_digest: str,
        policy_seed: int,
        goal: GoalIR,
    ) -> ActionProposal | None:
        try:
            constraints = extract_goal_constraints(goal)
            root_path = _constraint_projection_root(constraints)
            if root_path is None:
                return None
            start = numeric_feature_projection(
                perception.observation,
                root_path=root_path,
            )
        except (KeyError, TypeError, ValueError):
            return None
        if (
            not constraints
            or not start
            or any(path["path"] not in start for path in constraints)
            or _goal_satisfied(start, constraints)
        ):
            return None

        signature_to_actions: dict[str, list[ActionOption]] = {}
        for action in valid_actions:
            signature = action_payload_signature(action)
            if signature is not None:
                signature_to_actions.setdefault(signature, []).append(action)
        # A semantic signature must identify exactly one currently valid action.
        signature_to_action = {
            signature: actions[0]
            for signature, actions in signature_to_actions.items()
            if len(actions) == 1
        }
        available_signatures = set(signature_to_action) & {
            rule["action_signature"] for rule in self.memory.usable_rules()
        }
        if not available_signatures:
            return None

        start_token = f"feature:{canonical_digest(start)}"
        queue: deque[tuple[FrozenMap, tuple[dict[str, Any], ...]]] = deque(
            [(start, ())]
        )
        seen = {canonical_digest(start)}
        graph_pairs: dict[tuple[str, str], int] = {}
        plan_candidates: list[tuple[dict[str, Any], ...]] = []
        while queue and len(seen) <= MAX_RULE_PLAN_NODES:
            state, plan = queue.popleft()
            if len(plan) >= MAX_RULE_PLAN_DEPTH:
                continue
            state_token = f"feature:{canonical_digest(state)}"
            for signature in sorted(available_signatures):
                successor = self._rule_successor(state, signature)
                if successor is None:
                    continue
                next_state, rules = successor
                action_token = "feature_action:" + canonical_digest(
                    {"from": state, "action_signature": signature}
                )
                next_token = f"feature:{canonical_digest(next_state)}"
                graph_pairs[(state_token, action_token)] = 1
                graph_pairs[(action_token, next_token)] = 1
                step = {
                    "action_signature": signature,
                    "after": next_state.to_dict(),
                    "before": state.to_dict(),
                    "rule_digests": sorted(canonical_digest(rule) for rule in rules),
                }
                next_plan = plan + (step,)
                if _goal_satisfied(next_state, constraints):
                    if next_plan[0]["action_signature"] in signature_to_action:
                        plan_candidates.append(next_plan)
                    continue
                digest = canonical_digest(next_state)
                if digest not in seen:
                    seen.add(digest)
                    queue.append((next_state, next_plan))
        if not plan_candidates or not graph_pairs:
            return None

        def candidate_key(plan: tuple[dict[str, Any], ...]) -> tuple[Any, ...]:
            action = signature_to_action[plan[0]["action_signature"]]
            score, _grounding = self._resonance(perception, action)
            return (
                len(plan),
                -score,
                self._tie_key(
                    policy_seed=policy_seed,
                    state_digest=perception.observation_digest,
                    action_id=action.action_id,
                ),
            )

        selected_plan = min(plan_candidates, key=candidate_key)
        first_signature = selected_plan[0]["action_signature"]
        selected = signature_to_action[first_signature]
        graph = EventTransitionGraph(
            graph_pairs,
            event_vocab=set().union(*graph_pairs),
        )
        target_token = f"feature:{canonical_digest(selected_plan[-1]['after'])}"
        path_items: list[str] = [start_token]
        for step in selected_plan:
            state_token = f"feature:{canonical_digest(step['before'])}"
            action_token = "feature_action:" + canonical_digest(
                {
                    "from": step["before"],
                    "action_signature": step["action_signature"],
                }
            )
            next_token = f"feature:{canonical_digest(step['after'])}"
            if path_items[-1] != state_token:
                return None
            path_items.extend((action_token, next_token))
        graph_path = tuple(path_items)
        if graph_path[-1] != target_token or any(
            right
            not in {
                edge.target for edge in graph.successors(left, margin=0.6)
            }
            for left, right in zip(graph_path, graph_path[1:])
        ):
            return None

        facts = [
            (
                f"feature:{canonical_digest(step['before'])}",
                "transition",
                f"feature:{canonical_digest(step['after'])}",
            )
            for step in selected_plan
        ]

        def facts_about(subject: str) -> list[tuple[str, str, str]]:
            return [fact for fact in facts if fact[0] == subject]

        deliberator = Deliberator(
            facts_about,
            rules=[
                Rule(
                    "transition_transitive",
                    ("?x", "transition", "?z"),
                    [("?x", "transition", "?y"), ("?y", "transition", "?z")],
                )
            ],
            with_kernels=False,
            max_depth=min(MAX_RULE_PLAN_DEPTH, 64),
            budget=4_000,
        )
        route = deliberator.can_prove(start_token, "transition", target_token)
        if route.get("provable") is not True:
            return None
        all_rules = [rule.to_dict() for rule in self.memory.usable_rules()]
        score, grounding = self._resonance(perception, selected)
        proof = FrozenMap(
            {
                "goal_constraint_digest": canonical_digest(
                    [item.to_dict() for item in constraints]
                ),
                "goal_constraints": [item.to_dict() for item in constraints],
                "grounded": True,
                "route": {
                    "depth": int(route.get("depth", 0)),
                    "hops": int(route.get("hops", 0)),
                    "provable": True,
                    "trail": str(route.get("trail", "")),
                },
                "selected_plan": list(selected_plan),
                "selector": "reasoning_vm.deliberator",
                "transition_rule_hypotheses": all_rules,
            }
        )
        return ActionProposal(
            action_id=selected.action_id,
            strategy="typed_rule_goal_plan",
            valid_actions_digest=valid_actions_digest,
            observation_digest=perception.observation_digest,
            transition_graph_path=graph_path,
            deliberator_proof=proof,
            affordance_resonance=score,
            affordance_grounding=grounding,
        )

    def _select_rule_acquisition(
        self,
        *,
        perception: PerceptionBundle,
        valid_actions: Sequence[ActionOption],
        valid_actions_digest: str,
        policy_seed: int,
        goal: GoalIR,
    ) -> ActionProposal | None:
        """Prefer bounded evidence acquisition until each semantic action has a rule."""

        try:
            constraints = extract_goal_constraints(goal)
            root_path = _constraint_projection_root(constraints)
            if root_path is None:
                return None
            if not numeric_feature_projection(
                perception.observation,
                root_path=root_path,
            ):
                return None
        except (KeyError, TypeError, ValueError):
            return None

        signature_to_actions: dict[str, list[ActionOption]] = {}
        for action in valid_actions:
            signature = action_payload_signature(action)
            if signature is not None:
                signature_to_actions.setdefault(signature, []).append(action)
        unique = {
            signature: actions[0]
            for signature, actions in signature_to_actions.items()
            if len(actions) == 1
        }
        if not unique:
            return None
        usable = {
            rule["action_signature"] for rule in self.memory.usable_rules()
        }
        missing = set(unique) - usable
        if not missing:
            return None
        provisional = {
            rule["action_signature"] for rule in self.memory.provisional_rules()
        }
        distinct_inputs: dict[str, int] = {}
        edge_counts: dict[str, int] = {}
        for signature in missing:
            rows = [
                edge
                for edge in self.memory.feature_edges.values()
                if edge["action_signature"] == signature
            ]
            distinct_inputs[signature] = len(
                {canonical_digest(edge["before"]) for edge in rows}
            )
            edge_counts[signature] = len(rows)

        def acquisition_key(item: tuple[str, ActionOption]) -> tuple[Any, ...]:
            signature, action = item
            current_attempts = self.memory.attempts.get(
                (perception.observation_digest, action.action_id),
                0,
            )
            return (
                current_attempts > 0,
                signature not in provisional,
                distinct_inputs[signature],
                edge_counts[signature],
                self._tie_key(
                    policy_seed=policy_seed,
                    state_digest=perception.observation_digest,
                    action_id=action.action_id,
                ),
            )

        _signature, selected = min(
            ((signature, unique[signature]) for signature in missing),
            key=acquisition_key,
        )
        score, grounding = self._resonance(perception, selected)
        return ActionProposal(
            action_id=selected.action_id,
            strategy="bounded_semantic_rule_acquisition",
            valid_actions_digest=valid_actions_digest,
            observation_digest=perception.observation_digest,
            deliberator_proof=self._current_hypothesis_evidence(
                "bounded_semantic_rule_acquisition"
            ),
            affordance_resonance=score,
            affordance_grounding=grounding,
        )

    def select(
        self,
        *,
        perception: PerceptionBundle,
        valid_actions: Sequence[ActionOption],
        valid_actions_digest: str,
        policy_seed: int,
        goal: GoalIR | None = None,
    ) -> ActionProposal | None:
        """Return one proposal from the evaluator-owned set, or honest silence."""

        if not valid_actions:
            return None
        state = perception.observation_digest
        action_by_id = {item.action_id: item for item in valid_actions}
        self.memory.register_actions(state, tuple(action_by_id))
        if goal is not None:
            acquisition = self._select_rule_acquisition(
                perception=perception,
                valid_actions=valid_actions,
                valid_actions_digest=valid_actions_digest,
                policy_seed=policy_seed,
                goal=goal,
            )
            if acquisition is not None:
                return acquisition
            planned = self._select_rule_plan(
                perception=perception,
                valid_actions=valid_actions,
                valid_actions_digest=valid_actions_digest,
                policy_seed=policy_seed,
                goal=goal,
            )
            if planned is not None:
                return planned
        graph, action_nodes = self._graph()

        # First exploit an empirically learned route to a previously observed success.
        target = self.memory.target_state_digest
        if target and state != target:
            path = self._path(
                graph,
                _state_token(state),
                target=_state_token(target),
            )
            if len(path) >= 3 and path[1] in action_nodes:
                before, action_id, after = action_nodes[path[1]]
                if before == state and action_id in action_by_id:
                    proof = self._prove_route(
                        before=before,
                        action_id=action_id,
                        after=after,
                        target=target,
                    )
                    if proof["grounded"] is True:
                        score, grounding = self._resonance(
                            perception,
                            action_by_id[action_id],
                        )
                        return ActionProposal(
                            action_id=action_id,
                            strategy="verified_route_to_observed_success",
                            valid_actions_digest=valid_actions_digest,
                            observation_digest=state,
                            transition_graph_path=path,
                            deliberator_proof=proof,
                            affordance_resonance=score,
                            affordance_grounding=grounding,
                        )

        # Explore an untried action at the current state before revisiting one.
        untried = [
            action
            for action in valid_actions
            if self.memory.attempts.get((state, action.action_id), 0) == 0
        ]
        if untried:
            chosen = min(
                untried,
                key=lambda item: self._tie_key(
                    policy_seed=policy_seed,
                    state_digest=state,
                    action_id=item.action_id,
                ),
            )
            score, grounding = self._resonance(perception, chosen)
            return ActionProposal(
                action_id=chosen.action_id,
                strategy="systematic_untried_action",
                valid_actions_digest=valid_actions_digest,
                observation_digest=state,
                deliberator_proof=self._current_hypothesis_evidence(
                    "bounded_systematic_exploration"
                ),
                affordance_resonance=score,
                affordance_grounding=grounding,
            )

        # When the local state is exhausted, follow a verified path to a known frontier.
        frontier = {
            _state_token(known_state)
            for known_state, actions in self.memory.action_sets.items()
            if any(
                self.memory.attempts.get((known_state, action), 0) == 0
                for action in actions
            )
        }
        path = self._path(
            graph,
            _state_token(state),
            frontier=frontier,
        )
        if len(path) >= 3 and path[1] in action_nodes:
            before, action_id, after = action_nodes[path[1]]
            target_state = path[-1].removeprefix("state:")
            if before == state and action_id in action_by_id:
                proof = self._prove_route(
                    before=before,
                    action_id=action_id,
                    after=after,
                    target=target_state,
                )
                if proof["grounded"] is True:
                    score, grounding = self._resonance(
                        perception,
                        action_by_id[action_id],
                    )
                    return ActionProposal(
                        action_id=action_id,
                        strategy="verified_route_to_unexplored_frontier",
                        valid_actions_digest=valid_actions_digest,
                        observation_digest=state,
                        transition_graph_path=path,
                        deliberator_proof=proof,
                        affordance_resonance=score,
                        affordance_grounding=grounding,
                    )

        # Fully explored or disconnected: least-used deterministic fallback.
        chosen = min(
            valid_actions,
            key=lambda item: (
                self.memory.attempts.get((state, item.action_id), 0),
                self._tie_key(
                    policy_seed=policy_seed,
                    state_digest=state,
                    action_id=item.action_id,
                ),
            ),
        )
        score, grounding = self._resonance(perception, chosen)
        return ActionProposal(
            action_id=chosen.action_id,
            strategy="least_used_deterministic_fallback",
            valid_actions_digest=valid_actions_digest,
            observation_digest=state,
            deliberator_proof=self._current_hypothesis_evidence(
                "least_used_deterministic_fallback"
            ),
            affordance_resonance=score,
            affordance_grounding=grounding,
        )

    def learn(
        self,
        *,
        perception: PerceptionBundle,
        action_id: str,
        post_observation: Mapping[str, Any],
        success: bool,
        action: ActionOption | None = None,
        goal: GoalIR | None = None,
    ) -> tuple[str, ProofCandidate]:
        """Record an observed edge and return its non-authoritative proof candidate."""

        if action is not None and action.action_id != action_id:
            raise ValueError("learning action payload does not match selected action")
        after = bounded_mapping(post_observation, name="post-step observation")
        after_digest = opaque_digest(after)
        self.memory.record(
            before_digest=perception.observation_digest,
            action_id=action_id,
            after_digest=after_digest,
            concepts=perception.concepts,
            success=success,
        )
        edge_id = canonical_id(
            "transition_edge",
            {
                "action_id": action_id,
                "from": perception.observation_digest,
                "to": after_digest,
            },
        )[0]
        signature = action_payload_signature(action) if action is not None else None
        before_features = FrozenMap()
        after_features = FrozenMap()
        if goal is not None:
            try:
                constraints = extract_goal_constraints(goal)
                root_path = _constraint_projection_root(constraints)
                if root_path is not None:
                    before_features = numeric_feature_projection(
                        perception.observation,
                        root_path=root_path,
                    )
                    after_features = numeric_feature_projection(
                        after,
                        root_path=root_path,
                    )
            except (KeyError, TypeError, ValueError):
                before_features = FrozenMap()
                after_features = FrozenMap()
        confirmed_rule_digests: tuple[str, ...] = ()
        emitted_rule_digests: tuple[str, ...] = ()
        if signature is not None and before_features and after_features:
            confirmed_rule_digests = self.memory.confirm_provisional_rules(
                before=before_features,
                action_signature=signature,
                after=after_features,
                confirmation_edge_ref=edge_id,
            )
            self.memory.record_feature_edge(
                edge_ref=edge_id,
                before=before_features,
                action_signature=signature,
                after=after_features,
            )
            emitted_rule_digests = self.memory.induce_provisional_rules(signature)
        predicted = ClaimEnvelope(
            statement=f"Observed transition edge {edge_id}.",
            tier=EpistemicTier.INFERRED,
            source_claim_ids=(perception.claim.contract_id,),
            lineage_tiers=(EpistemicTier.OBSERVED,),
            metadata={
                "action_id": action_id,
                "action_signature": signature,
                "from_observation_digest": perception.observation_digest,
                "to_observation_digest": after_digest,
            },
        )
        proof = ProofCandidate(
            claim_id=predicted.contract_id,
            method="environment_transition_witness",
            premise_claim_ids=(perception.claim.contract_id,),
            derivation_steps=(
                "Bind the selected action to the evaluator-owned valid set.",
                "Observe the evaluator-owned post-step state.",
            ),
            verifier_refs=(edge_id,),
            metadata={
                "action_signature": signature,
                "after_features": after_features.to_dict(),
                "before_features": before_features.to_dict(),
                "confirmed_rule_digests": list(confirmed_rule_digests),
                "edge_id": edge_id,
                "emitted_provisional_rule_digests": list(emitted_rule_digests),
                "provisional_transition_rule_hypotheses": [
                    rule.to_dict() for rule in self.memory.provisional_rules()
                ],
                "target_claim": predicted.to_dict(),
                "transition_rule_hypotheses": [
                    rule.to_dict() for rule in self.memory.hypothesis_rules()
                ],
            },
        )
        return edge_id, proof


def _proof_mapping(value: ProofCandidate | Mapping[str, Any] | FrozenMap) -> dict[str, Any]:
    if isinstance(value, ProofCandidate):
        return value.to_dict()
    if isinstance(value, FrozenMap):
        return value.to_dict()
    if isinstance(value, Mapping):
        return FrozenMap(value).to_dict()
    raise TypeError("proof must be a ProofCandidate or mapping")


def verify_rule_plan_proof(
    *,
    proof: Mapping[str, Any] | FrozenMap,
    goal: GoalIR,
    observation: Mapping[str, Any] | FrozenMap,
    action: ActionOption,
    memory: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently reconstruct a rule-backed proposal from bound inputs."""

    findings: list[str] = []
    try:
        raw = proof.to_dict() if isinstance(proof, FrozenMap) else FrozenMap(proof).to_dict()
        policy_memory = InteractivePolicyMemory.load(memory)
        expected_rules = [
            rule.to_dict() for rule in policy_memory.usable_rules()
        ]
        supplied_rules = raw.get("transition_rule_hypotheses")
        if supplied_rules != expected_rules:
            findings.append("usable_rule_set_mismatch")
        constraints = extract_goal_constraints(goal)
        root_path = _constraint_projection_root(constraints)
        if root_path is None:
            raise ValueError("goal constraints do not share one projection root")
        expected_constraints = [item.to_dict() for item in constraints]
        if raw.get("goal_constraints") != expected_constraints:
            findings.append("goal_constraints_mismatch")
        if raw.get("goal_constraint_digest") != canonical_digest(expected_constraints):
            findings.append("goal_constraint_digest_mismatch")
        if (
            raw.get("selector") != "reasoning_vm.deliberator"
            or raw.get("grounded") is not True
        ):
            findings.append("rule_plan_selector_mismatch")
        plan = raw.get("selected_plan")
        if (
            not isinstance(plan, list)
            or not plan
            or len(plan) > MAX_RULE_PLAN_DEPTH
        ):
            findings.append("selected_plan_invalid")
            plan = []
        current = numeric_feature_projection(
            observation,
            root_path=root_path,
        )
        selected_signature = action_payload_signature(action)
        rules_by_signature: dict[str, list[FrozenMap]] = {}
        for item in expected_rules:
            rule = validate_rule_ir(item)
            rules_by_signature.setdefault(rule["action_signature"], []).append(rule)
        for index, step in enumerate(plan):
            if not isinstance(step, Mapping) or set(step) != {
                "action_signature",
                "after",
                "before",
                "rule_digests",
            }:
                findings.append(f"plan_{index}:fields_mismatch")
                break
            if step["before"] != current.to_dict():
                findings.append(f"plan_{index}:before_mismatch")
                break
            signature = step["action_signature"]
            rules = sorted(
                rules_by_signature.get(signature, []),
                key=canonical_digest,
            )
            if not rules:
                findings.append(f"plan_{index}:rule_missing")
                break
            if step["rule_digests"] != sorted(canonical_digest(rule) for rule in rules):
                findings.append(f"plan_{index}:rule_digest_mismatch")
                break
            output_paths = [rule["output_path"] for rule in rules]
            if len(output_paths) != len(set(output_paths)):
                findings.append(f"plan_{index}:ambiguous_output")
                break
            result = current.to_dict()
            for rule in rules:
                evaluated = evaluate_rule_ir(rule, current)
                result[rule["output_path"]] = evaluated[rule["output_path"]]
            current = FrozenMap(result)
            if step["after"] != current.to_dict():
                findings.append(f"plan_{index}:after_mismatch")
                break
        if plan:
            if plan[0]["action_signature"] != selected_signature:
                findings.append("selected_action_signature_mismatch")
            if not _goal_satisfied(current, constraints):
                findings.append("plan_does_not_satisfy_goal")
    except (KeyError, TypeError, ValueError) as exc:
        findings.append(f"verification_error:{type(exc).__name__}:{exc}")
    return {"findings": findings, "passed": not findings}


def verify_learning_proof(
    *,
    proof: ProofCandidate | Mapping[str, Any] | FrozenMap,
    before_observation: Mapping[str, Any] | FrozenMap,
    action: ActionOption,
    after_observation: Mapping[str, Any] | FrozenMap,
    edge_ref: str,
    memory_before: Mapping[str, Any],
    memory_after: Mapping[str, Any],
    goal: GoalIR | None = None,
) -> dict[str, Any]:
    """Bind learning evidence and real prequential chronology to memory."""

    findings: list[str] = []
    try:
        raw = _proof_mapping(proof)
        metadata = raw.get("metadata")
        if not isinstance(metadata, Mapping):
            raise ValueError("learning proof metadata missing")
        before = bounded_mapping(before_observation, name="learning verifier before")
        after = bounded_mapping(after_observation, name="learning verifier after")
        expected_edge = canonical_id(
            "transition_edge",
            {
                "action_id": action.action_id,
                "from": opaque_digest(before),
                "to": opaque_digest(after),
            },
        )[0]
        if edge_ref != expected_edge or metadata.get("edge_id") != expected_edge:
            findings.append("learning_edge_mismatch")
        signature = action_payload_signature(action)
        if metadata.get("action_signature") != signature:
            findings.append("learning_action_signature_mismatch")
        before_features = FrozenMap()
        after_features = FrozenMap()
        if goal is not None:
            constraints = extract_goal_constraints(goal)
            root_path = _constraint_projection_root(constraints)
            if root_path is not None:
                before_features = numeric_feature_projection(
                    before,
                    root_path=root_path,
                )
                after_features = numeric_feature_projection(
                    after,
                    root_path=root_path,
                )
        if metadata.get("before_features") != before_features.to_dict():
            findings.append("learning_before_features_mismatch")
        if metadata.get("after_features") != after_features.to_dict():
            findings.append("learning_after_features_mismatch")

        prior = InteractivePolicyMemory.load(memory_before)
        current = InteractivePolicyMemory.load(memory_after)
        if signature is not None and before_features and after_features:
            feature_edge = current.feature_edges.get(expected_edge)
            if (
                feature_edge is None
                or feature_edge["action_signature"] != signature
                or feature_edge["before"].to_dict() != before_features.to_dict()
                or feature_edge["after"].to_dict() != after_features.to_dict()
            ):
                findings.append("feature_edge_memory_mismatch")
        expected_hypotheses = [
            rule.to_dict() for rule in current.hypothesis_rules()
        ]
        expected_provisional = [
            rule.to_dict() for rule in current.provisional_rules()
        ]
        if metadata.get("transition_rule_hypotheses") != expected_hypotheses:
            findings.append("learning_hypothesis_rule_set_mismatch")
        if (
            metadata.get("provisional_transition_rule_hypotheses")
            != expected_provisional
        ):
            findings.append("learning_provisional_rule_set_mismatch")

        actually_confirmed: list[str] = []
        for key, record in current.rule_records.items():
            prior_record = prior.rule_records.get(key)
            if (
                record["status"] == "usable"
                and record["confirmation_edge_refs"] == (expected_edge,)
                and prior_record is not None
                and prior_record["status"] == "provisional"
                and canonical_digest(record["rule"])
                == canonical_digest(prior_record["rule"])
            ):
                actually_confirmed.append(canonical_digest(record["rule"]))
        if metadata.get("confirmed_rule_digests") != sorted(actually_confirmed):
            findings.append("prequential_confirmation_mismatch")

        actually_emitted = sorted(
            canonical_digest(record["rule"])
            for key, record in current.rule_records.items()
            if record["status"] == "provisional" and key not in prior.rule_records
        )
        if metadata.get("emitted_provisional_rule_digests") != actually_emitted:
            findings.append("provisional_emission_mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        findings.append(f"verification_error:{type(exc).__name__}:{exc}")
    return {"findings": findings, "passed": not findings}


__all__ = [
    "COEFFICIENT_SEARCH_BOUND",
    "LEGACY_MEMORY_SCHEMA_VERSION",
    "MAX_OPAQUE_JSON_BYTES",
    "MEMORY_SCHEMA_VERSION",
    "RULE_IR_SCHEMA_VERSION",
    "ActionOption",
    "ActionProposal",
    "AtanorInteractivePolicy",
    "InteractivePolicyMemory",
    "PerceptionBundle",
    "action_payload_signature",
    "bounded_mapping",
    "evaluate_rule_ir",
    "extract_goal_constraints",
    "normalize_valid_actions",
    "numeric_feature_projection",
    "opaque_digest",
    "perceive_observation",
    "validate_rule_ir",
    "verify_learning_proof",
    "verify_rule_plan_proof",
]
