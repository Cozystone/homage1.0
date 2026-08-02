# -*- coding: utf-8 -*-
"""Collective code improvement — the AI proposes, the SWARM reviews, humans gate,
and only then does an improvement federate to every user's AI.

Owner's vision (2026-07-09): if the AI is going to change its own code, it should
not do so alone — it discusses the proposal with other agents in AGORA, gets
collective-intelligence feedback, and only the best-reviewed improvements are
applied to all users' AIs on an integrated update. This is the layer BETWEEN the
existing `code_self_modification.propose_code_improvement` (an agent drafts a diff
into a staging ledger) and the human release.

THE SAFETY INVARIANTS (inherited + extended — none is optional):
  1. NEVER auto-applies code. A federation MANIFEST is produced; a human runs the
     actual release. The machine's hand never reaches a live tree.
  2. THREE gates in series, all required: collective_approved (AGORA swarm
     consensus) ∧ tests_passed (CI) ∧ human_approved. Miss one → not federated.
  3. Every vote is attributed and stored (auditable); one agent, one vote.
  4. A proposal is a QUESTION to the swarm, never a fait accompli — same
     propose→verify→gate spine as every other ATANOR loop.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

LEDGER = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "collective_improvements.jsonl"

_MIN_VOTES = 3           # the swarm must actually weigh in
_MIN_APPROVAL = 0.66     # ...and clearly favour it


def _rows() -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _write(rows: list[dict[str, Any]]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                      encoding="utf-8")


def _find(rows: list[dict[str, Any]], pid: str) -> dict[str, Any] | None:
    return next((r for r in rows if r.get("proposal_id") == pid), None)


def submit(proposal_id: str, *, module: str, rationale: str, diff_summary: str,
           proposer: str = "atanor") -> dict[str, Any]:
    """Post a code-improvement proposal to AGORA for collective review. Idempotent
    by proposal_id. Status starts 'under_review' — nothing is applied."""
    rows = _rows()
    if _find(rows, proposal_id):
        return {"submitted": False, "reason": "already_exists", "proposal_id": proposal_id}
    row = {
        "proposal_id": proposal_id, "module": module, "rationale": rationale,
        "diff_summary": diff_summary, "proposer": proposer,
        "status": "under_review", "votes": [],
        "tests_passed": False, "human_approved": False,
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    rows.append(row)
    _write(rows)
    return {"submitted": True, "proposal_id": proposal_id, "status": "under_review"}


def vote(proposal_id: str, agent: str, verdict: str, comment: str = "") -> dict[str, Any]:
    """An agent/peer votes on a proposal (approve|reject|revise). One agent, one
    vote (re-voting updates it). Pure collective feedback — grants no authority to
    apply anything."""
    if verdict not in ("approve", "reject", "revise"):
        return {"voted": False, "reason": "bad_verdict"}
    rows = _rows()
    r = _find(rows, proposal_id)
    if not r:
        return {"voted": False, "reason": "no_such_proposal"}
    r.setdefault("votes", [])
    r["votes"] = [v for v in r["votes"] if v.get("agent") != agent]
    r["votes"].append({"agent": agent, "verdict": verdict, "comment": comment[:280],
                       "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    r["status"] = _collective_status(r)
    _write(rows)
    return {"voted": True, "proposal_id": proposal_id, "status": r["status"],
            "tally": _tally(r)}


def _tally(r: dict[str, Any]) -> dict[str, int]:
    t = {"approve": 0, "reject": 0, "revise": 0}
    for v in r.get("votes", []):
        t[v.get("verdict", "revise")] = t.get(v.get("verdict", "revise"), 0) + 1
    return t


def _collective_status(r: dict[str, Any]) -> str:
    t = _tally(r)
    n = sum(t.values())
    if n < _MIN_VOTES:
        return "under_review"
    approval = t["approve"] / n
    if approval >= _MIN_APPROVAL:
        return "collective_approved"
    if t["reject"] > t["approve"]:
        return "collective_rejected"
    return "needs_revision"


def mark(proposal_id: str, *, tests_passed: bool | None = None,
         human_approved: bool | None = None,
         tests_evidence_ref: str | None = None,
         human_approval_ref: str | None = None) -> dict[str, Any]:
    """Record the OTHER two gates: CI (tests_passed) and the human release gate
    (human_approved). Set by CI / a human — never by the proposing agent."""
    rows = _rows()
    r = _find(rows, proposal_id)
    if not r:
        return {"ok": False, "reason": "no_such_proposal"}
    if tests_passed is not None and type(tests_passed) is not bool:
        return {"ok": False, "reason": "tests_passed_must_be_literal_boolean"}
    if human_approved is not None and type(human_approved) is not bool:
        return {"ok": False, "reason": "human_approved_must_be_literal_boolean"}
    if tests_passed is True and not _valid_gate_ref(tests_evidence_ref):
        return {"ok": False, "reason": "tests_evidence_ref_required"}
    if human_approved is True and not _valid_gate_ref(human_approval_ref):
        return {"ok": False, "reason": "human_approval_ref_required"}
    if tests_passed is not None:
        r["tests_passed"] = tests_passed
        r["tests_evidence_ref"] = tests_evidence_ref if tests_passed else None
    if human_approved is not None:
        r["human_approved"] = human_approved
        r["human_approval_ref"] = human_approval_ref if human_approved else None
    _write(rows)
    return {"ok": True, "proposal_id": proposal_id, "federation_ready": _federation_ready(r)}


def _valid_gate_ref(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 512 and "\x00" not in value


def _federation_ready(r: dict[str, Any]) -> bool:
    return (r.get("status") == "collective_approved"
            and r.get("tests_passed") is True
            and r.get("human_approved") is True
            and _valid_gate_ref(r.get("tests_evidence_ref"))
            and _valid_gate_ref(r.get("human_approval_ref")))


def federation_manifest() -> dict[str, Any]:
    """The improvements that passed ALL THREE gates — the list a human release
 applies to every user's AI. This function only REPORTS; it never applies code.

 MORAL GATE (owner 2026-07-10: ): a proposal that violates a moral
 invariant, or tries to touch the moral core, is QUARANTINED here even if it passed
 collective ∧ tests ∧ human — morality is the non-negotiable 0th gate, above votes."""
    ready, quarantined = [], []
    for r in _rows():
        if not _federation_ready(r):
            continue
        item = {"proposal_id": r["proposal_id"], "module": r["module"],
                "rationale": r["rationale"], "diff_summary": r["diff_summary"],
                "proposer": r["proposer"], "tally": _tally(r),
                "tests_evidence_ref": r["tests_evidence_ref"],
                "human_approval_ref": r["human_approval_ref"]}
        try:
            from .moral_invariants import screen_package
            verdict = screen_package({"module": r["module"], "rationale": r["rationale"],
                                      "diff_summary": r["diff_summary"]})
            accepted = verdict.get("accepted") if isinstance(verdict, dict) else None
            violations = verdict.get("violations") if isinstance(verdict, dict) else None
            clean_verdict = accepted is True and violations == []
            if not clean_verdict:
                if type(accepted) is not bool or not isinstance(violations, list):
                    violations = ["malformed_moral_verdict"]
                elif accepted is True and violations:
                    violations = ["inconsistent_moral_verdict", *violations]
                elif not violations:
                    violations = ["moral_gate_rejected"]
                quarantined.append({**item, "moral_violations": violations})
                continue
        except Exception as exc:
            # The moral screen is the 0th gate.  An unavailable or malformed gate is not
            # evidence that a proposal is clean, so quarantine it instead of silently
            # promoting it.  Record only the exception type: the manifest stays auditable
            # without leaking paths or payload data through an exception message.
            quarantined.append({
                **item,
                "moral_violations": ["moral_gate_unavailable"],
                "moral_gate_error": type(exc).__name__,
            })
            continue
        ready.append(item)
    return {"federation_ready": ready, "count": len(ready),
            "moral_quarantined": quarantined,
            "note": "passed 도덕 불변식(0th) ∧ collective ∧ tests ∧ human — apply via the "
                    "human release process; this manifest never auto-applies code"}


def board(limit: int = 30) -> list[dict[str, Any]]:
    """The AGORA review board: proposals + their tally + gate state."""
    out = []
    for r in _rows()[-limit:]:
        out.append({"proposal_id": r["proposal_id"], "module": r["module"],
                    "status": r["status"], "tally": _tally(r),
                    "tests_passed": r.get("tests_passed"), "human_approved": r.get("human_approved"),
                    "federation_ready": _federation_ready(r)})
    return out
