# -*- coding: utf-8 -*-
"""H4 — the GENERATIVE SELF-ACCELERATION ENGINE (Switch 2 v1).

When the invention engine hits a synthesis WALL, this package INVENTS a new scheme to cross it — the
generative bridge `meta_diagnose.propose_novel_module` marks as the frontier. It builds ON the proven
invention engine (packages/evolution scheme_synthesis / open_domain: fold_s, oe_enumerate, lambda^2
deduction, promotion) — it does not rebuild it — and closes the loop:

    wall -> failure signature -> generative proposer (recombine schemes/primitives) -> synthesise+verify
         -> promote+record -> compound.

Public surface:
  * scheme_space   — the arbitrary-k projection/computed fold substrate + the lift/grow/promote moves
  * trace_signature— FHRR failure signature over the synthesis trace (reuses vsa_reasoning algebra)
  * ledger         — scheme-recipe flywheel (reuses meta_diagnosis recipe_ledger serialisation)
  * proposer       — the generative proposer (reuses vsa_reasoning behavior_signature ranker)
  * curriculum     — the order-statistic + computed-projection wall ladder
  * h4             — the loop (`cross_wall`, `run_curriculum`) + the signal-4 harness (`signal4`)

No-LLM, numpy + stdlib, verification-anchored (propose-verify; zero fabricated modules).
"""
from __future__ import annotations
