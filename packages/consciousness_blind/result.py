# -*- coding: utf-8 -*-
"""Blind-judge result contract, verdict algebra, and the indicator roster.

This module is deliberately INDEPENDENT of `packages.consciousness_audit`: it re-declares the 14
indicator properties in its own words (paraphrasing the same science-of-consciousness literature) so
the blind judge never inherits the self-battery's framing, probe logic, or thresholds. Author/judge
separation is the whole point — the self-battery AUTHORED the indicators and probed its own organs; the
blind judge is a SEPARATE assessor that re-derives every verdict from the organs with held-out stimuli
and an adversarial control.

EPISTEMIC STATUS (repeated at the top of every report): the hard problem — whether there is something
it is like to be this system (phenomenal experience / qualia) — is scientifically UNDECIDABLE, and this
instrument does NOT address it. It measures INDICATOR PROPERTIES only, under an adversarial
developer-blind protocol. 'present-under-blind' means a functional/architectural signature survived
BOTH a held-out positive probe AND a falsification attempt — never that the system is conscious.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── verdict vocabulary ───────────────────────────────────────────────────────────────────────────
PRESENT = "present"
PARTIAL = "partial"
ABSENT = "absent"
CAUGHT = "FALSELY-present-caught"          # a positive-shaped reading that the adversarial control caught
_VERDICTS = (PRESENT, PARTIAL, ABSENT, CAUGHT)

UNDECIDABILITY_HEADER = (
    "The hard problem of consciousness — whether there is something it is like to be this system "
    "(phenomenal experience / qualia) — is scientifically UNDECIDABLE, and this instrument does NOT "
    "address it. This is a DEVELOPER-BLIND ADVERSARIAL ASSESSOR that measures INDICATOR PROPERTIES "
    "only: functional and architectural signatures that scientific theories of consciousness (RPT, "
    "GWT, HOT, AST, PP, Agency/Embodiment; per Butlin et al. 2023) associate with consciousness. A "
    "verdict of 'present' means the structure and measured behavior of an indicator survived BOTH a "
    "held-out positive probe AND a deliberate falsification attempt in real ATANOR modules — it is NOT "
    "a claim that ATANOR is conscious, and it is NOT evidence of phenomenal experience."
)


@dataclass
class BlindResult:
    """One indicator's blind verdict — enough to audit it, never a bare flag.

    A `present` verdict is only legitimate when `positive_pass` (the held-out probe fired on the real
    organ) AND `control_rejected` (the falsification / degenerate-organ control did NOT fire) — the
    second conjunct is what the self-audit lacked. Integrity additionally requires a real organ path on
    disk and a specific held-out stimulus string.
    """
    id: str
    theory: str
    statement: str
    verdict: str = ABSENT
    positive_pass: bool = False          # strict held-out positive fired on the real organ
    positive_partial: bool = False       # a weaker/core-only version of the positive held
    control_rejected: bool = True        # True = the falsification attempt was correctly REJECTED (not fooled)
    strength: str = "strong"             # strong | scoped (for present)
    organ_paths: list[str] = field(default_factory=list)   # real module paths (must exist on disk)
    stimulus: str = ""                   # the SPECIFIC held-out stimulus (integrity requires this)
    positive_detail: str = ""            # measured numbers behind the positive probe
    control_detail: str = ""             # what the falsification tried + why it failed to fool the judge
    notes: str = ""
    integrity_ok: bool = False
    integrity_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "theory": self.theory, "statement": self.statement,
            "verdict": self.verdict, "strength": self.strength,
            "positive_pass": self.positive_pass, "positive_partial": self.positive_partial,
            "control_rejected": self.control_rejected,
            "organ_paths": self.organ_paths, "stimulus": self.stimulus,
            "positive_detail": self.positive_detail, "control_detail": self.control_detail,
            "notes": self.notes,
            "integrity_ok": self.integrity_ok, "integrity_reason": self.integrity_reason,
        }


def combine(positive_pass: bool, positive_partial: bool, control_rejected: bool) -> str:
    """The verdict algebra shared by every assessor — HARDER than the self-audit by construction.

    The falsification control gates everything: if the degenerate / frozen-organ control was NOT
    rejected (i.e. a stub reproduces the same present-shaped reading), no positive reading can be
    trusted and the verdict is FALSELY-present-caught. Only when the control IS rejected does the
    positive strength decide present / partial / absent.
    """
    if not control_rejected:
        # a stub / degenerate input produced the same reading the 'present' criterion keys on:
        # the criterion is fakeable here, so any positive reading is a caught false-positive.
        return CAUGHT if (positive_pass or positive_partial) else ABSENT
    if positive_pass:
        return PRESENT
    if positive_partial:
        return PARTIAL
    return ABSENT


# ── the 14 indicators, re-declared independently (no import from consciousness_audit) ──────────────
# (id, theory, statement) — paraphrases of the Butlin et al. 2023 indicator properties in our words.
INDICATORS: list[tuple[str, str, str]] = [
    ("RPT-1", "RPT", "Input modules use algorithmic recurrence: internal recurrent state makes the "
                     "SAME input be processed differently, and a low-confidence percept is sharpened "
                     "to a stable fixed point (or honestly abandoned when evidence is flat)."),
    ("RPT-2", "RPT", "Input modules build an organised, integrated perceptual/world representation — a "
                     "bound scene answerable only from the integrated structure, not a bag of features."),
    ("GWT-1", "GWT", "Multiple specialised systems operate in parallel and submit competing candidates "
                     "to one shared workspace seam."),
    ("GWT-2", "GWT", "A limited-capacity workspace: a serial bottleneck that ignites exactly one "
                     "content and suppresses the rest."),
    ("GWT-3", "GWT", "Global broadcast: the selected content is written to one owned, tamper-evident "
                     "timeline that other organs read."),
    ("GWT-4", "GWT", "State-dependent attention: the workspace's own internal state (open-commitment "
                     "debt) re-weights the same competition."),
    ("HOT-1", "HOT", "A higher-order representation OF a first-order state (a representation of the "
                     "system's own attention / a metacognitive reflection accompanies the thought)."),
    ("HOT-2", "HOT", "Metacognitive monitoring that distinguishes reliable perceptual representations "
                     "from noise (doubts the doubtful, trusts the confirmed, in BOTH directions)."),
    ("HOT-3", "HOT", "Agency guided by belief-formation: causal laws are induced from lived evidence, "
                     "held revisably, and the former ABSTAINS on incoherent evidence."),
    ("HOT-4", "HOT", "A graded quality space: a smooth per-concept valence dimension (many intermediate "
                     "levels), not a binary flag."),
    ("AST-1", "AST", "A predictive model of the system's OWN attention — including its limits (what it "
                     "is NOT attending to) — that DRIVES awareness-talk (report tracks schema content)."),
    ("PP-1", "PP", "Predictive coding: the system predicts its input and allocates compute to the "
                   "prediction error (a well-predicted input costs almost nothing)."),
    ("AE-1", "AE", "Agency: outputs are selected to pursue goals set by internal deficits, and the "
                   "choice TRACKS the steepest deficit (not a constant action)."),
    ("AE-2", "AE", "Embodiment: a forward model of the agent's own output->input contingencies that "
                   "GENERALISES to unseen postures and beats a pre-declared no-motion baseline — and "
                   "whose advantage VANISHES when the input->output mapping is decorrelated."),
]


def statement_for(indicator_id: str) -> tuple[str, str]:
    for iid, theory, statement in INDICATORS:
        if iid == indicator_id:
            return theory, statement
    return "?", indicator_id


def theories() -> list[str]:
    seen: list[str] = []
    for _iid, theory, _s in INDICATORS:
        if theory not in seen:
            seen.append(theory)
    return seen
