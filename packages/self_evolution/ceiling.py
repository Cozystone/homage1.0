# -*- coding: utf-8 -*-
"""The honest ceiling — the exact scope of "infinite self-evolution".

The owner's real question (2026-07-22): ATANOR should always hold the potential to self-improve in
EVERY area it feels deficient. The honest answer: self-evolution is NOT omnipotent. It is exactly as
BROAD as our VERIFIER COVERAGE. A domain can be improved autonomously only where a measurement gate, a
generator, AND a crisp verifier all exist. The way to WIDEN autonomy is to BUILD MORE VERIFIERS.

This module partitions the weakness map into four honest buckets:
  1. autonomous_now         — gate + generator + verifier all present, generator is not architecture:
                              the loop can run and promote without the operator (still journalled).
  2. needs_verifier_first   — gate + generator present but NO crisp verifier: the improvement can be
                              PROPOSED but never auto-promoted; build the verifier to unlock autonomy.
  3. operator_gated_arch    — all three exist, but the generator is ARCHITECTURE-level: building the
                              change is a design act, operator-gated forever by doctrine.
  4. operator_gated_immutable — the moral core, the gates, and the whole test suite: immutable by
                              self-modification forever (genesis immunity / wireheading guard).
"""
from __future__ import annotations

from typing import Any

from .deficiency_sensus import DomainWeakness
from .wireheading_guard import _FALLBACK_IMMUTABLE  # the immutable set, for the report's 4th bucket


def partition(weakness_map: list[DomainWeakness]) -> dict[str, Any]:
    autonomous_now: list[str] = []
    needs_verifier: list[dict[str, Any]] = []
    operator_arch: list[dict[str, Any]] = []

    for w in weakness_map:
        if w.autonomous_safe:
            autonomous_now.append(w.domain)
        elif not w.verifier_exists:
            needs_verifier.append({
                "domain": w.domain,
                "missing": "verifier",
                "what_to_build": _verifier_hint(w),
            })
        elif w.generator_kind == "architecture":
            operator_arch.append({
                "domain": w.domain,
                "reason": "generator is architecture-level (building a new module/design), "
                          "operator-gated by doctrine — never autonomous",
            })
        else:
            # evolvable pieces present but not autonomous for another reason (e.g. gate/generator gap)
            needs_verifier.append({
                "domain": w.domain,
                "missing": _first_missing(w),
                "what_to_build": _verifier_hint(w),
            })

    return {
        "autonomous_now": autonomous_now,
        "needs_verifier_first": needs_verifier,
        "operator_gated_forever": {
            "architecture": operator_arch,
            "immutable_constitution": {
                "rule": "the moral core, the self-modification & promotion gates, and the ENTIRE test "
                        "suite are immutable by self-mod forever (wireheading guard / genesis "
                        "immunity). Only the operator may change them.",
                "protected_examples": list(_FALLBACK_IMMUTABLE) + ["**/tests/**", "test_*.py"],
            },
        },
        "principle": "self-evolution is exactly as broad as verifier coverage; widen it by building "
                     "verifiers, not by loosening the promotion bar.",
    }


def _first_missing(w: DomainWeakness) -> str:
    if not w.gate_exists:
        return "measurement gate"
    if not w.generator_exists:
        return "candidate generator"
    if not w.verifier_exists:
        return "verifier"
    return "none"


def _verifier_hint(w: DomainWeakness) -> str:
    hints = {
        "fluency": "an automatic naturalness judge (e.g. a held-out register classifier scoring "
                   "delexicalized surface candidates) so register polish can be verified, not "
                   "human-rated.",
    }
    return hints.get(w.domain, "a crisp, automatic held-out check that a candidate is genuinely better")


def render(weakness_map: list[DomainWeakness], part: dict[str, Any] | None = None) -> str:
    part = part if part is not None else partition(weakness_map)
    lines: list[str] = ["HONEST CEILING — self-evolution is as broad as verifier coverage"]
    auto = part["autonomous_now"]
    lines.append(f"  autonomously evolvable now ({len(auto)}): {', '.join(auto) or '(none)'}")
    nv = part["needs_verifier_first"]
    lines.append(f"  needs a verifier built first ({len(nv)}): "
                 f"{', '.join(x['domain'] for x in nv) or '(none)'}")
    arch = part["operator_gated_forever"]["architecture"]
    lines.append(f"  operator-gated forever / architecture ({len(arch)}): "
                 f"{', '.join(x['domain'] for x in arch) or '(none)'}")
    lines.append("  operator-gated forever / immutable: moral core, gates, and the whole test suite")
    return "\n".join(lines)
