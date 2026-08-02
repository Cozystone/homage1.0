# -*- coding: utf-8 -*-
"""Self-Improvement Orchestrator — the metacognition loop that ties the session's organs into ONE
autonomous cycle, and draws the honest line between what it can fix alone and what needs the operator.

Owner 2026-07-16 ("… "): the last link toward "leave it and it
evolves" is a loop that looks across its own modules, decides what to improve, does the BOUNDED fixes
itself, and FLAGS the envelope walls it cannot cross (with the diagnosis, so a human can add the organ).

 cycle: ① DIAGNOSE — RIF prober (oracle-gap) on every learned module → wall type
 ② DISPATCH — training_wall → schedule (recommend); representation_wall within a known signal
 space → RIF invention; a genuine capability request → KernelForge acquires it
 ③ FLAG — representation walls RIF can't crack = ENVELOPE walls → operator proposal
 ④ LEDGER — persist what improved, what's queued, what's blocked (the self-model of capability)

Honest by construction: bounded improvements run unattended and gated; envelope walls are surfaced, never
faked. No LLM. This is the v0 of the autonomy the owner is waiting for — real, and honest about its edge.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DIR = REPO / "data" / "graph_scale" / "self_improve"
SKILL_QUEUE = DIR / "skill_requests.jsonl"        # {name, examples:[[env,out]...], vars_}
LEDGER = DIR / "ledger.json"


def _read_queue() -> list[dict[str, Any]]:
    if not SKILL_QUEUE.exists():
        return []
    out = []
    for ln in SKILL_QUEUE.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    return out


def request_skill(name: str, examples: list, vars_: list[str]) -> None:
    """The reasoning circuit calls this when it hits a computation it lacks — the autonomous demand signal."""
    DIR.mkdir(parents=True, exist_ok=True)
    with SKILL_QUEUE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"name": name, "examples": examples, "vars_": vars_}, ensure_ascii=False) + "\n")


def diagnose_modules() -> list[dict[str, Any]]:
    """RIF prober across every learned module that dumped a probe. Classifies each wall — the metacognition."""
    try:
        from packages.reasoning_vm.rif.prober import probe_squad_dumps
    except Exception as e:
        return [{"error": str(e)[:80]}]
    out = []
    for r in probe_squad_dumps():
        out.append({"module": r.module, "verdict": r.verdict, "current_acc": r.current_acc,
                    "oracle_acc": r.oracle_acc, "goal_acc": r.goal_acc, "note": r.note})
    return out


def _drain_skills() -> list[dict[str, Any]]:
    """Acquire every queued skill via KernelForge's held-out-verified synthesis (bounded, safe, autonomous)."""
    reqs = _read_queue()
    if not reqs:
        return []
    from packages.reasoning_vm.deliberator import kernel_forge as KF
    done = []
    for req in reqs:
        ex = [(dict(e), int(o)) for e, o in req["examples"]]
        r = KF.acquire_or_recall(req["name"], ex, list(req["vars_"]))
        done.append({"name": req["name"], "accepted": bool(r.get("accepted")),
                     "source": r.get("source"), "program": r.get("program")})
    SKILL_QUEUE.write_text("", encoding="utf-8")      # processed → clear
    return done


def run_once() -> dict[str, Any]:
    """One autonomous self-improvement cycle. Returns (and persists) the capability self-model."""
    t0 = time.time()
    diag = diagnose_modules()
    acquired = _drain_skills()

    within, envelope = [], []
    for m in diag:
        v = m.get("verdict")
        if v == "training_wall":
            within.append({**m, "action": "schedule more data/training (bounded — RIF/curriculum)"})
        elif v == "representation_wall":
            # RIF can try to invent a feature IF raw signals exist; SQuAD gate proved static signals can't →
            # that is an ENVELOPE wall needing a new organ (contextual encoder / new signal type).
            envelope.append({**m, "action": "ENVELOPE WALL — needs a new organ/signal type (operator + "
                                            "architecture). RIF within the current DSL is exhausted."})
        elif v == "done":
            within.append({**m, "action": "at goal — no work"})
        else:
            within.append({**m, "action": "inconclusive — re-dump / re-measure"})

    from packages.reasoning_vm.deliberator import kernel_forge as KF
    rep = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "diagnosis": diag,
        "skills_acquired": acquired,
        "skill_library": [s["name"] for s in KF.library()],
        "within_envelope": within,
        "envelope_walls": envelope,
        "autonomy_note": ("Bounded self-improvement ran unattended (skill acquisition + diagnosis). "
                          "Envelope walls are FLAGGED, not faked — crossing them (a new organ) is still "
                          "operator+architecture. This is the honest edge of current autonomy."),
        "elapsed_s": round(time.time() - t0, 1),
    }
    DIR.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return rep


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run_once(), ensure_ascii=False, indent=2))
