# -*- coding: utf-8 -*-
"""Epistemic-tier tagging — 기관 C of ATANOR V2 (holographic temporal reasoning).

The one thing Gemini's vision got exactly right (advisor = DATA, we adjudicate): a time-reasoning
output must carry a STRICT epistemic status, and only present/recorded claims may be voiced as fact.
That was ALREADY our doctrine — the generative-leap rule ("a leap is flagged, never asserted") and
block_universe stamping every projection ``hypothesis=True``. This module turns the convention into an
ENFORCED LAYER: every temporal claim is tagged with one of four tiers; the two HYPOTHESIS tiers
(RETRODICTED / PROJECTED) can never be surfaced without the canonical hedge; and the tag is IMMUTABLE
so it can never be silently stripped to bare fact downstream (작화 0 강제).

The four tiers (design doc §3 기관 C):
  PERCEIVED   — present perception ("now").                              -> assertable as fact
  RECORDED    — a measured fact on the UTC timeline (unified_timeline).  -> assertable as fact
  RETRODICTED — backward inference over learned order (infer_backward).  -> a HYPOTHESIS, must hedge
  PROJECTED   — forward projection / branch (project_forward, branches). -> a HYPOTHESIS, must hedge

The hedge phrasings are reused VERBATIM from ``block_universe.render_human`` — a tiered surface reads
in the block-universe narrator's own voice, and there is a single source of the "not a certainty"
wording (no second phrasing to drift out of sync).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Tier(str, Enum):
    PERCEIVED = "PERCEIVED"
    RECORDED = "RECORDED"
    RETRODICTED = "RETRODICTED"
    PROJECTED = "PROJECTED"


# the two tiers that MAY be voiced as fact; the other two must always carry a hedge marker
ASSERTABLE: frozenset[Tier] = frozenset({Tier.PERCEIVED, Tier.RECORDED})
HYPOTHESIS: frozenset[Tier] = frozenset({Tier.RETRODICTED, Tier.PROJECTED})

# Canonical hedge markers — the EXACT substrings block_universe.render_human emits, so this
# enforcement is satisfied by the narrator's own words. (render_human forward line ends
# "— a projection, not a certainty."; backward line ends "— an inference from learned order, not a
# record.") Kept as lowercase fragments for case-insensitive containment checks.
_PROJECTED_MARK = "a projection, not a certainty"
_RETRODICTED_MARK = "an inference from learned order, not a record"
# the shared terse cores, accepted as a fallback hedge (still explicit, never bare fact)
_GENERIC_FRAGMENTS = ("not a certainty", "not a record")


class EpistemicViolation(RuntimeError):
    """Raised when a HYPOTHESIS-tier claim would be surfaced WITHOUT its required hedge marker.
    Voicing a projection/retrodiction as a bare certainty is a 작화-0 violation, refused here."""


def is_hypothesis(tier: Tier | str) -> bool:
    """RETRODICTED / PROJECTED -> True (must always be hedged). Never silently False for these."""
    return Tier(tier) in HYPOTHESIS


def is_assertable(tier: Tier | str) -> bool:
    """PERCEIVED / RECORDED -> True (may be voiced as fact)."""
    return Tier(tier) in ASSERTABLE


def marker_for(tier: Tier | str) -> str | None:
    """The canonical hedge a surfaced claim of this tier MUST contain (None for assertable tiers)."""
    t = Tier(tier)
    if t is Tier.PROJECTED:
        return _PROJECTED_MARK
    if t is Tier.RETRODICTED:
        return _RETRODICTED_MARK
    return None


def _carries_hedge(tier: Tier, text: str) -> bool:
    if tier not in HYPOTHESIS:
        return True
    low = (text or "").lower()
    mark = marker_for(tier)
    if mark and mark in low:
        return True
    return any(frag in low for frag in _GENERIC_FRAGMENTS)


@dataclass(frozen=True)
class TieredClaim:
    """An epistemically-tagged temporal claim.

    FROZEN by design: the tier can never be silently mutated or stripped after construction (any
    attribute assignment raises ``dataclasses.FrozenInstanceError``). The ``hypothesis`` flag is
    DERIVED from the tier — it cannot be constructed out of step with the tier, so a hypothesis tier
    can never masquerade as assertable.
    """
    text: str
    tier: Tier
    confidence: float | None = None

    def __post_init__(self) -> None:
        # normalize a str/enum tier in place (still frozen for every later assignment)
        object.__setattr__(self, "tier", Tier(self.tier))

    @property
    def hypothesis(self) -> bool:
        return self.tier in HYPOTHESIS

    @property
    def assertable(self) -> bool:
        return self.tier in ASSERTABLE

    def hedged(self) -> bool:
        """Does the surface text already carry the required hedge for this tier?"""
        return _carries_hedge(self.tier, self.text)


def tag(text: str, tier: Tier | str, confidence: float | None = None) -> TieredClaim:
    """Tag a temporal claim with its epistemic tier. Pure — performs no marker enforcement itself
    (call :func:`enforce` before surfacing a hypothesis-tier claim)."""
    return TieredClaim(text=text, tier=Tier(tier), confidence=confidence)


def enforce(claim: TieredClaim) -> TieredClaim:
    """Assert a HYPOTHESIS-tier claim carries its hedge marker; raise :class:`EpistemicViolation` if
    the tag has been stripped to bare fact. Returns the claim unchanged so callers can wrap in-line::

        answer = enforce(tag(text, Tier.PROJECTED, conf)).text

    ASSERTABLE tiers (PERCEIVED / RECORDED) pass through untouched — they need no hedge.
    """
    if claim.tier in HYPOTHESIS and not claim.hedged():
        raise EpistemicViolation(
            f"{claim.tier.value} claim surfaced without its hedge marker "
            f"({marker_for(claim.tier)!r}); refusing to voice a projection as a certainty (작화 0).")
    return claim


def assertable_as_fact(claim: TieredClaim) -> bool:
    """CO L2's speak-as-fact gate: only PERCEIVED / RECORDED may be voiced as fact. A hypothesis tier
    returns False — the caller MUST keep the hedge (never promote a projection to a bare assertion)."""
    return claim.tier in ASSERTABLE
