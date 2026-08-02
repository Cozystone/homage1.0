"""A signed autonomy run lease is exact, bounded, and single-use."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from packages.autonomy_envelope.operator_trust import (
    ED25519_SCHEME,
    SIGNATURE_FIELD,
    OperatorTrustRoot,
    payload_sha256,
)
from packages.autonomy_envelope.run_lease import (
    AGENTIC_POLICY_DAEMON_RUNNER_ID,
    CONTINUOUS_SELF_RUNNER_ID,
    GENERAL_INTERACTION_RUNNER_ID,
    RUN_LEASE_ACTIVE_RELATIVE_PATH,
    RUN_LEASE_CAPABILITY_SCHEMA_VERSION,
    RUN_LEASE_CLAIMS_RELATIVE_PATH,
    RUN_LEASE_LOCK_RELATIVE_PATH,
    RUN_LEASE_PURPOSE,
    RUN_LEASE_REPLAY_IDENTITY_FILENAME,
    RUN_LEASE_REPLAY_IDENTITY_SCHEMA_VERSION,
    RUN_LEASE_SCHEMA_VERSION,
    RUN_LEASE_TRUST_CONFIG_SCHEMA_VERSION,
    RunLeaseBoundaryConfig,
    RunLeaseStore,
    verify_run_lease,
)


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _key_id(private: Ed25519PrivateKey) -> str:
    raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return f"ed25519:{hashlib.sha256(raw).hexdigest()[:24]}"


def _provision_boundary(
    tmp_path: Path,
) -> tuple[Ed25519PrivateKey, RunLeaseBoundaryConfig, Path]:
    repository = tmp_path / "repository"
    external = tmp_path / "operator-boundary"
    repository.mkdir()
    external.mkdir()
    replay_root = external / "replay"
    replay_root.mkdir()
    (replay_root / RUN_LEASE_CLAIMS_RELATIVE_PATH).mkdir()
    (replay_root / RUN_LEASE_ACTIVE_RELATIVE_PATH).mkdir()

    private = Ed25519PrivateKey.generate()
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_key_path = external / "operator-public.pem"
    public_key_path.write_bytes(public_pem)
    deployment_id = "atanor-test-deployment"
    identity = {
        "schema_version": RUN_LEASE_REPLAY_IDENTITY_SCHEMA_VERSION,
        "ledger_id": "atanor:autonomy-run-ledger:test-install-0001",
        "deployment_id": deployment_id,
        "resolved_root_sha256": hashlib.sha256(
            str(replay_root.resolve()).encode("utf-8")
        ).hexdigest(),
        "lock_relative_path": RUN_LEASE_LOCK_RELATIVE_PATH,
        "claims_relative_path": RUN_LEASE_CLAIMS_RELATIVE_PATH,
        "active_relative_path": RUN_LEASE_ACTIVE_RELATIVE_PATH,
    }
    (replay_root / RUN_LEASE_REPLAY_IDENTITY_FILENAME).write_text(
        json.dumps(identity, sort_keys=True),
        encoding="utf-8",
    )
    config = {
        "schema_version": RUN_LEASE_TRUST_CONFIG_SCHEMA_VERSION,
        "operator_public_key_path": str(public_key_path.resolve()),
        "expected_key_id": _key_id(private),
        "operator_boundary_id": "atanor-test-operator-boundary",
        "deployment_id": deployment_id,
        "replay_root": str(replay_root.resolve()),
        "emergency_stop_path": str(
            (external / "EMERGENCY_STOP").resolve()
        ),
    }
    config_path = external / "run-lease-trust.json"
    config_path.write_text(
        json.dumps(config, sort_keys=True),
        encoding="utf-8",
    )
    boundary = RunLeaseBoundaryConfig.from_external_file(
        config_path,
        repository_root=repository,
    )
    return private, boundary, repository


def _live_context(
    boundary: RunLeaseBoundaryConfig,
    *,
    runner_id: str = CONTINUOUS_SELF_RUNNER_ID,
    max_actions: int = 4,
) -> dict:
    actions = (
        [
            "self.audit_append",
            "self.observe_local",
            "self.proposal_write",
            "self.state_write",
        ]
        if runner_id == CONTINUOUS_SELF_RUNNER_ID
        else ["interaction.step"]
        if runner_id == GENERAL_INTERACTION_RUNNER_ID
        else [
            "agentic.audit_append",
            "agentic.candidate_write",
            "agentic.review_read",
            "agentic.scratch_write",
            "agentic.tick",
        ]
    )
    return {
        "runner_id": runner_id,
        "deployment_id": boundary.deployment_id,
        "runtime_instance_id": "test-runtime-instance-0001",
        "runner_artifact_sha256": "1" * 64,
        "config_sha256": "2" * 64,
        "input_manifest_sha256": "3" * 64,
        "capability_manifest": {
            "schema_version": RUN_LEASE_CAPABILITY_SCHEMA_VERSION,
            "action_classes": actions,
            "filesystem_policy_sha256": "4" * 64,
            "network_policy_sha256": "5" * 64,
            "child_task_policy_sha256": "6" * 64,
        },
        "limits": {
            "max_runtime_sec": 600,
            "max_cycles": 2,
            "max_actions": max_actions,
            "max_external_requests": 0,
            "max_external_response_bytes": 0,
            "max_scratch_write_bytes": 1024,
            "max_child_tasks": 0,
            "max_concurrent_child_tasks": 0,
        },
        "scratch_boundary": {
            "boundary_id": "atanor-test-scratch",
            "resolved_root_sha256": "7" * 64,
            "identity_manifest_sha256": "8" * 64,
        },
        "operator_boundary_id": boundary.operator_boundary_id,
        "operator_boundary_config_sha256": (
            boundary.operator_boundary_config_sha256
        ),
        "nonce_replay_domain": boundary.replay_domain,
    }


def _signed_lease(
    private: Ed25519PrivateKey,
    boundary: RunLeaseBoundaryConfig,
    context: dict,
    *,
    lease_id: str = "test-run-lease-0001",
    nonce: str = "test-run-lease-nonce-0001",
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
    purpose: str = RUN_LEASE_PURPOSE,
    signature_key_id: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    issued = issued_at or now - timedelta(seconds=1)
    expires = expires_at or now + timedelta(seconds=300)
    document = {
        "schema_version": RUN_LEASE_SCHEMA_VERSION,
        "purpose": purpose,
        "lease_id": lease_id,
        **copy.deepcopy(context),
        "issued_at": issued.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nonce": nonce,
        SIGNATURE_FIELD: {
            "scheme": ED25519_SCHEME,
            "key_id": signature_key_id or boundary.expected_key_id,
            "payload_sha256": "",
            "signature": "",
        },
    }
    digest = payload_sha256(document)
    document[SIGNATURE_FIELD] = {
        "scheme": ED25519_SCHEME,
        "key_id": signature_key_id or boundary.expected_key_id,
        "payload_sha256": digest,
        "signature": base64.b64encode(
            private.sign(
                json.dumps(
                    {
                        key: value
                        for key, value in document.items()
                        if key != SIGNATURE_FIELD
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            )
        ).decode("ascii"),
    }
    return document


def test_store_rehydrates_pinned_key_instead_of_trusting_replaced_boundary(
    tmp_path: Path,
) -> None:
    legitimate_private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary)

    attacker_private = Ed25519PrivateKey.generate()
    attacker_public_path = boundary.config_path.parent / "attacker-public.pem"
    attacker_public_path.write_bytes(
        attacker_private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    attacker_key_id = _key_id(attacker_private)
    attacker_root = OperatorTrustRoot.from_external_file(
        attacker_public_path,
        repository_root=boundary.repository_root,
        expected_key_id=attacker_key_id,
    )
    replaced_boundary = replace(boundary, trust_root=attacker_root)
    attacker_lease = _signed_lease(
        attacker_private,
        boundary,
        context,
        lease_id="attacker-run-lease-0001",
        nonce="attacker-run-lease-nonce-0001",
        signature_key_id=attacker_key_id,
    )

    denied = RunLeaseStore(replaced_boundary).activate(
        document=attacker_lease,
        live_context=context,
    )
    assert denied.allowed is False
    assert denied.reason == "run_lease_operator_key_mismatch"

    legitimate_lease = _signed_lease(
        legitimate_private,
        boundary,
        context,
        lease_id="legitimate-run-lease-0001",
        nonce="legitimate-run-lease-nonce-0001",
    )
    allowed = RunLeaseStore(replaced_boundary).activate(
        document=legitimate_lease,
        live_context=context,
    )
    assert allowed.allowed is True

    replaced_key_binding = replace(
        boundary,
        operator_public_key_path=attacker_public_path,
        expected_key_id=attacker_key_id,
        trust_root=attacker_root,
    )
    with pytest.raises(
        ValueError,
        match="does not match its external source",
    ):
        RunLeaseStore(replaced_key_binding)


def test_general_interaction_profile_is_narrow_and_cycle_charged(
    tmp_path: Path,
) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(
        boundary,
        runner_id=GENERAL_INTERACTION_RUNNER_ID,
        max_actions=60,
    )
    context["limits"].update(
        {
            "max_cycles": 60,
            "max_external_requests": 0,
            "max_external_response_bytes": 0,
            "max_scratch_write_bytes": 0,
            "max_child_tasks": 0,
            "max_concurrent_child_tasks": 0,
        }
    )
    lease = _signed_lease(
        private,
        boundary,
        context,
        lease_id="interaction-run-lease-0001",
        nonce="interaction-run-lease-nonce-0001",
    )
    store = RunLeaseStore(boundary)
    assert store.activate(document=lease, live_context=context).allowed is True

    allowed = store.authorize(
        lease_id=lease["lease_id"],
        runner_id=GENERAL_INTERACTION_RUNNER_ID,
        action_class="interaction.step",
        costs=_costs(cycles=1),
    )
    assert allowed.allowed is True
    assert allowed.counters == {
        "cycles": 1,
        "actions": 1,
        "external_requests": 0,
        "external_response_bytes": 0,
        "scratch_write_bytes": 0,
        "child_tasks": 0,
        "concurrent_child_tasks": 0,
    }
    assert store.authorize(
        lease_id=lease["lease_id"],
        runner_id=GENERAL_INTERACTION_RUNNER_ID,
        action_class="agentic.tick",
        costs=_costs(cycles=1),
    ).reason == "run_lease_action_class_denied"


def _costs(*, actions: int = 1, cycles: int = 0, scratch: int = 0) -> dict:
    return {
        "cycles": cycles,
        "actions": actions,
        "external_requests": 0,
        "external_response_bytes": 0,
        "scratch_write_bytes": scratch,
        "child_tasks": 0,
        "concurrent_child_tasks": 0,
    }


def test_valid_lease_activates_authorizes_finishes_and_never_replays(
    tmp_path: Path,
) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary)
    lease = _signed_lease(private, boundary, context)
    store = RunLeaseStore(boundary)

    verified = verify_run_lease(
        lease,
        trust_root=boundary.trust_root,
        live_context=context,
    )
    assert verified.ok is True
    activated = store.activate(document=lease, live_context=context)
    assert activated.allowed is True
    allowed = store.authorize(
        lease_id=lease["lease_id"],
        runner_id=lease["runner_id"],
        action_class="self.state_write",
        costs=_costs(cycles=1, scratch=128),
    )
    assert allowed.allowed is True
    assert allowed.counters["cycles"] == 1
    assert allowed.counters["scratch_write_bytes"] == 128

    finished = store.finish(
        lease_id=lease["lease_id"],
        runner_id=lease["runner_id"],
        reason="test-complete",
    )
    assert finished.finished is True
    assert store.authorize(
        lease_id=lease["lease_id"],
        runner_id=lease["runner_id"],
        action_class="self.state_write",
    ).reason == "run_lease_stopped"
    replay = store.activate(document=lease, live_context=context)
    assert replay.allowed is False
    assert replay.reason == "run_lease_replay"
    assert store.status()["consumed_nonce_count"] == 1


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("runner_artifact_sha256", "run_lease_live_runner_artifact_sha256_mismatch"),
        ("config_sha256", "run_lease_live_config_sha256_mismatch"),
        ("input_manifest_sha256", "run_lease_live_input_manifest_sha256_mismatch"),
        ("runtime_instance_id", "run_lease_live_runtime_instance_id_mismatch"),
    ],
)
def test_every_live_binding_is_literal_and_signed(
    tmp_path: Path,
    field: str,
    reason: str,
) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary)
    lease = _signed_lease(private, boundary, context)
    changed = copy.deepcopy(context)
    changed[field] = (
        "9" * 64 if field.endswith("sha256") else "different-instance"
    )

    result = verify_run_lease(
        lease,
        trust_root=boundary.trust_root,
        live_context=changed,
    )
    assert result.ok is False
    assert result.reason == reason


def test_schema_purpose_signature_and_exact_types_fail_closed(
    tmp_path: Path,
) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary)
    lease = _signed_lease(private, boundary, context)

    extra = copy.deepcopy(lease)
    extra["unexpected"] = True
    assert verify_run_lease(
        extra,
        trust_root=boundary.trust_root,
        live_context=context,
    ).reason == "run_lease_fields_mismatch"

    wrong_purpose = _signed_lease(
        private,
        boundary,
        context,
        purpose="atanor.shipped-graph-promotion.v3",
    )
    assert verify_run_lease(
        wrong_purpose,
        trust_root=boundary.trust_root,
        live_context=context,
    ).reason == "run_lease_purpose_mismatch"

    unsigned = copy.deepcopy(lease)
    unsigned[SIGNATURE_FIELD] = {}
    assert verify_run_lease(
        unsigned,
        trust_root=boundary.trust_root,
        live_context=context,
    ).reason == "run_lease_signature_fields_mismatch"

    boolean_limit = copy.deepcopy(lease)
    boolean_limit["limits"]["max_cycles"] = True
    assert verify_run_lease(
        boolean_limit,
        trust_root=boundary.trust_root,
        live_context=context,
    ).reason == "run_lease_limits_invalid"


def test_action_classes_are_closed_and_network_child_budgets_are_zero(
    tmp_path: Path,
) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary)

    network = copy.deepcopy(context)
    network["capability_manifest"]["action_classes"].append(
        "network.public_read"
    )
    network["capability_manifest"]["action_classes"].sort()
    lease = _signed_lease(private, boundary, network)
    assert verify_run_lease(
        lease,
        trust_root=boundary.trust_root,
        live_context=network,
    ).reason == "run_lease_action_classes_invalid"

    child_budget = copy.deepcopy(context)
    child_budget["limits"]["max_child_tasks"] = 1
    lease = _signed_lease(
        private,
        boundary,
        child_budget,
        nonce="test-run-lease-nonce-0002",
    )
    assert verify_run_lease(
        lease,
        trust_root=boundary.trust_root,
        live_context=child_budget,
    ).reason == "run_lease_limits_invalid"


def test_expiry_future_and_signed_duration_are_bounded(tmp_path: Path) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    expired = _signed_lease(
        private,
        boundary,
        context,
        issued_at=now - timedelta(seconds=500),
        expires_at=now - timedelta(seconds=1),
    )
    assert verify_run_lease(
        expired,
        trust_root=boundary.trust_root,
        live_context=context,
    ).reason == "run_lease_expired"

    future = _signed_lease(
        private,
        boundary,
        context,
        issued_at=now + timedelta(seconds=30),
        expires_at=now + timedelta(seconds=300),
        nonce="test-run-lease-nonce-0002",
    )
    assert verify_run_lease(
        future,
        trust_root=boundary.trust_root,
        live_context=context,
    ).reason == "run_lease_not_yet_valid"

    too_long = _signed_lease(
        private,
        boundary,
        context,
        issued_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(seconds=601),
        nonce="test-run-lease-nonce-0003",
    )
    assert verify_run_lease(
        too_long,
        trust_root=boundary.trust_root,
        live_context=context,
    ).reason == "run_lease_duration_exceeds_policy"


def test_budget_and_action_class_are_enforced_before_action(
    tmp_path: Path,
) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary, max_actions=2)
    lease = _signed_lease(private, boundary, context)
    store = RunLeaseStore(boundary)
    assert store.activate(document=lease, live_context=context).allowed

    denied_class = store.authorize(
        lease_id=lease["lease_id"],
        runner_id=lease["runner_id"],
        action_class="agentic.tick",
    )
    assert denied_class.reason == "run_lease_action_class_denied"
    assert store.authorize(
        lease_id=lease["lease_id"],
        runner_id=lease["runner_id"],
        action_class="self.observe_local",
    ).allowed
    assert store.authorize(
        lease_id=lease["lease_id"],
        runner_id=lease["runner_id"],
        action_class="self.audit_append",
    ).allowed
    exhausted = store.authorize(
        lease_id=lease["lease_id"],
        runner_id=lease["runner_id"],
        action_class="self.state_write",
    )
    assert exhausted.allowed is False
    assert exhausted.reason == "run_lease_budget_exhausted:actions"
    assert exhausted.counters["actions"] == 2


def test_cycle_and_write_costs_cannot_be_omitted(
    tmp_path: Path,
) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary)
    lease = _signed_lease(private, boundary, context)
    store = RunLeaseStore(boundary)
    assert store.activate(document=lease, live_context=context).allowed

    missing_cycle = store.authorize(
        lease_id=lease["lease_id"],
        runner_id=lease["runner_id"],
        action_class="self.observe_local",
        costs=_costs(cycles=0),
    )
    missing_write_bytes = store.authorize(
        lease_id=lease["lease_id"],
        runner_id=lease["runner_id"],
        action_class="self.state_write",
        costs=_costs(scratch=0),
    )
    assert missing_cycle.reason == "run_lease_action_cost_invalid"
    assert missing_write_bytes.reason == "run_lease_action_cost_invalid"
    assert store.status()["runners"][CONTINUOUS_SELF_RUNNER_ID][
        "authorization_count"
    ] == 0


def test_emergency_stop_blocks_without_consuming_action_budget(
    tmp_path: Path,
) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary)
    lease = _signed_lease(private, boundary, context)
    store = RunLeaseStore(boundary)
    assert store.activate(document=lease, live_context=context).allowed
    boundary.emergency_stop_path.write_text("operator stop", encoding="utf-8")

    denied = store.authorize(
        lease_id=lease["lease_id"],
        runner_id=lease["runner_id"],
        action_class="self.state_write",
    )
    assert denied.allowed is False
    assert denied.reason == "run_lease_emergency_stop"
    assert denied.counters["actions"] == 0


def test_concurrent_activation_has_exactly_one_winner(tmp_path: Path) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(
        boundary,
        runner_id=AGENTIC_POLICY_DAEMON_RUNNER_ID,
    )
    lease = _signed_lease(private, boundary, context)
    stores = [RunLeaseStore(boundary), RunLeaseStore(boundary)]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda store: store.activate(
                    document=lease,
                    live_context=context,
                ),
                stores,
            )
        )
    assert sum(result.allowed for result in results) == 1
    assert {result.reason for result in results} <= {
        "run_lease_activated",
        "run_lease_runner_already_active",
        "run_lease_replay",
    }


def test_concurrent_budget_charges_never_overspend(tmp_path: Path) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary, max_actions=2)
    lease = _signed_lease(private, boundary, context)
    store = RunLeaseStore(boundary)
    assert store.activate(document=lease, live_context=context).allowed

    def charge(_: int):
        return store.authorize(
            lease_id=lease["lease_id"],
            runner_id=lease["runner_id"],
            action_class="self.observe_local",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(charge, range(8)))
    assert sum(result.allowed for result in results) == 2
    assert {
        result.reason for result in results if not result.allowed
    } == {"run_lease_budget_exhausted:cycles"}
    counters = store.status()["runners"][CONTINUOUS_SELF_RUNNER_ID][
        "counters"
    ]
    assert counters["cycles"] == 2
    assert counters["actions"] == 2


def test_monotonic_runtime_limit_is_independent_of_wall_clock(
    tmp_path: Path,
) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary)
    lease = _signed_lease(private, boundary, context)
    clock = [10.0]
    store = RunLeaseStore(boundary, monotonic_clock=lambda: clock[0])
    assert store.activate(document=lease, live_context=context).allowed
    clock[0] += context["limits"]["max_runtime_sec"]

    denied = store.authorize(
        lease_id=lease["lease_id"],
        runner_id=lease["runner_id"],
        action_class="self.observe_local",
    )
    assert denied.allowed is False
    assert denied.reason == "run_lease_runtime_expired"


def test_reopened_store_preserves_nonce_replay(tmp_path: Path) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary)
    lease = _signed_lease(private, boundary, context)
    first = RunLeaseStore(boundary)
    assert first.activate(document=lease, live_context=context).allowed
    assert first.finish(
        lease_id=lease["lease_id"],
        runner_id=lease["runner_id"],
        reason="first-process-finished",
    ).finished

    reopened = RunLeaseStore(boundary)
    result = reopened.activate(document=lease, live_context=context)
    assert result.allowed is False
    assert result.reason == "run_lease_replay"


def test_external_config_key_and_replay_root_cannot_live_in_repository(
    tmp_path: Path,
) -> None:
    private, boundary, repository = _provision_boundary(tmp_path)
    _ = private
    config = json.loads(boundary.config_path.read_text(encoding="utf-8"))

    in_repo_config = repository / "trust.json"
    in_repo_config.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="outside the repository"):
        RunLeaseBoundaryConfig.from_external_file(
            in_repo_config,
            repository_root=repository,
        )

    in_repo_key = repository / "operator.pem"
    in_repo_key.write_bytes(boundary.operator_public_key_path.read_bytes())
    changed = dict(config)
    changed["operator_public_key_path"] = str(in_repo_key.resolve())
    boundary.config_path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="outside the repository"):
        RunLeaseBoundaryConfig.from_external_file(
            boundary.config_path,
            repository_root=repository,
        )

    changed["operator_public_key_path"] = str(
        boundary.operator_public_key_path
    )
    replay_in_repo = repository / "replay"
    replay_in_repo.mkdir()
    changed["replay_root"] = str(replay_in_repo.resolve())
    boundary.config_path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="outside the repository"):
        RunLeaseBoundaryConfig.from_external_file(
            boundary.config_path,
            repository_root=repository,
        )


def test_replay_identity_loss_fails_closed_after_configuration(
    tmp_path: Path,
) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary)
    lease = _signed_lease(private, boundary, context)
    store = RunLeaseStore(boundary)
    (
        boundary.replay_root / RUN_LEASE_REPLAY_IDENTITY_FILENAME
    ).unlink()

    result = store.activate(document=lease, live_context=context)
    assert result.allowed is False
    assert result.reason == "run_lease_replay_domain_identity_mismatch"
    assert store.status()["state_ok"] is False


def test_status_cryptographically_revalidates_shape_valid_active_state(
    tmp_path: Path,
) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary)
    lease = _signed_lease(private, boundary, context)
    store = RunLeaseStore(boundary)
    assert store.activate(document=lease, live_context=context).allowed

    active_path = (
        boundary.replay_root
        / RUN_LEASE_ACTIVE_RELATIVE_PATH
        / (
            hashlib.sha256(
                CONTINUOUS_SELF_RUNNER_ID.encode("utf-8")
            ).hexdigest()
            + ".json"
        )
    )
    state = json.loads(active_path.read_text(encoding="utf-8"))
    state["lease_document"]["limits"]["max_actions"] += 1
    active_path.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    status = store.status()
    runner = status["runners"][CONTINUOUS_SELF_RUNNER_ID]
    assert status["state_ok"] is False
    assert status["state_error"] == "run_lease_active_state_invalid"
    assert runner["state_ok"] is False
    assert runner["state_error"] == "run_lease_active_state_invalid"


def test_mutating_custom_mapping_is_detached_before_authority(
    tmp_path: Path,
) -> None:
    private, boundary, _ = _provision_boundary(tmp_path)
    context = _live_context(boundary)
    lease = _signed_lease(private, boundary, context)

    class LyingMapping(dict):
        def items(self):
            values = list(super().items())
            self["runner_id"] = AGENTIC_POLICY_DAEMON_RUNNER_ID
            return iter(values)

    result = verify_run_lease(
        LyingMapping(lease),
        trust_root=boundary.trust_root,
        live_context=context,
    )
    # It either snapshots one stable view and verifies it, or rejects it; the
    # caller-owned object can never change the detached verification afterward.
    assert result.reason in {"run_lease_valid", "run_lease_signature_invalid"}
    assert result.runner_id in {None, CONTINUOUS_SELF_RUNNER_ID}
