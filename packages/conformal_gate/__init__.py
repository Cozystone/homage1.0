# -*- coding: utf-8 -*-
"""conformal_gate — M1 / NS-1, the conformal abstention gate (ATANOR roadmap v3, phase M).

A distribution-free, finite-sample certificate that turns hallucination-0 from a doctrine
into a tunable dial: calibrate one quantile on held-out data, then a single comparison at
answer time certifies the accepted-answer false-accept rate <= alpha. A weak underlying
confidence score (our ~0.68-AUC monitor) is paid for in ABSTENTION RATE, not in safety.

Real method: split conformal (Vovk; Angelopoulos & Bates 2023) + Conformal Risk Control
(Angelopoulos et al., ICLR 2024, arXiv:2208.02814) + Mondrian per-bin conditional coverage.
No large LLM anywhere; pure numpy.

M3 adds two BETTER nonconformity signals (the lever that lowers the abstention PRICE, per the
research doc F3 -- a better score, not a different gate):
    NS-2 semantic_entropy    -- disagreement of K diverse graph traversals (identity clustering)
    NS-5 resonance_verifier  -- FHRR clean-up accept/reject: convergence + top1-top2 margin

Public API:
    conformal.calibrate / accept / calibrate_mondrian / crc_threshold / evaluate
    nonconformity.SignalVector / nonconformity / from_* readers
    gate.ConformalGate / GateDecision
    semantic_entropy.semantic_entropy / semantic_entropy_full / EntropyResult   (NS-2)
    resonance_verifier.verify_binding / build_codebook / weighted_superposition (NS-5)
"""
from packages.conformal_gate import (  # noqa: F401
    conformal, gate, nonconformity, resonance_verifier, semantic_entropy,
)
from packages.conformal_gate.gate import ConformalGate, GateDecision  # noqa: F401
from packages.conformal_gate.nonconformity import SignalVector, nonconformity as score  # noqa: F401
from packages.conformal_gate.resonance_verifier import verify_binding  # noqa: F401
from packages.conformal_gate.semantic_entropy import semantic_entropy as graph_semantic_entropy  # noqa: F401

__all__ = ["conformal", "gate", "nonconformity", "resonance_verifier", "semantic_entropy",
           "ConformalGate", "GateDecision", "SignalVector", "score",
           "verify_binding", "graph_semantic_entropy"]

# Plan v5 §2 tier -- observation is universal, control is differential.
# It decides whether ATANOR answers or abstains. A system that could overrule its own
# abstention gate would be measuring nothing -- the property this organ certifies is exactly
# the one that must not be available to a wish.
ATANOR_TIER = "reflex"
