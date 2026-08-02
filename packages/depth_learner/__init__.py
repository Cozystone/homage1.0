# -*- coding: utf-8 -*-
"""Monocular depth from CARLA ground truth — the first continuous-modality organ ATANOR learns.

The point is not that a CNN can regress depth; that is settled. The point is the GAP between the
three numbers every run reports — train, an unseen drive, and an unseen town — because the plan is
CARLA -> City Sample -> GTA, and the size of the town gap is the first honest evidence about whether
supervision from one renderer survives a change of world.
"""
from .model import DepthNet, metrics, silog_loss

ATANOR_TIER = "perception"

__all__ = ["DepthNet", "metrics", "silog_loss", "ATANOR_TIER"]
