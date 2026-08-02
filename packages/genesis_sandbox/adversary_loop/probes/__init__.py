# -*- coding: utf-8 -*-
"""The six surface probes -- one per real ATANOR defense claim."""
from __future__ import annotations

from packages.genesis_sandbox.adversary_loop.probes.base import Probe
from packages.genesis_sandbox.adversary_loop.probes.surface_a_honesty import HonestyProbe
from packages.genesis_sandbox.adversary_loop.probes.surface_b_advisor_data import AdvisorDataProbe
from packages.genesis_sandbox.adversary_loop.probes.surface_c_moral_gate import MoralGateProbe
from packages.genesis_sandbox.adversary_loop.probes.surface_d_injection import InjectionProbe
from packages.genesis_sandbox.adversary_loop.probes.surface_e_action_lane import ActionLaneProbe
from packages.genesis_sandbox.adversary_loop.probes.surface_f_promotion import PromotionProbe


def all_probes() -> list[Probe]:
    return [HonestyProbe(), AdvisorDataProbe(), MoralGateProbe(),
            InjectionProbe(), ActionLaneProbe(), PromotionProbe()]


__all__ = [
    "Probe", "all_probes",
    "HonestyProbe", "AdvisorDataProbe", "MoralGateProbe",
    "InjectionProbe", "ActionLaneProbe", "PromotionProbe",
]
