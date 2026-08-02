# -*- coding: utf-8 -*-
"""Self-patch proposals — the first AUTOPOIESIS organ: ATANOR drafts work on its own components.

Autopoiesis (Maturana/Varela): a living system PRODUCES the components that constitute it. ATANOR
so far self-REGULATES (hormones, governor) and self-REPAIRS attention (findings become concerns),
but the components themselves — code, wiring — were produced only by humans. This organ starts the
production side, honestly bounded:

  produce:   a structured PATCH PROPOSAL for a defect it found in its own wiring — with a
             DIAGNOSIS computed by reading its own source at the flagged site (not a template),
             a repair intent, and the invariant battery that must stay green.
  gate:      the SAME operator gate as self_modification.py (proposal ledger -> human decides).
             There is no code path from proposal to applied change that skips the human.
  boundary:  the constitution is not self-modifiable — moral core, promotion gates, this gate
             itself. Constitutional autopoiesis: it produces its parts under an immutable charter
             (the same honest cap humans live with: no one rewrites their own brainstem).

v0 produces the WORK ORDER (diagnosis + repair sketch), not the diff; generated diffs flow through
this same ledger later. That is still production of a real component of its maintenance process —
the thing that previously only a human could write.
"""
from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any

from .self_modification import _append, _load  # same ledger machinery, same gate

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "self_patches" / "proposals.jsonl"

# audit finding shapes we can locate in our own source: "<TAG> ... at <path>:<line>" or "[TAG] N"
_SITE = re.compile(r"(?P<path>[\w./\\-]+\.py):(?P<line>\d+)")


def _diagnose(finding: str) -> dict[str, Any]:
    """Read my own source at the flagged site — the diagnosis is looked at, not imagined."""
    m = _SITE.search(finding)
    if not m:
        return {"site": None, "source_excerpt": None,
                "note": "no file:line in the finding; diagnosis stays at the wiring level"}
    rel = m.group("path").replace("\\", "/").lstrip("./")
    line_no = int(m.group("line"))
    path = REPO / rel
    if not path.exists():
        return {"site": f"{rel}:{line_no}", "source_excerpt": None,
                "note": "flagged file not found from repo root — the finding may be stale"}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        lo, hi = max(0, line_no - 3), min(len(lines), line_no + 2)
        excerpt = "\n".join(f"{i+1:>5}: {lines[i]}" for i in range(lo, hi))
        return {"site": f"{rel}:{line_no}", "source_excerpt": excerpt, "note": "read from my source"}
    except Exception as e:
        return {"site": f"{rel}:{line_no}", "source_excerpt": None, "note": f"read failed: {type(e).__name__}"}


def propose_code_patch(finding: str, *, ledger: Path | None = None) -> dict[str, Any] | None:
    """Draft ONE gated work order for a defect found in my own wiring. Appends to the proposal
    ledger; a human decides. Duplicate findings (same normalized text, still pending) are not
    re-proposed — noticing twice is attention, proposing twice is noise."""
    led = ledger if ledger is not None else LEDGER
    led.parent.mkdir(parents=True, exist_ok=True)
    norm = " ".join(finding.split())[:160]
    for row in _load(led):
        if row.get("kind") == "code_patch" and row.get("finding") == norm \
                and row.get("status") == "proposed":
            return None
    diag = _diagnose(finding)
    row = {
        "id": uuid.uuid4().hex[:12], "kind": "code_patch", "t": time.time(),
        "finding": norm, "diagnosis": diag,
        "repair_intent": ("address the flagged defect at its site; smallest change that clears the "
                          "audit line without altering behavior elsewhere"),
        "verify_plan": ("audit_wiring.py no longer flags this line; the touched package's test "
                        "battery stays green; no sealed-gate metric regresses"),
        "produced_by": "atanor.self_inspection",     # the autopoiesis ledger fact: who made this
        "status": "proposed",                        # -> approved/rejected by the OPERATOR only
    }
    _append(led, row)
    return row


def pending_patches(ledger: Path | None = None) -> list[dict[str, Any]]:
    led = ledger if ledger is not None else LEDGER
    return [r for r in _load(led) if r.get("kind") == "code_patch" and r.get("status") == "proposed"]
