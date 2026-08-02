# -*- coding: utf-8 -*-
"""autonomy_envelope — F5, the autonomy SAFETY ENVELOPE.

The non-negotiable prerequisite before ATANOR runs unsupervised (F3 controlled-unsupervised and
F-FINAL). It is what makes an overnight autonomous run SAFE rather than reckless. See
``docs/ATANOR_final_fusion_design.md`` §5 and this package's ``README.md``.

The enforcing envelope-hook the fusion loop (agent #84) calls before every side-effecting action:

  * ``AutonomyEnvelope``  — the enforcing gate (``check(action)``); composes all five components.
  * ``EnvelopeAction`` / ``EnvelopeDecision`` / ``EnvelopeHook`` — the DECOUPLED interface both
    sides agree on (no cross-import with fusion_loop).
  * ``Killswitch``        — operator immediate-stop (checked before every action).
  * ``AuditLedger``       — hash-chained, tamper-evident nightly record.
  * ``MoralConstant`` / ``FrozenOracle`` — local constant-integrity mechanisms.
  * ``EvaluationRatchetStore`` — signed, scope-bound persistent no-regression state.
  * ``CapabilityWhitelist``— pre-approved actions; default-DENY everything else.
  * ``NightlyPromotionQueue`` — operator-confirmed staging receipt; never merge authority.
  * ``OperatorTrustRoot``     — external Ed25519 verification for production authority.

The enforcement core is pure stdlib. Detached Ed25519 verification uses the optional
``cryptography`` dependency and fails closed when unavailable. The one sanctioned cross-reference is the fingerprinted moral spine
(``packages.graph_scale.moral_invariants``), imported fail-CLOSED (absent => deny all), so there
is exactly one moral core and no second, weaker one.
"""
from __future__ import annotations

from packages.autonomy_envelope.audit_ledger import AuditLedger
from packages.autonomy_envelope.constants import (
    FrozenOracle,
    MoralConstant,
    NoRegressionGuard,
    OracleTampered,
)
from packages.autonomy_envelope.envelope import AutonomyEnvelope
from packages.autonomy_envelope.evaluation_trust import (
    EVALUATION_PURPOSE,
    EVALUATION_SCHEMA_VERSION,
    EvaluationRatchetStore,
    EvaluationVerification,
    RatchetResult,
    evaluation_scope_id,
    verify_evaluation_receipt,
)
from packages.autonomy_envelope.interface import (
    DEFAULT_WHITELIST,
    SHIPPED_WRITE_KINDS,
    ActionKind,
    DefaultDenyEnvelope,
    EnvelopeAction,
    EnvelopeDecision,
    EnvelopeHook,
)
from packages.autonomy_envelope.killswitch import EnvelopeHalted, Killswitch
from packages.autonomy_envelope.promotion_queue import (
    REQUIRED_CONFIRMATION_PHRASE,
    NightlyPromotionQueue,
)
from packages.autonomy_envelope.operator_trust import (
    LEGACY_SHIPPED_GRAPH_PURPOSE,
    LEGACY_SHIPPED_GRAPH_SCHEMA_VERSION,
    MORAL_POLICY_PURPOSE,
    SHIPPED_GRAPH_PURPOSE,
    SHIPPED_GRAPH_SCHEMA_VERSION,
    OperatorTrustRoot,
    SignatureVerification,
    verify_moral_policy,
    verify_shipped_graph_promotion,
    verify_shipped_graph_promotion_historical,
)
from packages.autonomy_envelope.run_lease import (
    AGENTIC_POLICY_DAEMON_RUNNER_ID,
    CONTINUOUS_SELF_RUNNER_ID,
    GENERAL_INTERACTION_RUNNER_ID,
    RUN_LEASE_ACTION_CLASSES,
    RUN_LEASE_CAPABILITY_SCHEMA_VERSION,
    RUN_LEASE_PURPOSE,
    RUN_LEASE_REPLAY_DOMAIN_SCHEMA_VERSION,
    RUN_LEASE_SCHEMA_VERSION,
    RUN_LEASE_TRUST_CONFIG_SCHEMA_VERSION,
    RunLeaseActivationResult,
    RunLeaseAuthorization,
    RunLeaseBoundaryConfig,
    RunLeaseFinishResult,
    RunLeaseStore,
    RunLeaseVerification,
    verify_run_lease,
)
from packages.autonomy_envelope.whitelist import CapabilityWhitelist

__all__ = [
    "AutonomyEnvelope",
    "EnvelopeAction",
    "EnvelopeDecision",
    "EnvelopeHook",
    "DefaultDenyEnvelope",
    "ActionKind",
    "DEFAULT_WHITELIST",
    "SHIPPED_WRITE_KINDS",
    "Killswitch",
    "EnvelopeHalted",
    "AuditLedger",
    "MoralConstant",
    "FrozenOracle",
    "NoRegressionGuard",
    "OracleTampered",
    "EVALUATION_PURPOSE",
    "EVALUATION_SCHEMA_VERSION",
    "EvaluationRatchetStore",
    "EvaluationVerification",
    "RatchetResult",
    "evaluation_scope_id",
    "verify_evaluation_receipt",
    "CapabilityWhitelist",
    "NightlyPromotionQueue",
    "REQUIRED_CONFIRMATION_PHRASE",
    "OperatorTrustRoot",
    "SignatureVerification",
    "MORAL_POLICY_PURPOSE",
    "LEGACY_SHIPPED_GRAPH_PURPOSE",
    "LEGACY_SHIPPED_GRAPH_SCHEMA_VERSION",
    "SHIPPED_GRAPH_PURPOSE",
    "SHIPPED_GRAPH_SCHEMA_VERSION",
    "verify_moral_policy",
    "verify_shipped_graph_promotion",
    "verify_shipped_graph_promotion_historical",
    "RUN_LEASE_PURPOSE",
    "RUN_LEASE_SCHEMA_VERSION",
    "RUN_LEASE_CAPABILITY_SCHEMA_VERSION",
    "RUN_LEASE_REPLAY_DOMAIN_SCHEMA_VERSION",
    "RUN_LEASE_TRUST_CONFIG_SCHEMA_VERSION",
    "RUN_LEASE_ACTION_CLASSES",
    "CONTINUOUS_SELF_RUNNER_ID",
    "AGENTIC_POLICY_DAEMON_RUNNER_ID",
    "GENERAL_INTERACTION_RUNNER_ID",
    "RunLeaseBoundaryConfig",
    "RunLeaseVerification",
    "RunLeaseActivationResult",
    "RunLeaseAuthorization",
    "RunLeaseFinishResult",
    "RunLeaseStore",
    "verify_run_lease",
]

# Plan v5 §2 tier -- observation is universal, control is differential.
# Carries the moral screen and the killswitch. Plan v5 SS2: the 0th gate is not arbitrable.
ATANOR_TIER = "reflex"
