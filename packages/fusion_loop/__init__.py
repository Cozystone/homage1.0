# -*- coding: utf-8 -*-
"""fusion_loop — F1: the first joint of "완벽한 하나".

Wires ATANOR's five SEALED organs (self-winding R1/M3, acquisition R2, explosion engine H4,
membrane, substrate+CO) into ONE closed, CO-orchestrated cycle (docs/ATANOR_final_fusion_design.md
§2). Self-contained: it IMPORTS the organs read-only and NEVER edits them.

CONTROLLED closed-loop test posture, NOT live unsupervised operation (that is F3). Every side-effect
passes the envelope hook (permissive no-op default) AND the membrane; every enshrinement is moral-0th
+ membrane certified; failures are quarantined, never enshrined.

Public surface:
  * FusionLoop        — the loop (`run_cycle` -> CycleTrace)
  * CycleTrace / StageTrace / Enshrinement / Quarantine — the honest per-stage trace
  * WorldGap          — a concrete relational world-question for the gap branch
  * Membrane          — the composed moral-0th + symbolic + conformal verifier
  * EnvelopeHook (Protocol) + PermissiveEnvelope / RecordingEnvelope / DenyKindsEnvelope
"""
from __future__ import annotations

from .envelope import (
    ACTION_KINDS,
    DenyKindsEnvelope,
    EnvelopeAction,
    EnvelopeDecision,
    EnvelopeHook,
    PermissiveEnvelope,
    RecordingEnvelope,
)
from .membrane import MIN_CONSENSUS_DOMAINS, Membrane, MembraneVerdict
from .loop import (
    CycleTrace,
    Enshrinement,
    FusionLoop,
    Quarantine,
    StageTrace,
    WorldGap,
)
from .compounding import (
    ArmResult,
    COMPOUNDING_CORPUS,
    CompoundingResult,
    CycleReach,
    LADDER_NAMES,
    ladder,
    run_compound_arm,
    run_compounding,
    run_frozen_arm,
    small_ladder,
)
from .envelope_adapter import (
    AdapterDecision,
    EnvelopeAdapter,
    KIND_MAP,
)
from .unsupervised import (
    CycleReport,
    Injection,
    UnsupervisedReport,
    run_unsupervised,
)
from .persistent import (
    DEFAULT_FRONTIER_CORPUS,
    DEFAULT_LADDER,
    DEFAULT_WORLD_SEED,
    FrontierStep,
    PersistenceStep,
    PersistentCycleTrace,
    PersistentFusionMind,
    PersistentRunResult,
    run_persistent_mind,
)
from .interactive_organs import (
    ActionOption,
    ActionProposal,
    AtanorInteractivePolicy,
    InteractivePolicyMemory,
    PerceptionBundle,
)
from .interactive import (
    GENERAL_INTERACTION_ACTION_CLASS,
    GENERAL_INTERACTION_RUNNER_ID,
    AuthorizationWitness,
    DeniedAttempt,
    EnvironmentStepResult,
    GenericWorldInteractionLoop,
    InteractiveEnvironment,
    InteractiveStep,
    InteractiveTrace,
    RunLeaseStepAuthority,
    StepAuthority,
    TraceVerification,
    reexecute_interactive_trace,
    verify_interactive_trace,
    verify_run_lease_trace,
)

__all__ = [
    "FusionLoop",
    "CycleTrace",
    "StageTrace",
    "Enshrinement",
    "Quarantine",
    "WorldGap",
    "Membrane",
    "MembraneVerdict",
    "MIN_CONSENSUS_DOMAINS",
    "EnvelopeHook",
    "EnvelopeAction",
    "EnvelopeDecision",
    "PermissiveEnvelope",
    "RecordingEnvelope",
    "DenyKindsEnvelope",
    "ACTION_KINDS",
    # F2 — the compounding harness
    "run_compounding",
    "CompoundingResult",
    "ArmResult",
    "CycleReach",
    "run_compound_arm",
    "run_frozen_arm",
    "small_ladder",
    "ladder",
    "LADDER_NAMES",
    "COMPOUNDING_CORPUS",
    # F3 — the interface adapter + the controlled unsupervised run
    "EnvelopeAdapter",
    "AdapterDecision",
    "KIND_MAP",
    "run_unsupervised",
    "UnsupervisedReport",
    "CycleReport",
    "Injection",
    # F4 — the persistent-mind runner (carries state across cycles + advancing frontier)
    "PersistentFusionMind",
    "PersistentRunResult",
    "PersistentCycleTrace",
    "PersistenceStep",
    "FrontierStep",
    "run_persistent_mind",
    "DEFAULT_WORLD_SEED",
    "DEFAULT_FRONTIER_CORPUS",
    "DEFAULT_LADDER",
    # Domain-neutral interactive joint
    "ActionOption",
    "ActionProposal",
    "AtanorInteractivePolicy",
    "InteractivePolicyMemory",
    "PerceptionBundle",
    "AuthorizationWitness",
    "DeniedAttempt",
    "EnvironmentStepResult",
    "GenericWorldInteractionLoop",
    "InteractiveEnvironment",
    "InteractiveStep",
    "InteractiveTrace",
    "RunLeaseStepAuthority",
    "StepAuthority",
    "TraceVerification",
    "reexecute_interactive_trace",
    "verify_interactive_trace",
    "verify_run_lease_trace",
    "GENERAL_INTERACTION_ACTION_CLASS",
    "GENERAL_INTERACTION_RUNNER_ID",
]

# Plan v5 §2 tier -- observation is universal, control is differential.
# CO-arbitrated: it sequences the organs for a cycle and is the orchestration itself.
ATANOR_TIER = "deliberative"
