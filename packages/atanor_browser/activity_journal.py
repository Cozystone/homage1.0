# -*- coding: utf-8 -*-
"""Personal browsing activity journal — the AI browser's private brain graph.

The owner's actual browser: a Chrome-like web browser where EVERY browsing
action (visit, search, click, dwell) is organized into the PERSONAL brain graph.
This is the private, local-first half — distinct from browser_ingest, which
distills page CONTENT into the shared consensus-gated knowledge store.

Two lanes, never crossed:
 * CONTENT (browser_ingest) -> shared world knowledge, consensus-gated
 * ACTIVITY (this module) -> the USER's own history/interests, local only

Contract (local-first, like the perception frames-never-stored rule):
 * every event is a timestamped triple on the SAME episodic timeline the rest
 of selfhood uses (" example.com", " "), so
 " " is answerable from one place
 * a private domain-interest graph accrues so the browser learns what the user
 cares about (feeds the user model) — derived, never authored
 * revisit detection + session threading make the history a MAP, not a log
 * PII guard runs on every recorded string (a search query can hold PII); the
 raw query is dropped if it does, only the safe part is kept
 * NOTHING leaves the device — this is the user's memory, not a candidate
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_DATA = Path(__file__).resolve().parents[2] / "data" / "atanor_browser"
JOURNAL = _DATA / "activity_journal.jsonl"

_SESSION_GAP_S = 30 * 60   # a >30min gap starts a new browsing session
_STOP_DOMAINS = {"google.com", "bing.com", "duckduckgo.com", "search.naver.com"}


def _host(url: str) -> str:
    try:
        h = (urlparse(url).hostname or "").lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def _pii_safe(text: str) -> str | None:
    """Drop a string that carries PII (a query can leak personal data). Returns
    the text if clean, None if it must not be journaled."""
    try:
        from packages.graph_scale.pii_guard import has_pii

        return None if has_pii(text) else text
    except Exception:
        return text


def _rows() -> list[dict[str, Any]]:
    if not JOURNAL.exists():
        return []
    out = []
    for line in JOURNAL.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _append(row: dict[str, Any]) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _session_id(now: float) -> str:
    """Same session unless the gap since the last event exceeds the threshold."""
    rows = _rows()
    if rows:
        try:
            last = float(rows[-1].get("ts") or 0)
            if now - last < _SESSION_GAP_S:
                return str(rows[-1].get("session") or int(last))
        except Exception:
            pass
    return str(int(now))


def record_activity(kind: str, url: str = "", query: str = "", title: str = "",
                    dwell_s: float = 0.0) -> dict[str, Any]:
    """Journal one browsing action into the personal brain graph + episodic
    timeline. kind: visit | search | click | dwell. Local only, PII-gated."""
    now = time.time()
    host = _host(url)
    safe_query = _pii_safe(query) if query else ""
    safe_title = _pii_safe(title) if title else ""
    session = _session_id(now)
    row = {"ts": now, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "kind": kind, "host": host, "url": url if _pii_safe(url) else "",
           "query": safe_query or "", "title": safe_title or "",
           "dwell_s": round(float(dwell_s), 1), "session": session}
    _append(row)

    try:
        from packages.episodic_memory.timeline import record_event

        if kind == "search" and safe_query:
            record_event("사용자", "검색", safe_query, note=host, source="browser")
        elif kind == "visit" and host:
            record_event("사용자", "방문", host, note=safe_title or "", source="browser")
    except Exception:
        pass
    return {"recorded": True, "kind": kind, "host": host, "session": session,
            "pii_dropped": bool(query and not safe_query)}


def interests(limit: int = 10) -> list[dict[str, Any]]:
    """The user's browsing interests, derived from visited domains (search
    engines excluded — they are the road, not the destination)."""
    rows = _rows()
    dom = Counter()
    for r in rows:
        h = r.get("host") or ""
        if not h or h in _STOP_DOMAINS:
            continue
        # weight a visit by dwell (a 5s bounce < a 3min read)
        dom[h] += 1 + min(5, int(float(r.get("dwell_s") or 0) / 30))
    total = sum(dom.values()) or 1
    return [{"domain": h, "weight": w, "share": round(w / total, 3)}
            for h, w in dom.most_common(limit)]


def recall(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """ : history matching a term (domain/query/title), newest first."""
    q = str(query or "").strip().lower()
    rows = _rows()
    hits = []
    for r in reversed(rows):
        blob = f"{r.get('host','')} {r.get('query','')} {r.get('title','')}".lower()
        if not q or q in blob:
            hits.append({k: r.get(k) for k in ("at", "kind", "host", "query", "title", "dwell_s")})
        if len(hits) >= limit:
            break
    return hits


def revisits(min_count: int = 3) -> list[dict[str, Any]]:
    """Domains the user returns to (a habit signal for the user model)."""
    rows = _rows()
    dom = Counter(r.get("host") for r in rows
                  if r.get("host") and r.get("host") not in _STOP_DOMAINS)
    return [{"domain": h, "visits": c} for h, c in dom.most_common()
            if c >= min_count]


def sessions_summary(limit: int = 5) -> list[dict[str, Any]]:
    """Recent browsing sessions as coherent threads (not a flat log)."""
    rows = _rows()
    by_session: dict[str, dict[str, Any]] = {}
    for r in rows:
        sid = str(r.get("session") or "")
        s = by_session.setdefault(sid, {"session": sid, "started": r.get("at"),
                                        "hosts": [], "events": 0})
        h = r.get("host")
        if h and h not in s["hosts"]:
            s["hosts"].append(h)
        s["events"] += 1
        s["ended"] = r.get("at")
    out = sorted(by_session.values(), key=lambda s: s["started"] or "", reverse=True)
    return out[:limit]


def status() -> dict[str, Any]:
    rows = _rows()
    return {"events": len(rows), "domains": len({r.get("host") for r in rows if r.get("host")}),
            "sessions": len({r.get("session") for r in rows}),
            "top_interests": interests(5), "local_only": True}
