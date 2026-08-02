# -*- coding: utf-8 -*-
"""Where the gate's decisions go, so that what it did can be checked afterwards.

The gate already BUILT a receipt -- `GateDecision` carries the accept/abstain, the nonconformity,
the threshold that was applied and a full certificate naming the guarantee. It simply never
persisted one, so nothing in the system could look back and ask what the gate had been doing. The
B1 census read the organ as having no receipt, which was correct: the only logging-shaped line in
the whole package was `import logging`, and an ephemeral console line cannot be replayed or held to.

This matters more here than anywhere else in the repo. Plan v5 §2 puts this organ in the REFLEX
tier -- un-overridable, precisely because it certifies the honesty property and a system that could
decide it was calibrated would be measuring nothing. But an un-overridable organ that leaves no
trace is worse than one that can be argued with: it governs and it cannot be checked. The fix for
that is receipts, not command.

THREE PROPERTIES, and each is a constraint on how this is allowed to be written:

  1. IT CANNOT CHANGE THE DECISION. Canonical §2.3 -- nothing may alter an evaluator outcome. The
     write happens after the verdict exists and any failure is swallowed, so the worst case of a
     full disk is a missing row, never a different answer.
  2. IT CANNOT BE SWITCHED OFF. There is no `enabled` flag and no environment variable, because a
     reflex organ whose observability is optional is not observed. `LEDGER` is a DESTINATION, not a
     switch: tests point it somewhere else, which is a different thing from turning it off.
  3. IT IS BOUNDED WITHOUT BEING SILENT ABOUT IT. This fires on every answer, so the file rotates
     at a size cap and keeps one previous generation. Rotation is recorded IN the ledger as its own
     row -- a gap in the record has to be visible in the record, or the audit reads a truncation as
     a quiet period.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "conformal_gate" / "decisions.jsonl"

# ~8 MB of compact rows is a long recent window at any plausible answer rate, and small enough that
# reading the whole file to audit it stays cheap.
MAX_BYTES = 8 * 1024 * 1024


def _rotate(path: Path) -> None:
    prev = path.with_suffix(".jsonl.1")
    try:
        if prev.exists():
            prev.unlink()
        path.rename(prev)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "event": "rotated",
                "note": f"previous generation moved to {prev.name}",
            }) + "\n")
    except OSError:
        pass


def record_decision(decision: Any, *, query: str = "", lane: str = "",
                    path: Path | None = None) -> None:
    """Append one gate verdict. Never raises, never alters anything.

    The query is stored TRUNCATED and the answer is not stored at all. The audit's questions are
    about rates and thresholds -- how often the gate accepted, at what q_hat, on which signals --
    and none of them need the content. A gate ledger that accumulated everything anyone ever asked
    would be a second copy of the conversation wearing an audit's name."""
    dest = path or LEDGER
    try:
        cert = getattr(decision, "certificate", {}) or {}
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "accept": bool(getattr(decision, "accept", False)),
            "nonconformity": round(float(getattr(decision, "nonconformity", 0.0)), 6),
            "q_hat": round(float(getattr(decision, "q_hat", 0.0)), 6),
            "alpha": float(getattr(decision, "alpha", 0.0)),
            "method": str(getattr(decision, "method", "")),
            "bin": getattr(decision, "bin", None),
            "reason": str(getattr(decision, "reason", ""))[:200],
            "signals_present": list(cert.get("signals_present") or []),
            "calibration_n": cert.get("calibration_n"),
            "lane": lane,
            "query": str(query)[:120],
        }
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > MAX_BYTES:
            _rotate(dest)
        with dest.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass                                       # §2.3: an evaluator's outcome is never altered


def read_decisions(*, limit: int = 5000, path: Path | None = None) -> list[dict[str, Any]]:
    """Recent rows, newest last. Rotation markers are kept, not filtered out."""
    src = path or LEDGER
    try:
        lines = src.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def observed_rates(*, path: Path | None = None) -> dict[str, Any]:
    """What the gate ACTUALLY did, against what it was calibrated to do.

    This is the whole point of persisting anything. `achieved` in the certificate is the gate's
    calibration-time self-report; this is the live record, and the two are allowed to disagree.
    When they do, the calibration set no longer resembles what the gate is seeing -- which is a
    fact about the world that a self-report structurally cannot deliver."""
    rows = [r for r in read_decisions(path=path) if r.get("event") != "rotated"]
    if not rows:
        return {"decisions": 0}
    accepts = sum(1 for r in rows if r.get("accept"))
    blind = sum(1 for r in rows if not r.get("signals_present"))
    alphas = {float(r.get("alpha", 0.0)) for r in rows}
    return {
        "decisions": len(rows),
        "accept_rate": round(accepts / len(rows), 4),
        "abstain_rate": round(1 - accepts / len(rows), 4),
        "no_signal_rate": round(blind / len(rows), 4),
        "alpha_targets": sorted(alphas),
        "first": rows[0].get("ts"),
        "last": rows[-1].get("ts"),
    }


def ledger_path() -> str:
    return str(LEDGER)


if os.environ.get("ATANOR_GATE_LEDGER_REPORT"):    # pragma: no cover - operator convenience
    print(json.dumps(observed_rates(), indent=2))
