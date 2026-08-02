# -*- coding: utf-8 -*-
"""Bridge the scene algebra into the SAME core-answer contract `relational_lookup.resolve_relational`
already produces, so it can be wired as a FALLBACK inside `answer_with_base_brain` -- not a new lane,
a second attempt at the same job when the first cannot represent the question.

Returns None for exactly the cases `resolve_relational` returns None for: not English, nothing the
graph can name in the question, or (new here) the composition ran too long. A None here means the
caller falls through to the untouched define pipeline, unchanged from today. A dict here means an
answer or an HONEST abstention -- both must short-circuit the define lane, because letting an
abstention fall through is exactly the 'capital is named after Washington' defect this whole line of
work exists to kill.

WHY A TIMEOUT, not a smarter algorithm, for the slow case: composing over a large-extension type
(`city`, 8k members) measured 45-280s even with per-store caching, because the store has no reverse
(predicate -> subjects) index and a cold scan of a high-cardinality predicate over 115M rows is
genuinely expensive. Fixing that is real work (the "structural_gaps.py" class of O(n) walls, not done
here). Until it is, the honest choice is a bounded budget: most compositions resolve in under a few
seconds (measured), so a generous ceiling lets those through while guaranteeing the live answer path
never gets slower than today for the ones that don't."""
from __future__ import annotations

import os
import threading
from typing import Any

_DEFAULT_TIMEOUT_S = 8.0


def _timeout_s() -> float:
    try:
        return float(os.environ.get("ATANOR_SCENE_TIMEOUT_S", _DEFAULT_TIMEOUT_S))
    except (TypeError, ValueError):
        return _DEFAULT_TIMEOUT_S


def _run_bounded(fn, timeout_s: float):
    """Run `fn` in a daemon thread; None on timeout OR any exception -- a scene-lane fault or a
    slow query must never make the answer path worse than before this lane existed."""
    box: dict[str, Any] = {}

    def _runner() -> None:
        try:
            box["result"] = fn()
        except Exception:
            pass

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return None            # abandoned; the daemon thread finishes in the background, unused
    return box.get("result")


def _sample_clause(labels: list[str], total: int, *, limit: int = 6) -> str:
    shown = labels[:limit]
    tail = f", and {total - len(shown)} more" if total > len(shown) else ""
    return ", ".join(shown) + tail


def _format_answer(scene, result: dict[str, Any]) -> dict[str, Any] | None:
    cert = result.get("certificate", {})
    suspects = int(cert.get("alias_suspect_count") or 0)
    subj = scene.entity or (scene.var_type + "s" if not scene.var_type.endswith("s")
                            else scene.var_type)
    cond = scene.conditions[0] if scene.conditions else None
    rel_txt = cond.predicate.replace("_", " ") if cond else (scene.readout_predicate or "")
    obj_txt = f" {cond.obj}" if (cond and cond.obj) else ""

    if scene.readout == "values":
        vals = result.get("values") or []
        if not vals:
            return None                                       # nothing to say -- let caller abstain
        answer = f"{subj}'s {rel_txt} {'is' if len(vals) == 1 else 'are'} {', '.join(vals)}."
    elif scene.readout == "count":
        universe = cert.get("universe_size", 0)
        answer = f"{result['count']} of the {universe} {subj} I know have{' no' if cond and cond.negated else ''} {rel_txt}{obj_txt}."
    elif scene.readout == "exist":
        answer = (f"No -- {scene.entity} has no grounded {rel_txt}{obj_txt} edge in my graph."
                  if not result.get("exists")
                  else f"Yes -- {scene.entity} has a grounded {rel_txt}{obj_txt} edge.")
    else:  # "set"
        members = result.get("members") or []
        universe = cert.get("universe_size", 0)
        negated = bool(cond and cond.negated)
        if not members:
            answer = (f"Every {subj[:-1] if subj.endswith('s') else subj} I know has {rel_txt}{obj_txt}."
                      if negated else
                      f"None of the {universe} {subj} I know have {rel_txt}{obj_txt}.")
        else:
            answer = (f"{len(members)} of the {universe} {subj} I know have "
                      f"{'no ' if negated else ''}{rel_txt}{obj_txt}: "
                      f"{_sample_clause(members, len(members))}.")
            if negated and suspects:
                # Honesty over completeness (structure-over-memorization doctrine): the complement
                # is contaminated by surface-form twins of a bearer (measured: 53/158 on 'countries
                # with no capital'). Reported inline, never silently subtracted -- subtracting would
                # assert an identity the graph does not hold.
                answer += (f" ({suspects} of those look like spelling/case variants of an entry "
                          f"that DOES have {rel_txt}, so the real count may be lower.)")

    return {
        "answer": answer,
        "reasoning_certificate": cert,
        "confidence": 0.75 if not (cert.get("closed_world_assumption") and
                                   cert.get("alias_suspect_count")) else 0.55,
        "answer_kind": "scene_algebra",
        "intent": "relational",
        "relational": {"rel": rel_txt, "entity": scene.entity or scene.var_type,
                       "edge": rel_txt, "resolved": True},
    }


def _format_abstain(scene, result: dict[str, Any]) -> dict[str, Any]:
    subj = scene.entity or scene.var_type
    reason = result.get("abstain", "no grounded basis")
    return {
        "answer": f"I don't hold enough about {subj} to answer that ({reason}).",
        "reasoning_certificate": result.get("certificate", {"derivation_kind": "scene_abstention",
                                                             "basis": reason}),
        "confidence": 0.2,
        "answer_kind": "scene_algebra_abstain",
        "intent": "relational",
        "relational": {"rel": None, "entity": subj, "edge": None, "resolved": False},
    }


def _log_unread(query: str, reason: str, *, detail: str = "") -> None:
    """Best-effort by the same contract as the rest of this file: a logging fault must never
    change what the caller gets back."""
    try:
        from packages.flywheel.logger import log_unread
        log_unread(query, reason, organ="scene_model.compose", detail=detail)
    except Exception:
        pass


def _compose_and_evaluate(query: str, store: Any) -> dict[str, Any] | None:
    from packages.scene_model.compose import compose
    from packages.scene_model.evaluate import evaluate

    scene, why = compose(query, store)
    if scene is None:
        # The curriculum signal. A question this composer could not form is the only evidence of
        # what the REPRESENTATION is missing, as opposed to what the knowledge is missing -- and
        # without it the training wheels can never come off by measurement, because there is no
        # record of which shapes traffic actually asks for.
        _log_unread(query, why)
        return None
    if scene.dropped_qualifiers:
        _log_unread(query, "qualifier had nowhere to bind",
                    detail=", ".join(scene.dropped_qualifiers))
        # A word the composer itself recognised as grounded had nowhere to bind (measured:
        # "atanor" in "which atanor organs have no tests" -- Scene has one var_type slot, no
        # second-hop possessive restriction). Answering the narrower question we COULD represent,
        # confidently, would silently substitute it for the one actually asked.
        return _format_abstain(scene, {
            "abstain": f"question also named {', '.join(scene.dropped_qualifiers)}, which this "
                      "composer cannot yet bind into the scene"})
    result = evaluate(scene, store)
    if result.get("ok"):
        return _format_answer(scene, result) or _format_abstain(
            scene, {"abstain": "resolved to an empty, uninformative reading"})
    return _format_abstain(scene, result)


def scene_relational_answer(query: str, language: str = "en", store: Any | None = None
                            ) -> dict[str, Any] | None:
    """The scene-algebra fallback. Same contract as `resolve_relational`: a dict (answer or
    honest abstention) or None (not this lane's job -- fall through unchanged)."""
    if str(language or "").lower().startswith("ko"):
        return None
    if store is None:
        try:
            from packages.graph_scale.answer_bridge import _store
            store = _store()
        except Exception:
            store = None
    if store is None:
        return None
    return _run_bounded(lambda: _compose_and_evaluate(query, store), _timeout_s())
