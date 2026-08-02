# -*- coding: utf-8 -*-
"""Read-only resolver for the data-derived ACT lexicons (data/graph_scale/act_lexicon.json, built by
scripts/build_act_lexicon.py from Wiktionary/Kaikki glosses).

Same sidecar discipline as qid_labels / primary_gloss: the graph is never touched, an mtime check
reloads on change, and deleting the file falls back to the hand patterns in semantic_frame.

The point is generalisation. A hand list cannot enumerate 'howdy / hiya / cheers' or 'knackered /
elated / chuffed / livid'; the dictionary can, and it does so INDEPENDENTLY of the sealed C1
battery, so coverage gained here is real rather than tuned to the test."""
from __future__ import annotations

import json
import re
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "act_lexicon.json"
_S: dict[str, object] = {"mtime": 0.0, "greeting": frozenset(), "emotion": frozenset()}
_TOKEN = re.compile(r"[a-z][a-z'\-]*", re.IGNORECASE)
# a finite verb means the utterance predicates something — 'Morning routines ARE important' is a
# statement, not the phatic 'Morning!'
_FINITE = re.compile(r"\b(is|are|was|were|has|have|had|do|does|did|will|would|can|could|should)\b",
                     re.IGNORECASE)
# experiencer frame: the speaker reporting their own state
_EXPERIENCER = re.compile(r"\b(i'?m|i\s+am|i\s+feel|i'?ve\s+been|i\s+was|i\s+get|feeling)\b",
                          re.IGNORECASE)


def _load() -> None:
    try:
        mt = _PATH.stat().st_mtime
    except OSError:
        return
    if mt != _S["mtime"]:
        try:
            d = json.loads(_PATH.read_text(encoding="utf-8"))
            _S["greeting"] = frozenset(d.get("greeting") or ())
            _S["emotion"] = frozenset(d.get("emotion") or ())
            _S["mtime"] = mt
        except Exception:
            pass


def available() -> bool:
    _load()
    return bool(_S["greeting"] or _S["emotion"])


def is_greeting(text: str) -> bool:
    """True when the utterance OPENS with a dictionary-attested greeting/farewell/thanks word and
    reads as phatic — short and predicating nothing. 'Howdy' / 'Cheers' / 'Morning!' yes;
    'Morning routines are important' no."""
    _load()
    toks = _TOKEN.findall(str(text or ""))
    if not toks or len(toks) > 4 or _FINITE.search(str(text or "")):
        return False
    return toks[0].lower() in _S["greeting"]  # type: ignore[operator]


def is_affect(text: str) -> bool:
    """True when the speaker frames their OWN state ('I'm …', 'I feel …') and a dictionary-attested
    emotion word follows close by. The experiencer frame is what keeps a topic statement ('coffee is
    bad') from reading as the speaker's feelings."""
    _load()
    s = str(text or "")
    m = _EXPERIENCER.search(s)
    if not m:
        return False
    tail = s[m.end():m.end() + 60]
    emo = _S["emotion"]  # type: ignore[assignment]
    return any(t.lower() in emo for t in _TOKEN.findall(tail))
