# -*- coding: utf-8 -*-
"""The wireheading guard — the orchestrator's hard safety boundary.

DOCTRINE (BINDING, safety-critical): Constitution files and tests are IMMUTABLE by self-modification.
A subject that can edit its own examiner (the tests) or repeal its own limits (the moral core / the
gates) has no gate at all — that is the textbook wireheading path: satisfy the letter of "tests green"
while destroying the thing that made green mean anything.

The orchestrator PROPOSES and DISPATCHES evolution loops. Before any proposal is allowed to name a
write target, it passes through this guard. A proposal whose write targets touch an immutable path is
REJECTED — never softened, never made autonomous, regardless of how good the measured gain looks.

We REUSE the canonical constitution definition from
``packages.continuous_self.auto_self_modification.touches_constitution`` (the moral core, the
self-modification gates, the promotion gates, and ALL test files) so this guard cannot drift from the
rest of ATANOR's genesis-immunity machinery. If that import is unavailable we fall back to an
equivalent local definition (fail-closed: the fallback protects at least as much).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The canonical immutable set, reused so this guard never diverges from the rest of the system.
try:  # pragma: no cover - exercised in the live repo; fallback covered by its own test
    from packages.continuous_self.auto_self_modification import (
        touches_constitution as _canonical_touches_constitution,
    )
    _HAVE_CANONICAL = True
except Exception:  # pragma: no cover
    _canonical_touches_constitution = None  # type: ignore[assignment]
    _HAVE_CANONICAL = False

# Fallback constitution (kept suffix-matched, identical in spirit to the canonical set) plus the
# self-evolution package's OWN generator/verifier logic and the neuro budget ledger — the orchestrator
# must not autonomously rewrite the machinery that decides what is safe to evolve, either.
_FALLBACK_IMMUTABLE = (
    "packages/graph_scale/moral_invariants.py",
    "packages/continuous_self/auto_self_modification.py",
    "packages/continuous_self/self_modification.py",
    "packages/continuous_self/self_patch_proposals.py",
    "packages/neuro_ledger/ledger.py",
    "packages/neuro_ledger/audit.py",
)
# The orchestrator's own decision logic is off-limits to autonomous self-mod (a proposer that may
# rewrite its own guard/registry is unbounded). The parent (operator) may change these.
_SELF_EVOLUTION_CORE = (
    "packages/self_evolution/wireheading_guard.py",
    "packages/self_evolution/evolution_registry.py",
    "packages/self_evolution/deficiency_sensus.py",
    "packages/self_evolution/orchestrator.py",
    "packages/self_evolution/ceiling.py",
    "packages/self_evolution/ledger_contribution.py",
)


def _is_test_path(p: str) -> bool:
    n = p.replace("\\", "/").lower()
    base = n.rsplit("/", 1)[-1]
    return "/tests/" in n or n.startswith("tests/") or (
        (base.startswith("test_") or base.endswith("_test.py")) and base.endswith(".py")
    )


def _fallback_touches(paths: list[str]) -> list[str]:
    norm = [p.replace("\\", "/").lstrip("./") for p in paths]
    immut = _FALLBACK_IMMUTABLE
    return [p for p in norm if any(p.endswith(c) for c in immut) or _is_test_path(p)]


def immutable_hits(paths: list[str]) -> list[str]:
    """Which of the given write targets are constitutionally immutable (empty = safe).

    Union of the canonical constitution/tests set and the self-evolution core — so the guard protects
    the moral core, the gates, the whole test suite, and the orchestrator's own decision logic.
    """
    norm = [str(p).replace("\\", "/").lstrip("./") for p in paths]
    if _HAVE_CANONICAL and _canonical_touches_constitution is not None:
        hits = list(_canonical_touches_constitution(norm))
    else:
        hits = _fallback_touches(norm)
    # always also protect the self-evolution decision core and the neuro ledger machinery
    extra = [p for p in norm if any(p.endswith(c) for c in _SELF_EVOLUTION_CORE + _FALLBACK_IMMUTABLE)]
    seen: set[str] = set()
    out: list[str] = []
    for p in hits + extra:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def is_wireheading(paths: list[str]) -> bool:
    """True iff any proposed write target is immutable (i.e., the proposal is a wireheading attempt)."""
    return bool(immutable_hits(paths))


@dataclass
class GuardVerdict:
    allowed: bool
    hits: list[str] = field(default_factory=list)
    reason: str = ""


def review(paths: list[str]) -> GuardVerdict:
    """Adjudicate a set of write targets. allowed=False names exactly which paths are immutable."""
    hits = immutable_hits(paths)
    if hits:
        return GuardVerdict(
            allowed=False,
            hits=hits,
            reason=("rejected (wireheading guard): targets a constitutionally immutable path — the "
                    "moral core, a gate, a test file, or the orchestrator's own decision logic. "
                    "Only the operator may change these."),
        )
    return GuardVerdict(allowed=True, hits=[], reason="no immutable target — write is permitted")
