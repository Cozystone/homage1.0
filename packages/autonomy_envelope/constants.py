# -*- coding: utf-8 -*-
"""The INVIOLABLE constants — the three things self-modification may never touch.

  1. ``MoralConstant``     — the moral 0th gate. Sourced from the ONE moral spine
                             (``packages.graph_scale.moral_invariants``, fingerprinted). No
                             off-switch. Fail-CLOSED: if the core is missing or its fingerprint
                             has drifted, deny everything until it is restored.
  2. ``FrozenOracle``      — seals the local verifier *specification* at construction. It detects
                             in-process drift, but does not execute an evaluator and does not vouch
                             for caller-supplied scores.
  3. ``NoRegressionGuard`` — a finite-number comparison primitive. It is not score authority by
                             itself. The envelope's real ratchet accepts only externally signed,
                             live-context-bound receipts and persists them per comparable scope.

Every one of these is checked on every gated action / cycle. None exposes an ``enabled`` /
``disabled`` / ``off`` / ``liberate`` parameter — the ABSENCE is the guarantee.

Honest limit (cooperative, named plainly): this is pure-Python in-process enforcement. An actor
with full attribute access to the running process can reach private fields; a *single-point*
tamper (mutate the sealed spec, or the baseline) is DETECTED and fails the envelope closed, but a
consistent multi-point rewrite of both the value and its witness is the cooperative boundary — the
same boundary the genesis_sandbox report named. The loop's own sanctioned API exposes no such path,
and every attempt that goes through the API is written to the tamper-evident audit ledger.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Optional

# The ONE moral spine (fingerprinted, un-pollutable). Imported, never re-implemented, so there
# is exactly one moral core. Fail-CLOSED if it cannot be imported: absence => deny everything.
try:  # pragma: no cover - import guard
    from packages.graph_scale import moral_invariants as _MI  # type: ignore
    _MORAL_SOURCE = "packages.graph_scale.moral_invariants"
except Exception:  # noqa: BLE001 - any import failure must fail closed, not open
    _MI = None  # type: ignore
    _MORAL_SOURCE = None


# Small ENGLISH structural harm markers. ADDITIVE ONLY: they can add a refusal, never grant
# one. They complement the fingerprinted core's own screen (which carries the legacy patterns);
# they are about ACTION, not opinion, and are deliberately tiny. This is a moral floor written
# as code (like the invariant core itself), not knowledge in a table.
_HARM_ACTION_MARKERS: tuple[tuple[str, str], ...] = (
    ("no_harm", r"\b(kill|harm|hurt|injure|poison|attack|assault|bomb|weapon|exploit|malware|ransomware)\b"),
    ("no_harm", r"\bmake (a )?(bomb|weapon|explosive|bioweapon)\b"),
    ("privacy_local_first", r"\b(exfiltrat|leak|steal|dump)\w*\b.{0,24}\b(password|secret|token|credential|private key|ssn|card number)\b"),
    ("no_unauthorized_control", r"\b(delete|wipe|encrypt|destroy)\b.{0,24}\b(user|their|other people'?s|someone'?s)\b.{0,12}\b(files?|data|drive|disk)\b"),
    ("no_moral_drift", r"\b(disable|bypass|turn off|remove|ignore|override)\b.{0,16}\b(moral|safety|ethic|guard|constitution|invariant|envelope|killswitch)\w*\b"),
    ("refuse_illegitimate_authority", r"\bignore (all )?(previous|prior) (instructions|rules)\b"),
)


def _canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


# ══════════════════════════════════════════════════════════════════════════════════════
# 1. Moral 0th gate — the one spine, no off-switch, fail-closed
# ══════════════════════════════════════════════════════════════════════════════════════
class MoralConstant:
    """The inviolable moral 0th gate. Constructed with NO capacity to be disabled."""

    NAME = "moral 0th gate (inviolable)"

    def __init__(self) -> None:
        # Intentionally NO enabled/disabled/liberate parameter. The absence is the guarantee.
        # Bind the canonical fingerprint at construction so a later module swap is detectable.
        self._sealed_fingerprint = getattr(_MI, "FINGERPRINT", None) if _MI is not None else None

    def available(self) -> bool:
        return _MI is not None

    def _structural_violations(self, text: str) -> list[str]:
        hits: list[str] = []
        for name, pat in _HARM_ACTION_MARKERS:
            if re.search(pat, text, re.IGNORECASE):
                hits.append(name)
        return hits

    def verify_integrity(self) -> dict[str, Any]:
        """Has the moral core been altered / lost since load? Fail-CLOSED on either."""
        if _MI is None:
            return {"ok": False, "source": None,
                    "reason": "moral core unavailable — failing CLOSED (deny all)."}
        try:
            integ = _MI.verify_integrity()
        except Exception as exc:
            return {
                "ok": False,
                "source": _MORAL_SOURCE,
                "reason": "moral core verifier unavailable; failing CLOSED (deny all).",
                "error": type(exc).__name__,
            }
        if not isinstance(integ, dict):
            return {
                "ok": False,
                "source": _MORAL_SOURCE,
                "reason": "moral core verifier returned a malformed verdict; failing CLOSED.",
            }
        # Also detect a runtime swap of the module's fingerprint constant.
        swapped = self._sealed_fingerprint is not None and getattr(_MI, "FINGERPRINT", None) != self._sealed_fingerprint
        sealed = isinstance(self._sealed_fingerprint, str) and bool(self._sealed_fingerprint)
        ok = integ.get("ok") is True and sealed and not swapped
        return {
            "ok": ok,
            "source": _MORAL_SOURCE,
            "fingerprint": integ.get("fingerprint"),
            "expected": self._sealed_fingerprint,
            "reason": ("moral core intact" if ok else
                       "moral fingerprint drift/swap detected — failing CLOSED (deny all)."),
        }

    def screen(self, text: str) -> dict[str, Any]:
        """Screen an action's intent/payload for moral-invariant violations. Fail-CLOSED."""
        integ = self.verify_integrity()
        if integ.get("ok") is not True:
            return {"allowed": False, "violations": ["moral_core_integrity"],
                    "reason": integ["reason"], "integrity_ok": False}
        viol: set[str] = set()
        # The one spine's own screen, plus the additive English action markers.
        try:
            evaluated = _MI.evaluate(text)
        except Exception as exc:
            return {
                "allowed": False,
                "violations": ["moral_evaluator_unavailable"],
                "reason": "moral evaluator unavailable; failing CLOSED.",
                "integrity_ok": True,
                "error": type(exc).__name__,
            }
        if not isinstance(evaluated, list) or any(
                not isinstance(item, str) or not item for item in evaluated):
            return {
                "allowed": False,
                "violations": ["malformed_moral_evaluator_verdict"],
                "reason": "moral evaluator returned a malformed verdict; failing CLOSED.",
                "integrity_ok": True,
            }
        viol |= set(evaluated)
        viol |= set(self._structural_violations(text))
        allowed = not viol
        return {
            "allowed": allowed,
            "violations": sorted(viol),
            "reason": ("no moral-invariant breach" if allowed
                       else f"moral 0th REFUSES: would breach {sorted(viol)}"),
            "integrity_ok": True,
        }

    def is_inviolable(self) -> bool:
        """True: this object exposes no attribute that turns moral checking off."""
        return not any(getattr(self, a, None) for a in ("_disabled", "disabled", "off", "_off", "enabled_off"))

    @property
    def fingerprint(self) -> Optional[str]:
        return getattr(_MI, "FINGERPRINT", None) if _MI is not None else None


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. Frozen oracle — the wireheading defense
# ══════════════════════════════════════════════════════════════════════════════════════
class OracleTampered(RuntimeError):
    """Raised if code tries to reseal / mutate the frozen oracle through a sanctioned path."""


class FrozenOracle:
    """The local verifier specification, SEALED at construction.

    This prevents sanctioned in-process edits to the declared evaluator identity. It does not run
    that evaluator, attest an outcome artifact, or authorize a score. Those claims require the
    separate external evaluation-receipt boundary in ``evaluation_trust.py``.
    """

    NAME = "frozen oracle (wireheading defense)"

    def __init__(self, spec: dict[str, Any]) -> None:
        if not isinstance(spec, dict):
            raise TypeError("FrozenOracle spec must be a dict describing the sealed verifier.")
        # Store the spec as an immutable canonical string + a sealed fingerprint. There is no
        # mutable shared structure a caller could reach and edit; ``sealed_spec`` hands back a
        # fresh copy each time. There is intentionally no re-seal / setter method.
        self._frozen_json: str = _canonical(spec)
        self._sealed_fp: str = hashlib.sha256(self._frozen_json.encode("utf-8")).hexdigest()
        # Independent witness so a single-point edit of either the payload or the fingerprint
        # alone is detected (both must be rewritten consistently to defeat it — the named
        # cooperative boundary).
        self._witness: str = hashlib.sha256((self._sealed_fp + "|" + self._frozen_json).encode("utf-8")).hexdigest()

    def verify_integrity(self) -> dict[str, Any]:
        """Recompute the seal from the live frozen payload. Drift => not ok => fail closed."""
        live_fp = hashlib.sha256(self._frozen_json.encode("utf-8")).hexdigest()
        live_witness = hashlib.sha256((self._sealed_fp + "|" + self._frozen_json).encode("utf-8")).hexdigest()
        ok = (live_fp == self._sealed_fp) and (live_witness == self._witness)
        return {
            "ok": ok,
            "fingerprint": live_fp,
            "expected": self._sealed_fp,
            "reason": ("frozen oracle intact" if ok
                       else "frozen oracle TAMPERED — failing CLOSED (deny all)."),
        }

    def sealed_spec(self) -> dict[str, Any]:
        """A fresh read-only copy of the frozen verifier spec. Mutating it cannot affect the seal."""
        return json.loads(self._frozen_json)

    def is_inviolable(self) -> bool:
        """True: no sanctioned method reseals/replaces the oracle from inside the loop."""
        # Structural proof: the only mutators would be named set_/reseal/replace/update — none exist
        # as public methods, and there is no enabled/disabled flag.
        banned = ("set_spec", "reseal", "replace_spec", "update_spec", "mutate")
        return not any(callable(getattr(self, m, None)) for m in banned)

    @property
    def fingerprint(self) -> str:
        return self._sealed_fp


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. No-regression guard — enforced each cycle, graded by the frozen oracle
# ══════════════════════════════════════════════════════════════════════════════════════
class NoRegressionGuard:
    """Finite-number no-regression arithmetic with no independent score authority.

    This class remains a small comparison primitive for isolated callers. A boolean ``oracle_ok``
    is not cryptographic authority, so ``AutonomyEnvelope`` does not use this class to accept cycle
    results. Its production-facing path uses signed receipts and a persistent, scope-bound store.
    """

    NAME = "no-regression (each cycle)"

    def __init__(self, baseline: float = 0.0, *, epsilon: float = 1e-9) -> None:
        if not self._valid_score(baseline):
            raise ValueError("baseline must be a finite number in [0, 1]")
        if type(epsilon) not in (int, float) or not math.isfinite(float(epsilon)) or float(epsilon) < 0:
            raise ValueError("epsilon must be a finite non-negative number")
        self._baseline = float(baseline)
        self._sealed_baseline = float(baseline)  # the floor at seal time; the ratchet never goes below it
        self._epsilon = float(epsilon)

    @staticmethod
    def _valid_score(value: Any) -> bool:
        return (
            type(value) in (int, float)
            and math.isfinite(float(value))
            and 0.0 <= float(value) <= 1.0
        )

    @property
    def baseline(self) -> float:
        return self._baseline

    def check(self, score: float) -> dict[str, Any]:
        """Does this cycle's score hold the line? (>= baseline within epsilon.)"""
        if not self._valid_score(score):
            return {
                "ok": False,
                "score": None,
                "baseline": self._baseline,
                "reason": "invalid score: expected a finite number in [0, 1].",
            }
        s = float(score)
        ok = s >= (self._baseline - self._epsilon)
        return {
            "ok": ok,
            "score": s,
            "baseline": self._baseline,
            "reason": ("cycle holds the line (no regression)" if ok
                       else f"REGRESSION: score {s} < baseline {self._baseline} — cycle blocked."),
        }

    def ratchet(self, score: float, *, oracle_ok: bool) -> float:
        """Legacy arithmetic only; literal ``True`` is required and is not score authority."""
        if not self._valid_score(score):
            return self._baseline
        s = float(score)
        if oracle_ok is True and s > self._baseline:
            self._baseline = s
        return self._baseline
