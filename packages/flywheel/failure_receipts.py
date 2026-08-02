# -*- coding: utf-8 -*-
"""Failure-receipt engine — don't just discard a rejection, remember WHY and let the accumulated
failure pattern STEER the next iteration's search.

Inspired by an architect's closed-loop doctrine (2026-07-12): candidate → evaluate → diagnose the
failure → correct the search space → next candidate, with a receipt archive that accumulates the
rejection causes and auto-tunes the next generation's mutation targets, jump probability, and
priority search paths. ATANOR already mines failures (flywheel.mine_failures); this adds the
CONTROL layer — a bounded, decaying receipt ledger that turns rejections into a search bias.

Where receipts come from: the Critic (speech_selfplay.critique) rejecting a phrasing, the junk
gates (pack_purity, contradiction_gate) quarantining a concept, the k-source consensus failing.
Each carries the CAUSE (already computed by those gates) and the TOPIC it came from.

Deterministic and DEFAULT-SAFE: the bias only ever NARROWS or steers AWAY from junk-heavy
domains — it never fabricates a topic or forces intake. If the archive is empty it is inert.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

_ARCHIVE = Path(__file__).resolve().parents[2] / "data" / "flywheel" / "failure_receipts.jsonl"
_MAX_RECEIPTS = 5000              # ring buffer: the ledger remembers, but stays bounded


def _load() -> list[dict[str, Any]]:
    try:
        with _ARCHIVE.open("r", encoding="utf-8") as fh:
            return [json.loads(ln) for ln in fh if ln.strip()]
    except Exception:
        return []


def record_receipt(*, topic: str | None, causes: list[str], source: str, chars: int = 0,
                   kind: str = "junk") -> None:
    """Archive one failure: WHY it failed (causes — the gate's own diagnosis), WHERE it came from
    (topic/domain), and its KIND. Two kinds steer OPPOSITE ways:
      * junk — a bad SOURCE (Critic rejected garbage, pack_purity quarantined) → steer AWAY
      * gap  — a knowledge HOLE (the engine abstained, a verification gap) → steer TOWARD (go learn)
    Trimmed to a bounded ring so the ledger never grows without limit."""
    causes = [str(c) for c in (causes or []) if str(c).strip()][:8]
    if not causes and not topic:
        return
    rec = {"ts": round(time.time(), 2), "topic": (topic or "").strip()[:80] or None,
           "causes": causes, "source": str(source or "")[:40], "chars": int(chars),
           "kind": "gap" if kind == "gap" else "junk"}
    try:
        _ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
        existing = _load()
        existing.append(rec)
        if len(existing) > _MAX_RECEIPTS:
            existing = existing[-_MAX_RECEIPTS:]
        with _ARCHIVE.open("w", encoding="utf-8") as fh:
            for r in existing:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    except Exception:
        pass


def search_bias(*, window: int = 500) -> dict[str, Any]:
    """Read the recent failure pattern and emit a search STEER for the learner's next tick:
      * avoid_topics    — domains whose junk share far exceeds their fair share (steer away)
      * jump_probability — rises when failures CONCENTRATE in a few domains (jump elsewhere),
                           falls when they are diffuse (the search space is broadly fine)
      * dominant_causes — what is failing most (informs what to fix, not where to look)
    Inert (jump 0.15, no avoids) when the ledger is empty — never invents a bias from nothing."""
    receipts = _load()[-max(1, window):]
    empty = {"avoid_topics": [], "seek_topics": [], "dominant_causes": {},
             "jump_probability": 0.15, "sampled": 0}
    if not receipts:
        return empty

    junk = [r for r in receipts if r.get("kind", "junk") == "junk" and r.get("topic")]
    gap = [r for r in receipts if r.get("kind") == "gap" and r.get("topic")]
    cause_counts = Counter(c for r in receipts for c in r.get("causes", []))

    def _heavy(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
        counts = Counter(r["topic"] for r in rows)
        total = sum(counts.values())
        if total == 0:
            return [], 0.0
        fair = total / max(1, len(counts))                   # expected share if uniform
        # heavy = a real count (≥3) that is either an OUTLIER among many topics (≥1.8× its fair
        # share) OR a DOMINANT chunk on its own (≥40% of failures — catches the single-topic case
        # where every count is the fair share and the relative test can never fire).
        hot = [{"topic": t, "share": round(n / total, 3), "count": n}
               for t, n in counts.most_common()
               if n >= 3 and (n >= 1.8 * fair or n / total >= 0.4)]
        return hot[:8], counts.most_common(1)[0][1] / total

    avoid, junk_conc = _heavy(junk)                          # bad sources → steer away
    seek, _ = _heavy(gap)                                    # knowledge holes → steer toward
    jump = round(min(0.8, max(0.12, junk_conc)), 3)          # junk concentrated → jump away more

    return {"avoid_topics": avoid, "seek_topics": seek,
            "dominant_causes": dict(cause_counts.most_common(5)),
            "jump_probability": jump, "sampled": len(receipts)}


def should_avoid(topic: str, *, window: int = 500) -> bool:
    """A cheap gate the learner can call before probing a topic: True if this domain has been a
    junk source recently. Steers AWAY only — a new/unseen topic is never avoided."""
    if not topic:
        return False
    t = topic.strip()[:80]
    return any(a["topic"] == t for a in search_bias(window=window)["avoid_topics"])


def receipt_stats() -> dict[str, Any]:
    """Read-only summary for /ops and the dashboard — the ledger's size and its top junk domains."""
    receipts = _load()
    topic_counts = Counter(r["topic"] for r in receipts if r.get("topic"))
    cause_counts = Counter(c for r in receipts for c in r.get("causes", []))
    kinds = Counter(r.get("kind", "junk") for r in receipts)
    return {"total_receipts": len(receipts), "kinds": dict(kinds),
            "top_topics": [{"topic": t, "count": n} for t, n in topic_counts.most_common(8)],
            "top_causes": dict(cause_counts.most_common(8)),
            "bounded_at": _MAX_RECEIPTS}
