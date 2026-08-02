# -*- coding: utf-8 -*-
"""What this gate REFUSED, which is the half it was not recording.

The gate already persists what it allowed: `_write_manifest` puts every approved promotion on disk
with its signature. Refusals went nowhere. For a DEFAULT-DENY gate that is the wrong half to keep --
the refusals are the substance of what it does, and without them two failures are invisible:

  * the gate starts refusing everything (a threshold drifts, a field is renamed upstream, provenance
    stops arriving) and the system merely looks quiet;
  * the gate starts ALLOWING what it used to refuse, and there is no before-picture to compare to.

Plan v5 §2 puts this organ in the reflex tier: not overridable, and therefore obliged to be
observable. The B1 census read it as having no receipt of any kind, which was accurate.

House style, deliberately: this is a small per-organ ledger rather than a shared utility, matching
`knowledge_repair.conflict_ledger` and `flywheel.logger`. The row shape belongs to the organ; only
the append is generic, and a shared appender would be ~15 lines of indirection between two files
that already read clearly.

NOTHING HERE CAN CHANGE A VERDICT. The write happens after the entries exist and every failure is
swallowed -- canonical §2.3.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "candidate_promotion_gate" / "verdicts.jsonl"
MAX_BYTES = 4 * 1024 * 1024


def record_verdicts(entries: Sequence[Any], *, mode: str = "operator",
                    path: Path | None = None) -> None:
    """Append one row per evaluated candidate. Never raises.

    Both outcomes are recorded, not only the refusals: a ledger holding refusals alone could not
    answer "did the accept rate move?", which is the question that catches a gate quietly loosening.
    Titles are truncated and no candidate payload is stored -- the audit asks about rates and
    reasons, and a gate ledger that accumulated every candidate's content would be a second copy of
    the review queue wearing an audit's name."""
    dest = path or LEDGER
    try:
        rows = []
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for e in entries:
            rows.append({
                "ts": stamp,
                "mode": mode,
                "item_id": str(getattr(e, "item_id", ""))[:80],
                "item_type": str(getattr(e, "item_type", ""))[:60],
                "title": str(getattr(e, "title", ""))[:100],
                "risk_level": str(getattr(e, "risk_level", "")),
                "confidence": getattr(e, "confidence", None),
                "source_ref_count": getattr(e, "source_ref_count", None),
                "eligible": bool(getattr(e, "eligible", False)),
                "rejection_reasons": list(getattr(e, "rejection_reasons", ()) or ()),
            })
        if not rows:
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > MAX_BYTES:
            _rotate(dest)
        with dest.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass                                       # §2.3: an evaluator's outcome is never altered


def _rotate(path: Path) -> None:
    """Rotation is itself a row, because a gap in the record has to be visible IN the record."""
    prev = path.with_suffix(".jsonl.1")
    try:
        if prev.exists():
            prev.unlink()
        path.rename(prev)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "event": "rotated", "note": f"previous -> {prev.name}"}) + "\n")
    except OSError:
        pass


def read_verdicts(*, limit: int = 5000, path: Path | None = None) -> list[dict[str, Any]]:
    src = path or LEDGER
    try:
        lines = src.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def refusal_profile(*, path: Path | None = None) -> dict[str, Any]:
    """Accept rate and WHY things were refused, ranked.

    The ranked reasons are the operational payload. A gate refusing everything for
    `missing_source_refs` is a broken upstream, not a strict gate, and the two are
    indistinguishable from the accept rate alone."""
    rows = [r for r in read_verdicts(path=path) if r.get("event") != "rotated"]
    if not rows:
        return {"verdicts": 0}
    from collections import Counter
    reasons: Counter = Counter()
    for r in rows:
        reasons.update(str(x).split(":")[0] for x in (r.get("rejection_reasons") or []))
    ok = sum(1 for r in rows if r.get("eligible"))
    return {
        "verdicts": len(rows),
        "eligible": ok,
        "accept_rate": round(ok / len(rows), 4),
        "top_refusal_reasons": reasons.most_common(8),
        "first": rows[0].get("ts"),
        "last": rows[-1].get("ts"),
    }


def ledger_path() -> str:
    return str(LEDGER)
