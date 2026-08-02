"""ATANOR digital ecosystem — an ISOLATED, OBSERVE-only evolution experiment.

The owner's reframed connectome idea: not a reasoner, but a META-CONTROLLER
(attention/energy scheduler) whose arbitrary firing→trust mapping is replaced
by NATURAL SELECTION — the existing hallucination-0 guardrail is the predator
that kills any agent whose scheduling injects a false fact.

This package is the SANDBOX that tests whether that mechanism actually works,
measured, before anything touches the live answer path:
  * agents are tiny scheduling policies (optionally connectome-shaped)
  * fitness = correct internal scheduling MINUS a death penalty for any decision
    the trusted guardrail flags as a hallucination
  * evolution = mutate + select + kill; only coherent survivors replicate
  * an A/B compares connectome-initialised vs random-initialised populations,
    so we can HONESTLY say whether the biological topology helps or is narrative

Nothing here writes to any store, touches the answer path, or asserts a fact.
It is a measured experiment; promotion to anything live would be a separate,
human-gated decision — same discipline as every other ATANOR subsystem.
"""

from .evolution import Agent, Ecosystem, connectome_seed, evolve, run_ab

__all__ = ["Agent", "Ecosystem", "connectome_seed", "evolve", "run_ab"]
