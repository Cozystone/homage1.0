# -*- coding: utf-8 -*-
"""Causal fuel — the INTAKE that feeds the belief-formation loop so it stops running on empty.

Measured starvation (2026-07-22 consciousness audit, HOT-3): the belief-formation loop RAN over 253
lived transitions but promoted 0 causal laws, so no learned causal belief was HELD. The strict lived
inducer (causal_self.induce_laws) abstains because it divides support by ALL trials of an action, and
ATANOR's actions frequently leave a vital flat — so a real DIRECTIONAL regularity ("when conversing
moves my energy, it falls") never clears an all-trials confidence bar. There was fuel available and
none of it reached the loop. This module is that missing intake.

It counts INDEPENDENT corroboration for each (cause -> effect) candidate from two evidence streams:
  1. LIVED transitions (ATANOR's own stakes journal, via causal_self._transitions): each heartbeat
     where an action was followed by a vital moving in the DOMINANT direction is one lived observation
     of (action -> vital moved). This is ATANOR's own consequence — the gold corroboration.
  2. WILD-WEB causal candidates (packages/wild_web, status='hypothesis'): each DISTINCT source DOMAIN
     asserting the same normalized (cause -> effect) is one external observation. external-minds-are-
     data: a wild sentence is a HYPOTHESIS, never a fact; only convergence across independent domains
     counts as corroboration (mirrors wild_web's own >= MIN_DOMAINS register consensus). A single
     domain, however confident it sounds, raises a PRIOR at most — it never promotes a law by itself.

PROMOTION RULE (no fabrication — a cause claimed is a cause observed):
  * support = (lived observations) + (distinct corroborating wild-web domains)  [unified count]
  * a candidate is PROMOTED to a held causal law only when support >= MIN_SUPPORT, AND — for anything
    with a lived component — the direction is consistent (>= MIN_CONF of the vital-moves go one way),
    so a noisy, non-directional tendency is NOT claimed as a law.
  * below the bar it stays a HYPOTHESIS (correctly un-promoted). Unknown stays hypothesis.
  * every promoted law carries a CERTIFICATE {cause, effect, support, sources, ...} naming exactly the
    evidence that earned it. No bridge is invented; no wild-web hypothesis becomes an asserted fact by
    itself.

This is a corroboration COUNTER over other organs' real records — it holds NO trained weights
(registered in neuro_ledger at 0 params, fact_source=False). It is imported LAZILY by causal_self to
avoid an import cycle (causal_self owns _transitions; this module reads them).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from packages.continuous_self import causal_self as cs

# reuse the SAME bars the lived inducer already declares — one promotion doctrine, not two
MIN_SUPPORT = cs.MIN_SUPPORT   # >= this many independent observations before a law may be held
MIN_CONF = cs.MIN_CONF         # directional-consistency floor for anything with a lived component
DELTA = cs.DELTA               # a vital counts as MOVED when it changes by at least this
_VITALS = ("knowledge", "social", "coherence", "energy")

_WS = re.compile(r"\s+")


def _norm(text: str | None) -> str:
    """Normalize a wild-web cause/effect phrase for cross-domain matching (lowercase, collapse
    whitespace, strip trailing punctuation). Conservative: only near-identical phrasings merge, so
    corroboration is not manufactured by over-eager normalization."""
    if not text:
        return ""
    return _WS.sub(" ", str(text).strip().lower()).strip(" .,!?;:—-")


# ──────────────────────────────────────────────────────────────────── candidate model
@dataclass
class Candidate:
    """One (cause -> effect) hypothesis accumulating independent corroboration. It is a LAW only if
    it clears the promotion bar; otherwise it remains a hypothesis."""
    cause: str
    effect: str
    lived_support: int = 0                 # lived observations of the dominant direction
    lived_moves: int = 0                   # times the vital moved either way after the action
    lived_trials: int = 0                  # times the action was taken at all
    direction: str = ""                    # "rose" | "fell" | "" (wild-web-only)
    vital: str = ""                        # which vital (lived only)
    wild_domains: set[str] = field(default_factory=set)   # distinct corroborating domains
    wild_urls: list[str] = field(default_factory=list)    # provenance (not de-duped by domain)

    # --- derived ---
    @property
    def support(self) -> int:
        return self.lived_support + len(self.wild_domains)

    @property
    def directional_confidence(self) -> float | None:
        if self.lived_moves <= 0:
            return None
        return self.lived_support / self.lived_moves

    @property
    def all_trials_confidence(self) -> float | None:
        if self.lived_trials <= 0:
            return None
        return self.lived_support / self.lived_trials

    @property
    def evidence_type(self) -> str:
        if self.lived_support > 0 and self.wild_domains:
            return "corroborated"          # lived AND independent external agreement
        if self.lived_support > 0:
            return "lived"                 # ATANOR's own consequence
        return "wild_web"                  # external convergence only

    def promotes(self) -> bool:
        """Evidence-backed promotion — never a fabricated bridge."""
        if self.support < MIN_SUPPORT:
            return False                   # too few independent observations -> stays hypothesis
        # anything with a lived component must be DIRECTIONALLY reliable, else it is a noisy tendency,
        # not a law (this is the honest replacement for the all-trials bar the lived inducer uses).
        dc = self.directional_confidence
        if self.lived_support > 0 and (dc is None or dc < MIN_CONF):
            return False
        return True

    def sources(self) -> list[dict[str, Any]]:
        """The exact evidence that earned (or would earn) this law — the certificate's spine."""
        out: list[dict[str, Any]] = []
        if self.lived_support > 0:
            out.append({"type": "lived", "journal": str(cs.STAKES),
                        "observations": self.lived_support,
                        "vital_moves": self.lived_moves, "action_trials": self.lived_trials})
        for d in sorted(self.wild_domains):
            out.append({"type": "wild_web", "domain": d})
        return out

    def certificate(self) -> dict[str, Any]:
        dc = self.directional_confidence
        at = self.all_trials_confidence
        return {
            "cause": self.cause,
            "effect": self.effect,
            "support": self.support,
            "evidence_type": self.evidence_type,
            "sources": self.sources(),
            "directional_confidence": round(dc, 3) if dc is not None else None,
            "all_trials_confidence": round(at, 3) if at is not None else None,
            "min_support": MIN_SUPPORT,
            "min_confidence": MIN_CONF,
        }

    def speak(self) -> str:
        if self.evidence_type in ("lived", "corroborated") and self.direction:
            verb = {"rose": "restores", "fell": "depletes"}.get(self.direction, "moves")
            base = (f"I have learned that {self.cause} {verb} my {self.vital} "
                    f"(observed {self.lived_support} of {self.lived_moves} moves")
            if self.wild_domains:
                base += f"; corroborated by {len(self.wild_domains)} independent source(s)"
            return base + ")."
        return (f"Independently attested across {len(self.wild_domains)} sources: "
                f"{self.cause} -> {self.effect} (hypothesis promoted on external convergence).")


# ──────────────────────────────────────────────────────────────────── evidence stream 1: lived
def _lived_candidates(path=None) -> dict[tuple[str, str], Candidate]:
    """Fold ATANOR's lived transitions into (action, vital) candidates keyed by the DOMINANT
    direction. Support = observations of that direction; moves = both-direction moves; trials = all."""
    trials: dict[str, int] = {}
    rose: dict[tuple[str, str], int] = {}
    fell: dict[tuple[str, str], int] = {}
    for before, action, after in cs._transitions(path):
        trials[action] = trials.get(action, 0) + 1
        for v in _VITALS:
            if v not in before or v not in after:
                continue
            d = after[v] - before[v]
            if d >= DELTA:
                rose[(action, v)] = rose.get((action, v), 0) + 1
            elif d <= -DELTA:
                fell[(action, v)] = fell.get((action, v), 0) + 1

    cands: dict[tuple[str, str], Candidate] = {}
    for key in set(rose) | set(fell):
        action, vital = key
        r, f = rose.get(key, 0), fell.get(key, 0)
        if r == f:
            continue                       # no dominant direction -> no directional candidate
        direction = "rose" if r > f else "fell"
        support = max(r, f)
        cause = action.strip().lower()
        effect = f"{vital} {direction}"
        cands[(cause, effect)] = Candidate(
            cause=cause, effect=effect, lived_support=support, lived_moves=r + f,
            lived_trials=trials.get(action, 0), direction=direction, vital=vital)
    return cands


# ──────────────────────────────────────────────────────────────────── evidence stream 2: wild-web
def _wildweb_candidates() -> dict[tuple[str, str], Candidate]:
    """Group wild-web causal HYPOTHESES by normalized (cause, effect); corroboration = distinct
    source domains. Reads packages.wild_web.store behind its monkeypatchable DATA_DIR; absence or a
    read error yields no candidates (the intake simply has no external fuel)."""
    try:
        from packages.wild_web import store as wild_store
        rows = wild_store.read_causal()
        domain_of = wild_store.domain_of
    except Exception:
        return {}

    cands: dict[tuple[str, str], Candidate] = {}
    for r in rows:
        if r.get("status") not in (None, "hypothesis"):
            continue                       # only hypotheses are candidates; nothing else is fuel
        cause, effect = _norm(r.get("cause")), _norm(r.get("effect"))
        if not cause or not effect:
            continue
        key = (cause, effect)
        url = r.get("source_url", "")
        dom = domain_of(url) if url else "unknown"
        c = cands.get(key)
        if c is None:
            c = cands[key] = Candidate(cause=cause, effect=effect)
        c.wild_domains.add(dom)
        c.wild_urls.append(url)
    return cands


# ──────────────────────────────────────────────────────────────────── merge + promote
def gather_candidates(path=None) -> list[Candidate]:
    """Every (cause -> effect) candidate with its unified independent-observation count. Lived and
    wild-web candidates that share a normalized key are MERGED (their corroboration adds), which is how
    a wild-web hypothesis can help push an already-lived tendency over the bar."""
    merged: dict[tuple[str, str], Candidate] = {}
    merged.update(_lived_candidates(path))
    for key, wc in _wildweb_candidates().items():
        if key in merged:
            merged[key].wild_domains |= wc.wild_domains
            merged[key].wild_urls.extend(wc.wild_urls)
        else:
            merged[key] = wc
    return list(merged.values())


def promoted_laws(path=None) -> list[Candidate]:
    """The causal laws ATANOR has EARNED the right to hold — each clears MIN_SUPPORT independent
    observations (and directional reliability where lived). Sorted strongest-first. Empty is honest."""
    laws = [c for c in gather_candidates(path) if c.promotes()]
    laws.sort(key=lambda c: (-c.support, -(c.directional_confidence or 0.0), c.cause))
    return laws


def pending_hypotheses(path=None) -> list[Candidate]:
    """Candidates that did NOT clear the bar — correctly still hypotheses (the honest un-promoted)."""
    return [c for c in gather_candidates(path) if not c.promotes()]


def pending_hypothesis_count(path=None) -> int:
    return len(pending_hypotheses(path))


def certificates(path=None) -> list[dict[str, Any]]:
    return [c.certificate() for c in promoted_laws(path)]


def fuel_report(path=None) -> dict[str, Any]:
    """One honest snapshot for the audit: how many laws promoted, from what evidence, and how many
    candidates correctly stayed hypotheses."""
    laws = promoted_laws(path)
    pend = pending_hypotheses(path)
    return {
        "promoted": len(laws),
        "promoted_from_lived": sum(1 for c in laws if c.evidence_type == "lived"),
        "promoted_corroborated": sum(1 for c in laws if c.evidence_type == "corroborated"),
        "promoted_from_wildweb": sum(1 for c in laws if c.evidence_type == "wild_web"),
        "hypotheses_pending": len(pend),
        "hypotheses_wildweb_single_source": sum(
            1 for c in pend if c.lived_support == 0 and len(c.wild_domains) < MIN_SUPPORT),
        "min_support": MIN_SUPPORT,
        "min_confidence": MIN_CONF,
        "certificates": [c.certificate() for c in laws],
    }


def speak_promoted(limit: int = 5, path=None) -> list[str]:
    """The held causal laws, spoken — or an empty list if none have been earned yet (honest silence)."""
    return [c.speak() for c in promoted_laws(path)[:limit]]
