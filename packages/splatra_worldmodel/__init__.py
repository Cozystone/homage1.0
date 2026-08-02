# -*- coding: utf-8 -*-
"""SPLATRA world model v0 -- the 3D twin of the perception V-JEPA fusion.

Design: docs/ATANOR_vjepa_fusion.md sec 9. Pipeline:

    state --encode--> turbovec z_t --JEPA g_phi(z_t, action)--> z_hat_{t+1} (light vector)
          --decode--> per-particle delta (Dynamic 3DGS deformation)
          --PBD / physics-truth VERIFY--> pass: render/advance | fail: quarantine (never learned)

Non-generative: physics drives the deformation; the turbovec/3DGS layer is the
representation/renderer, NEVER the truth signal. JEPA prediction is DATA/proposal; the
physics membrane VERIFIES; violations are quarantined. No-LLM; single model <= 25M params.

This is a v0 MECHANISM proof on TOY dynamics -- not a general real-world simulator.
Read-only imports: splatra_turbovec (codec), embodiment.splatra_body (act->predict->surprise
kernel + ground plane), splatra_imagination.generative (body particles).
"""
from __future__ import annotations

from .baselines import LinearForwardMap, PersistenceBaseline
from .contact_dynamics import (
    ContactDynamicsParams,
    ContactLatticeBody,
    contact_ground_y,
    simulate_contact_episode,
)
from .forward_model import (
    DynamicsParams,
    Episode,
    ToyDeformingBody,
    Transition,
    ground_y,
    simulate_episode,
)
from .jepa import (
    ContextEncoder,
    FieldDecoder,
    JEPAConfig,
    Predictor,
    TurbovecJEPA,
    train_jepa,
    vicreg_terms,
)
from .mechanism_proof import (
    ProofConfig,
    Scorecard,
    format_scorecard,
    run_mechanism_proof,
)
from .physics_truth import PhysicsTruthGate, PhysicsVerdict, QuarantineResult
from .rich_mechanism_proof import (
    CrossoverRow,
    RichProofConfig,
    crossover_sweep,
    format_crossover,
    run_rich_mechanism_proof,
)
from .rollout import (
    ChaosCurve,
    RolloutCurve,
    TrueDynamics,
    chaos_floor_for_model,
    default_encode,
    fit_hi_fidelity_velocity_codec,
    gate_project_fn,
    intrinsic_divergence,
    project_to_physical,
    raw_velocity_encode,
    rollout_closed_loop,
    rollout_curve,
    usable_horizon,
)
from .rollout_proof import (
    RolloutProofConfig,
    RolloutScorecard,
    format_rollout_scorecard,
    run_rollout_proof,
)
from .turbovec_field import (
    DEFAULT_FIELD_BITS,
    FIELD_NAMES,
    FieldState,
    TurbovecFieldCodec,
)

__all__ = [
    "DEFAULT_FIELD_BITS",
    "FIELD_NAMES",
    "ChaosCurve",
    "ContactDynamicsParams",
    "ContactLatticeBody",
    "ContextEncoder",
    "CrossoverRow",
    "DynamicsParams",
    "Episode",
    "FieldDecoder",
    "FieldState",
    "JEPAConfig",
    "LinearForwardMap",
    "PersistenceBaseline",
    "PhysicsTruthGate",
    "PhysicsVerdict",
    "Predictor",
    "ProofConfig",
    "QuarantineResult",
    "RichProofConfig",
    "RolloutCurve",
    "RolloutProofConfig",
    "RolloutScorecard",
    "Scorecard",
    "ToyDeformingBody",
    "Transition",
    "TrueDynamics",
    "TurbovecFieldCodec",
    "TurbovecJEPA",
    "chaos_floor_for_model",
    "contact_ground_y",
    "crossover_sweep",
    "default_encode",
    "fit_hi_fidelity_velocity_codec",
    "format_crossover",
    "format_rollout_scorecard",
    "format_scorecard",
    "gate_project_fn",
    "ground_y",
    "intrinsic_divergence",
    "project_to_physical",
    "raw_velocity_encode",
    "rollout_closed_loop",
    "rollout_curve",
    "run_mechanism_proof",
    "run_rich_mechanism_proof",
    "run_rollout_proof",
    "simulate_contact_episode",
    "simulate_episode",
    "train_jepa",
    "usable_horizon",
    "vicreg_terms",
]
