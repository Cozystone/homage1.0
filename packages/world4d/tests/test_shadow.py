from __future__ import annotations

import json
import threading

import pytest

from packages.cognitive_core import EpistemicTier
from packages.cognitive_core.canonical import canonical_digest, canonical_json
from packages.world4d import (
    BlockUniverseQuery,
    CheckScope,
    CheckVerdict,
    Direction,
    JsonlReceiptSink,
    ProviderResultStatus,
    World4DCheck,
    World4DProviderDescriptor,
    World4DProviderResult,
    World4DRequest,
    World4DShadowAdapter,
    World4DShadowDispatcher,
    World4DStep,
    World4DTrajectory,
)


def _request() -> World4DRequest:
    return World4DRequest(
        request_id="request_shadow",
        source_kind="fixture",
        source_digest=canonical_digest("top secret prompt"),
        direction=Direction.FORWARD,
    )


def _result() -> World4DProviderResult:
    artifact_digest = canonical_digest("fake frozen artifact")
    return World4DProviderResult(
        provider_id="fake",
        provider_version="v1",
        status=ProviderResultStatus.PROPOSED,
        trajectories=(
            World4DTrajectory(
                branch_id="branch",
                initial_state_digest=canonical_digest("initial"),
                steps=(
                    World4DStep(
                        step_index=1,
                        state_digest=canonical_digest("secret predicted token"),
                        confidence=0.5,
                        tier=EpistemicTier.PREDICTED,
                    ),
                ),
                checks=(
                    World4DCheck(
                        check_id="physics",
                        scope=CheckScope.PHYSICAL,
                        verdict=CheckVerdict.NOT_RUN,
                    ),
                ),
            ),
        ),
        model_artifact_digest=artifact_digest,
    )


class FakeProvider:
    descriptor = World4DProviderDescriptor(
        provider_id="fake",
        provider_version="v1",
        input_kind="fixture",
        source_refs=("fixture",),
    )

    def propose(self, request, payload):
        assert request.request_id == "request_shadow"
        assert payload == {"opaque": True}
        return _result()


class MemorySink:
    def __init__(self):
        self.values = []

    def append(self, value):
        self.values.append(value)


def test_disabled_adapter_factories_are_lazy():
    class PoisonSink:
        def append(self, _value):
            raise AssertionError("disabled adapter touched sink")

    def poison():
        raise AssertionError("disabled adapter touched factory")

    adapter = World4DShadowAdapter(
        enabled=False,
        provider_factory=poison,
        sink=PoisonSink(),
    )
    assert adapter.observe(poison, poison) is None


def test_truthy_string_enablement_is_rejected():
    with pytest.raises(TypeError, match="literal boolean"):
        World4DShadowAdapter(enabled="1", provider_factory=FakeProvider)


def test_dispatcher_bounds_backlog_without_waiting_for_provider():
    started = threading.Event()
    release = threading.Event()

    def blocked_worker(_query):
        started.set()
        release.wait(2.0)
        return True

    dispatcher = World4DShadowDispatcher(worker=blocked_worker, capacity=1)
    query = BlockUniverseQuery(
        question="What happens after crops grow?",
        direction=Direction.FORWARD,
    )

    assert dispatcher.submit(query) is True
    assert started.wait(1.0)
    assert dispatcher.submit(query) is True
    assert dispatcher.submit(query) is False
    assert dispatcher.snapshot()["dropped"] == 1

    release.set()
    assert dispatcher.wait_idle(2.0)
    snapshot = dispatcher.snapshot()
    assert snapshot["completed"] == 2
    assert snapshot["pending"] == 0


def test_dispatcher_counts_false_observation_as_failed():
    dispatcher = World4DShadowDispatcher(
        worker=lambda _query: False,
        capacity=1,
    )
    query = BlockUniverseQuery(
        question="What happens after crops grow?",
        direction=Direction.FORWARD,
    )

    assert dispatcher.submit(query)
    assert dispatcher.wait_idle(1.0)
    snapshot = dispatcher.snapshot()
    assert snapshot["completed"] == 1
    assert snapshot["failed"] == 1
    assert snapshot["faults"] == 0


def test_enabled_adapter_emits_only_bounded_digest_receipt(tmp_path):
    sink = JsonlReceiptSink(tmp_path / "world4d.jsonl")
    adapter = World4DShadowAdapter(
        enabled=True,
        provider_factory=FakeProvider,
        sink=sink,
    )
    receipt = adapter.observe(_request, lambda: {"opaque": True})
    assert receipt is not None
    assert receipt.adapter_answer_influenced is False
    assert receipt.trajectory_count == 1
    assert receipt.step_count == 1
    assert receipt.model_artifact_digest == canonical_digest(
        "fake frozen artifact"
    )
    serialized = (tmp_path / "world4d.jsonl").read_text(encoding="utf-8")
    assert "top secret prompt" not in serialized
    assert "secret predicted token" not in serialized
    assert len(json.dumps(receipt.to_dict()).encode("utf-8")) < 8 * 1024
    assert sink.verify()["record_count"] == 1


def test_provider_error_is_sanitized_and_contained():
    class BrokenProvider(FakeProvider):
        def propose(self, request, payload):
            raise RuntimeError("password=must-not-leak")

    sink = MemorySink()
    adapter = World4DShadowAdapter(
        enabled=True,
        provider_factory=BrokenProvider,
        sink=sink,
    )
    receipt = adapter.observe(_request, lambda: object())
    assert receipt is not None
    assert receipt.provider_status == "error"
    assert receipt.error_kind == "provider_observation_error"
    assert "must-not-leak" not in json.dumps(receipt.to_dict())
    assert adapter.fault_count == 1


def test_provider_result_identity_must_match_descriptor():
    class MismatchedProvider(FakeProvider):
        def propose(self, request, payload):
            result = _result()
            return World4DProviderResult(
                provider_id="different_provider",
                provider_version=result.provider_version,
                status=result.status,
                trajectories=result.trajectories,
                limitations=result.limitations,
                model_artifact_digest=result.model_artifact_digest,
            )

    adapter = World4DShadowAdapter(
        enabled=True,
        provider_factory=MismatchedProvider,
    )
    receipt = adapter.observe(_request, lambda: {"opaque": True})

    assert receipt is not None
    assert receipt.provider_status == "error"
    assert receipt.error_kind == "provider_observation_error"
    assert receipt.provider_result_digest is None
    assert receipt.provider_effects_attested is False
    assert receipt.provider_isolation_enforced is False


def test_provider_result_tier_must_match_request_direction():
    class WrongTierProvider(FakeProvider):
        def propose(self, request, payload):
            return World4DProviderResult(
                provider_id=self.descriptor.provider_id,
                provider_version=self.descriptor.provider_version,
                status=ProviderResultStatus.PROPOSED,
                trajectories=(
                    World4DTrajectory(
                        branch_id="wrong_direction",
                        initial_state_digest=canonical_digest("initial"),
                        steps=(
                            World4DStep(
                                step_index=1,
                                state_digest=canonical_digest("retrodicted"),
                                confidence=0.5,
                                tier=EpistemicTier.RETRODICTED,
                            ),
                        ),
                        checks=(),
                    ),
                ),
            )

    adapter = World4DShadowAdapter(
        enabled=True,
        provider_factory=WrongTierProvider,
    )
    receipt = adapter.observe(_request, lambda: {"opaque": True})

    assert receipt is not None
    assert receipt.provider_status == "error"
    assert receipt.error_kind == "provider_observation_error"
    assert receipt.provider_result_digest is None


def test_sink_error_is_contained():
    class BrokenSink:
        def append(self, _value):
            raise OSError("disk secret")

    adapter = World4DShadowAdapter(
        enabled=True,
        provider_factory=FakeProvider,
        sink=BrokenSink(),
    )
    assert adapter.observe(_request, lambda: {"opaque": True}) is None
    assert adapter.fault_count == 1


def test_ledger_tamper_and_partial_record_fail_closed(tmp_path):
    path = tmp_path / "world4d.jsonl"
    sink = JsonlReceiptSink(path)
    adapter = World4DShadowAdapter(
        enabled=True,
        provider_factory=FakeProvider,
        sink=sink,
    )
    assert adapter.observe(_request, lambda: {"opaque": True}) is not None
    original = path.read_bytes()
    parsed = json.loads(original)
    parsed["receipt"]["provider_status"] = "tampered"
    path.write_text(
        json.dumps(parsed, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        sink.verify()
    path.write_bytes(original[:-1])
    with pytest.raises(ValueError, match="partial trailing"):
        sink.verify()


def test_ledger_rejects_rehashed_unknown_and_oversized_receipt_fields(tmp_path):
    path = tmp_path / "world4d.jsonl"
    sink = JsonlReceiptSink(path)
    adapter = World4DShadowAdapter(
        enabled=True,
        provider_factory=FakeProvider,
        sink=sink,
    )
    assert adapter.observe(_request, lambda: {"opaque": True}) is not None
    clean = json.loads(path.read_text(encoding="utf-8"))

    forged = json.loads(canonical_json(clean))
    forged["receipt"]["raw_prompt"] = "must-not-be-accepted"
    forged["receipt_hash"] = canonical_digest(forged["receipt"])
    forged["record_hash"] = canonical_digest(
        {key: value for key, value in forged.items() if key != "record_hash"}
    )
    path.write_text(canonical_json(forged) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="keys invalid"):
        sink.verify()

    oversized = json.loads(canonical_json(clean))
    oversized["receipt"]["raw_prompt"] = "x" * (8 * 1024)
    oversized["receipt_hash"] = canonical_digest(oversized["receipt"])
    oversized["record_hash"] = canonical_digest(
        {key: value for key, value in oversized.items() if key != "record_hash"}
    )
    path.write_text(canonical_json(oversized) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exceeds 8 KiB"):
        sink.verify()

    impossible = json.loads(canonical_json(clean))
    impossible["receipt"]["check_summary"] = {
        "not_run": 0,
        "not_contradicted": 0,
        "contradicted": 1,
    }
    impossible["receipt_hash"] = canonical_digest(impossible["receipt"])
    impossible["record_hash"] = canonical_digest(
        {
            key: value
            for key, value in impossible.items()
            if key != "record_hash"
        }
    )
    path.write_text(canonical_json(impossible) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot report contradicted"):
        sink.verify()


def test_ledger_record_index_rejects_boolean_alias(tmp_path):
    path = tmp_path / "world4d.jsonl"
    sink = JsonlReceiptSink(path)
    adapter = World4DShadowAdapter(
        enabled=True,
        provider_factory=FakeProvider,
        sink=sink,
    )
    assert adapter.observe(_request, lambda: {"opaque": True}) is not None
    assert (
        adapter.observe(
            lambda: World4DRequest(
                request_id="request_shadow_second",
                source_kind="fixture",
                source_digest=canonical_digest("top secret prompt"),
                direction=Direction.FORWARD,
            ),
            lambda: {"opaque": True},
        )
        is not None
    )
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    records[1]["record_index"] = True
    records[1]["record_hash"] = canonical_digest(
        {
            key: value
            for key, value in records[1].items()
            if key != "record_hash"
        }
    )
    path.write_text(
        "".join(canonical_json(record) + "\n" for record in records),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="indexes are not contiguous"):
        sink.verify()
