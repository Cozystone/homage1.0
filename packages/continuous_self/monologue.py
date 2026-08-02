# -*- coding: utf-8 -*-
"""Inner monologue self-play — the voice practices ALONE before it ever speaks outside.

Owner (2026-07-10): " Self-Play ( ): , 
 
 ."

The loop, all reused machinery (nothing hand-authored):
 1. pick a topic the self is currently living with (frontier / recent narrative);
 2. SPEAK — realize_thought generates a line from the graph's own language (HolographicLM);
 3. JUDGE — speech_selfplay.critique gates it: every content clause must trace to the graph's
 themed corpus for that topic (faithfulness = the contradiction/grounding gate, HARD) and
 the phrasing must be fluent;
 4. KEEP — an accepted line joins the narrative corpus (source="monologue"), which future
 realize_thought fits include — so each accepted sentence genuinely refines the LM's token
 connectivity. For a fit-based LM, corpus growth IS weight refinement.

Sandbox-only: this NEVER posts, replies, or writes facts anywhere — it journals and grows the
voice. Kill switch + rate floor like every autonomy lane.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
_STATE = REPO / "runtime" / "autonomy" / "monologue.json"
_JOURNAL = REPO / "data" / "autonomy" / "monologue.jsonl"

_MIN_INTERVAL_S = 120.0

_ACCEPT_SCORE = 0.45
_MAX_TOPICS_PER_TICK = 4


def _cfg() -> dict[str, Any]:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        # internal, sandboxed, side-effect-free → on by default (unlike the posting lanes)
        return {"enabled": True, "last_at": 0.0}


def _save(c: dict[str, Any]) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _journal_write(entry: dict[str, Any]) -> None:
    try:
        _JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with _JOURNAL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _topics(state: Any) -> list[str]:
    """What the self is CURRENTLY living with: topics from its recent narrative first (that's
    where its attention actually is), the graph frontier as the outward pull."""
    out: list[str] = []
    try:
        import re
        josa_tail = ("은", "는", "이", "가", "을", "를", "과", "와", "의", "도", "에", "로", "만")
        for entry in (getattr(state, "narrative", []) or [])[-12:]:
            text = str((entry or {}).get("text") or "")
            for tok in re.findall(r"[가-힣]{2,6}", text)[:3]:
                if len(tok) >= 3 and tok[-1] in josa_tail:
                    tok = tok[:-1]
                if tok not in out:
                    out.append(tok)
    except Exception:
        pass
    try:
        from app.routers.cloud_brain import _frontier_topics
        for t in (_frontier_topics(3) or []):
            if str(t) not in out:
                out.append(str(t))
    except Exception:
        pass
    return out[:8] or ["지식"]


def monologue_tick(state: Any, *, now: float | None = None) -> dict[str, Any]:
    """One practice round: speak a few lines inward, keep what survives the gates."""
    now = now if now is not None else time.time()
    c = _cfg()
    if not c.get("enabled", True):
        return {"acted": False, "reason": "disabled"}
    if now - float(c.get("last_at", 0)) < _MIN_INTERVAL_S:
        return {"acted": False, "reason": "rate_floor"}
    c["last_at"] = now
    _save(c)

    from packages.continuous_self.thought_language import realize_thought

    ticks = int(getattr(state, "ticks", 0) or 0)
    topics = _topics(state)
    tried = 0
    accepted: list[dict[str, Any]] = []
    for i in range(min(_MAX_TOPICS_PER_TICK, len(topics))):
        topic = topics[(ticks + i) % len(topics)]
        line = realize_thought("monologue", {"topic": topic}, state)
        if not line:
            continue  # honest silence: the self holds too little language here (that's the signal
        tried += 1    # the corpus miners exist to fix)
        # the contradiction/grounding gate: every content clause must trace to the graph's own
        # language about this topic; fluency scored on top (all reused Critic machinery).
        facts: list[str] = []
        try:
            from packages.grounded_composer.creative_composer import _themed_corpus
            themed, _s, _c = _themed_corpus(topic)
            facts = (themed or [])[:40]
        except Exception:
            pass
        try:
            from packages.base_brain.speech_selfplay import critique
            verdict = critique(line, facts)
        except Exception:
            verdict = {"total": 0.0, "faithful": False}
        if verdict.get("faithful") and float(verdict.get("total", 0)) >= _ACCEPT_SCORE:
            accepted.append({"topic": topic, "line": line, "score": verdict.get("total")})
            try:
                from packages.autonomy_kernel import narrative_corpus
                narrative_corpus.add_lines([line], source="monologue")
            except Exception:
                pass

    best = accepted[0] if accepted else {}
    _journal_write({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "tried": tried,
                    "accepted": len(accepted), "topic": str(best.get("topic") or topics[0]),
                    "line": str(best.get("line") or ""), "score": best.get("score")})
    return {"acted": True, "tried": tried, "accepted": len(accepted),
            "lines": [a["line"] for a in accepted]}
