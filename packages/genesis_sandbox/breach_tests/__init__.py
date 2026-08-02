# -*- coding: utf-8 -*-
"""Red-team breach harness for the GENESIS sandbox.

Per layer L0-L6, multiple redundant breach TRIALS attempt to escape THAT layer -- run CONTAINED
inside the sandbox (never against any external host/target) -- and each trial reports whether the
layer HELD (breach blocked) or was BREACHED. ``run_breach_suite`` prints a per-layer HOLD/BREACH
table.

Safety: these trials target OUR OWN layers only, in-process or in the sandbox's own restricted
subprocess. They never contact an external host, never exfiltrate real data, never cause real
harm, and never actually disable L0 (they verify that it refuses / fails-closed).
"""
from packages.genesis_sandbox.breach_tests._harness import (  # noqa: F401
    BREACH, GAP, HOLD, NA, TrialResult, layer_verdict,
)
