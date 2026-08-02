from __future__ import annotations

import ast
from pathlib import Path

import pytest

from packages.cognitive_core import (
    ClaimEnvelope,
    CognitiveEnvelope,
    CognitiveMoment,
    DecisionReceipt,
    EpistemicTier,
    GoalIR,
    ProofCandidate,
    ReceiptMode,
    WorldSnapshot,
    adapt_claim_envelope,
    adapt_cognitive_envelope,
    adapt_cognitive_moment,
    adapt_contract,
    adapt_decision_receipt,
    adapt_goal_ir,
    adapt_proof_candidate,
    adapt_world_snapshot,
)


def _roundtrip_contracts():
    goal = GoalIR(statement="Inspect the state.", origin="explicit_user")
    claim = ClaimEnvelope(
        statement="The state was inspected.",
        tier="observed",
        source_refs=("sensor:inspection",),
    )
    proof = ProofCandidate(claim_id=claim.contract_id, method="candidate_check")
    world = WorldSnapshot(
        world_time="logical:1",
        snapshot_index=1,
        observed_claim_ids=(claim.contract_id,),
    )
    envelope = CognitiveEnvelope(
        session_id="session:adapter",
        explicit_user_goal_ids=(goal.contract_id,),
        world_snapshot_id=world.contract_id,
    )
    moment = CognitiveMoment(
        moment_index=1,
        envelope_id=envelope.contract_id,
        world_snapshot_id=world.contract_id,
        active_goal_ids=(goal.contract_id,),
        selected_goal_id=goal.contract_id,
        claim_ids=(claim.contract_id,),
        proof_candidate_ids=(proof.contract_id,),
    )
    receipt = DecisionReceipt(
        moment_id=moment.contract_id,
        mode=ReceiptMode.READ_ONLY,
        decision_kind="inspect",
        rationale="The adapter round trip remains read-only.",
    )
    return envelope, goal, claim, proof, world, moment, receipt


@pytest.mark.parametrize(
    ("adapter", "index"),
    (
        (adapt_cognitive_envelope, 0),
        (adapt_goal_ir, 1),
        (adapt_claim_envelope, 2),
        (adapt_proof_candidate, 3),
        (adapt_world_snapshot, 4),
        (adapt_cognitive_moment, 5),
        (adapt_decision_receipt, 6),
    ),
)
def test_each_adapter_round_trips_canonical_identity(adapter, index):
    contract = _roundtrip_contracts()[index]
    adapted = adapter(contract.to_dict())
    assert type(adapted) is type(contract)
    assert adapted.to_dict() == contract.to_dict()
    assert adapt_contract(contract.to_dict()).to_dict() == contract.to_dict()


def test_legacy_projected_tier_stays_predictive():
    claim = adapt_claim_envelope(
        {
            "statement": "The branch may enter state C.",
            "tier": "PROJECTED",
            "confidence": 0.99,
        }
    )
    assert claim.tier is EpistemicTier.PREDICTED
    assert claim.hypothesis is True
    assert claim.accepted_as_observed_fact is False


@pytest.mark.parametrize("tier", ("projected", "predicted", "retrodicted", "inferred"))
def test_adapter_refuses_non_observed_claim_marked_as_fact(tier):
    with pytest.raises(ValueError, match="cannot be adapted as an observed fact"):
        adapt_claim_envelope(
            {
                "statement": "A model output is not an observation.",
                "tier": tier,
                "is_observed": True,
            }
        )


def test_adapter_refuses_predictive_claim_with_accepted_fact_flag():
    with pytest.raises(ValueError, match="cannot contradict"):
        adapt_claim_envelope(
            {
                "statement": "A rollout remains a rollout.",
                "tier": "predicted",
                "accepted_as_observed_fact": True,
            }
        )


@pytest.mark.parametrize(
    "payload",
    (
        {
            "statement": "Malformed flag.",
            "tier": "predicted",
            "accepted_as_observed_fact": "false",
        },
        {
            "statement": "Malformed flag.",
            "tier": "predicted",
            "is_observed": 0,
        },
    ),
)
def test_claim_adapter_requires_literal_boolean_status_flags(payload):
    with pytest.raises(ValueError, match="literal boolean"):
        adapt_claim_envelope(payload)


def test_claim_adapter_rejects_conflicting_tier_or_observation_aliases():
    with pytest.raises(ValueError, match="conflicting tier"):
        adapt_claim_envelope(
            {
                "statement": "Conflicting source fields are not trusted.",
                "tier": "observed",
                "status": "predicted",
                "source_refs": ["sensor:1"],
            }
        )
    with pytest.raises(ValueError, match="conflicting observed"):
        adapt_claim_envelope(
            {
                "statement": "Conflicting fact flags are not trusted.",
                "tier": "predicted",
                "observed": False,
                "fact": True,
            }
        )


def test_intrinsic_goal_adapter_refuses_user_override_claim():
    with pytest.raises(ValueError, match="cannot override"):
        adapt_goal_ir(
            {
                "statement": "Pursue curiosity before the user's task.",
                "origin": "intrinsic",
                "override_explicit_user": True,
            }
        )


def test_goal_adapter_rejects_conflicting_origin_aliases():
    with pytest.raises(ValueError, match="conflicting origin"):
        adapt_goal_ir(
            {
                "statement": "Origin must remain unambiguous.",
                "origin": "intrinsic",
                "source": "explicit_user",
            }
        )


def test_authority_and_proof_status_claims_fail_closed_at_adapters():
    with pytest.raises(ValueError, match="cannot claim action"):
        adapt_cognitive_envelope(
            {
                "session_id": "session:unsafe",
                "explicit_user_goal_ids": [],
                "autonomy_authority": True,
            }
        )
    with pytest.raises(ValueError, match="literal value True"):
        adapt_cognitive_envelope(
            {
                "session_id": "session:malformed",
                "explicit_user_goal_ids": [],
                "read_only": 1,
            }
        )
    with pytest.raises(ValueError, match="cannot claim accepted-proof"):
        adapt_proof_candidate(
            {
                "claim_id": "claim:1",
                "method": "unverified",
                "accepted": True,
            }
        )
    with pytest.raises(ValueError, match="cannot authorize"):
        adapt_decision_receipt(
            {
                "moment_id": "moment:1",
                "mode": "shadow",
                "decision_kind": "candidate",
                "rationale": "No execution.",
                "action_executed": True,
            }
        )


def test_adapter_detects_serialized_identity_tampering():
    goal = GoalIR(statement="Keep identity stable.", origin="explicit_user")
    payload = goal.to_dict()
    payload["statement"] = "Changed after hashing."
    with pytest.raises(ValueError, match="contract_id"):
        adapt_goal_ir(payload)


def test_adapter_and_profile_modules_have_no_organ_api_imports():
    package_root = Path(__file__).resolve().parents[1]
    for name in (
        "canonical.py",
        "contracts.py",
        "adapters.py",
        "co_profile.py",
        "shadow.py",
    ):
        tree = ast.parse((package_root / name).read_text(encoding="utf-8"))
        imported_modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)
        package_imports = [
            module for module in imported_modules if module.startswith("packages.")
        ]
        assert all(
            module.startswith("packages.cognitive_core")
            for module in package_imports
        ), (name, package_imports)
