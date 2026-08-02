# -*- coding: utf-8 -*-
"""Conversation flywheel — the data engine every LEARNED component feeds on.

An LLM improves by gradient descent on prediction error at scale. ATANOR's
equivalent is this loop: log every real turn, MINE the failures (abstentions,
re-asks, corrections), and turn them into (a) battery cases that keep us honest
and (b) training rows for the learned router / phase space / discourse model.

Failure signals (all measured from the log itself, no human labeling):
 abstain — the engine said it lacked evidence
 re-ask — the next user turn repeats the same content terms (the previous
 answer did not satisfy; the strongest implicit failure signal)
 correction — the next user turn opens with a correction marker (/
 /// )

Privacy: local JSONL under data/flywheel/, never leaves the machine — the same
local-first contract as the rest of the brain.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
FLYWHEEL_DIR = REPO / "data" / "flywheel"
TURNS_PATH = FLYWHEEL_DIR / "turns.jsonl"
FAILURES_PATH = FLYWHEEL_DIR / "failures.jsonl"
UNREAD_PATH = FLYWHEEL_DIR / "unread.jsonl"

# questions already turned into a gap-receipt this process — avoid re-recording the same abstain
# every time mine_failures runs (the receipt ledger is bounded, but this keeps it clean)
_receipted: set[str] = set()

_ABSTAIN_MARKERS = ("근거가 부족", "단정하기 어렵", "확인 가능한 근거", "지어내지 않",
                    "not have enough", "실시간 근거")
_CORRECTION_RE = re.compile(r"^\s*(아니|그게 아니|아니라|틀렸|다시|무슨 소리|엉뚱|뭐라는)")


def log_turn(question: str, answer: str, answer_kind: str = "", confidence: float = 0.0,
             latency_ms: int = 0, language: str = "", context_len: int = 0,
             lane: str = "", router_pred: str = "", router_conf: float = 0.0,
             gold_intent: str = "") -> None:
    """Append one turn. Best-effort by contract: a logging failure must never
    touch the chat path. `lane` is the rule lane that actually fired; `router_pred`
    is the learned router's SHADOW prediction; `gold_intent` is the authoritative
    intent in the ROUTER's OWN vocabulary (query_frame.answer_type) — so
    router-vs-gold agreement is measurable and promotion can finally be judged."""
    try:
        FLYWHEEL_DIR.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "q": (question or "")[:500],
            "a": (answer or "")[:500],
            "kind": answer_kind, "conf": round(float(confidence or 0.0), 3),
            "ms": int(latency_ms), "lang": language, "ctx": int(context_len),
            "lane": lane, "router": router_pred, "router_conf": round(float(router_conf or 0.0), 3),
            "gold_intent": gold_intent,
        }
        with TURNS_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def log_unread(question: str, reason: str, *, organ: str = "", detail: str = "") -> None:
    """Record a question a reader recognised as its KIND but could not represent.

    This is the curriculum lane, and it is deliberately distinct from `failures.jsonl`. A failure
    is "I tried and got it wrong or abstained". An unread is "I could not even form the question" --
    which is the only signal that says what the representation is missing, as opposed to what the
    knowledge is missing.

    The scene composer is the first producer: it returns the reason a question did not compose
    (no readout marker, no span naming a relation the graph uses, a qualifier with nowhere to
    bind). Those reasons ARE the widening curriculum -- without them the "training wheels come off
    by measurement" plan has no data, and the composer can only ever read the shapes it was born
    reading.

    Best-effort by the same contract as `log_turn`: a logging failure must never touch the chat
    path."""
    try:
        FLYWHEEL_DIR.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "q": (question or "")[:500],
            "reason": (reason or "")[:200],
            "organ": organ,
            "detail": (detail or "")[:200],
        }
        with UNREAD_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def unread_curriculum(limit: int = 50) -> list[dict[str, Any]]:
    """Unread reasons ranked by how often they blocked a real question.

    What to widen next is not a judgement call -- it is whichever reason appears most in live
    traffic. Returned as data so the decision stays external to the composer."""
    counts: dict[tuple[str, str], int] = {}
    samples: dict[tuple[str, str], str] = {}
    try:
        for line in UNREAD_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            key = (str(r.get("organ", "")), str(r.get("reason", "")))
            counts[key] = counts.get(key, 0) + 1
            samples.setdefault(key, str(r.get("q", "")))
    except OSError:
        return []
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return [{"organ": k[0], "reason": k[1], "count": n, "example": samples.get(k, "")}
            for k, n in ranked]


def _content_terms(text: str) -> set[str]:
    return {t for t in re.findall(r"[가-힣A-Za-z0-9]{2,}", text or "")
            if t not in ("그럼", "그리고", "그런데", "혹시", "좀", "제발")}


def _is_abstain(answer: str) -> bool:
    return any(m in (answer or "") for m in _ABSTAIN_MARKERS)


def mine_failures(limit: int = 5000) -> dict[str, Any]:
    """Scan the turn log for failure signals. Returns counters and writes the
    mined cases (deduped by question) to failures.jsonl — the seed corpus for
    battery generation and router retraining."""
    counters = {"turns": 0, "abstain": 0, "re_ask": 0, "correction": 0, "mined": 0}
    if not TURNS_PATH.exists():
        return counters
    rows: list[dict[str, Any]] = []
    with TURNS_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    rows = rows[-limit:]
    counters["turns"] = len(rows)
    seen: set[str] = set()
    if FAILURES_PATH.exists():
        with FAILURES_PATH.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    seen.add(json.loads(line).get("q", ""))
                except Exception:
                    continue
    mined: list[dict[str, Any]] = []

    def _mine(row: dict[str, Any], signal: str) -> None:
        q = row.get("q", "")
        if q and q not in seen:
            seen.add(q)
            mined.append({"q": q, "signal": signal, "kind": row.get("kind", ""),
                          "lane": row.get("lane", ""), "router": row.get("router", ""),
                          "ts": row.get("ts", "")})

    from packages.flywheel.failure_receipts import record_receipt

    for i, row in enumerate(rows):
        if _is_abstain(row.get("a", "")):
            counters["abstain"] += 1
            _mine(row, "abstain")
            # an abstain is a knowledge GAP → a receipt that steers the learner TOWARD this
            # topic (its longest content term as a coarse domain proxy). Deduped like _mine.
            terms = sorted(_content_terms(row.get("q", "")), key=len, reverse=True)
            if terms and row.get("q", "") not in _receipted:
                _receipted.add(row.get("q", ""))
                record_receipt(topic=terms[0], causes=["abstain"], source="flywheel", kind="gap")
        if i + 1 < len(rows):
            nxt = rows[i + 1]
            nq = str(nxt.get("q") or "")
            if _CORRECTION_RE.match(nq):
                counters["correction"] += 1
                _mine(row, "correction")
            else:
                cur, follow = _content_terms(row.get("q", "")), _content_terms(nq)

                # (the question word differs) — that IS the canonical re-ask shape
                if cur and follow and len(cur & follow) / max(1, len(cur)) >= 0.5 \
                        and nq != row.get("q"):
                    counters["re_ask"] += 1
                    _mine(row, "re_ask")
    if mined:
        FLYWHEEL_DIR.mkdir(parents=True, exist_ok=True)
        with FAILURES_PATH.open("a", encoding="utf-8") as fh:
            for m in mined:
                fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    counters["mined"] = len(mined)
    return counters


def flywheel_stats() -> dict[str, Any]:
    """Live counters for the dashboard: volume, abstain rate, router agreement."""
    out = {"turns": 0, "abstains": 0, "router_disagreements": 0, "failures_mined": 0}
    try:
        if TURNS_PATH.exists():
            with TURNS_PATH.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    out["turns"] += 1
                    if _is_abstain(row.get("a", "")):
                        out["abstains"] += 1
                    if row.get("router") and row.get("lane") and row["router"] != row["lane"]:
                        out["router_disagreements"] += 1
        if FAILURES_PATH.exists():
            out["failures_mined"] = sum(1 for _ in FAILURES_PATH.open(encoding="utf-8"))
    except Exception:
        pass
    return out
