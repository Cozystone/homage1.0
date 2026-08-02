# -*- coding: utf-8 -*-
"""Dialogue-pair consumption — the harvested turn-taking becomes a voice, consensus-gated.

youtube_learn stores (comment -> reply) pairs: how real people actually answer each other, with
the video topic as context. This module is the READ side: given a user utterance, find pairs
whose opening (q) resonates with it and offer the reply (r) as a response skeleton.

Doctrine (same as facts and comfort register): ONE stranger's reply is never spoken. A reply
surface is usable only when its normalized form was harvested from >= MIN_SOURCES distinct
sources (different videos/domains) — a way-people-answer, not a person's answer. Safety floor
re-checked at read time; the store only ever holds scrubbed, capped fragments.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_PAIRS = _ROOT / "data" / "register_bank" / "discourse_pairs.jsonl"
MIN_SOURCES = 2

_TOKEN = re.compile(r"[가-힣]{2,}")


def _norm(s: str) -> str:
    return re.sub(r"[\s.,!?~…'\"·;]+", "", s or "")


def _tokens(s: str) -> set[str]:
    return set(_TOKEN.findall(s or ""))


def _load() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for ln in _PAIRS.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    except Exception:
        pass
    return rows


def reply_for(message: str, *, min_overlap: int = 2) -> dict[str, Any] | None:
    """A consensus-backed reply skeleton for `message`, or None. Resonance = shared content
    tokens between the message and a pair's opening; the chosen reply's normalized surface must
    appear across >= MIN_SOURCES distinct sources."""
    msg_toks = _tokens(message)
    if len(msg_toks) < 1:
        return None
    rows = _load()
    if not rows:
        return None
    # consensus index: normalized reply -> distinct sources that used it
    sources: dict[str, set[str]] = {}
    for r in rows:
        sources.setdefault(_norm(r.get("r", "")), set()).add(str(r.get("src") or "?"))
    try:
        from packages.autonomy_kernel.register_harvest import _SAFETY_REJECT
    except Exception:
        _SAFETY_REJECT = re.compile(r"$^")
    best: tuple[int, dict[str, Any]] | None = None
    for r in rows:
        q = str(r.get("q") or "")
        reply = str(r.get("r") or "")
        if not reply or _SAFETY_REJECT.search(reply):
            continue
        if len(sources.get(_norm(reply), set())) < MIN_SOURCES:
            continue                      # one stranger's words — not yet a way-people-answer
        overlap = len(msg_toks & _tokens(q))
        if overlap >= min_overlap and (best is None or overlap > best[0]):
            best = (overlap, r)
    if best is None:
        return None
    _n, row = best
    return {"reply": str(row.get("r")), "context": str(row.get("context") or ""),
            "overlap": _n, "sources": len(sources.get(_norm(str(row.get("r"))), set())),
            "kind": "learned_dialogue_pair"}


def pairs_status() -> dict[str, Any]:
    rows = _load()
    sources: dict[str, set[str]] = {}
    for r in rows:
        sources.setdefault(_norm(r.get("r", "")), set()).add(str(r.get("src") or "?"))
    usable = sum(1 for ds in sources.values() if len(ds) >= MIN_SOURCES)
    return {"pairs": len(rows), "distinct_replies": len(sources),
            "usable_consensus": usable, "min_sources": MIN_SOURCES}
