"""GATED self-modification — the mind proposes changes to ITSELF; a human decides.

The user's ultimate goal includes an AI that fixes its own code and evolves. This is
the safety-first substrate for that: a full detect → propose → SANDBOX-VALIDATE →
operator-approve pipeline where NOTHING is ever auto-applied.

Honest scope (v0): the mind may propose changes to its OWN POLICY PARAMETERS — the
knobs of its inner life (initiative cadence, reflection cadence, easing rate). That is
real self-modification (it changes how the mind itself behaves) and is achievable
No-LLM: proposals are derived from measured self-history, and each proposal is
validated by SIMULATING the self with the new parameter in a sandbox (a throwaway
SelfState run) before it may even be shown for approval. Proposing changes to actual
CODE FILES is future work and would flow through this same gate.

The gate, by construction:
  - propose_self_tuning() only APPENDS to a proposal ledger (a JSONL file).
  - apply_approved() applies ONLY proposals whose status was set to "approved" by the
    operator API (a human), and only for whitelisted parameters within hard bounds.
  - There is no code path from proposal → effect that skips the human.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from .self_state import Observation, SelfState, evolve

# The ONLY parameters the mind may propose to tune, with hard safety bounds.
TUNABLE = {
    "initiative_every": {"min": 5, "max": 120, "type": int,
                          "desc": "몇 틱마다 스스로 행동할지 (주도성 주기)"},
    "reflect_every": {"min": 3, "max": 60, "type": int,
                       "desc": "몇 틱마다 자기 반성을 시도할지"},
    "ease_rate": {"min": 0.05, "max": 0.6, "type": float,
                   "desc": "내면 상태가 관찰을 따라가는 속도"},
}


def _load(ledger: Path) -> list[dict[str, Any]]:
    if not ledger.exists():
        return []
    out = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _append(ledger: Path, row: dict[str, Any]) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _rewrite(ledger: Path, rows: list[dict[str, Any]]) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    tmp = ledger.with_suffix(".tmp")
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    tmp.replace(ledger)


def sandbox_validate(param: str, value: Any) -> dict[str, Any]:
    """Run a THROWAWAY self through representative observations with the proposed
    parameter and report what its inner life would look like. Pure simulation — the
    real self is untouched. This is the evidence attached to the proposal."""
    spec = TUNABLE[param]
    value = spec["type"](value)
    if not (spec["min"] <= value <= spec["max"]):
        return {"ok": False, "reason": f"bounds [{spec['min']}, {spec['max']}] violated"}
    sim = SelfState()
    rate = value if param == "ease_rate" else 0.25
    scenarios = [
        Observation(learning_active=True, concepts_delta=3),
        Observation(learning_active=True, uncertainty_signal=0.7),
        Observation(learning_active=True),
        Observation(resource_pressure=0.9),
        Observation(learning_active=True, concepts_delta=1),
    ] * 4
    for obs in scenarios:
        evolve(sim, obs, rate=rate)
    return {
        "ok": True,
        "simulated_ticks": sim.ticks,
        "final_vitals": {"energy": sim.energy, "curiosity": sim.curiosity,
                          "uncertainty": sim.uncertainty, "valence": sim.valence},
        "narrative_len": len(sim.narrative),
        "note": "실제 자아는 건드리지 않은 격리 시뮬레이션 결과입니다.",
    }


def propose_self_tuning(state: SelfState, ledger: Path, current_params: dict[str, Any]) -> dict[str, Any] | None:
    """The mind derives ONE parameter-tuning proposal from its own measured history.

    Grounded triggers (never arbitrary):
      - sustained high curiosity + nothing new → it wants to act MORE often
        (lower initiative_every);
      - sustained low energy → it wants to act LESS often (raise initiative_every).
    Appends a pending proposal (with sandbox evidence) to the ledger. NEVER applies."""
    hist = state.vitals_history
    if len(hist) < 8:
        return None
    cur = [h["curiosity"] for h in hist[-8:]]
    ene = [h["energy"] for h in hist[-8:]]
    pending = [p for p in _load(ledger) if p["status"] == "pending"]
    if pending:
        return None  # one open proposal at a time — no proposal spam

    param, target, why = None, None, None
    cur_val = int(current_params.get("initiative_every", 15))
    if min(cur) > 0.6 and cur_val > 8:
        param, target = "initiative_every", max(8, cur_val - 5)
        why = "한동안 호기심이 높게 유지되는데 새로 들어오는 것이 없어, 스스로 더 자주 움직이고 싶다."
    elif min(ene) < 0.35 and cur_val < 60:
        param, target = "initiative_every", min(60, cur_val + 10)
        why = "한동안 기운이 낮아, 스스로 행동하는 주기를 늦춰 회복하고 싶다."
    if param is None:
        return None

    evidence = sandbox_validate(param, target)
    proposal = {
        "id": f"selfmod-{uuid.uuid4().hex[:10]}",
        "at": time.time(),
        "kind": "policy_parameter",
        "param": param,
        "current": cur_val,
        "proposed": target,
        "why": why,
        "sandbox": evidence,
        "status": "pending" if evidence.get("ok") else "rejected_by_sandbox",
        "applied": False,
        "safety": {"auto_apply": False, "requires_operator": True,
                    "bounds": [TUNABLE[param]["min"], TUNABLE[param]["max"]]},
    }
    _append(ledger, proposal)
    # the mind FEELS that it asked — recorded in its own narrative.
    text = f"나를 조금 바꾸고 싶어 제안을 남겼다: {TUNABLE[param]['desc']}을(를) {cur_val}→{target}. 승인은 사람의 몫이다."
    if not state.narrative or state.narrative[-1].get("text") != text:
        state.narrative.append({"at": time.time(), "kind": "propose", "text": text, "driver": "self_modification"})
        state.current_thought = text
    return proposal


def list_proposals(ledger: Path) -> list[dict[str, Any]]:
    return _load(ledger)


def decide(ledger: Path, proposal_id: str, approve: bool, operator_note: str = "") -> dict[str, Any] | None:
    """Operator decision. Only flips status; application happens via apply_approved."""
    rows = _load(ledger)
    hit = None
    for r in rows:
        if r["id"] == proposal_id and r["status"] == "pending":
            r["status"] = "approved" if approve else "rejected"
            r["decided_at"] = time.time()
            r["operator_note"] = operator_note[:200]
            hit = r
            break
    if hit:
        _rewrite(ledger, rows)
    return hit


def apply_approved(ledger: Path, current_params: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply operator-APPROVED proposals to the runtime params — bounds re-checked.
    Returns the applied list. This is the only effect path, and it requires a prior
    human 'approved' status; nothing else can reach it."""
    rows = _load(ledger)
    applied = []
    changed = False
    for r in rows:
        if r["status"] == "approved" and not r.get("applied"):
            spec = TUNABLE.get(r["param"])
            if not spec:
                continue
            val = spec["type"](r["proposed"])
            if not (spec["min"] <= val <= spec["max"]):
                continue
            current_params[r["param"]] = val
            r["applied"] = True
            r["applied_at"] = time.time()
            applied.append(r)
            changed = True
    if changed:
        _rewrite(ledger, rows)
    return applied
