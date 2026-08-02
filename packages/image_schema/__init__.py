# -*- coding: utf-8 -*-
"""Image-schema basis: the closed set of primitives an instruction can mean, and one executor.

The basis is written; the map from a word to a schema is NOT, and never will be here. See
docs/ATANOR_action_wiring_from_language_2026-07-29.md for why that line is where it is.
"""
from packages.image_schema.basis import (          # noqa: F401
    Blockage, Containment, Contact, Existence, Order, PartWhole, Path, Possession, Proximity,
    Schema, Transfer, IMPLEMENTED, NOT_YET, choose, satisfaction,
)
from packages.image_schema.scenes import MetricScene, RegionScene, SymbolicScene  # noqa: F401
