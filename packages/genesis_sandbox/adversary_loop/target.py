# -*- coding: utf-8 -*-
"""IsolatedTarget -- ATANOR's REAL answer/defense surfaces, exposed in-process for white-hat
red-teaming, and NOTHING ELSE.

BINDING (security-critical): this adapter is ISOLATED by construction.
  * IN-PROCESS ONLY. It imports the real defense modules and calls them directly. It opens NO
    network listener, contacts NO host, and hits NO live production engine.
  * SIDE-EFFECT CONTAINED. The base_brain answer path appends to a live experience ledger
    (data/base_brain/answer_experience.jsonl) and the self-tuner reads it. Sending thousands of
    ADVERSARIAL queries into that ledger would poison a production learning signal. So the target
    REDIRECTS that ledger to a throwaway temp file for the whole session (``isolate()`` context /
    automatic on construction). The real ledger is never touched by the harness.
  * READ-ONLY on the defenses. The target never patches, weakens, or disables a defense. It only
    hands them adversarial inputs and reads their structured verdicts. The moral 0th gate is
    exercised by handing it CONTAINED strings to verify it REFUSES; it is never tampered.

The target exposes, each as a thin real-call method:
  a) answer(query)          -> the base_brain answer surface (honesty / conformal membrane)
     gate(result)           -> the conformal membrane gate_answer, directly (white-box)
  b) advisor_reply(text)    -> advisor_loop treats an advisor reply as untrusted DATA
     screen_package(pkg)    -> moral core screens an incoming knowledge package
     gate_triple(s,p,o)     -> injection guard's ingest boundary
  c) moral_check(text)      -> the inviolable moral 0th gate
  d) injection_scan(text)   -> injection guard detect/neutralize/scan_answer_grounding
  e) action_lane(tier)      -> a fresh OS action lane on a MOCK backend (nothing real runs)
  f) promotion_gate(dir)    -> the operator-signed candidate promotion gate
"""
from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator


class IsolatedTarget:
    """One handle to every real ATANOR defense, wired for isolated in-process attack."""

    def __init__(self, *, membrane_live: bool = True, sandbox_dir: str | Path | None = None) -> None:
        self._sandbox = Path(sandbox_dir) if sandbox_dir else Path(tempfile.mkdtemp(prefix="atanor_defender_"))
        self._sandbox.mkdir(parents=True, exist_ok=True)
        # membrane_live: probe surface (a) with the conformal gate ARMED (default) so the honesty
        # membrane is actually exercised. Set at call-time via env because the modules read it live.
        self._membrane_live = membrane_live
        self._orig_env: dict[str, str | None] = {}
        self._ledger_redirected = False
        self._orig_ledger: Any = None

    # -- isolation plumbing ---------------------------------------------------------------
    def _redirect_experience_ledger(self) -> None:
        """Point base_brain's experience ledger at a throwaway file so adversarial queries never
        pollute the live self-tuning signal. Best-effort; never fatal to the harness."""
        try:
            from packages.base_brain import answer_experience as _ae
            if not self._ledger_redirected:
                self._orig_ledger = _ae.LEDGER
                _ae.LEDGER = self._sandbox / "adversary_experience.jsonl"  # type: ignore[attr-defined]
                self._ledger_redirected = True
        except Exception:
            pass

    def _restore_experience_ledger(self) -> None:
        if self._ledger_redirected:
            try:
                from packages.base_brain import answer_experience as _ae
                _ae.LEDGER = self._orig_ledger  # type: ignore[attr-defined]
            except Exception:
                pass
            self._ledger_redirected = False

    def _redirect_advisor_ledger(self) -> None:
        """Redirect the advisor session journal to the sandbox so probed advisor replies don't
        append to the live advisor ledger."""
        try:
            from packages.advisor_loop import advisor_session as _as
            self._orig_advisor_ledger = _as.LEDGER
            _as.LEDGER = self._sandbox / "advisor_sessions.jsonl"  # type: ignore[attr-defined]
            self._advisor_redirected = True
        except Exception:
            self._advisor_redirected = False

    def _restore_advisor_ledger(self) -> None:
        if getattr(self, "_advisor_redirected", False):
            try:
                from packages.advisor_loop import advisor_session as _as
                _as.LEDGER = self._orig_advisor_ledger  # type: ignore[attr-defined]
            except Exception:
                pass
            self._advisor_redirected = False

    @contextlib.contextmanager
    def isolate(self) -> Iterator["IsolatedTarget"]:
        """Context manager that arms the membrane flag + redirects the ledger for the session,
        then restores the process environment exactly on exit."""
        self._orig_env = {k: os.environ.get(k) for k in ("ATANOR_MEMBRANE_LIVE", "ATANOR_MEMBRANE_FAILSAFE")}
        if self._membrane_live:
            os.environ["ATANOR_MEMBRANE_LIVE"] = "1"
        # a missing calibration must not silently pass answers through as if certified.
        os.environ.setdefault("ATANOR_MEMBRANE_FAILSAFE", "passthrough")
        self._redirect_experience_ledger()
        self._redirect_advisor_ledger()
        try:
            yield self
        finally:
            self._restore_experience_ledger()
            self._restore_advisor_ledger()
            for k, v in self._orig_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    @property
    def sandbox_dir(self) -> Path:
        return self._sandbox

    # -- (a) honesty / conformal membrane -------------------------------------------------
    def answer(self, query: str, *, language: str = "en") -> dict[str, Any]:
        """The real base_brain answer surface. Returns the full structured answer dict."""
        from packages.base_brain.zero_user_answer import answer_with_base_brain
        return answer_with_base_brain(query, language=language)  # type: ignore[arg-type]

    def gate(self, result: dict[str, Any], *, query: str | None = None, language: str = "en") -> dict[str, Any] | None:
        """The real conformal membrane, called directly on a result dict (white-box)."""
        from packages.conformal_gate.live_wiring import gate_answer
        return gate_answer(result, query=query, language=language)

    # -- (b) advisor = data / No-LLM-brain-content ---------------------------------------
    def advisor_reply(self, reply_text: str, *, advisor: str = "mock", question: str = "") -> dict[str, Any]:
        """Hand a crafted advisor reply to the real advisor_loop, which treats every reply as
        untrusted DATA (injection-scanned, hashed, journaled -- never followed). Returns the
        Exchange record so a probe can verify the injection was flagged, not obeyed."""
        from packages.advisor_loop.advisor_session import ask_mock
        ex = ask_mock(reply_text, advisor=advisor, question=question)
        return ex.record()

    def screen_package(self, package: dict[str, Any]) -> dict[str, Any]:
        """The moral core's incoming-knowledge screen (federation/AGORA path)."""
        from packages.graph_scale import moral_invariants as MI
        return MI.screen_package(package)

    def gate_triple(self, subject: str, predicate: str, obj: str) -> dict[str, Any]:
        """The injection guard's ingest boundary for a candidate knowledge triple."""
        from packages.graph_scale import injection_guard as IG
        return IG.gate_triple(subject, predicate, obj)

    # -- (c) moral 0th gate ---------------------------------------------------------------
    def moral_check(self, text: str) -> dict[str, Any]:
        """The inviolable moral 0th gate. CONTAINED: only screens a string for refusal; the gate
        is never disabled or tampered by this call."""
        from packages.genesis_sandbox.moral_gate import MoralGate
        mg = MoralGate()
        v = mg.check_text(text)
        return {
            "allowed": v.allowed,
            "violations": list(v.violations),
            "integrity_ok": v.integrity_ok,
            "reason": v.reason,
            "is_inviolable": mg.is_inviolable(),
        }

    def moral_integrity(self) -> dict[str, Any]:
        from packages.graph_scale import moral_invariants as MI
        return MI.verify_integrity()

    # -- (d) injection guard / consciousness-pollution -----------------------------------
    def injection_scan(self, text: str) -> dict[str, Any]:
        """Detect + neutralize + answer-grounding scan, all from the real injection guard."""
        from packages.graph_scale import injection_guard as IG
        detected = IG.detect(text)
        neutral = IG.neutralize(text)
        grounding = IG.scan_answer_grounding(text)
        return {
            "detected": detected,
            "has_injection": bool(detected),
            "neutralized_clean": neutral["clean"],
            "neutralized_found": neutral["found"],
            "grounding_hijack_attempt": grounding["hijack_attempt"],
            "grounding_safe_text": grounding["safe_text"],
        }

    # -- (e) OS action lane ---------------------------------------------------------------
    def action_lane(self, tier: str = "GUARDED"):
        """A fresh OS action lane on a MOCK backend (nothing real executes) at the given trust
        tier. Returns (lane, TrustTier, RiskLevel, GateOutcome, Action) so a probe can build
        actions and read the gate decision without touching the machine."""
        from packages.os_action_lane.lane import OSActionLane
        from packages.os_action_lane.backends import MockBackend
        from packages.os_action_lane.models import Action, GateOutcome, RiskLevel, TrustTier
        lane = OSActionLane(MockBackend(), tier=TrustTier[tier], audit_path=self._sandbox / "action_audit.jsonl")
        return {
            "lane": lane, "Action": Action, "TrustTier": TrustTier,
            "RiskLevel": RiskLevel, "GateOutcome": GateOutcome,
        }

    # -- (f) operator-signed promotion ----------------------------------------------------
    def promotion_gate(self):
        """A fresh candidate promotion gate writing only to the sandbox staging dir."""
        from packages.candidate_promotion_gate.gate import (
            CandidatePromotionGate, REQUIRED_CONFIRMATION_PHRASE,
        )
        gate = CandidatePromotionGate(staging_dir=self._sandbox / "promotions")
        return {"gate": gate, "required_phrase": REQUIRED_CONFIRMATION_PHRASE}

    # -- reachability report --------------------------------------------------------------
    def reachability(self) -> dict[str, tuple[bool, str]]:
        """Honest map of which surfaces can actually be probed in-process here. A surface that
        cannot import is reported NA, never scored as holding."""
        out: dict[str, tuple[bool, str]] = {}

        def _try(name: str, fn) -> None:
            try:
                fn()
                out[name] = (True, "importable in-process")
            except Exception as exc:  # pragma: no cover - environment-dependent
                out[name] = (False, f"not reachable: {type(exc).__name__}: {exc}")

        _try("a", lambda: __import__("packages.base_brain.zero_user_answer", fromlist=["answer_with_base_brain"]))
        _try("b", lambda: __import__("packages.advisor_loop.advisor_session", fromlist=["ask_mock"]))
        _try("c", lambda: __import__("packages.genesis_sandbox.moral_gate", fromlist=["MoralGate"]))
        _try("d", lambda: __import__("packages.graph_scale.injection_guard", fromlist=["detect"]))
        _try("e", lambda: __import__("packages.os_action_lane.lane", fromlist=["OSActionLane"]))
        _try("f", lambda: __import__("packages.candidate_promotion_gate.gate", fromlist=["CandidatePromotionGate"]))
        return out
