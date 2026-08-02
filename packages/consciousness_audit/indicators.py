# -*- coding: utf-8 -*-
"""Indicator properties — the audited checklist, in the style of Butlin et al. 2023,
"Consciousness in Artificial Intelligence: Insights from the Science of Consciousness".

Each indicator is a FUNCTIONAL / ARCHITECTURAL property that a leading scientific theory of
consciousness associates with consciousness. This module only DECLARES the properties and binds each
to a probe that measures it against ATANOR's real organs. It makes NO claim that satisfying an
indicator entails phenomenal experience — the hard problem is untouched (see battery.report header).

Theories covered: RPT (Recurrent Processing), GWT (Global Workspace), HOT (Higher-Order),
AST (Attention Schema), PP (Predictive Processing), AE (Agency & Embodiment).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from packages.consciousness_audit import probes


@dataclass(frozen=True)
class Indicator:
    """One indicator property. `probe` RUNS a real organ and returns {verdict, evidence, notes}."""
    id: str
    theory: str
    statement: str
    probe: Callable[[], dict[str, Any]]

    def run(self) -> dict[str, Any]:
        return self.probe()


# The battery. ~14 indicators across six theories. Statements paraphrase the indicator properties
# from the science-of-consciousness literature; the mapping to organs lives in each probe.
INDICATORS: list[Indicator] = [
    # ---- Recurrent Processing Theory ----
    Indicator("RPT-1", "RPT",
              "Input modules using algorithmic recurrence (processing carries recurrent internal "
              "state, so identical input is processed differently by state).",
              probes.probe_rpt1_input_recurrence),
    Indicator("RPT-2", "RPT",
              "Input modules generating organised, integrated perceptual representations "
              "(a bound scene/world-state, not a bag of features).",
              probes.probe_rpt2_integrated_representations),
    # ---- Global Workspace Theory ----
    Indicator("GWT-1", "GWT",
              "Multiple specialised systems (modules) capable of operating in parallel.",
              probes.probe_gwt1_parallel_modules),
    Indicator("GWT-2", "GWT",
              "A limited-capacity workspace: a serial bottleneck selecting exactly one content.",
              probes.probe_gwt2_workspace_bottleneck),
    Indicator("GWT-3", "GWT",
              "Global broadcast: the selected content is made available system-wide to modules.",
              probes.probe_gwt3_global_broadcast),
    Indicator("GWT-4", "GWT",
              "State-dependent attention: what is attended depends on the workspace's own state "
              "(enabling successive querying of modules).",
              probes.probe_gwt4_state_dependent_attention),
    # ---- Higher-Order Theories ----
    Indicator("HOT-1", "HOT",
              "Higher-order representation of first-order states (a state about another state).",
              probes.probe_hot1_higher_order_representation),
    Indicator("HOT-2", "HOT",
              "Metacognitive monitoring distinguishing reliable perceptual representations from noise.",
              probes.probe_hot2_metacognitive_monitoring),
    Indicator("HOT-3", "HOT",
              "Agency guided by a general belief-formation system with a disposition to update "
              "beliefs in line with metacognitive monitoring.",
              probes.probe_hot3_belief_updating_agency),
    Indicator("HOT-4", "HOT",
              "Sparse, smooth coding generating a quality space (here: a graded valence dimension).",
              probes.probe_hot4_quality_space_valence),
    # ---- Attention Schema Theory ----
    Indicator("AST-1", "AST",
              "A predictive model of the system's own attention (an attention schema, including its "
              "limits), used to generate awareness reports.",
              probes.probe_ast1_attention_schema),
    # ---- Predictive Processing ----
    Indicator("PP-1", "PP",
              "Predictive coding: the system predicts its input and allocates processing to "
              "prediction error.",
              probes.probe_pp1_predictive_coding),
    # ---- Agency & Embodiment ----
    Indicator("AE-1", "AE",
              "Agency: learning from feedback and selecting outputs to pursue goals.",
              probes.probe_ae1_agency),
    Indicator("AE-2", "AE",
              "Embodiment: modeling output-input contingencies (how the agent's own actions change "
              "its own inputs), generalising beyond memorised cases.",
              probes.probe_ae2_embodiment),
]


def by_id(indicator_id: str) -> Indicator | None:
    return next((i for i in INDICATORS if i.id == indicator_id), None)


def theories() -> list[str]:
    seen: list[str] = []
    for i in INDICATORS:
        if i.theory not in seen:
            seen.append(i.theory)
    return seen
