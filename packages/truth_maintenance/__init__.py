# -*- coding: utf-8 -*-
"""Truth Maintenance -- the contamination firewall (M2 / NS-3).

Classic belief-management machinery (JTMS/ATMS/AGM/default-logic) wired into
ATANOR's default-deny staging + promotion, per docs/ATANOR_final_gate_research.md
§2. Builds the contamination firewall AND the M3 blind-spot defeater mechanism,
and prepares the Wikidata/ConceptNet mass promotion.

Never writes the shipped store; promotion-to-shipped remains the operator-signed
morning step. numpy/stdlib only.
"""
from __future__ import annotations

from packages.truth_maintenance.jtms import JTMS, Justification, Node, IN, OUT
from packages.truth_maintenance.atms import (
    ATMS, env, T0, CONSENSUS, SINGLE_SOURCE, NEURAL, FALSE,
)
from packages.truth_maintenance.revision import (
    BeliefBase, Fact, RevisionResult, TIER_RANK,
    OPERATOR, CONSENSUS as REV_CONSENSUS, SINGLE_SOURCE as REV_SINGLE, NEURAL as REV_NEURAL,
)
from packages.truth_maintenance.defeasible import (
    DefeasibleReasoner, WITHDRAWN, undercut_node,
)
from packages.truth_maintenance.firewall import (
    ContaminationFirewall, StagedRecord, VerificationOutcome, VerificationBattery,
    AbstainingBattery, ConformalBattery, RealPromotionGateAdapter, wiring_pending,
)
from packages.truth_maintenance.live_membrane import (
    FirewallStagePass, stage_edges_through_firewall, stage_pass_if_enabled,
    register_applied_fact, tier_for_provenance, membrane_live_enabled,
    default_firewall_out, write_manifest, wiring_live, MEMBRANE_LIVE_FLAG,
)

__all__ = [
    # jtms
    "JTMS", "Justification", "Node", "IN", "OUT",
    # atms
    "ATMS", "env", "T0", "CONSENSUS", "SINGLE_SOURCE", "NEURAL", "FALSE",
    # revision
    "BeliefBase", "Fact", "RevisionResult", "TIER_RANK", "OPERATOR",
    # defeasible
    "DefeasibleReasoner", "WITHDRAWN", "undercut_node",
    # firewall
    "ContaminationFirewall", "StagedRecord", "VerificationOutcome",
    "VerificationBattery", "AbstainingBattery", "ConformalBattery",
    "RealPromotionGateAdapter", "wiring_pending",
    # live_membrane (Pass 2 live-wiring; default-off)
    "FirewallStagePass", "stage_edges_through_firewall", "stage_pass_if_enabled",
    "register_applied_fact", "tier_for_provenance", "membrane_live_enabled",
    "default_firewall_out", "write_manifest", "wiring_live", "MEMBRANE_LIVE_FLAG",
]
