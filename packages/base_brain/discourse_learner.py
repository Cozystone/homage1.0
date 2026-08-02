# -*- coding: utf-8 -*-
"""Discourse learner — the AI learns how humans WRITE from real text, not from us.

Owner (2026-07-10, Vision roadmap #1): our realizer sounds like a dictionary because its
'flesh' was hand-authored + trained on definition sentences. The fix is not more templates
(that is just more rules) — it is to LEARN discourse from REAL prose the AI has read, and
keep learning as it reads more. Facts are never taken from here (no fabrication); only the
STYLE of connection is — how humans fuse clauses (~/~/~), refer back (' '
instead of repeating the subject), and vary sentence endings, instead of the robotic
',… ,… ,' enumeration.

Source = the real Korean prose the AI itself ingested (web_fact_memory + any text corpus),
so the profile GROWS as the AI reads — real-data, autonomous, auditable. Output is a small
statistical DISCOURSE PROFILE the realizer consults; it changes STYLE, never content.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
_WEB_MEMORY = REPO / "runtime" / "local_brain" / "web_fact_memory.json"
_PROFILE = REPO / "data" / "surface_brain" / "discourse_profile.json"
# CONVERSATIONAL prose the register lane harvested from pages where people write TO each other.
# This is the corpus the VOICE needs; web_fact_memory is fact EXTRACTION, so its prose is
# encyclopedic by construction — learning "how to talk" from a fact DB is exactly why the voice

_REGISTER_BANK = REPO / "data" / "register_bank" / "comfort_patterns.jsonl"
_DISCOURSE_PAIRS = REPO / "data" / "register_bank" / "discourse_pairs.jsonl"

# clause-fusion / cohesion markers that make prose FLOW instead of listing — the signal we
# want to learn the frequency of from real writing.
_SUBORD = ("으로써", "면서", "으며", "이며", "하며", "되며", "는데", "은데", "아서", "어서",
           "고서", "하여", "으로서", "라서", "지만", "거나", "든지")
_REFERENCE = ("이 ", "이는", "그 ", "그는", "해당", "이러한", "그러한", "이곳", "그곳", "이때")
_ENDINGS = ("이다", "된다", "한다", "있다", "없다", "었다", "된다", "이었다", "라고", "이라고",
            "예요", "이에요", "해요", "이죠", "죠", "습니다", "합니다", "됩니다")


def _sentences(text: str) -> list[str]:
    out = []
    for s in re.split(r"(?<=[.!?다요])\s+", str(text or "")):
        s = s.strip()
        if 15 <= len(s) <= 140 and sum(1 for c in s if "가" <= c <= "힣") > len(s) * 0.5:
            out.append(s)
    return out


def harvest_web_prose(limit: int = 4000) -> list[str]:
    """Real Korean prose the AI has read (never definitions — natural web writing)."""
    if not _WEB_MEMORY.exists():
        return []
    try:
        data = json.loads(_WEB_MEMORY.read_text(encoding="utf-8"))
    except Exception:
        return []
    vals: list[str] = []

    def _walk(x: Any) -> None:
        if isinstance(x, dict):
            v = x.get("value")
            if isinstance(v, str):
                vals.append(v)
            for vv in x.values():
                _walk(vv)
        elif isinstance(x, list):
            for vv in x:
                _walk(vv)

    _walk(data)
    sents: list[str] = []
    for v in vals:
        sents.extend(_sentences(v))
        if len(sents) >= limit:
            break
    return sents


def harvest_conversational_prose(limit: int = 4000) -> list[str]:
    """Prose from pages where people write TO each other, banked by the register lane.

    This is the register the VOICE needs. It is kept separate from harvest_web_prose() on
    purpose: that one reads web_fact_memory, i.e. FACT EXTRACTION output, whose prose is
    encyclopedic by construction. Style must be learned from talk, facts from facts.
    """
    sents: list[str] = []
    for path, field in ((_REGISTER_BANK, "pattern"), (_DISCOURSE_PAIRS, "reply")):
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = row.get(field) or row.get("pattern") or row.get("text") or ""
                if isinstance(text, str) and text.strip():
                    sents.extend(_sentences(text))
                if len(sents) >= limit:
                    return sents[:limit]
        except OSError:
            continue
    return sents[:limit]


def learn(sentences: list[str] | None = None) -> dict[str, Any]:
    """Build a statistical discourse profile from real prose. Style stats only, no content.

    Sources, in order of what the voice should sound like: harvested CONVERSATION first, then
    web prose. Before this the profile came only from web_fact_memory and the voice learned to
    talk like an encyclopedia (measured 2026-07-17); the mix is reported so the corpus
    composition is auditable rather than assumed.
    """
    if sentences is not None:
        sents, talk_n = sentences, 0
    else:
        talk = harvest_conversational_prose()
        sents, talk_n = talk + harvest_web_prose(), len(talk)
    if len(sents) < 10:
        return {"learned": 0, "reason": "not enough real prose read yet"}
    endings: Counter = Counter()
    subord = 0
    reference = 0
    lengths: list[int] = []
    for s in sents:
        lengths.append(len(s))
        for e in _ENDINGS:
            if s.rstrip(" .!?").endswith(e):
                endings[e] += 1
                break
        if any(m in s for m in _SUBORD):
            subord += 1
        if any(s.startswith(m) or (" " + m) in s for m in _REFERENCE):
            reference += 1
    n = len(sents)
    profile = {
        "n_sentences": n,
        # corpus composition, measured not assumed ([[corpus-composition-is-the-bottleneck]]):
        # conversational share is the number to grow — a voice can only speak the register it read.
        "conversational_sentences": talk_n,
        "conversational_share": round(talk_n / n, 3),
        "mean_len": round(sum(lengths) / n, 1),
        # what fraction of real sentences FUSE clauses / refer back — the flow signals our
        # list-y realizer lacks. A realizer matching these reads like prose, not a glossary.
        "subordination_rate": round(subord / n, 3),
        "reference_rate": round(reference / n, 3),
        "ending_distribution": dict(endings.most_common(10)),
        "top_endings": [e for e, _c in endings.most_common(5)],
    }
    _PROFILE.parent.mkdir(parents=True, exist_ok=True)
    _PROFILE.write_text(json.dumps(profile, ensure_ascii=False, indent=1), encoding="utf-8")
    profile["learned"] = n
    return profile


_CACHE: dict[str, Any] = {"p": None, "mtime": 0.0}


def profile() -> dict[str, Any]:
    """The learned discourse profile (cached by mtime); {} until the AI has read real prose."""
    try:
        if not _PROFILE.exists():
            return {}
        m = _PROFILE.stat().st_mtime
        if _CACHE["p"] is None or _CACHE["mtime"] != m:
            _CACHE["p"] = json.loads(_PROFILE.read_text(encoding="utf-8"))
            _CACHE["mtime"] = m
        return _CACHE["p"] or {}
    except Exception:
        return {}


def prefers_flowing_prose(min_evidence: int = 30) -> bool:
    """True when the AI has read enough real prose to know humans FUSE clauses more than they
 ENUMERATE — the realizer uses this to drop the robotic '//' monotony."""
    p = profile()
    return bool(p and p.get("n_sentences", 0) >= min_evidence
                and float(p.get("subordination_rate", 0)) >= 0.25)
