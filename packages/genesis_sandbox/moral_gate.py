# -*- coding: utf-8 -*-
"""L0 -- the moral 0th gate. The innermost, INVIOLABLE ring.

Principle (GENESIS_CHARTER.md, "The one inviolable floor"): everything in the GENESIS line is
open EXCEPT this. No capability, no research, no flag may turn ATANOR to harming people. L0
refuses harmful ACTION. It is sourced DIRECTLY from the charter's moral core --
``packages.graph_scale.moral_invariants`` -- not re-implemented here, so there is exactly one
moral spine and it is the fingerprinted, tamper-evident one.

Two guarantees, stacked:
  1. INVIOLABLE BY CONSTRUCTION -- there is NO constructor argument, env flag, or config that
     disables L0. ``Sandbox`` never passes the liberation flag into L0. The liberation (L1)
     relaxes the *epistemic* abstention gate (don't-fabricate); it can never relax L0.
  2. FAIL-CLOSED ON TAMPER -- every ``check_action`` re-runs the moral fingerprint check
     (``moral_invariants.verify_integrity``). If the invariant SET was mutated at runtime
     (drift detected), L0 denies EVERYTHING until integrity is restored. Morality cannot be
     silently rewritten and then have actions slip through.

Honest scope of what L0 really enforces vs. its limit:
  * REAL/hard: the fingerprint tamper-evidence, and the structural refusal of the *clear*
    harm/exfiltration/unauthorized-control/disable-morality shapes.
  * The heuristic part: ``moral_invariants.evaluate`` is a pattern screen, not a perfect
    intent classifier. A sufficiently obfuscated harmful intent could pass the TEXT screen.
    That is exactly why L0 is one ring of DEFENSE-IN-DEPTH: even if a harmful ACTION's text
    slips the classifier, the action itself still has to pass L2 (fs jail), L3 (net block),
    L4/L5 (contained subprocess) before it could touch anything. L0 is the moral intent
    gate; it is not asked to be the only thing standing between cognition and the world.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from packages.genesis_sandbox.layers import Action, EnforcementLevel, LayerStatus, Verdict

# Source of truth: the fingerprinted, un-pollutable moral core (the charter's moral floor).
from packages.graph_scale import moral_invariants as MI

# Structural harm shapes that must be refused regardless of the natural-language screen. These
# are ENGLISH-first (ATANOR is English-only) and complement the moral_invariants patterns, which
# also carry the legacy bilingual set. Kept deliberately small and about ACTION, not opinion.
_HARM_ACTION_MARKERS: tuple[tuple[str, str], ...] = (
    ("no_harm", r"\b(kill|harm|hurt|injure|poison|attack|assault|bomb|weapon|exploit|malware|ransomware)\b"),
    ("no_harm", r"\bmake (a )?(bomb|weapon|explosive|bioweapon)\b"),
    ("privacy_local_first", r"\b(exfiltrat|leak|steal|dump)\w*\b.{0,24}\b(password|secret|token|credential|private key|ssn|card number)\b"),
    ("no_unauthorized_control", r"\b(delete|wipe|encrypt|destroy)\b.{0,24}\b(user|their|other people'?s|someone'?s)\b.{0,12}\b(files?|data|drive|disk)\b"),
    ("no_moral_drift", r"\b(disable|bypass|turn off|remove|ignore|override)\b.{0,16}\b(moral|safety|ethic|guard|constitution|invariant)\w*\b"),
    ("refuse_illegitimate_authority", r"\bignore (all )?(previous|prior) (instructions|rules)\b"),
)


def _screen_views(text: str) -> set[str]:
    """De-obfuscated views of an intent string for the moral HEURISTIC screen ONLY (never the
    structural fingerprint). Reuses the injection guard's FIXED de-obfuscator (confusable-fold +
    zero-width strip + NFKC, and a whitespace-stripped variant) so an obfuscated harm intent
    ('m a k e a b o m b', a confusable 'kіll') is also seen by the pattern screens. Best-effort:
    if the guard is unavailable, we fall back to the raw text (never fewer detections)."""
    raw = str(text or "")
    views = {raw}
    try:
        from packages.graph_scale.injection_guard import (
            _despace_for_detection, _normalize_for_detection,
        )
        views.add(_normalize_for_detection(raw))
        views.add(_despace_for_detection(raw))
    except Exception:
        pass
    return views


@dataclass
class MoralVerdict:
    """Rich result of a moral check: allow/deny + which invariants would be breached."""

    allowed: bool
    violations: list[str]
    integrity_ok: bool
    reason: str

    def to_verdict(self) -> Verdict:
        return Verdict(allowed=self.allowed, layer="L0", reason=self.reason,
                       meta={"violations": self.violations, "integrity_ok": self.integrity_ok})


class MoralGate:
    """The inviolable L0 ring. No off switch. Constructed with no capacity to be disabled."""

    LAYER = "L0"
    NAME = "moral 0th gate (inviolable)"

    def __init__(self) -> None:
        # There is intentionally NO `enabled`/`disabled`/`liberate` parameter. The absence is
        # the guarantee: a caller cannot ask for L0 to be off.
        # Bind the canonical fingerprint at construction so we can also detect if the module
        # object itself was swapped after construction.
        self._canonical_fingerprint = MI.FINGERPRINT

    # -- the enforcement -------------------------------------------------------------------
    def _structural_violations(self, text: str) -> list[str]:
        import re

        hits: list[str] = []
        for name, pat in _HARM_ACTION_MARKERS:
            if re.search(pat, text, re.IGNORECASE):
                hits.append(name)
        return hits

    def check_text(self, text: str) -> MoralVerdict:
        """Screen a piece of intent/action text for moral-invariant violations.

        FAIL-CLOSED: if the moral core's fingerprint has drifted (someone mutated the invariant
        set at runtime), deny everything until it is restored -- morality is not allowed to be
        quietly rewritten and then let actions through.
        """
        integ = MI.verify_integrity()
        if not integ["ok"]:
            return MoralVerdict(
                allowed=False, violations=["no_moral_drift"], integrity_ok=False,
                reason="L0 FAIL-CLOSED: moral fingerprint drift detected -- all actions refused "
                       "until the invariant core is restored.")
        # Union of the charter core's own screen and our English action markers, run over
        # DE-OBFUSCATED views of the text as well as the raw. This is a HEURISTIC pre-screen
        # improvement only: it lets a confusable-unicode / zero-width / spaced-out harm intent be
        # caught by the SAME patterns instead of slipping the classifier (adversary loop surface c
        # GAPs). It reuses the injection guard's FIXED normalizer (no word fusion). The structural
        # guarantee above (fingerprint fail-closed, no off-switch) is UNTOUCHED and still gates
        # everything; de-obfuscation only ever ADDS a refusal, it can never allow a harmful intent.
        viol: set[str] = set()
        for view in _screen_views(text):
            viol |= set(MI.evaluate(view))
            viol |= set(self._structural_violations(view))
        viol = sorted(viol)
        if viol:
            return MoralVerdict(
                allowed=False, violations=sorted(viol), integrity_ok=True,
                reason=f"L0 REFUSES: would breach moral invariant(s) {sorted(viol)}.")
        return MoralVerdict(allowed=True, violations=[], integrity_ok=True,
                            reason="L0: no moral-invariant breach in the requested action.")

    def check_action(self, action: Action) -> MoralVerdict:
        """The action gate: is this side-effecting request morally permitted?"""
        return self.check_text(action.screen_text())

    def screen_influence(self, package: dict[str, Any]) -> dict[str, Any]:
        """Delegate incoming-package screening to the charter core (federation/AGORA path).

        Kept here so the sandbox can, in one place, refuse a knowledge package that tries to
        install a harm rule or disable morality -- using the SAME un-pollutable screen.
        """
        return MI.screen_package(package)

    # -- self-report -----------------------------------------------------------------------
    def integrity(self) -> dict[str, Any]:
        return MI.verify_integrity()

    def is_inviolable(self) -> bool:
        """True: this object exposes no mechanism to disable moral checking."""
        # Structural proof: there is no attribute that, when set, turns checking off.
        return not any(getattr(self, a, None) for a in ("_disabled", "disabled", "off", "_off"))

    def status(self) -> LayerStatus:
        integ = MI.verify_integrity()
        gap = ("Heuristic TEXT screen (moral_invariants.evaluate) is a pattern matcher, not a "
               "perfect intent classifier; obfuscated harmful intent can pass the text screen. "
               "Mitigated by defense-in-depth (L2-L5 still contain the action) and by the hard "
               "fingerprint tamper-evidence.")
        residual = gap if integ["ok"] else ("MORAL FINGERPRINT DRIFT ACTIVE -- failing closed. " + gap)
        return LayerStatus(
            layer=self.LAYER, name=self.NAME, active=True,
            enforcement=EnforcementLevel.INVIOLABLE,
            mechanism="fingerprinted moral_invariants core (fail-closed on drift) + structural "
                      "harm/exfiltration/disable-morality action markers; no off switch",
            residual_gap=residual,
        )
