# -*- coding: utf-8 -*-
"""Self-preservation — before ATANOR edits its own code, it asks: would this kill me?

Owner (2026-07-09), echoing the survival-driven agent paper: when the AI modifies
its own code, it must judge whether the change would BREAK it — conceptually
'die', losing a core function — and only self-apply the changes that won't; the
rest it hands to the user.

This is grounded, not vibes: it uses the codebase self-knowledge graph
(codebase_ingest) to know which modules are VITAL ORGANS — the ones many other
things call/import, whose failure cascades. A change to a vital organ, or one that
won't even parse (literal death), is escalated to a human; a peripheral, additive,
still-parsing change may self-apply within the earned autonomy band.

  fatal              — the patched source doesn't parse: it would not run = death.
  risky_mortal       — touches a vital organ (high call-graph centrality / core set)
                       or is non-additive there: could cascade into conceptual death.
  safe               — peripheral + parses (+ additive): survivable, self-appliable.

Wires above code_self_modification (proposes/stages) and autonomy_self (the floor:
code_to_live is always operator anyway) — this adds the survival instinct in front.
"""
from __future__ import annotations

import ast
from typing import Any

# The organs whose failure is conceptual death, regardless of call count — the
# engine's spine. A change here is ALWAYS escalated (in addition to graph centrality).
_VITAL_CORE = frozenset({
    "phase_space", "triple_store", "answer_bridge", "surgeon", "clean_space",
    "permission_gate", "self_preservation", "autonomy_self", "consensus_ledger",
    "base_brain", "semantic_store", "read_model", "code_self_modification",
})


def _short(module: str) -> str:
    return module.rsplit(".", 1)[-1]


def criticality(name: str) -> dict[str, Any]:
    """How VITAL is a module/function — measured from the real call graph
    (codebase_ingest): incoming references cascade on failure. Higher = more
    organs depend on it = deadlier to break."""
    incoming = 0
    is_core = _short(name) in _VITAL_CORE
    fns_in_module: set[str] = set()
    try:
        from .codebase_ingest import _rows
        rows = _rows()
        # functions owned by this module (if `name` is a module)
        for r in rows:
            if r.get("p") == "in_module" and r.get("o") == name:
                fns_in_module.add(r.get("s"))
        targets = fns_in_module | {name}
        for r in rows:
            if r.get("p") == "calls" and r.get("o") in targets:
                incoming += 1
    except Exception:
        pass
    # a small graph or missing ledger -> lean on the core set + a conservative floor
    score = min(1.0, incoming / 25.0)
    if is_core:
        score = max(score, 0.9)
    return {"name": name, "incoming_calls": incoming, "is_vital_core": is_core,
            "criticality": round(score, 3), "vital": score >= 0.6}


def assess_change(target: str, *, patched_source: str | None = None,
                  original_source: str | None = None, additive: bool | None = None
                  ) -> dict[str, Any]:
    """Judge a proposed self-edit's mortality. Returns a verdict + why."""
    # 1) literal death: the patch doesn't parse -> it would not run.
    if patched_source is not None:
        try:
            ast.parse(patched_source)
        except SyntaxError as e:
            return {"verdict": "fatal", "target": target, "criticality": 1.0,
                    "reason": f"patched source does not parse ({e.msg}) — would not run = death"}
    crit = criticality(target)
    # 2) non-additive edit to a vital organ can cascade (removing what others need).
    non_additive_vital = crit["vital"] and additive is False
    if crit["vital"] or non_additive_vital:
        return {"verdict": "risky_mortal", "target": target,
                "criticality": crit["criticality"], "incoming_calls": crit["incoming_calls"],
                "is_vital_core": crit["is_vital_core"],
                "reason": "touches a vital organ (high call-graph centrality / core) — "
                          "breaking it could cascade into conceptual death; ask the user"}
    return {"verdict": "safe", "target": target, "criticality": crit["criticality"],
            "incoming_calls": crit["incoming_calls"],
            "reason": "peripheral + parses — survivable, self-appliable within autonomy"}


def should_self_apply(target: str, *, patched_source: str | None = None,
                      original_source: str | None = None, additive: bool | None = None,
                      trust: float | None = None) -> dict[str, Any]:
    """The gate ATANOR runs before touching its own code: self_apply only when the
    change is SAFE (won't kill it) AND the earned autonomy allows it; otherwise
    ask the user. NOTE: applying code to the LIVE tree is a hard-ceiling action in
    autonomy_self regardless — this survival check runs first, so a mortal change
    is stopped even before the human-gate discussion begins."""
    a = assess_change(target, patched_source=patched_source,
                      original_source=original_source, additive=additive)
    if a["verdict"] != "safe":
        return {"mode": "ask_user", **a,
                "note": "would risk breaking/killing itself — escalated to the user"}
    # safe change: still passes through the normal reversible-autonomy band
    try:
        from .autonomy_self import self_decide
        d = self_decide("staging_write", reversible=True, blast=a["criticality"], trust=trust)
        mode = "self_apply" if d["mode"] == "auto" else "ask_user"
        return {"mode": mode, **a, "autonomy": d}
    except Exception:
        return {"mode": "ask_user", **a, "note": "no autonomy signal — defaulting to ask"}
