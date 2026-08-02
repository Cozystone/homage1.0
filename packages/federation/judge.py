# -*- coding: utf-8 -*-
"""The SEALED JUDGE — the orchestrator's developer-blind holdout examiner.

DOCTRINE (BINDING — constitution 2, MSH-style): a contributed capability is promoted to the universal
layer ONLY if it REPRODUCES on the orchestrator's holdout — a set of tasks the contributing node (and
its developer) never saw — with NO REGRESSION against the current universal floor. Promotion is earned
by evidence, never by a node's self-report. A node that "felt" its capability was excellent gets the
same blind exam as one that under-claimed; ``self_reported_score`` is recorded, never decisive.

The judge is a small, deterministic INTERPRETER per capability kind (no learned weights — it is a
verifier, not a model):
  * schema      — runs a state-transition schema over held-out abstract event sequences and checks the
                  held-out query answers (the L3 verb-frame / bAbI-style state-tracking task).
  * router      — applies a feature-signature -> lane map to held-out routing cases.
  * organ-param — applies a small linear model (sign(w·x + b)) to held-out labeled vectors.

Held-out tasks live HERE (sealed); a contribution ships only its capability payload. The judge is
robust to adversarial/broken payloads: any interpreter error scores the task WRONG, never crashes the
exam. ``no regression`` is enforced by re-scoring the candidate on every OTHER suite already promoted
into the floor (a candidate that claims-and-breaks a neighbouring suite is rejected even if it aces
its own).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

PROMOTE_THRESHOLD = 0.90     # a capability must solve >= 90% of its sealed holdout to be eligible
REGRESSION_EPS = 1e-9        # zero tolerance: the floor may not drop at all


# ======================================================================================
# SEALED holdout suites (developer-blind; abstract symbols only — never real entities).
# ======================================================================================
def _schema_holdout() -> list[dict[str, Any]]:
    """State-tracking tasks: a sequence of predicate EVENTS, then a WHERE query. Abstract tokens
    (x1, a, c...) carry no identity — the schema must model the *mechanism* (a move clears the old
    binding and sets the new), not memorize content."""
    return [
        {"events": [["enter", "x1", "a"], ["enter", "x2", "b"], ["move", "x1", "a", "c"]],
         "query": ["where", "x1"], "answer": "c"},
        {"events": [["enter", "x1", "a"], ["move", "x1", "a", "b"], ["move", "x1", "b", "d"]],
         "query": ["where", "x1"], "answer": "d"},
        {"events": [["enter", "x1", "r"], ["enter", "x2", "s"], ["move", "x2", "s", "t"]],
         "query": ["where", "x2"], "answer": "t"},
        {"events": [["enter", "x1", "a"], ["enter", "x2", "b"]],
         "query": ["where", "x1"], "answer": "a"},
        {"events": [["enter", "x1", "a"], ["move", "x1", "a", "b"], ["move", "x1", "b", "a"]],
         "query": ["where", "x1"], "answer": "a"},
        {"events": [["enter", "x3", "p"], ["move", "x3", "p", "q"], ["enter", "x4", "p"]],
         "query": ["where", "x3"], "answer": "q"},
    ]


def _router_holdout() -> list[dict[str, Any]]:
    """Held-out routing cases: a feature-signature -> the lane it should route to."""
    return [
        {"signature": "define|term", "lane": "define"},
        {"signature": "attr|of", "lane": "relational"},
        {"signature": "who|are|you", "lane": "self"},
        {"signature": "greeting|hi", "lane": "social"},
        {"signature": "cause|why", "lane": "causal"},
    ]


def _organ_param_holdout() -> list[dict[str, Any]]:
    """Held-out labeled vectors for a small linear separator: y = 1 iff (x0 + x1 - x2) > 0."""
    def y(v):
        return 1 if (v[0] + v[1] - v[2]) > 0 else 0
    xs = [[2.0, 1.0, 0.5], [-1.0, -2.0, 0.0], [3.0, -1.0, 1.0], [0.0, 0.0, 1.0],
          [1.0, 1.0, 3.0], [-2.0, 0.5, -1.0], [0.2, 0.2, 0.1], [-0.5, -0.5, 0.2]]
    return [{"x": x, "y": y(x)} for x in xs]


def sealed_suites() -> dict[str, dict[str, Any]]:
    """The full sealed exam: {suite_name: {kind, holdout}}. Never shipped to nodes."""
    return {
        "location_tracking": {"kind": "schema", "holdout": _schema_holdout()},
        "intent_lane":       {"kind": "router", "holdout": _router_holdout()},
        "linear_sep":        {"kind": "organ-param", "holdout": _organ_param_holdout()},
    }


# ======================================================================================
# Interpreters — deterministic, robust to broken/adversarial payloads (error => task wrong).
# ======================================================================================
def _run_schema(payload: dict[str, Any], events: list[list[str]]) -> dict[tuple, str]:
    """Execute a state-transition schema over an event sequence, returning the symbolic state.

    Schema shape (structure only):
      {"rules": [{"on": <pred>, "args": [<names>], "effect": [["set"|"clear", <predname>, <ref>...]]}],
       "queries": {<qname>: {"predicate": <predname>, "by": <argname>}}}
    A ``ref`` is either a rule arg name (bound from the event) or a literal.
    """
    rules = {r["on"]: r for r in payload.get("rules", []) if isinstance(r, dict) and "on" in r}
    state: dict[tuple, str] = {}
    for ev in events:
        pred, args = ev[0], ev[1:]
        rule = rules.get(pred)
        if not rule:
            continue
        binding = {name: args[i] for i, name in enumerate(rule.get("args", [])) if i < len(args)}

        def val(ref):
            return binding.get(ref, ref)

        for eff in rule.get("effect", []):
            op = eff[0]
            if op == "set":
                _, predname, keyref, valref = eff
                state[(predname, val(keyref))] = val(valref)
            elif op == "clear":
                _, predname, keyref = eff
                state.pop((predname, val(keyref)), None)
    return state


def _answer_schema(payload: dict[str, Any], state: dict[tuple, str], query: list[str]) -> Any:
    qname, key = query[0], query[1]
    q = payload.get("queries", {}).get(qname)
    if not q:
        return None
    return state.get((q.get("predicate"), key))


def _score_schema(payload: dict[str, Any], holdout: list[dict[str, Any]]) -> float:
    ok = 0
    for task in holdout:
        try:
            st = _run_schema(payload, task["events"])
            got = _answer_schema(payload, st, task["query"])
            ok += int(got == task["answer"])
        except Exception:
            pass                                  # a broken schema simply fails the task
    return ok / max(1, len(holdout))


def _score_router(payload: dict[str, Any], holdout: list[dict[str, Any]]) -> float:
    routes = payload.get("routes", {}) or {}
    default = payload.get("default")
    ok = 0
    for task in holdout:
        try:
            got = routes.get(task["signature"], default)
            ok += int(got == task["lane"])
        except Exception:
            pass
    return ok / max(1, len(holdout))


def _score_organ_param(payload: dict[str, Any], holdout: list[dict[str, Any]]) -> float:
    w = payload.get("weights", []) or []
    b = float(payload.get("bias", 0.0) or 0.0)
    ok = 0
    for task in holdout:
        try:
            x = task["x"]
            dot = sum(float(wi) * float(xi) for wi, xi in zip(w, x))
            pred = 1 if (dot + b) > 0 else 0
            ok += int(pred == int(task["y"]))
        except Exception:
            pass
    return ok / max(1, len(holdout))


_SCORERS: dict[str, Callable[[dict[str, Any], list[dict[str, Any]]], float]] = {
    "schema": _score_schema,
    "router": _score_router,
    "organ-param": _score_organ_param,
}


def score_on_suite(capability_kind: str, payload: dict[str, Any], suite: str,
                   suites: dict[str, dict[str, Any]] | None = None) -> float | None:
    """Score a payload of ``capability_kind`` on the sealed ``suite``. Returns None if the suite is
    unknown or the kind mismatches the suite's kind (a schema cannot be scored on a router suite)."""
    suites = suites if suites is not None else sealed_suites()
    spec = suites.get(suite)
    if not spec or spec["kind"] != capability_kind:
        return None
    scorer = _SCORERS.get(capability_kind)
    if scorer is None:
        return None
    return scorer(payload, spec["holdout"])


# ======================================================================================
# The verdict + the blind evaluation.
# ======================================================================================
@dataclass
class Verdict:
    promote: bool
    capability_id: str
    capability_kind: str
    target_suite: str
    holdout_score: float | None                 # None => could not be examined (kind/suite mismatch)
    regression_ok: bool
    regression_detail: dict[str, float] = field(default_factory=dict)
    threshold: float = PROMOTE_THRESHOLD
    self_reported_score: float = 0.0            # RECORDED for audit; NOT part of the decision
    developer_blind: bool = True
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


def evaluate(contribution, floor: dict[str, dict[str, Any]] | None = None,
             suites: dict[str, dict[str, Any]] | None = None) -> Verdict:
    """Blind-examine one (already-sanitized) contribution.

    ``floor`` is the current universal layer: {capability_id: {capability_kind, payload, target_suite}}.
    Promotion requires BOTH:
      (1) holdout_score >= PROMOTE_THRESHOLD on the contribution's own sealed suite, AND
      (2) NO REGRESSION — installing this capability does not lower any OTHER floor suite's score.
    The node's self_reported_score is copied into the verdict but never enters the decision.
    """
    suites = suites if suites is not None else sealed_suites()
    floor = floor or {}
    kind = contribution.capability_kind
    suite = contribution.target_suite
    self_score = float(getattr(contribution, "self_reported_score", 0.0) or 0.0)

    holdout_score = score_on_suite(kind, contribution.payload, suite, suites)
    if holdout_score is None:
        return Verdict(promote=False, capability_id=contribution.capability_id, capability_kind=kind,
                       target_suite=suite, holdout_score=None, regression_ok=True,
                       self_reported_score=self_score,
                       reason=f"unexaminable: no sealed suite matches kind={kind!r} suite={suite!r}")

    # NO-REGRESSION: build the floor's per-suite scores WITH and WITHOUT the candidate installed.
    # A candidate installs under its capability_id; if that id already holds a floor capability, the
    # candidate REPLACES it — so a replacement that breaks the incumbent's suite is caught here.
    def floor_scores(layer: dict[str, dict[str, Any]]) -> dict[str, float]:
        out: dict[str, float] = {}
        for cap in layer.values():
            sc = score_on_suite(cap["capability_kind"], cap["payload"], cap.get("target_suite", ""),
                                suites)
            if sc is not None:
                out[cap.get("target_suite", "")] = max(out.get(cap.get("target_suite", ""), 0.0), sc)
        return out

    baseline = floor_scores(floor)
    candidate_layer = dict(floor)
    candidate_layer[contribution.capability_id] = {
        "capability_kind": kind, "payload": contribution.payload, "target_suite": suite}
    after = floor_scores(candidate_layer)

    regression_ok = True
    regression_detail: dict[str, float] = {}
    for s, base in baseline.items():
        if s == suite:
            continue                              # the candidate's own suite is the holdout gate, not regression
        now = after.get(s, 0.0)
        regression_detail[s] = round(now - base, 6)
        if now < base - REGRESSION_EPS:
            regression_ok = False

    passed = holdout_score >= PROMOTE_THRESHOLD
    promote = bool(passed and regression_ok)
    if promote:
        reason = (f"promoted: holdout {holdout_score:.3f} >= {PROMOTE_THRESHOLD:.2f} on sealed "
                  f"'{suite}', no regression (self-report {self_score:.3f} was NOT used)")
    elif not passed:
        reason = (f"rejected: holdout {holdout_score:.3f} < {PROMOTE_THRESHOLD:.2f} on sealed "
                  f"'{suite}' — did not reproduce blind (self-report {self_score:.3f} ignored)")
    else:
        broke = [s for s, d in regression_detail.items() if d < -REGRESSION_EPS]
        reason = f"rejected: regression on floor suite(s) {broke} — would lower the universal floor"
    return Verdict(promote=promote, capability_id=contribution.capability_id, capability_kind=kind,
                   target_suite=suite, holdout_score=round(holdout_score, 6),
                   regression_ok=regression_ok, regression_detail=regression_detail,
                   self_reported_score=self_score, reason=reason)
