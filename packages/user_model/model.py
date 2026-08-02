# -*- coding: utf-8 -*-
"""User deep model derivation (Phase 3-2).

Inputs are the two real local stores:
 * episodic events (data/episodic/events.jsonl) — dated 
 * local brain facts (LocalBrainMemory) — /

Outputs are evidence-backed aggregates:
 * possessions — what the user owns/bought, since when, how old
 * habits — recurring (predicate, object) pairs with a MEASURED median
 interval (periodicity claimed only from >= 3 dated events)
 * preferences — stated likes/dislikes with their source

The 's " " layer: ,
 (fabrication-free by construction).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from packages.episodic_memory.timeline import _rows as _episodic_rows

_OWN_PREDICATES = {"구매", "소유", "선물받음"}
_PREF_PREDICATES = {"선호", "좋아함", "싫어함"}


def _days_since(at: str) -> int | None:
    try:
        return (date.today() - datetime.strptime(at[:10], "%Y-%m-%d").date()).days
    except Exception:
        return None


def _median(xs: list[int]) -> int:
    s = sorted(xs)
    return s[len(s) // 2]


def derive_user_model(events: list[dict[str, Any]] | None = None,
                      brain_facts: list[dict[str, Any]] | None = None,
                      subject: str = "사용자") -> dict[str, Any]:
    """Aggregate the stores into an evidence-backed user model. Pass explicit
    lists for tests; default loads the real local stores."""
    # live mode = no explicit inputs; only then pull the global browsing journal
    # (so tests with explicit events stay isolated from the real journal file)
    _live = events is None and brain_facts is None
    if events is None:
        events = _episodic_rows()
    if brain_facts is None:
        brain_facts = _load_brain_facts()

    mine = [e for e in events if e.get("subject") == subject]

    # -- possessions: own-class predicates, aggregated per object --
    poss: dict[str, dict[str, Any]] = {}
    for e in mine:
        if e.get("predicate") not in _OWN_PREDICATES:
            continue
        obj = str(e.get("object") or "").strip()
        if not obj:
            continue
        slot = poss.setdefault(obj, {"object": obj, "events": [], "since": None, "last": None})
        slot["events"].append(e)
        at = str(e.get("at") or "")
        slot["since"] = min(filter(None, [slot["since"], at])) if slot["since"] else at
        slot["last"] = max(filter(None, [slot["last"], at])) if slot["last"] else at
    possessions = []
    for slot in poss.values():
        possessions.append({
            "object": slot["object"],
            "since": slot["since"],
            "last": slot["last"],
            "age_days": _days_since(slot["last"]) if slot["last"] else None,
            "evidence_count": len(slot["events"]),
            "evidence": slot["events"][-3:],
        })
    possessions.sort(key=lambda p: p.get("age_days") or 0, reverse=True)

    # -- habits: recurring (predicate, object), periodicity ONLY from >=3 dates --
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for e in mine:
        pred = str(e.get("predicate") or "")
        if pred in _OWN_PREDICATES or pred in _PREF_PREDICATES:
            continue
        obj = str(e.get("object") or "").strip()
        if pred and obj:
            groups[(pred, obj)].append(str(e.get("at") or ""))
    habits = []
    for (pred, obj), dates in groups.items():
        dates = sorted(d for d in dates if d)
        if len(dates) < 3:
            continue
        try:
            ds = [datetime.strptime(d[:10], "%Y-%m-%d").date() for d in dates]
            gaps = [(ds[i + 1] - ds[i]).days for i in range(len(ds) - 1)]
            interval = _median([g for g in gaps if g >= 0]) if gaps else None
        except Exception:
            interval = None
        habits.append({
            "predicate": pred, "object": obj,
            "count": len(dates), "first": dates[0], "last": dates[-1],
            "median_interval_days": interval,
            "days_since_last": _days_since(dates[-1]),
        })
    habits.sort(key=lambda h: h["count"], reverse=True)

    # -- preferences: episodic pref events + local brain conversational facts --
    preferences = []
    for e in mine:
        if e.get("predicate") in _PREF_PREDICATES:
            preferences.append({
                "value": str(e.get("object") or ""),
                "polarity": "negative" if e.get("predicate") == "싫어함" else "positive",
                "source": "episodic", "at": e.get("at"),
            })
    for f in brain_facts:
        if str(f.get("kind")) == "preference":
            preferences.append({
                "value": f"{f.get('subject')}: {f.get('value')}",
                "polarity": "positive",
                "source": "local_brain", "confidence": f.get("confidence"),
            })

    # browsing interests (the AI browser's contribution): domains the user
    # dwells on become derived interests — the browser deepens the user model.
    browsing_interests = []
    try:
        from packages.atanor_browser.activity_journal import interests as _bi

        for it in (_bi(limit=5) if _live else []):
            browsing_interests.append(it)
            preferences.append({
                "value": it["domain"], "polarity": "positive",
                "source": "browsing", "weight": it["weight"]})
    except Exception:
        browsing_interests = []

    return {
        "subject": subject,
        "possessions": possessions,
        "habits": habits,
        "preferences": preferences,
        "browsing_interests": browsing_interests,
        "evidence_totals": {
            "episodic_events": len(mine),
            "brain_facts": len(brain_facts),
        },
    }


def _load_brain_facts() -> list[dict[str, Any]]:
    try:
        from packages.local_brain.memory_store import LocalBrainMemory

        return [f.to_dict() for f in LocalBrainMemory().all_facts()]
    except Exception:
        return []


def summary_facts(model: dict[str, Any] | None = None, limit: int = 6) -> list[str]:
    """Korean sentences for the answer path — each cites its evidence count so
    the surface stays honest about how much it rests on."""
    m = model or derive_user_model()
    out: list[str] = []
    for p in m["possessions"][:limit]:
        if p.get("age_days") is not None:
            years = p["age_days"] // 365
            span = f"약 {years}년 전" if years >= 1 else f"{p['age_days']}일 전"
            out.append(f"사용자는 {p['object']}을(를) {span}에 들였습니다 (근거 {p['evidence_count']}건).")
    for h in m["habits"][:limit]:
        if h.get("median_interval_days"):
            out.append(
                f"사용자는 {h['object']}에 약 {h['median_interval_days']}일 간격으로 "
                f"{h['predicate']} 기록이 있습니다 (총 {h['count']}회).")
    for pref in m["preferences"][:limit]:
        pol = "좋아합니다" if pref.get("polarity") == "positive" else "선호하지 않습니다"
        out.append(f"사용자는 {pref['value']}을(를) {pol} ({pref['source']} 기록).")
    return out[:limit]


def user_context_line(model: dict[str, Any] | None = None) -> str | None:
    """One dense line for prompt-free in-graph reasoning surfaces (UI panels,
    self-narration). None when nothing is recorded — silence over invention."""
    m = model or derive_user_model()
    bits: list[str] = []
    if m["possessions"]:
        bits.append("소유 " + ", ".join(p["object"] for p in m["possessions"][:3]))
    if m["habits"]:
        bits.append("습관 " + ", ".join(f"{h['object']}({h['count']}회)" for h in m["habits"][:2]))
    if m["preferences"]:
        bits.append("선호 " + ", ".join(p["value"] for p in m["preferences"][:2]))
    return " · ".join(bits) if bits else None
