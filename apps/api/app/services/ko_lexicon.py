"""Relational lexicon loader — keeps antonym/causal-verb lists OUT of reasoner code.

The reasoners used to hard-code these lists. That is exactly the "knowledge/lexicon belongs in
data the system owns, not in code" rule. This module makes `data/lexicon/ko_relation_lexicon.json`
the authoritative, extensible source: the learner (or an external lexical resource like
Wiktionary ) can grow it via add_antonym / add_causal_verb, and it persists. A tiny code
seed remains only as an emergency fallback if the file is unreadable.
"""
from __future__ import annotations

import json
import pathlib
import threading
from typing import Any

_PATH = pathlib.Path(__file__).resolve().parents[4] / "data" / "lexicon" / "ko_relation_lexicon.json"

# Emergency fallback only — the JSON is the real source. Kept minimal on purpose.
_FALLBACK: dict[str, Any] = {
    "antonyms": {"작": "크", "적": "많", "낮": "높", "느": "빠", "짧": "길", "어": "많", "좁": "넓", "얕": "깊", "약": "강"},
    "causal_verbs": ["일으키", "일으켜", "일으킨", "유발", "초래", "야기", "불러", "부른", "부르", "이끌", "이끈", "이어지", "이어진", "이어져", "낳"],
}

_lock = threading.Lock()
_cache: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    data = dict(_FALLBACK)
    try:
        loaded = json.loads(_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded.get("antonyms"), dict):
            data["antonyms"] = {str(k): str(v) for k, v in loaded["antonyms"].items()}
        if isinstance(loaded.get("causal_verbs"), list):
            data["causal_verbs"] = [str(v) for v in loaded["causal_verbs"] if v]
    except Exception:  # pragma: no cover - fall back to the seed
        pass
    _cache = data
    return _cache


def antonyms() -> dict[str, str]:
    return dict(_load()["antonyms"])


def causal_verbs() -> list[str]:
    return list(_load()["causal_verbs"])


def causal_verb_pattern() -> str:
    """A non-capturing regex alternation of causal verb stems, longest-first so wins over ."""
    verbs = sorted(set(causal_verbs()), key=len, reverse=True)
    return "(?:" + "|".join(verbs) + ")" if verbs else "(?!x)x"


def _persist(data: dict[str, Any]) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"_note": "extended by ko_lexicon.add_*", **data}
    _PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def add_antonym(negative_stem: str, positive_twin: str) -> None:
    """Learner/lexical-resource hook: record that `negative_stem` is the opposite pole of
    `positive_twin` on one scale. Persists and refreshes the cache."""
    with _lock:
        data = _load()
        data["antonyms"][str(negative_stem)] = str(positive_twin)
        _persist(data)
        globals()["_cache"] = None


def add_causal_verb(stem: str) -> None:
    with _lock:
        data = _load()
        if stem and stem not in data["causal_verbs"]:
            data["causal_verbs"].append(str(stem))
            _persist(data)
            globals()["_cache"] = None
