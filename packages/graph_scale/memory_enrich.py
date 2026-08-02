# -*- coding: utf-8 -*-
"""Memory enrichment — a faint glasses memory + live web = a rich recall.

Owner's scenario (2026-07-09): after ATANOR recalls " 7 ? 
", the user asks "! . ?". The smart
glasses only recognized it ROUGHLY (' '), so ATANOR fuses that faint
episodic trace with a LIVE web search to pin the exact model and surface an image
(or hand it to SPLATRA to render). Glasses don't exist yet — the faint label is
whatever was recorded — but the enrichment path is real and ready.

HONESTY: the remembered part is flagged as a FAINT memory; the web part is flagged
as CONFIRMATION. They are never blended into one confident claim. If the web finds
nothing, we say so — a faint memory is not upgraded to certainty by wishing.
Local/personal (the episode is the user's), the web query is impersonal.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Callable


def _default_search(query: str, count: int) -> list[dict[str, Any]]:
    try:
        from .web_knowledge_drain import _search_rows
        return _search_rows(query, count=count) or []
    except Exception:
        return []


def _build_query(label: str, context: list[str] | None) -> str:
    ctx = [c for c in (context or []) if c and c != label][:2]
    return " ".join([label, *ctx]).strip()


def _domain(url: str) -> str:
    try:
        return re.sub(r"^www\.", "", urllib.parse.urlparse(url).netloc.lower())
    except Exception:
        return ""


def enrich(label: str, context: list[str] | None = None, *,
           search: Callable[[str, int], list[dict[str, Any]]] | None = None,
           want: int = 6) -> dict[str, Any]:
    """Enrich a faint remembered label via live web search. Returns web candidates
    (the likely exact identity), any image candidates, a SPLATRA render hint, and
    honest framing that keeps 'remembered' separate from 'web-confirmed'."""
    label = (label or "").strip()
    if not label:
        return {"enriched": False, "reason": "no_label"}
    search = search or _default_search
    query = _build_query(label, context)
    rows = search(query, want) or []

    web_candidates, image_candidates = [], []
    for row in rows[:5]:
        url = str(row.get("url") or "")
        web_candidates.append({
            "title": str(row.get("title") or "")[:140],
            "url": url, "domain": _domain(url),
            "snippet": str(row.get("content") or row.get("snippet") or "")[:200],
        })
        for k in ("image", "image_url", "thumbnail"):
            if row.get(k):
                image_candidates.append(str(row[k]))
                break

    found = bool(web_candidates)
    if found:
        framing = (f"희미하게 '{label}'로 기억하는데, 웹으로 확인해보니 "
                   f"'{web_candidates[0]['title']}'인 것 같아요. 이미지 보여드릴까요?")
    else:
        framing = (f"'{label}'로 어렴풋이 기억하는데, 지금 웹에서 정확히 특정하진 "
                   f"못했어요. 웹 검증을 켜면 더 파고들 수 있어요.")
    return {
        "enriched": found,
        "remembered_label": label,           # the FAINT part (glasses)
        "query": query,
        "web_candidates": web_candidates,     # the CONFIRMATION part (web)
        "image_candidates": image_candidates[:4],
        "render_hint": {"engine": "splatra", "target": label,
                        "prompt": f"{label} 3D render", "ready": True},
        "framing": framing,
        "note": "faint episodic memory (glasses) + live web confirmation; "
                "remembered ≠ confirmed — never blended into one certain claim",
    }


def enrich_episode_observation(episode_id: str, label: str, *,
                               search: Callable[[str, int], list[dict[str, Any]]] | None = None
                               ) -> dict[str, Any]:
    """Enrich a specific recorded observation, using its episode's concepts as
    context to sharpen the web query."""
    context: list[str] = []
    try:
        from .episodic_memory import _rows
        for ep in _rows():
            if ep.get("episode_id") == episode_id:
                context = list(ep.get("concepts") or [])
                break
    except Exception:
        pass
    return enrich(label, context, search=search)
