# -*- coding: utf-8 -*-
"""Adapter: the System-2 back-chainer as a grounded MCQ tier for `exam_answer`. It reuses the SAME
surface extraction the discrimination organ already uses (category terms / relation cues — LAD, never
a fact) and hands the structure to the DELIBERATOR, which DERIVES a verified multi-hop answer or
abstains. Purely ADDITIVE: it returns a pick only on a verify-gated derivation, so it can convert a
would-be guess into a grounded answer but never overrides a pick the cascade already grounded, and
never fabricates (abstains → the cascade continues unchanged). No LLM.

Honest scope (why this rarely fires on GPQA): it grounds a pick only where the GRAPH holds the chain —
multi-hop is_a categorization, relation composition. Closed-book PhD-science MCQ whose facts are absent
from the graph fall straight through to the existing evidence/guess tiers — a KNOWLEDGE gap the engine
cannot and must not paper over.
"""
from __future__ import annotations

import os
from typing import Any, Callable

Fact = tuple[str, str, str]
FactsAbout = Callable[[str], list[Fact]]


def _deliberator(facts_about: FactsAbout):
    # kernels off: membership/composition needs no arithmetic, and forging on every MCQ call is waste.
    from packages.reasoning_vm.deliberator.reasoner import Deliberator
    return Deliberator(facts_about, with_kernels=False, max_depth=5, budget=2500)


def engine_pick(
    stem: str,
    choices: dict[str, str],
    facts_about: FactsAbout,
    *,
    compilation: Any | None = None,
) -> dict[str, Any] | None:
    """Grounded MCQ by DERIVATION. Currently grounds the categorization family — 'which of these is a
    <category>' — by proving (choice, is_a, category) with the multi-hop, proof-verified back-chainer
    (deeper than the single membership check discrimination already tries, and proof-carrying). Returns
    a grounded pick or None (abstain). Category extraction is reused from discrimination (surface LAD)."""
    if os.environ.get("ATANOR_S2_ENGINE", "1") == "0":
        return None
    from packages.reasoning_vm.deliberator.compiler import compile_mcq_goals

    if compilation is None:
        compilation = compile_mcq_goals(stem)
    if not compilation.compiled:
        return None
    dlb = _deliberator(facts_about)
    for goal in compilation.goals:
        # a category cannot be one of the options' own text (avoid trivial self-membership)
        out = dlb.answer_mcq_prove(
            goal.relation,
            goal.target,
            choices,
            negated=goal.negated,
        )
        if (
            out.get("choice_key") is not None
            and out.get("mode") == "grounded"
            and isinstance(out.get("hops"), int)
            and out.get("hops", 0) >= 1
            and out.get("trail")
        ):
            return {"choice_key": out["choice_key"], "mode": "grounded",
                    "confidence": out.get("confidence", 0.85),
                    "basis": f"S2-derived: {out.get('basis')}", "trail": out.get("trail"),
                    "engine": "back_chain",
                    "hops": out.get("hops", 0),
                    "multistep_fired": out.get("fired", False),
                    "compiler_schema": compilation.schema_version,
                    "compiler_rule": goal.compiler_rule,
                    "typed_relation": goal.relation}
    return None
