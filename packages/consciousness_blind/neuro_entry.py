# -*- coding: utf-8 -*-
"""Neuro-ledger self-registration for the blind consciousness-indicator judge.

Honest count: ZERO learned parameters. The blind judge is a MEASUREMENT / DISCRIMINATION instrument
(the same control-organ category as metacog_baselines and felt_judgment) — its held-out stimuli and
adversarial controls are curated structure, not weights fit to data, and there is no artifact on disk.
It is registered so the neuro budget audit and the unregistered-artifact detector account for it, and
`fact_source=False` is invariant: an assessor scores indicator properties, it never provides world
facts (and it makes no phenomenal claim).
"""
from __future__ import annotations


def ledger_entry():
    from packages.neuro_ledger.ledger import Organ
    return Organ(
        id="consciousness_blind_judge",
        path="packages/consciousness_blind/judge.py",
        role="developer-blind adversarial assessor for the 14 consciousness-INDICATOR properties "
             "(Butlin et al. 2023): re-derives each verdict from ATANOR's real organs with HELD-OUT "
             "stimuli + a falsification control, structurally separated from consciousness_audit "
             "(never imports its probes). A measurement instrument, never a fact source; makes NO "
             "phenomenal claim (qualia is scientifically undecidable)",
        gate="consciousness_blind judge (author/judge separation + held-out positive + adversarial "
             "falsification; present requires positive AND the control rejecting the falsification)",
        artifacts=[],                 # no weight artifacts on disk — curated stimuli + controls
        fact_source=False,            # INVARIANT: scores indicator properties, never provides facts
        enforced=False,               # control/measurement tier: zero budget impact
        status="active",
        fallback_params=0,            # honest count: 0 trained parameters
    )
