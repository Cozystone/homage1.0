# -*- coding: utf-8 -*-
"""Endogenous gap detection — the daemon's targets come from STATE PRESSURE, never a timer.

Doctrine (endogenous-self-inquiry): inquiry arises from pressure, not a bare schedule. A "gap"
here is a relational question the GRAPH HONESTLY ABSTAINS on — a real hole, measured by asking the
real store and seeing ``honest_abstain_relational``. A one-off abstention is REMEMBERED but not
pursued; a gap becomes a PURSUED target only when its abstention RECURS (recurrence = the state
pressure of "the system keeps hitting this same wall"), which is exactly the concentration signal
``flywheel.failure_receipts`` already turns into a search steer.

Two organs, cleanly split:
  * REUSED — ``flywheel.failure_receipts`` is the shared pressure ledger. Every observed abstention
    records a ``kind="gap"`` receipt (the same idiom ``autonomy_kernel.intrinsic_drive._steer_topic``
    consumes as "jump to a gap — learn what we abstain on"). ``search_bias().seek_topics`` (gaps that
    CONCENTRATED) is read back as a co-signal, so a gap other organs are also failing on is pursued.
  * NEW GLUE — a small SCOPED index (the path the daemon is given) that keys each gap by its
    canonical (entity, relation) and stores the concrete question + a recurrence count, so a hot gap
    key can be turned back into the exact question to run through the acquisition loop. Deterministic
    and isolated (no dependency on the shared ledger's other contents), so the sealed gate is
    reproducible.

Honesty (stated for the report): "pressure" here is operationalised as abstention-RECURRENCE past a
declared floor (:data:`MIN_PRESSURE`). It is genuinely not a schedule — a gap under the floor is
never pursued, and nothing is pursued when there is no recurring abstention — but it is a
recurrence-of-demand proxy, not an intrinsic structural-curiosity signal. That limitation is a
documented residual, not a hidden schedule.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

# A gap must RECUR at least this many times (distinct observations) before it is worth an
# expedition. Below the floor the gap is remembered but NOT pursued — this is what makes the
# selection pressure-driven rather than a queue/schedule over every abstention.
MIN_PRESSURE = 2


def gap_key(question: str) -> str | None:
    """Canonical, phrasing-independent key for a relational gap: ``entity|rel_norm`` from the
    LAD relational-shape parser, so "what is the capital of France?" and "France's capital?" are
    the SAME gap. Returns None for a non-relational shape (the acquisition loop can't pursue it)."""
    try:
        from packages.base_brain.relational_lookup import parse_relational_shape
        shape = parse_relational_shape(question)
    except Exception:
        shape = None
    if shape and shape.get("entity") and shape.get("rel_norm"):
        return f"{str(shape['entity']).strip().lower()}|{str(shape['rel_norm']).strip().lower()}"
    return None


class GapLedger:
    """Scoped recurrence ledger for honest abstentions. ``index_path`` is a JSON file the daemon
    owns (ephemeral in the sealed gate). Feeds the shared failure-receipt ledger for real system
    integration, but reads recurrence from its OWN index so it is deterministic."""

    def __init__(self, index_path: Path | str):
        self.index_path = Path(index_path)

    # ---- persistence (scoped, deterministic) --------------------------------------------------
    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, idx: dict[str, dict[str, Any]]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2, sort_keys=True),
                                   encoding="utf-8")

    # ---- observation --------------------------------------------------------------------------
    def observe(self, question: str, *, store: Any = None, source: str = "daemon") -> dict[str, Any]:
        """Observe ONE question. If ``store`` is given, the abstention is VERIFIED against the real
        graph (READ-only) — only a genuine ``honest_abstain_relational`` counts as a gap; an
        already-grounded or non-relational question records nothing. Records a shared ``kind="gap"``
        failure receipt (pressure ledger) and bumps the scoped recurrence count."""
        gk = gap_key(question)
        if not gk:
            return {"gap": False, "reason": "not_relational_shape", "question": question}

        if store is not None:
            try:
                from packages.base_brain.relational_lookup import resolve_relational
                core = resolve_relational(question, "en", store=store)
            except Exception:
                core = None
            if not core or core.get("answer_kind") != "honest_abstain_relational":
                # not a real gap right now (already grounded / not relational) — record nothing
                return {"gap": False, "reason": "not_abstaining", "gap_key": gk,
                        "answer_kind": None if not core else core.get("answer_kind")}

        # shared pressure ledger (REUSED organ) — the same signal intrinsic_drive._steer_topic reads
        try:
            from packages.flywheel.failure_receipts import record_receipt
            record_receipt(topic=gk, causes=["honest_abstain_relational"], source=source, kind="gap")
        except Exception:
            pass

        idx = self._load()
        rec = idx.get(gk) or {"question": question, "count": 0,
                              "first_ts": round(time.time(), 2)}
        rec["question"] = question               # keep the most recent concrete phrasing
        rec["count"] = int(rec.get("count", 0)) + 1
        rec["last_ts"] = round(time.time(), 2)
        idx[gk] = rec
        self._save(idx)
        return {"gap": True, "gap_key": gk, "question": question, "count": rec["count"]}

    # ---- pressure selection (endogenous target list) ------------------------------------------
    def pressured(self, min_pressure: int = MIN_PRESSURE, *,
                  structural_holes: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """The endogenous target list, from TWO endogenous sources:

        1. RECURRENCE (recurrence-of-demand) — a gap qualifies if its abstention RECURRED to the
           floor (scoped recurrence) OR the shared failure-receipt engine flags its key as a
           concentrated ``seek_topic``. Every entry traces to a measured, recurring honest abstention.
        2. STRUCTURAL CURIOSITY (``structural_holes``, optional) — genuinely-valuable graph holes the
           system was NEVER re-asked about: a relation the induced schema says a salient entity should
           have but doesn't, scored by ``structural_gaps.StructuralGapScanner``. This is the
           self-winding source — pressure from the graph's own structure, not from repeated demand.

        Nothing hardcoded in EITHER source: recurrence traces to real abstentions; structural holes
        trace to the graph's own salience/coverage/uncertainty statistics. Recurrence keeps priority
        (a wall the system keeps hitting outranks a merely-latent hole); ties among structural holes
        fall to their curiosity score. When ``structural_holes`` is None the behaviour is byte-for-byte
        the original recurrence-only selection (no regression)."""
        idx = self._load()
        seek: set[str] = set()
        try:
            from packages.flywheel.failure_receipts import search_bias
            seek = {str(s.get("topic")) for s in (search_bias().get("seek_topics") or [])
                    if s.get("topic")}
        except Exception:
            seek = set()

        out: list[dict[str, Any]] = []
        by_key: dict[str, dict[str, Any]] = {}
        for gk, rec in idx.items():
            by_floor = int(rec.get("count", 0)) >= min_pressure
            by_seek = gk in seek
            if not (by_floor or by_seek):
                continue
            sources = []
            if by_floor:
                sources.append("recurrence")
            if by_seek:
                sources.append("failure_receipt_seek")
            entry = {"gap_key": gk, "question": rec.get("question", ""),
                     "count": int(rec.get("count", 0)), "pressure_sources": sources}
            out.append(entry)
            by_key[gk] = entry

        # SECOND SOURCE — merge structural-curiosity holes. A hole already under recurrence pressure
        # simply gains "structural_curiosity" as a co-source (and its curiosity score); a hole no one
        # re-asked enters as a fresh endogenous target with count 0.
        for h in (structural_holes or []):
            gk = str(h.get("gap_key") or "")
            if not gk:
                continue
            score = float(h.get("score") or 0.0)
            existing = by_key.get(gk)
            if existing is not None:
                if "structural_curiosity" not in existing["pressure_sources"]:
                    existing["pressure_sources"].append("structural_curiosity")
                existing["curiosity_score"] = score
                if not existing.get("question"):
                    existing["question"] = str(h.get("question") or "")
            else:
                entry = {"gap_key": gk, "question": str(h.get("question") or ""),
                         "count": 0, "pressure_sources": ["structural_curiosity"],
                         "curiosity_score": score}
                out.append(entry)
                by_key[gk] = entry

        # recurrence count first (a repeatedly-hit wall wins), then curiosity score, then key.
        out.sort(key=lambda r: (-int(r.get("count", 0)),
                                -float(r.get("curiosity_score") or 0.0), r["gap_key"]))
        return out

    def count(self, question_or_key: str) -> int:
        gk = question_or_key if "|" in question_or_key else (gap_key(question_or_key) or "")
        return int(self._load().get(gk, {}).get("count", 0))

    def all_gaps(self) -> dict[str, dict[str, Any]]:
        return self._load()
