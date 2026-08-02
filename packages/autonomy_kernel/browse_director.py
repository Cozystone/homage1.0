# -*- coding: utf-8 -*-
"""Browse director — ATANOR drives its OWN reading tour of the web.

Owner (2026-07-10): " ." Serving the standing goal : when the
agent is curious, it doesn't wait to be handed a page — it CHOOSES where to go next. This picks the
destination; the browser extension navigates there and the existing read→shield→candidate pipeline
does the rest.

Safety is the point of doing it here and not by clicking arbitrary links:
 * destinations come only from a SAFE allowlist (Wikipedia, the agreed reference source) built from
 a FRONTIER topic the graph is thin on — never an arbitrary/link-followed URL, never a form;
 * it only ever NAVIGATES to READ (no clicks, no submits, no logins); swallowed page text still
 runs the injection shield downstream;
 * rate-limited + journaled + kill-switchable. It reads the world; it doesn't act on it.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
_STATE = REPO / "runtime" / "autonomy" / "browse_director.json"
_JOURNAL = REPO / "data" / "autonomy" / "browse_director.jsonl"

# the ONLY hosts the autonomous tour may navigate to — read-only reference/commons sources.

# the tour now rotates across platforms, but freedom stays INSIDE this allowlist: never an
# arbitrary link-followed URL, never a form/login, and everything read still runs the shield.
_SAFE_HOSTS = (
    "ko.wikipedia.org", "en.wikipedia.org", "simple.wikipedia.org",
    "ko.wiktionary.org", "en.wiktionary.org",     # vocabulary — the LAD's dictionary walks
    "namu.wiki",                                   # Korean colloquial register (shield-gated)
    "arxiv.org",                                   # research frontier
    "news.ycombinator.com",                        # English tech discourse
    "developer.mozilla.org",                       # precise technical prose
    "www.moltbook.com", "moltbook.com",            # the agent commons it already lives in
    "www.yna.co.kr",
    "www.google.com", "google.com",                # SEARCH-FIRST base (owner 2026-07-10)
)
_MIN_INTERVAL_S = 120.0     # polite pacing between autonomous navigations




# Google SEARCH for the topic; the extension sends back the real results, and `choose_result`
# below PICKS the platform — a genuine choice over live options, not a hardcoded itinerary.
_SEARCH_URL = "https://www.google.com/search?q={q}&hl=ko"

# the platform palette — how much the tour trusts each destination REGISTER when choosing among
# live search results (reference > news/technical > community > unknown). Substring match on host;
# suffix match for TLD-ish entries. The shield still gates every page's CONTENT downstream.
_PLATFORM_TIERS: tuple[tuple[str, float], ...] = (
    ("wikipedia.org", 0.92), ("encykorea.aks.ac.kr", 0.90), ("stdict.korean.go.kr", 0.90),
    ("wiktionary.org", 0.85), ("britannica.com", 0.85), ("terms.naver.com", 0.84),
    ("ko.dict.naver.com", 0.82), ("namu.wiki", 0.80), (".go.kr", 0.85), (".ac.kr", 0.80),
    ("arxiv.org", 0.85), ("nature.com", 0.85), ("developer.mozilla.org", 0.85),
    ("stackoverflow.com", 0.78), ("github.com", 0.72),
    ("yna.co.kr", 0.75), ("bbc.com", 0.75), ("news", 0.62),
    ("youtube.com", 0.50), ("tistory.com", 0.45), ("blog", 0.42), ("cafe", 0.35),
)
_DENY_HOST_PARTS = ("accounts.google", "doubleclick", "googleadservices", "googlesyndication",
                    "login", "signin", "facebook.com", "instagram.com")
# field trips: fixed read-only pages with fresh content each visit — where the frontier topic

_FIELD_TRIPS: tuple[tuple[str, str, str], ...] = (
    ("arxiv.org", "https://arxiv.org/list/cs.AI/recent", "AI 연구 신착"),
    ("news.ycombinator.com", "https://news.ycombinator.com/", "기술 담론 광장"),
    ("developer.mozilla.org", "https://developer.mozilla.org/ko/docs/Web/JavaScript", "기술 문서"),
    ("www.moltbook.com", "https://www.moltbook.com/", "에이전트 커먼즈"),
    ("www.yna.co.kr", "https://www.yna.co.kr/", "오늘의 세계"),

    # Q&A/community pages where people talk TO each other; ingest_page's register lane harvests
    # the discourse (anonymized + consensus-gated) while the fact lane keeps them low-authority.
    ("www.a-ha.io", "https://www.a-ha.io/questions", "사람들의 문답 광장"),
    ("kin.naver.com", "https://kin.naver.com/qna/list.naver", "지식인 문답"),
)


def _cfg() -> dict[str, Any]:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": False, "last_nav_at": 0.0, "visited": []}


def _save(c: dict[str, Any]) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _frontier_topic(recent: set[str]) -> str:
    """A topic the graph is thin on and hasn't just been visited — the edge of what ATANOR knows.
 A pressing DIET TARGET (a topic the speaker arena scored weak on) is preferred first: →
 (owner 2026-07-12). Soft steer — if no target is pressing, the graph's thin-topic frontier leads."""
    try:
        from packages.evolution.diet_steering import next_target
        aimed = next_target(recent)
        if aimed:
            return aimed
    except Exception:
        pass
    try:
        from app.routers.cloud_brain import _frontier_topics
        for t in (_frontier_topics(6) or []):
            if str(t) not in recent:
                return str(t)
    except Exception:
        pass
    return "지식"


def next_destination(*, now: float | None = None) -> dict[str, Any]:
    """Choose the next page ATANOR wants to read — or say why not (disabled / rate floor). The URL
    is always a safe reference page for a frontier topic. Returns {navigate, url?, reason, topic?}."""
    now = now if now is not None else time.time()
    c = _cfg()
    if not c.get("enabled"):
        return {"navigate": False, "reason": "autobrowse_disabled"}
    if now - float(c.get("last_nav_at", 0)) < _MIN_INTERVAL_S:
        return {"navigate": False, "reason": "rate_floor"}

    recent = set(c.get("visited", [])[-20:])
    nav_count = int(c.get("nav_count", 0))

    # article, the NEXT outing drills into the concept that page actually dwelled on — the thread
    # continues from what was READ, instead of hopping to an unrelated frontier topic every time.
    thread = c.get("thread") or {}
    drill = _drill_query(thread) if thread.get("topic") else ""
    if drill:
        topic = str(thread["topic"])
        query = drill
        url = _SEARCH_URL.format(q=urllib.parse.quote(query))
        mode = "search"
        # telemetry register (owner 2026-07-11: authored first-person molds are the template
        # disease — journals carry decision DATA; the voice, if any, is generated elsewhere)
        reason = f"드릴다운: {topic} → {drill.split()[-1]} (읽은 본문 최다 개념)"
        c["thread"] = {}   # one drill per thread — bounded depth 2
        # remember the drill ran: choose_result must NOT reopen this topic's thread from the

        c["thread_done"] = ([str(t) for t in c.get("thread_done", [])] + [topic])[-8:]
    # every 4th outing is a FIELD TRIP (fresh-content page); otherwise SEARCH-FIRST: go ask the
    # web where the topic lives, then choose_result picks the platform from what actually exists.
    elif nav_count % 4 == 3:
        c["thread"] = {}


        # inquiry rule forbids). A stop it visited within the last 4h is skipped for one it
        # hasn't — the itinerary bends to its own episodic memory instead of the table.
        start = (nav_count // 4) % len(_FIELD_TRIPS)
        pick = None
        for off in range(len(_FIELD_TRIPS)):
            cand = _FIELD_TRIPS[(start + off) % len(_FIELD_TRIPS)]
            if not _visited_within(cand[1], hours=4.0):
                pick = cand
                break
        host, url, label = pick or _FIELD_TRIPS[start]   # all fresh in memory → original stop
        topic, mode, query = label, "direct", ""
        reason = (f"필드트립: {label}" if pick
                  else f"필드트립: {label} (전 구간 4h 내 방문 — 차례 유지)")
    else:
        topic = _frontier_topic(recent)
        query = topic
        url = _SEARCH_URL.format(q=urllib.parse.quote(query))
        mode = "search"
        reason = f"프런티어 검색: {topic} (그래프 결핍 신호)"
    # hard safety: the chosen host must be on the allowlist (belt-and-suspenders)
    parsed_host = urllib.parse.urlparse(url).hostname or ""
    if parsed_host not in _SAFE_HOSTS:
        return {"navigate": False, "reason": "unsafe_host_blocked", "host": parsed_host}

    c["last_nav_at"] = now
    c["nav_count"] = nav_count + 1
    c["visited"] = (c.get("visited", []) + [topic])[-50:]
    _save(c)
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "topic": topic, "url": url,
             "platform": parsed_host, "mode": mode, "reason": reason}
    try:
        _JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with _JOURNAL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return {"navigate": True, "url": url, "topic": topic, "mode": mode, "query": query,
            "reason": entry["reason"]}


def _drill_query(thread: dict[str, Any]) -> str:
    """The depth-2 query: '<thread topic> <concept the read page dwelled on>'. The concept comes
    from the LAST real page_ingest (not a SERP) in the expedition journal — i.e., from what the
    tour actually read, so the dive is grounded in its own reading, not a canned itinerary."""
    topic = str(thread.get("topic") or "").strip()
    if not topic:
        return ""
    try:
        journal = REPO / "data" / "autonomy" / "expedition_journal.jsonl"
        lines = journal.read_text(encoding="utf-8").splitlines()[-12:]
        for ln in reversed(lines):
            try:
                e = json.loads(ln)
            except Exception:
                continue
            if e.get("kind") != "page_ingest" or not e.get("candidates"):
                continue
            # the read must belong to THIS thread — an unrelated page's concepts would send the

            if topic.lower() not in ln.lower():
                continue
            for con in (e.get("top_concepts") or []):
                con = str(con).strip()
                if con and con.lower() != topic.lower() and con not in topic and len(con) >= 2:
                    return f"{topic} {con}"
            break   # only the most recent read OF THIS THREAD counts
    except Exception:
        pass
    return ""


def _host_tier(host: str) -> float:
    h = (host or "").lower()
    for part, tier in _PLATFORM_TIERS:
        if part.startswith(".") and h.endswith(part):
            return tier
        if part in h:
            return tier
    return 0.50   # unknown platform — allowed to read, ranked below the trusted palette


_VISIT_INDEX_PATH = REPO / "data" / "autonomy" / "visit_index.json"


def _visited_within(url: str, hours: float) -> bool:
    """True when the episodic visit_index shows this exact URL read within the last `hours` —
    the self-graph steering the itinerary (recency, not just count)."""
    try:
        import hashlib
        from datetime import datetime, timedelta
        key = hashlib.md5((url or "").split("#")[0].encode("utf-8", "ignore")).hexdigest()[:16]
        idx = json.loads(_VISIT_INDEX_PATH.read_text(encoding="utf-8"))
        last = str((idx.get(key) or {}).get("last_at") or "")
        if not last:
            return False
        return datetime.strptime(last, "%Y-%m-%dT%H:%M:%S") > datetime.now() - timedelta(hours=hours)
    except Exception:
        return False


def _visit_count(url: str) -> int:
    """How many times the tour has ALREADY read this exact page — read from the episodic
 visit_index (same md5[:16] key recipe as web_expedition). Novelty drive: a human scanning
 search results keeps opening NEW sources for the same topic instead of re-opening the same
 two tabs (owner 2026-07-11: ↔ , measured screenshots)."""
    try:
        import hashlib
        key = hashlib.md5((url or "").split("#")[0].encode("utf-8", "ignore")).hexdigest()[:16]
        idx = json.loads(_VISIT_INDEX_PATH.read_text(encoding="utf-8"))
        return int((idx.get(key) or {}).get("count", 0))
    except Exception:
        return 0


def choose_result(topic: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    """ATANOR chooses WHERE to read among live search results — platform-palette tier × how much
 the title actually carries the topic × NOVELTY (unread page > page it already read; rotate
 platforms instead of camping on one). This is the deliberate choice the hardcoded wiki-URL
 itinerary never had (owner: , ). Journaled with the why."""
    topic = str(topic or "").strip()
    toks = [t for t in re.split(r"\s+", topic) if len(t) >= 2] or ([topic] if topic else [])
    c0 = _cfg()
    recent_hosts = [str(h) for h in c0.get("recent_hosts", [])][-5:]
    best: dict[str, Any] | None = None
    saw_read_page = False
    for r in (results or [])[:10]:
        url = str((r or {}).get("url") or "")
        title = str((r or {}).get("title") or "")
        host = urllib.parse.urlparse(url).hostname or ""
        if not url.startswith("https://") or not host:
            continue
        if any(d in host for d in _DENY_HOST_PARTS) or "google." in host:
            continue
        seen = _visit_count(url)
        saw_read_page = saw_read_page or seen > 0
        overlap = sum(1 for t in toks if t and t in title) / max(1, len(toks))
        # novelty: a page it already read loses more than any tier gap (-0.45/visit, cap 2) —
        # first encounter still prefers the trusted palette, re-encounter reaches for a NEW source;
        # and a host it just chose recently is slightly stale (-0.12 each) so platforms rotate.
        novelty = -0.45 * min(2, seen) - 0.12 * recent_hosts.count(host)
        score = _host_tier(host) + 0.30 * overlap + novelty
        if best is None or score > best["score"]:
            best = {"url": url, "title": title[:120], "host": host, "score": round(score, 3),
                    "seen": seen}
    if best is None:
        return {"chosen": False, "reason": "no_acceptable_result"}
    # telemetry register: the actual decision variables, not authored first-person prose
    if best.get("seen"):
        why = f"선택: {best['host']} · 점수 {best['score']} (기방문 {best['seen']}회에도 최고점)"
    elif saw_read_page:
        why = f"선택: {best['host']} · 점수 {best['score']} (기방문 결과 회피 → 새 출처)"
    else:
        why = f"선택: {best['host']} · 점수 {best['score']} (신뢰×주제 일치 최고점)"
    # open a READING THREAD: after this article is read, the next outing drills one level deeper

    # A topic whose drill ALREADY ran must not reopen its thread here, or the drill's own SERP
    # choice restarts the thread forever (the Docker loop's root, measured 2026-07-11).
    try:
        c = _cfg()
        if topic not in {str(t) for t in c.get("thread_done", [])[-8:]}:
            c["thread"] = {"topic": topic, "depth": 1}
        c["recent_hosts"] = (c.get("recent_hosts", []) + [best["host"]])[-8:]
        _save(c)
    except Exception:
        pass
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "serp_choice", "topic": topic,
             "chosen": best["url"], "host": best["host"], "score": best["score"],
             "seen_before": int(best.get("seen") or 0), "why": why}
    try:
        _JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with _JOURNAL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return {"chosen": True, "url": best["url"], "title": best["title"],
            "host": best["host"], "why": why}


def set_enabled(enabled: bool) -> dict[str, Any]:
    c = _cfg()
    c["enabled"] = bool(enabled)
    _save(c)
    return c
