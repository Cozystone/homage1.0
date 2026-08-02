# -*- coding: utf-8 -*-
"""Live wiring for the M1 conformal abstention gate (the "membrane").

ONE import surface for the P0 answer path. Two entry points:

    attach_membrane_signals(result, subgraph=..., anchor=..., epistemic=...)
        Signal PLUMBING. Called by graph_native_answer.compose. When the flag is OFF it is a
        pure no-op that returns ``result`` unchanged (byte-identical). When ON it adds ONE
        additive field ``result["_membrane_signals"]`` (a plain JSON-safe dict of the real
        ActivatedSubgraph-derived signals + optional epistemic rung/confidence) so the gate can
        read the real signals instead of the hardcoded 0.85 constant.

    gate_answer(result, query=..., language=...)
        The GATE CALL. Called at the single exit of answer_bridge.answer_from_triples. When the
        flag is OFF it returns ``result`` unchanged (the exact same object -> byte-identical).
        When ON it builds a SignalVector, calls ConformalGate.decide, and on ABSTAIN returns an
        honest-abstain dict carrying the REAL gate certificate; on ACCEPT it attaches the
        certificate to the result and returns it.

FLAG (default OFF)
------------------
    env ``ATANOR_MEMBRANE_LIVE``  -- "1" enables; anything else (incl. unset) keeps it OFF.
    This is the single master switch. The live system does not change until an operator sets it.

FAIL-SAFE when there is NO calibration artifact yet (env ``ATANOR_MEMBRANE_FAILSAFE``)
--------------------------------------------------------------------------------------
    "passthrough" (DEFAULT) -- log once, return today's answer UNCHANGED, attach only a
        non-certifying marker ``result["_membrane"] = {"status": "uncalibrated_passthrough"}``.
        Never fabricates a certificate; never over-abstains (honors "reduce false abstention").
    "abstain" -- conservative: with no calibration the gate cannot certify, so abstain on every
        gated answer. Maximally safe against a wrong accept, at the cost of muting until the
        operator calibrates. Opt-in only.

HONESTY
-------
    * OFF is a true no-op: no signal is invented, no field is added, the same object is returned.
    * An uncalibrated ON path NEVER emits a certificate (see fail-safe above).
    * On a real ABSTAIN the certificate is the ConformalGate's own ``GateDecision.certificate``
      (a finite-sample bound), not a made-up number.
    * numpy/stdlib only; no network. The heavy imports (numpy via conformal) are lazy, inside
      the ON branch, so importing this module on the OFF path pulls in nothing heavy.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

_LOG = logging.getLogger("atanor.membrane")

# The single master flag and the fail-safe selector (read live so a test/operator can flip them).
_FLAG_ENV = "ATANOR_MEMBRANE_LIVE"
_FAILSAFE_ENV = "ATANOR_MEMBRANE_FAILSAFE"
_ALPHA_ENV = "ATANOR_MEMBRANE_ALPHA"          # only used to *read back* a default; calibration owns alpha
# CALIBRATION-MEASUREMENT flag (default OFF). Set ONLY by scripts/build_membrane_calibration.py.
# It turns the *signal-plumbing + coverage-routing* levers ON so the calibrator measures the SAME
# rich signals + broadened coverage the live gate will use -- WITHOUT arming the gate itself (the
# gate must not pre-filter the very answers it is being calibrated on). See signals_live() below.
_CALIB_ENV = "ATANOR_MEMBRANE_CALIBRATE"

# Calibration artifact location. NOT under data/graph_scale/ (S1 Wikidata ingest owns that tree).
_CALIB_PATH = (Path(__file__).resolve().parents[2]
               / "data" / "conformal_gate" / "membrane_calibration.json")

# Answer kinds that are already an abstention -> never re-gated (never abstain an abstention, and
# never let a stray threshold flip one to ACCEPT). Includes the relational lane's own abstention.
_ALREADY_ABSTAINED = frozenset({"honest_abstain", "honest_abstain_relational"})

# One-time warning latch so an uncalibrated ON path logs once, not per answer.
_warned_uncalibrated = False


# --------------------------------------------------------------------------------------
# Flag helpers
# --------------------------------------------------------------------------------------
def membrane_live() -> bool:
    """True iff the master flag ``ATANOR_MEMBRANE_LIVE`` is exactly "1". Default OFF.
    Gates the GATE ITSELF (gate_answer pre-filter). Calibration mode does NOT arm the gate."""
    return os.getenv(_FLAG_ENV, "0").strip() == "1"


def membrane_calibrating() -> bool:
    """True iff the calibration-measurement flag is set (build_membrane_calibration.py only)."""
    return os.getenv(_CALIB_ENV, "0").strip() == "1"


def signals_live() -> bool:
    """True when the membrane LEVERS (rich-signal plumbing + coverage routing) should run:
    either the live flag is on (production), or we are calibrating (measure the levers with the
    gate off). Default (both unset) is False -> the answer path is byte-identical to pre-membrane.

    Why decoupled from ``membrane_live``: the calibrator must observe the SAME answers + signals
    the live gate will, so the levers run during calibration; but arming the gate then would let
    a stale/abstain-all q_hat pre-filter the calibration set and corrupt the very measurement.
    """
    return membrane_live() or membrane_calibrating()


def _failsafe_mode() -> str:
    """Fail-safe behavior when there is no calibration artifact: 'passthrough' (default) or 'abstain'."""
    mode = os.getenv(_FAILSAFE_ENV, "passthrough").strip().lower()
    return mode if mode in ("passthrough", "abstain") else "passthrough"


# --------------------------------------------------------------------------------------
# Signal plumbing (called by graph_native_answer.compose)
# --------------------------------------------------------------------------------------
def attach_membrane_signals(result: Optional[dict], *, subgraph: Any = None,
                            anchor: Any = None, epistemic: Optional[dict] = None) -> Optional[dict]:
    """Attach real, JSON-safe confidence signals to ``result`` (ADDITIVE) when the flag is ON.

    OFF -> returns ``result`` unchanged (no field added, same object): byte-identical.
    ON  -> sets ``result["_membrane_signals"]`` to a plain dict of floats/strings derived from the
           real ActivatedSubgraph (via nonconformity.from_activated_subgraph) plus, if provided,
           the epistemic rung/graded confidence. Never stores the live object (keeps result
           JSON-serializable for the API). Fully guarded: any error leaves ``result`` untouched.

    "ON" here means signals_live() (live OR calibrating) -- the calibrator must see the same rich
    signals the live gate will, so plumbing runs during calibration even though the gate does not.
    """
    if result is None or not signals_live():
        return result
    try:
        from packages.conformal_gate.nonconformity import (
            SignalVector, from_activated_subgraph, from_epistemic_answer,
        )
        sv = SignalVector()
        if subgraph is not None:
            sv = sv.merge(from_activated_subgraph(subgraph))
        if epistemic is not None:
            sv = sv.merge(from_epistemic_answer(epistemic))
        present = sv.present()
        if present:
            # plain dict (floats/ints/str only) -> JSON-safe, no live-object reference on result.
            result["_membrane_signals"] = {k: (v if isinstance(v, (int, float, str, bool)) else float(v))
                                           for k, v in present.items()}
    except Exception:  # never let plumbing break an answer
        _LOG.debug("attach_membrane_signals skipped (non-fatal)", exc_info=True)
    return result


# --------------------------------------------------------------------------------------
# SignalVector construction for the gate
# --------------------------------------------------------------------------------------
def build_signal_vector(result: dict):
    """Build a SignalVector for ``result``.

    Prefers the rich plumbed signals (``result["_membrane_signals"]`` attached upstream by
    graph_native_answer.compose). Falls back to the answer's OWN reasoning certificate — every
    lane sets a real ``confidence`` and real ``evidence_concepts``/``steps`` — so the gate has a
    genuine (if coarse) doubt signal on any lane. Coarse ranking is paid for in abstention rate,
    never in safety (that is the conformal guarantee); no signal is fabricated.
    """
    from packages.conformal_gate.nonconformity import SignalVector
    plumbed = result.get("_membrane_signals") if isinstance(result, dict) else None
    if plumbed:
        valid = {f for f in SignalVector.__dataclass_fields__}  # type: ignore[attr-defined]
        return SignalVector(**{k: v for k, v in plumbed.items() if k in valid})
    # Fallback: derive from the certificate that every lane already carries.
    conf = result.get("confidence")
    cert = result.get("reasoning_certificate") or {}
    steps = cert.get("steps") or []
    evidence = cert.get("evidence_concepts") or []
    support = max(len(steps), len(evidence))
    return SignalVector(
        graded_confidence=(float(conf) if isinstance(conf, (int, float)) else None),
        support_path_count=(support if support > 0 else None),
    )


def bin_key_for(result: dict, query: Optional[str] = None) -> Optional[str]:
    """The Mondrian bin (relation/domain) for ``result``: the certificate's derivation kind, so
    per-relation calibration lands in the right bucket. None -> pooled fallback threshold."""
    cert = result.get("reasoning_certificate") or {}
    dk = cert.get("derivation_kind")
    return str(dk) if dk else None


def has_calibrated_bin(bin_key: str) -> bool:
    """True iff the live calibration artifact carries a Mondrian q_hat for ``bin_key``.

    A lane uses this to decide whether to route through the gate AT ALL: a lane whose OWN Mondrian
    bin is not calibrated must stay UNGATED (its pre-membrane behavior) rather than fall back to the
    pooled threshold, which is calibrated for a DIFFERENT lane (e.g. the coarse relational q_hat)
    and would falsely abstain this lane's good answers. Cheap: reuses the mtime-cached artifact."""
    gate = _load_calibration()
    return bool(gate is not None and bin_key in getattr(gate, "bin_q_hat", {}))


# --------------------------------------------------------------------------------------
# Calibration artifact (q_hat) loading
# --------------------------------------------------------------------------------------
_POS_INF, _NEG_INF = float("inf"), float("-inf")


def _qhat_from_json(v: Any) -> float:
    if v == "__abstain_all__":
        return _NEG_INF
    if v == "__accept_all__":
        return _POS_INF
    return float(v)


def qhat_to_json(v: float) -> Any:
    """Serialize a q_hat (may be +/-inf) to strict-JSON-safe form. Public so the builder reuses it."""
    if v == _NEG_INF:
        return "__abstain_all__"
    if v == _POS_INF:
        return "__accept_all__"
    return float(v)


_calib_cache: dict[str, Any] = {}


def _load_calibration():
    """Load the calibrated ConformalGate from the artifact, or None if absent/unreadable.

    Cached by (path, mtime) so a live process re-reads only when the operator rebuilds the artifact.
    Returns None (never a fabricated gate) when there is no calibration -> caller applies fail-safe.
    """
    try:
        st = _CALIB_PATH.stat()
    except OSError:
        return None
    key = f"{_CALIB_PATH}:{st.st_mtime_ns}"
    if key in _calib_cache:
        return _calib_cache[key]
    try:
        doc = json.loads(_CALIB_PATH.read_text(encoding="utf-8"))
        from packages.conformal_gate.gate import ConformalGate
        method = doc.get("method", "mondrian")
        alpha = float(doc.get("alpha", 0.1))
        if method == "mondrian":
            bin_q = {str(k): _qhat_from_json(v) for k, v in (doc.get("bin_q_hat") or {}).items()}
            fb = doc.get("fallback_q_hat")
            gate = ConformalGate(alpha=alpha, method="mondrian", bin_q_hat=bin_q,
                                 calibration_n=int(doc.get("calibration_n", 0)),
                                 fallback_q_hat=(None if fb is None else _qhat_from_json(fb)),
                                 achieved=doc.get("achieved") or {})
        else:
            gate = ConformalGate(alpha=alpha, method="split",
                                 q_hat=_qhat_from_json(doc.get("q_hat", "__abstain_all__")),
                                 calibration_n=int(doc.get("calibration_n", 0)),
                                 achieved=doc.get("achieved") or {})
        _calib_cache.clear()
        _calib_cache[key] = gate
        return gate
    except Exception:
        _LOG.warning("membrane calibration artifact present but unreadable: %s", _CALIB_PATH, exc_info=True)
        return None


# --------------------------------------------------------------------------------------
# The gate call (called at the single exit of answer_bridge.answer_from_triples)
# --------------------------------------------------------------------------------------
def _honest_abstain(result: dict, decision: Any, reason: str) -> dict:
    """An honest-abstention dict mirroring answer_bridge's existing honest_abstain shape, carrying
    the REAL gate certificate (or the fail-safe reason). Never fabricates a value or a bound."""
    cert = {
        "derivation_kind": "conformal_abstention",
        "anchor_concept": {"label": (result.get("reasoning_certificate") or {}).get("anchor_concept")},
        "steps": [{"type": "membrane_gate", "fact": reason}],
        "evidence_concepts": [],
        "confidence_basis": ("conformal abstention gate: nonconformity above the calibrated threshold "
                             "(P(accept|wrong) <= alpha); withholding rather than risk a wrong accept"),
        "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False,
                       "verified": True},
        "honesty": ("membrane held back a low-certified candidate rather than emit it "
                    "(no fabricated confidence)"),
    }
    if decision is not None and getattr(decision, "certificate", None):
        cert["membrane_certificate"] = decision.certificate
    return {
        "answer": ("I found a candidate answer but it does not clear my certified-confidence "
                   "threshold, so I'm holding back rather than state something I can't yet certify."),
        "reasoning_certificate": cert,
        "confidence": 0.0,
        "answer_kind": "honest_abstain",
        "_membrane": {"decision": "ABSTAIN", "reason": reason},
    }


def _is_source_verified_curated(result: dict) -> bool:
    """True for a provenance-backed CURATED-COMPOSITION answer that the membrane should NOT gate on
    its (weak) ActivatedSubgraph signals.

    Why a pass-through and not a threshold: the grounded_composition lane composes from curated
    structured triples (ConceptNet / wikidata-truthy) under a CLOSED vocabulary with
    fabricated_facts=False — it is provenance-certified, not the bulk-Wikidata namesake pollution the
    membrane exists to catch. It also carries no rich ActivatedSubgraph, so its raw nonconformity is
    high (measured ~0.36) AND its Mondrian bin is too reliable (few wrong exemplars) to calibrate a
    per-bin threshold at alpha 0.1 -> the bin goes abstain-all, dropping every correct curated answer
    (VERIFIED: 'capital of France' -> Paris abstained at every alpha). Gating a source-verified answer
    on weak signals is exactly the false-abstention the doctrine forbids, so we accept it on its
    provenance and record that basis honestly (no conformal bound is claimed for it).

    Keyed on ``composition_vocabulary_closed`` — UNIQUE to the grounded_composition lane. The noisy
    ``relational_edge_lookup`` lane carries ``verified=True`` but NOT this flag, so it is NEVER passed
    through here; it always faces the conformal gate."""
    if result.get("answer_kind") != "grounded_composition":
        return False
    cert = result.get("reasoning_certificate") or {}
    guar = cert.get("guarantees") or {}
    return (guar.get("fabricated_facts") is False
            and guar.get("composition_vocabulary_closed") is True)


def gate_answer(result: Optional[dict], *, query: Optional[str] = None,
                language: str = "ko") -> Optional[dict]:
    """Gate ``result`` through the conformal membrane. See module docstring.

    OFF -> returns ``result`` unchanged (same object): byte-identical to pre-membrane behavior.
    """
    if not membrane_live():
        return result                      # flag OFF: exact passthrough, no work done
    if result is None:
        return None                        # nothing to gate
    if not isinstance(result, dict):
        return result
    if result.get("answer_kind") in _ALREADY_ABSTAINED:
        return result                      # never re-gate an existing abstention

    # SOURCE-VERIFIED CURATED PASS-THROUGH (before the conformal decision): a provenance-backed
    # closed-vocabulary composition is accepted on its provenance, not on its weak ActivatedSubgraph
    # signals (see _is_source_verified_curated). The membrane still gates the noisy bulk-relational
    # lane; this only spares the curated composition lane a false abstention.
    if _is_source_verified_curated(result):
        cert = result.get("reasoning_certificate")
        if isinstance(cert, dict):
            cert["membrane_certificate"] = {
                "decision": "ACCEPT",
                "basis": "source_verified_passthrough",
                "guarantee": ("provenance-backed curated composition (fabricated_facts=False, "
                              "composition_vocabulary_closed=True); accepted on provenance, not gated "
                              "by the conformal membrane, which gates the noisy bulk-relational lane"),
            }
        result["_membrane"] = {"decision": "ACCEPT", "reason": "source_verified_passthrough"}
        return result

    try:
        gate = _load_calibration()
        if gate is None:
            return _apply_failsafe(result)
        sv = build_signal_vector(result)
        decision = gate.decide(sv, bin=bin_key_for(result, query))
        if decision.accept:
            # ADDITIVE: attach the real certificate; keep the answer as-is.
            cert = result.get("reasoning_certificate")
            if isinstance(cert, dict):
                cert["membrane_certificate"] = decision.certificate
            result["_membrane"] = {"decision": "ACCEPT", "nonconformity": decision.nonconformity,
                                   "q_hat": decision.q_hat, "reason": decision.reason}
            return result
        return _honest_abstain(result, decision, decision.reason)
    except Exception:
        # A membrane fault must NEVER regress the live answer: fall back to today's answer.
        _LOG.warning("membrane gate faulted; passing answer through unchanged", exc_info=True)
        return result


def _apply_failsafe(result: dict) -> Optional[dict]:
    """No calibration artifact yet: apply the documented fail-safe (default passthrough)."""
    global _warned_uncalibrated
    mode = _failsafe_mode()
    if mode == "abstain":
        return _honest_abstain(result, None,
                               "no calibration artifact; fail-safe=abstain (conservative, no certificate)")
    # passthrough (default): today's answer, no certificate, a visible non-certifying marker.
    if not _warned_uncalibrated:
        _LOG.warning("ATANOR_MEMBRANE_LIVE=1 but no calibration artifact at %s; "
                     "fail-safe=passthrough (answers returned UNCERTIFIED). Run "
                     "scripts/build_membrane_calibration.py to calibrate.", _CALIB_PATH)
        _warned_uncalibrated = True
    if isinstance(result, dict):
        result["_membrane"] = {"decision": "PASSTHROUGH", "status": "uncalibrated_passthrough"}
    return result
