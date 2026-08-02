# -*- coding: utf-8 -*-
"""VSA reasoning — wiring ATANOR's holographic/FHRR substrate into ALGEBRAIC rule inference.

FHRR (Fourier Holographic Reduced Representation) already lives in the codebase as a language /
speaker / code-understanding substrate (``packages/cgsr/cgsr/holographic_lm.py``). It was never
wired into *reasoning*. This package does that, following NVSA (Hersche et al., Nature Machine
Intelligence 2023, "A neuro-vector-symbolic architecture for solving Raven's progressive
matrices"): infer a transformation by UNBINDING (T = output ⊘ input) instead of searching a
program space, when — and ONLY when — the transformation is an algebraic group action the
vector algebra can represent (an additive shift on a cyclic attribute, a translation in space).

Two lanes:
  * ``rule_inference``      — infer T by one unbind per train pair, require CONSENSUS, apply to
                              the test input algebraically, decode via cleanup memory. Propose-
                              verify: the inferred rule must REPRODUCE every train pair exactly or
                              the lane abstains (0 fabrication).
  * ``behavior_signature``  — encode a primitive's I/O behaviour on a probe battery as one FHRR
                              signature; rank candidate primitives by phasor similarity to a spec
                              signature. Pure algebra, no training — search guidance for synthesis.

The bind / unbind / resonance primitives and the per-symbol phasor atom are REUSED from
``holographic_lm`` (read-only import). The ring / fractional-power encoder (φ(c)=B^c), which makes
an additive attribute rule a single algebraic T, is NEW here — ``holographic_lm`` has no ring.
"""
from __future__ import annotations

from packages.vsa_reasoning.fhrr_core import (
    RingCodebook,
    bind,
    unbind,
    superpose,
    resonance,
    cleanup,
    atom,
)
from packages.vsa_reasoning.rule_inference import (
    ShiftRule,
    infer_shift_rule,
    infer_colormap_rule,
    infer_position_shift_rule,
)
from packages.vsa_reasoning.behavior_signature import (
    behavior_signature,
    spec_signature,
    rank_candidates,
)

__all__ = [
    "RingCodebook",
    "bind",
    "unbind",
    "superpose",
    "resonance",
    "cleanup",
    "atom",
    "ShiftRule",
    "infer_shift_rule",
    "infer_colormap_rule",
    "infer_position_shift_rule",
    "behavior_signature",
    "spec_signature",
    "rank_candidates",
]
