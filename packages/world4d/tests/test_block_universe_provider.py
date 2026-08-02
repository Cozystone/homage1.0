from __future__ import annotations

import hashlib
import json

import pytest

from packages.cognitive_core import EpistemicTier
from packages.cognitive_core.canonical import canonical_digest
from packages.temporal_reasoning.block_universe import BlockUniverse
from packages.temporal_reasoning.precedence_field import PrecedenceField
from packages.temporal_reasoning.unified_timeline import default_timeline
from packages.world4d.block_universe_provider import DEFAULT_PRECEDENCE_ARTIFACT
from packages.world4d import (
    BlockUniverseQuery,
    BlockUniverseShadowProvider,
    Direction,
    ProviderResultStatus,
    World4DRequest,
)


def _field() -> PrecedenceField:
    return PrecedenceField(
        phase={"plant": -0.9, "grow": -0.3, "harvest": 0.3, "eat": 0.9},
        seen={"plant": 5, "grow": 5, "harvest": 5, "eat": 5},
    )


def _provider() -> BlockUniverseShadowProvider:
    return BlockUniverseShadowProvider(
        universe_factory=lambda timeline: BlockUniverse(timeline, _field())
    )


def _request(question: str, direction: Direction, **kwargs) -> World4DRequest:
    return World4DRequest(
        request_id=f"request_{direction.value}",
        source_kind="temporal_text_query",
        source_digest=canonical_digest(question),
        direction=direction,
        horizon=kwargs.get("horizon", 3),
        branch_limit=kwargs.get("branch_limit", 4),
    )


def test_forward_provider_builds_one_bounded_predicted_chain_without_shared_timeline():
    question = "What happens after the crops grow?"
    shared = default_timeline()
    before = shared.all()
    query = BlockUniverseQuery(question=question, direction=Direction.FORWARD)

    result = _provider().propose(
        _request(question, Direction.FORWARD, horizon=2),
        query,
    )

    assert result.status is ProviderResultStatus.PROPOSED
    assert len(result.trajectories) == 1
    steps = result.trajectories[0].steps
    assert len(steps) == 2
    assert all(step.tier is EpistemicTier.PREDICTED for step in steps)
    assert all(step.hypothesis and not step.accepted_as_fact for step in steps)
    assert shared.all() == before
    assert query.question == question


def test_backward_rows_remain_separate_one_step_retrodicted_branches():
    question = "What led to the harvest?"
    result = _provider().propose(
        _request(question, Direction.BACKWARD, branch_limit=2),
        BlockUniverseQuery(
            question=question,
            direction=Direction.BACKWARD,
            anchor_terms=("harvest",),
        ),
    )

    assert result.status is ProviderResultStatus.PROPOSED
    assert 1 <= len(result.trajectories) <= 2
    assert len({item.branch_id for item in result.trajectories}) == len(
        result.trajectories
    )
    assert all(len(item.steps) == 1 for item in result.trajectories)
    assert all(
        item.steps[0].tier is EpistemicTier.RETRODICTED
        for item in result.trajectories
    )


def test_unknown_query_abstains_without_inventing_a_trajectory():
    question = "What follows zzznonsense?"
    result = _provider().propose(
        _request(question, Direction.FORWARD),
        BlockUniverseQuery(question=question, direction=Direction.FORWARD),
    )
    assert result.status is ProviderResultStatus.ABSTAINED
    assert result.trajectories == ()


def test_missing_hypothesis_marker_is_contract_rejected():
    class ForgedUniverse:
        field = _field()

        def project_forward(self, horizon):
            return [{"step": 1, "event_token": "harvest", "confidence": 0.8}]

    provider = BlockUniverseShadowProvider(
        universe_factory=lambda _timeline: ForgedUniverse()
    )
    question = "What happens after crops grow?"
    try:
        provider.propose(
            _request(question, Direction.FORWARD),
            BlockUniverseQuery(question=question, direction=Direction.FORWARD),
        )
    except ValueError as error:
        assert "hypothetical" in str(error)
    else:
        raise AssertionError("forged bare-fact provider output was accepted")


def test_provider_consumes_only_the_requested_forward_bound():
    class BoundedUniverse:
        field = _field()

        def project_forward(self, horizon):
            for index in range(100):
                if index >= horizon:
                    raise AssertionError("provider consumed beyond horizon")
                yield {
                    "step": index + 1,
                    "event_token": f"event_{index}",
                    "confidence": 0.5,
                    "hypothesis": True,
                }

    provider = BlockUniverseShadowProvider(
        universe_factory=lambda _timeline: BoundedUniverse()
    )
    question = "What happens after crops grow?"
    result = provider.propose(
        _request(question, Direction.FORWARD, horizon=2),
        BlockUniverseQuery(question=question, direction=Direction.FORWARD),
    )

    assert result.status is ProviderResultStatus.PROPOSED
    assert len(result.trajectories[0].steps) == 2


def test_provider_rejects_boolean_confidence():
    class BooleanConfidenceUniverse:
        field = _field()

        def project_forward(self, horizon):
            return [
                {
                    "step": 1,
                    "after": "grow",
                    "event_token": "harvest",
                    "confidence": True,
                    "hypothesis": True,
                }
            ]

    provider = BlockUniverseShadowProvider(
        universe_factory=lambda _timeline: BooleanConfidenceUniverse()
    )
    question = "What happens after crops grow?"

    with pytest.raises(TypeError, match="numeric or null"):
        provider.propose(
            _request(question, Direction.FORWARD),
            BlockUniverseQuery(question=question, direction=Direction.FORWARD),
        )


def test_default_provider_loads_one_byte_bound_artifact_without_dynamic_fit(
    monkeypatch,
    tmp_path,
):
    artifact = tmp_path / "precedence_field.json"
    raw = json.dumps(
        {
            "phase": {
                "plant": -0.9,
                "grow": -0.3,
                "harvest": 0.3,
                "eat": 0.9,
            },
            "seen": {"plant": 5, "grow": 5, "harvest": 5, "eat": 5},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    artifact.write_bytes(raw)

    def forbidden_dynamic_fit(_cls, _timeline):
        raise AssertionError("shadow inference called BlockUniverse.over")

    monkeypatch.setattr(
        BlockUniverse,
        "over",
        classmethod(forbidden_dynamic_fit),
    )
    question = "What happens after the crops grow?"
    result = BlockUniverseShadowProvider(artifact_path=artifact).propose(
        _request(question, Direction.FORWARD, horizon=2),
        BlockUniverseQuery(question=question, direction=Direction.FORWARD),
    )

    assert result.status is ProviderResultStatus.PROPOSED
    assert result.model_artifact_digest == hashlib.sha256(raw).hexdigest()
    assert "local_precedence_artifact_is_unsigned" in result.limitations
    assert "no_external_artifact_attestation" in result.limitations


def test_repository_precedence_artifact_is_compatible_and_byte_bound():
    with DEFAULT_PRECEDENCE_ARTIFACT.open("rb") as handle:
        expected_digest = hashlib.file_digest(handle, "sha256").hexdigest()
    question = "What typically comes after we grow the crops?"

    result = BlockUniverseShadowProvider().propose(
        _request(question, Direction.FORWARD, horizon=3),
        BlockUniverseQuery(question=question, direction=Direction.FORWARD),
    )

    assert result.status is ProviderResultStatus.PROPOSED
    assert result.model_artifact_digest == expected_digest
    assert 1 <= len(result.trajectories[0].steps) <= 3


def test_default_provider_rejects_non_strict_artifact(tmp_path):
    artifact = tmp_path / "precedence_field.json"
    artifact.write_text(
        '{"phase":{"grow":0},"phase":{"harvest":1},"seen":{"harvest":3}}',
        encoding="utf-8",
    )
    question = "What happens after crops grow?"

    with pytest.raises(ValueError, match="strict JSON"):
        BlockUniverseShadowProvider(artifact_path=artifact).propose(
            _request(question, Direction.FORWARD),
            BlockUniverseQuery(question=question, direction=Direction.FORWARD),
        )


def test_provider_query_anchor_metadata_is_bounded():
    with pytest.raises(ValueError, match="more than 16 items"):
        BlockUniverseQuery(
            question="What led to the harvest?",
            direction=Direction.BACKWARD,
            anchor_terms=tuple(f"anchor_{index}" for index in range(17)),
        )


def test_default_provider_rejects_oversized_artifact_before_parsing(tmp_path):
    artifact = tmp_path / "precedence_field.json"
    with artifact.open("wb") as handle:
        handle.truncate(16 * 1024 * 1024 + 1)
    question = "What happens after crops grow?"

    with pytest.raises(ValueError, match="invalid bounded size"):
        BlockUniverseShadowProvider(artifact_path=artifact).propose(
            _request(question, Direction.FORWARD),
            BlockUniverseQuery(question=question, direction=Direction.FORWARD),
        )
