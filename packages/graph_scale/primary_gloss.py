# -*- coding: utf-8 -*-
"""Read-only resolver for the dominant-sense DEFINITION sidecar (data/graph_scale/primary_gloss.jsonl,
built by scripts/build_primary_gloss_sidecar.py). Same discipline as qid_labels: the graph is never
touched, an mtime check reloads if the file changes, and deleting the file reverts the behaviour.

`primary(word)` returns the word's PRIMARY (Kaikki sense-1) gloss, or None. The answer path prefers
this over the store's many competing senses, so 'coffee' surfaces the beverage — not the coffee
table, not 'eye color'."""
from __future__ import annotations

import json
from pathlib import Path

_DIR = Path(__file__).resolve().parents[2] / "data" / "graph_scale"
_PATH = _DIR / "primary_gloss.jsonl"
_S: dict[str, object] = {"mtime": 0.0, "map": {}}


def _load() -> dict[str, str]:
    try:
        mt = _PATH.stat().st_mtime
    except OSError:
        _S["map"] = {}
        return _S["map"]  # type: ignore[return-value]
    if mt != _S["mtime"]:
        m: dict[str, str] = {}
        try:
            with _PATH.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    w, g = r.get("word"), r.get("gloss")
                    # Key by the EXACT headword only. NO case-folding into the map: the common noun
                    # 'coffee' (beverage) and the proper noun 'Coffee' (a surname) are distinct
                    # headwords, and folding them lets the later one clobber the earlier (that made
                    # 'coffee' resolve to "A surname"). Case is reconciled at lookup instead.
                    if w and g and str(w) not in m:
                        m[str(w)] = str(g)
        except OSError:
            m = {}
        _S["map"], _S["mtime"] = m, mt
    return _S["map"]  # type: ignore[return-value]


def primary(word: str) -> str | None:
    """The word's dominant-sense (Kaikki sense-1) gloss, or None when the sidecar has no entry. A
    query subject is normally lower-case; we try it verbatim, then the all-lower and Title forms so
    'Coffee' still finds 'coffee' — but a lower-case query never picks up a proper-noun-only entry."""
    if not word:
        return None
    m = _load()
    w = str(word)
    return m.get(w) or m.get(w.lower()) or (m.get(w.capitalize()) if w.islower() else None)


def available() -> bool:
    return bool(_load())
