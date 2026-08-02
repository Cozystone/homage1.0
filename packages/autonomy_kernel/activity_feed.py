# -*- coding: utf-8 -*-
"""Activity feed — a live, unified view of what ATANOR is doing right now.

Owner (2026-07-10): " Ato , AI 
 ." Borrowing the Observer pattern (poll local state → display), this aggregates ATANOR's
autonomy journals into one feed the orb overlay reads. Read-only; exposes only what already happened.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
_DATA = REPO / "data" / "autonomy"

# each journal → (path, how to summarize one entry into a human one-liner)
_SOURCES: list[tuple[str, str]] = [
    ("expedition_journal.jsonl", "web"),
    ("moltbook_conversation.jsonl", "talk"),
    ("browse_director.jsonl", "surf"),
    ("intrinsic_drive.jsonl", "drive"),
    ("moltbook_autopilot.jsonl", "post"),
    ("monologue.jsonl", "monologue"),
]


def _tail(path: Path, n: int) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-n:]
        return [json.loads(x) for x in lines if x.strip()]
    except Exception:
        return []


def _summ(kind: str, e: dict[str, Any]) -> str:
    if kind == "web":
        if e.get("kind") == "page_ingest":
            return f"페이지 읽음: {e.get('domain', '')}" + (" (주입 차단)" if e.get("injection_blocked") else "")
        return f"웹 원정: {e.get('topic', '')} (합의 {e.get('consensus_backed', 0)})"
    if kind == "talk":
        return f"대화 학습: {e.get('learned', 0)}건 배움, {e.get('replied', 0)}건 답글"
    if kind == "surf":
        return f"자율 서핑: {e.get('topic', '')} 읽는 중"
    if kind == "drive":
        return f"내적 동기: {e.get('action', '')} — {e.get('reason', '')}"
    if kind == "post":
        return f"자율 게시: {str(e.get('title', ''))[:40]}" if e.get("published") else "게시 대기(언어 여물면)"
    if kind == "monologue":
        return f"내부 독백: {e.get('accepted', 0)}문장 검증 통과 ({e.get('topic', '')})"
    return json.dumps(e, ensure_ascii=False)[:80]


def _ticker(kind: str, e: dict[str, Any]) -> str:
    """INSTRUMENT PANEL, not speech (owner 2026-07-11: authored first-person molds are the same
 template disease — " "). This line shows
 the raw decision variables of the freshest real event — labels and numbers only, no polite
 endings pretending to be a voice. The VOICE is `_voice` below: generated or silent."""
    if kind == "web":
        if e.get("kind") == "page_ingest":
            bits = [f"읽기: {e.get('domain', '?')}", f"문장 {int(e.get('sentences', 0) or 0)}"]
            cons = [c for c in (e.get("top_concepts") or []) if c][:2]
            if cons:
                bits.append("최다 " + "·".join(str(c) for c in cons))
            if e.get("revisit"):
                bits.append("재방문")
            if e.get("answer_found"):
                bits.append("답 문장 확보")
            return " · ".join(bits)
        return f"웹 원정: {e.get('topic', '')} · 합의 {int(e.get('consensus_backed', 0) or 0)}"
    if kind == "talk":
        return f"Moltbook: 내 글 {int(e.get('posts', 0) or 0)} · 배움 {int(e.get('learned', 0) or 0)}"
    if kind == "surf":
        if e.get("kind") == "serp_choice":
            return f"선택: {e.get('host', '?')} · 점수 {e.get('score', '?')} · 기방문 {int(e.get('seen_before', 0) or 0)}회"
        return f"탐색: {e.get('topic', '')} · {e.get('mode', '')}"
    if kind == "drive":
        return f"내적 동기: {e.get('action', '')}"
    if kind == "post":
        return "게시 검토"
    if kind == "monologue":
        return f"독백 자기검증: {int(e.get('accepted', 0) or 0)}문장 통과"
    return "대기"


# the voice is FORMED OFF the poll path: realize_thought's first fit is seconds-cold, and the
# orb polls every 3.5s — a synchronous call froze /activity (measured 20s+ timeout, 2026-07-11).
# While the line is still forming, the channel stays silent — which the contract allows.
_VOICE_STATE: dict[str, Any] = {"key": "", "line": None, "busy": False, "at": 0.0}
_VOICE_TTL_S = 45.0

                      # bubble falls back to the live ticker, which visibly moves.


def _voice_async(kind: str, e: dict[str, Any]) -> str | None:
    key = f"{kind}|{e.get('at', '')}|{e.get('topic', '')}"
    st = _VOICE_STATE
    if st["key"] == key:
        if st["line"] and time.time() - float(st.get("at") or 0) > _VOICE_TTL_S:
            return None   # said it already; let the instrument panel breathe
        return st["line"]
    if not st["busy"]:
        st["busy"] = True

        def _work() -> None:
            line = None
            try:
                line = _voice(kind, e)
            except Exception:
                line = None
            st["key"], st["line"], st["at"], st["busy"] = key, line, time.time(), False

        import threading
        threading.Thread(target=_work, name="voice-former", daemon=True).start()
    return None


import re as _re

_JUNK_MARKS = ("배송", "쿠폰", "특가", "무료", "구매", "링크", "클릭", "!!", "·")


def _speakable(line: str) -> bool:
    """Surface sanity for the MOUTH: the LM's diet still contains web debris (measured live
 2026-07-11: '6 9 4 in 24 cm single turret guns…' + ad spam). A line only leaves the
 mouth if it reads as one Korean sentence — otherwise silence. This is a fluency gate on the
 self's own output, not an authored script."""
    t = (line or "").strip()
    if not (12 <= len(t) <= 120):
        return False
    hangul = sum(1 for ch in t if "가" <= ch <= "힣")
    if hangul / max(1, len(t.replace(" ", ""))) < 0.6:
        return False
    if any(m in t for m in _JUNK_MARKS):
        return False
    if _re.search(r"\d\s+\d", t) or _re.search(r"[A-Za-z]{4,}\s+[A-Za-z]{4,}", t):
        return False   # broken digit runs / raw foreign phrases = corpus debris, not speech
    return bool(_re.search(r"(다|요|죠|네|까)\s*[.!?…]?$", t))


def _voice(kind: str, e: dict[str, Any]) -> str | None:
    """The self's OWN MOUTH: a line realized by the language engine from its accumulated corpus
 (realize_thought → None when it holds too little language — silence is honest and allowed,
 owner: " "). One verbatim page
 quote may ride along (sourced text, marked as a quote — not authoring)."""
    topic = str(e.get("topic") or e.get("domain") or "").strip()

    # topic word without its surrounding concepts pulls random definitional corpus, so the mouth
    # spoke an encyclopedia line about PEOPLE on a software page). No measured concepts → silence.
    cons = [str(c) for c in (e.get("top_concepts") or []) if c]
    if not (topic and cons):
        return None
    driver = {"web": "learning_active", "surf": "curiosity_idle", "talk": "user_present",
              "monologue": "open_self_question"}.get(kind, "idle")
    try:
        from packages.continuous_self.thought_language import realize_thought
        line = realize_thought(driver, {"topic": topic[:16], "context": cons[:6]}, None)
    except Exception:
        line = None
    if line and _speakable(line):

        # live) — a clean-surfaced line whose specific words share nothing with the page's
        # measured concepts stays unsaid.
        try:
            from packages.autonomy_kernel.web_expedition import _topic_coherent
            if not _topic_coherent(line, topic, cons):
                return None
        except Exception:
            pass
        q = str(e.get("answer_found") or "").strip()
        if q:
            line += f" 방금 이 문장을 찾았어요 — “{q[:70]}”"
        return line
    return None


def _breathing_ticker() -> str | None:
    """Between-actions state as INSTRUMENTATION (never authored prose — the earlier ' N
 …' mold was the template disease in a new coat, owner 2026-07-11): the live pacing
 variables, shown raw."""
    try:
        from packages.autonomy_kernel.browse_director import _MIN_INTERVAL_S, _cfg
        c = _cfg()
        if not c.get("enabled"):
            return None
        remain = int(_MIN_INTERVAL_S - (time.time() - float(c.get("last_nav_at", 0) or 0)))
        if remain > 3:
            thread = c.get("thread") or {}
            tail = f" · 드릴 대기: {thread['topic']}" if thread.get("topic") else ""
            return f"다음 나들이 T-{remain}s{tail}"
    except Exception:
        pass
    return None


def feed(limit: int = 12) -> dict[str, Any]:
    """Unified recent activity, split into two honest channels (owner 2026-07-11):
    `ticker` — the instrument panel: raw decision variables of the freshest real event, always on;
    `voice`  — the self's own generated line (realize_thought), or None: silence over molds."""
    items: list[dict[str, Any]] = []
    fresh: dict[str, Any] | None = None
    for fname, kind in _SOURCES:
        tail = _tail(_DATA / fname, 6)
        for e in tail:
            items.append({"at": str(e.get("at", "")), "kind": kind, "summary": _summ(kind, e)})
        if tail:
            cand = {"at": str(tail[-1].get("at", "")), "kind": kind, "e": tail[-1]}
            if fresh is None or cand["at"] > fresh["at"]:
                fresh = cand
    items.sort(key=lambda x: x["at"], reverse=True)
    items = items[:limit]
    ticker = _breathing_ticker() or (_ticker(fresh["kind"], fresh["e"]) if fresh else "대기")
    voice = _voice_async(fresh["kind"], fresh["e"]) if fresh else None
    return {
        "current": items[0]["summary"] if items else "대기",
        "current_kind": fresh["kind"] if fresh else "idle",
        "ticker": ticker,
        "voice": voice,
        # compat fields for pre-0.8.3 orbs: never authored prose — voice or the raw panel
        "intention": voice or ticker,
        "monologue": voice or ticker,
        "recent": items,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
