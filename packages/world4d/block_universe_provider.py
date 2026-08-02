"""Read-only BlockUniverse provider for the World4D sibling shadow.

This provider creates a private in-memory timeline and never uses the shared
default timeline.  Its result is a proposal for observer telemetry only; the
existing low-grounding BlockUniverse answer bidder remains a separate path.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import islice
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Callable

from packages.cognitive_core.canonical import canonical_digest, canonical_id
from packages.cognitive_core.contracts import EpistemicTier
from packages.temporal_reasoning.block_universe import BlockUniverse
from packages.temporal_reasoning.precedence_field import PrecedenceField
from packages.temporal_reasoning.unified_timeline import Timeline
from packages.world4d.contracts import (
    MAX_METADATA_ITEMS,
    MAX_METADATA_TEXT_BYTES,
    CheckScope,
    CheckVerdict,
    Direction,
    ProviderResultStatus,
    World4DCheck,
    World4DProviderDescriptor,
    World4DProviderResult,
    World4DRequest,
    World4DStep,
    World4DTrajectory,
)


_WORD = re.compile(r"[a-z][a-z\-]{2,}")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRECEDENCE_ARTIFACT = (
    PROJECT_ROOT / "data" / "temporal_reasoning" / "precedence_field.json"
)
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_TOKENS = 250_000


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_frozen_precedence_artifact(
    path: Path,
) -> tuple[PrecedenceField, str]:
    """Load one byte-bound model snapshot without fitting or persisting it."""

    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_file():
        raise ValueError("precedence artifact must be a regular non-symlink file")
    with resolved.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if before.st_size < 1 or before.st_size > MAX_ARTIFACT_BYTES:
            raise ValueError("precedence artifact has an invalid bounded size")
        raw = handle.read(MAX_ARTIFACT_BYTES + 1)
        after = os.fstat(handle.fileno())
    if (
        len(raw) > MAX_ARTIFACT_BYTES
        or len(raw) != after.st_size
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError("precedence artifact changed or exceeded its bounded size")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant: {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("precedence artifact is not strict JSON") from error
    if not isinstance(value, dict) or set(value) != {"phase", "seen"}:
        raise ValueError("precedence artifact must contain only phase and seen")
    phase = value["phase"]
    seen = value["seen"]
    if not isinstance(phase, dict) or not isinstance(seen, dict):
        raise ValueError("precedence artifact phase and seen must be objects")
    if not phase or len(phase) > MAX_ARTIFACT_TOKENS or set(phase) != set(seen):
        raise ValueError("precedence artifact token inventory is invalid")

    clean_phase: dict[str, float] = {}
    clean_seen: dict[str, int] = {}
    for token, coordinate in phase.items():
        if not isinstance(token, str) or not token or len(token) > 256:
            raise ValueError("precedence artifact contains an invalid token")
        if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
            raise ValueError("precedence artifact phase must be numeric")
        number = float(coordinate)
        if not math.isfinite(number):
            raise ValueError("precedence artifact phase must be finite")
        count = seen[token]
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("precedence artifact seen counts must be positive integers")
        clean_phase[token] = number
        clean_seen[token] = count

    return (
        PrecedenceField(phase=clean_phase, seen=clean_seen),
        hashlib.sha256(raw).hexdigest(),
    )


@dataclass(frozen=True, kw_only=True)
class BlockUniverseQuery:
    question: str
    direction: Direction
    anchor_terms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.question, str):
            raise TypeError("question must be a string")
        if len(self.question) > 64 * 1024 or len(
            self.question.encode("utf-8")
        ) > 64 * 1024:
            raise ValueError("question exceeds the bounded provider input")
        if not self.question.strip():
            raise ValueError("question must be non-empty")
        object.__setattr__(self, "direction", Direction(self.direction))
        if len(self.anchor_terms) > MAX_METADATA_ITEMS:
            raise ValueError(
                f"anchor_terms cannot contain more than {MAX_METADATA_ITEMS} items"
            )
        terms_list: list[str] = []
        for term in self.anchor_terms:
            if not isinstance(term, str):
                raise TypeError("anchor_terms must contain strings")
            if len(term) > MAX_METADATA_TEXT_BYTES or len(
                term.encode("utf-8")
            ) > MAX_METADATA_TEXT_BYTES:
                raise ValueError(
                    "anchor_terms entries exceed the bounded UTF-8 size"
                )
            normalized = term.lower().strip()
            if not normalized:
                continue
            terms_list.append(normalized)
        terms = tuple(terms_list)
        if len(terms) != len(set(terms)):
            raise ValueError("anchor_terms cannot contain duplicates")
        object.__setattr__(self, "anchor_terms", terms)


class BlockUniverseShadowProvider:
    """Inference-only adapter over the existing learned temporal field."""

    descriptor = World4DProviderDescriptor(
        provider_id="block_universe_shadow",
        provider_version="v1",
        input_kind="bounded_text_temporal_query",
        source_refs=(
            "packages/temporal_reasoning/block_universe.py",
            "packages/temporal_reasoning/unified_timeline.py",
        ),
    )

    def __init__(
        self,
        *,
        universe_factory: Callable[[Timeline], BlockUniverse] | None = None,
        artifact_path: str | Path | None = None,
    ) -> None:
        self._universe_factory = universe_factory
        self._artifact_path = (
            Path(artifact_path)
            if artifact_path is not None
            else DEFAULT_PRECEDENCE_ARTIFACT
        )

    def _universe(self, timeline: Timeline) -> tuple[BlockUniverse, str | None]:
        if self._universe_factory is not None:
            return self._universe_factory(timeline), None
        field, artifact_digest = _load_frozen_precedence_artifact(
            self._artifact_path
        )
        return BlockUniverse(timeline, field), artifact_digest

    @staticmethod
    def _artifact_limitations(artifact_digest: str | None) -> tuple[str, ...]:
        if artifact_digest is None:
            return ("fixture_provider_has_no_bound_model_artifact",)
        return (
            "local_precedence_artifact_is_unsigned",
            "no_external_artifact_attestation",
        )

    @staticmethod
    def _checks() -> tuple[World4DCheck, ...]:
        return (
            World4DCheck(
                check_id="physical_consistency",
                scope=CheckScope.PHYSICAL,
                verdict=CheckVerdict.NOT_RUN,
            ),
            World4DCheck(
                check_id="temporal_logical_consistency",
                scope=CheckScope.TEMPORAL_LOGICAL,
                verdict=CheckVerdict.NOT_RUN,
            ),
            World4DCheck(
                check_id="statistical_calibration",
                scope=CheckScope.STATISTICAL,
                verdict=CheckVerdict.NOT_RUN,
            ),
        )

    @staticmethod
    def _require_hypothesis(row: object) -> dict:
        if not isinstance(row, dict) or row.get("hypothesis") is not True:
            raise ValueError("BlockUniverse output must remain explicitly hypothetical")
        return row

    @staticmethod
    def _confidence(row: dict) -> float | None:
        value = row.get("confidence")
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("BlockUniverse confidence must be numeric or null")
        number = float(value)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise ValueError("BlockUniverse confidence must be finite within [0, 1]")
        return number

    def _forward(
        self,
        *,
        request: World4DRequest,
        query: BlockUniverseQuery,
        universe: BlockUniverse,
        artifact_digest: str | None,
    ) -> World4DProviderResult:
        rows = [
            self._require_hypothesis(row)
            for row in islice(
                universe.project_forward(horizon=request.horizon),
                request.horizon,
            )
        ]
        if not rows:
            return self._abstention(
                "no_grounded_forward_hypothesis",
                artifact_digest=artifact_digest,
            )
        initial_digest = canonical_digest(
            {
                "direction": request.direction.value,
                "source_digest": request.source_digest,
            }
        )
        steps = tuple(
            World4DStep(
                step_index=index,
                state_digest=canonical_digest(row),
                confidence=self._confidence(row),
                tier=EpistemicTier.PREDICTED,
            )
            for index, row in enumerate(rows, start=1)
        )
        branch_id, _ = canonical_id(
            "world4d_branch",
            {
                "initial_state_digest": initial_digest,
                "step_digests": [step.state_digest for step in steps],
            },
        )
        trajectory = World4DTrajectory(
            branch_id=branch_id,
            initial_state_digest=initial_digest,
            steps=steps,
            checks=self._checks(),
        )
        return World4DProviderResult(
            provider_id=self.descriptor.provider_id,
            provider_version=self.descriptor.provider_version,
            status=ProviderResultStatus.PROPOSED,
            trajectories=(trajectory,),
            limitations=(
                "learned_order_hypothesis_not_world_truth",
                "no_physics_check",
                "no_temporal_logic_check",
                "no_calibration_check",
                *self._artifact_limitations(artifact_digest),
            ),
            model_artifact_digest=artifact_digest,
        )

    def _backward(
        self,
        *,
        request: World4DRequest,
        query: BlockUniverseQuery,
        universe: BlockUniverse,
        artifact_digest: str | None,
    ) -> World4DProviderResult:
        field = universe.field
        if field is None:
            return self._abstention(
                "temporal_field_unavailable",
                artifact_digest=artifact_digest,
            )
        terms = query.anchor_terms or tuple(
            match.group(0)
            for match in islice(
                _WORD.finditer(query.question.lower()),
                MAX_METADATA_ITEMS,
            )
        )
        covered = [
            term
            for term in terms
            if term in field.phase and field.seen.get(term, 0) >= 3
        ]
        if not covered:
            return self._abstention(
                "no_grounded_backward_anchor",
                artifact_digest=artifact_digest,
            )
        anchor = max(covered, key=lambda term: field.phase[term])
        rows = [
            self._require_hypothesis(row)
            for row in islice(
                universe.infer_backward(anchor, k=request.branch_limit),
                request.branch_limit,
            )
        ]
        if not rows:
            return self._abstention(
                "no_grounded_backward_hypothesis",
                artifact_digest=artifact_digest,
            )
        initial_digest = canonical_digest(
            {
                "anchor_digest": canonical_digest(anchor),
                "direction": request.direction.value,
                "source_digest": request.source_digest,
            }
        )
        trajectories = []
        for index, row in enumerate(rows):
            step = World4DStep(
                step_index=1,
                state_digest=canonical_digest(row),
                confidence=self._confidence(row),
                tier=EpistemicTier.RETRODICTED,
            )
            branch_id, _ = canonical_id(
                "world4d_branch",
                {
                    "alternative_index": index,
                    "initial_state_digest": initial_digest,
                    "step_digest": step.state_digest,
                },
            )
            trajectories.append(
                World4DTrajectory(
                    branch_id=branch_id,
                    initial_state_digest=initial_digest,
                    steps=(step,),
                    checks=self._checks(),
                )
            )
        return World4DProviderResult(
            provider_id=self.descriptor.provider_id,
            provider_version=self.descriptor.provider_version,
            status=ProviderResultStatus.PROPOSED,
            trajectories=tuple(trajectories),
            limitations=(
                "retrodicted_alternatives_not_observed_history",
                "no_physics_check",
                "no_temporal_logic_check",
                "no_calibration_check",
                *self._artifact_limitations(artifact_digest),
            ),
            model_artifact_digest=artifact_digest,
        )

    def _abstention(
        self,
        reason: str,
        *,
        artifact_digest: str | None,
    ) -> World4DProviderResult:
        return World4DProviderResult(
            provider_id=self.descriptor.provider_id,
            provider_version=self.descriptor.provider_version,
            status=ProviderResultStatus.ABSTAINED,
            trajectories=(),
            limitations=(
                reason,
                *self._artifact_limitations(artifact_digest),
            ),
            model_artifact_digest=artifact_digest,
        )

    def propose(
        self,
        request: World4DRequest,
        payload: object,
    ) -> World4DProviderResult:
        if not isinstance(request, World4DRequest):
            raise TypeError("request must be World4DRequest")
        if not isinstance(payload, BlockUniverseQuery):
            raise TypeError("payload must be BlockUniverseQuery")
        if request.direction is not payload.direction:
            raise ValueError("request and payload direction must match")
        if request.source_digest != canonical_digest(payload.question):
            raise ValueError("request source digest does not match provider payload")
        timeline = Timeline()
        timeline.record("utterance", payload.question, who="shadow_user")
        universe, artifact_digest = self._universe(timeline)
        if request.direction is Direction.FORWARD:
            return self._forward(
                request=request,
                query=payload,
                universe=universe,
                artifact_digest=artifact_digest,
            )
        return self._backward(
            request=request,
            query=payload,
            universe=universe,
            artifact_digest=artifact_digest,
        )
