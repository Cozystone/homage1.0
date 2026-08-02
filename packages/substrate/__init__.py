# -*- coding: utf-8 -*-
"""substrate — axis v7: a thing's coordinates read off HOW IT BEHAVES, not from what it is called.

`fhrr_core` assigns every atom a hash of its spelling, so the geometry carries no behavioural
information and nothing can transfer through it. This package is the other option, and V7-0
(``behaviour.read_signal``) is the rung that decides whether it carries any signal at all.
"""
from packages.substrate.behaviour import (  # noqa: F401
    Behaviour, SignalReading, behaviour_of, decisive_kind, distance, kind_match, rank_kinds,
    read_signal,
    shared_basis, shuffled)
from packages.substrate.holo import (  # noqa: F401
    OVERLAP_GATE, ProjectionReading, holo_distance, project, read_projection)
from packages.substrate.transfer import (  # noqa: F401
    SEPARATION_GATE, TransferReading, fit_direction, read_transfer, separation)

__all__ = ["Behaviour", "SignalReading", "behaviour_of", "distance", "read_signal",
           "shared_basis", "shuffled", "kind_match", "rank_kinds", "decisive_kind",
           "OVERLAP_GATE", "ProjectionReading", "holo_distance", "project", "read_projection",
           "SEPARATION_GATE", "TransferReading", "fit_direction", "read_transfer", "separation"]

# Plan v5 §2 tier -- observation is universal, control is differential.
# Reflex: V7-0 is an evaluator of the axis it belongs to, and an evaluator the orchestrator could
# overrule measures nothing.
ATANOR_TIER = "reflex"
