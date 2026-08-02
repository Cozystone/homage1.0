# -*- coding: utf-8 -*-
"""Streaming predictive-coding prefilter — prime the answer BEFORE Enter.

Owner's vision (2026-07-09): like the human auditory cortex priming neurons for
the next word before a sentence ends, ATANOR reads the user's TYPING STREAM (every
debounced keystroke) and progressively NARROWS the graph territory it will search,
so the moment Enter is pressed the candidate field is already ~99% collapsed —
cold-start latency → 0. And under the 4D time axis, " …" masks the
conversation to the relevant time-region and projects the concept onto it.

THE BINDING INVARIANT (why this is honest, not autocomplete-hallucination): the
prefilter NEVER answers and NEVER emits a fact from an incomplete sentence. It only
(a) activates the phase-space neighborhood of the concepts already typed,
(b) intersects them (the ∩ lens),
(c) offers BRANCHES (candidate directions, phrased as questions), and
(d) optionally masks conversation history by time + concept.
The real answer still runs only on Enter, through every existing gate. Priming
changes SPEED and FOCUS, never truth.

Read-only, fast (phase cosine over the trained space), no store writes.
"""
from __future__ import annotations

import re
from typing import Any

# Korean particles/endings to strip so a typed token resolves to its concept head.
_KO_TAIL = re.compile(r"(은|는|이|가|을|를|의|도|만|에게|에서|에|과|와|이라는|라는|때문|이유|"
                      r"라고|이라고|처럼|보다|까지|부터|으로|로)$")

_TEMPORAL_CUE = re.compile(r"(그때|그 때|저번|예전|지난번|지난 번|아까|전에|그날|그 날|우리\s*그때)")
_STOPWORD = {"그리고", "그런데", "아니", "또는", "혹은", "그럼", "이제", "정말", "너무",
             "the", "and", "or", "but", "why", "what", "is", "are", "a", "an"}


def _tokens(text: str) -> list[str]:
    """Content tokens from (possibly incomplete) text, particle-stripped, recent
    last. The trailing fragment being typed is kept only if it's already a word."""
    raw = re.findall(r"[A-Za-z가-힣0-9]{2,}", text)
    out = []
    for t in raw:
        h = _KO_TAIL.sub("", t) if any("가" <= c <= "힣" for c in t) else t
        if len(h) >= 2 and h.lower() not in _STOPWORD:
            out.append(h)
    return out


def _known(term: str, space_idx: Any, store: Any) -> bool:
    if space_idx is not None and term in space_idx:
        return True
    if store is not None:
        try:
            return bool(store.facts_about(term, limit=1))
        except Exception:
            return False
    return False


def prime(partial_text: str, store: Any = None, history: list[dict[str, Any]] | None = None,
          k: int = 8) -> dict[str, Any]:
    """Prime on an in-progress input. Returns a priming state: focus concepts,
    the activated neighbourhood, the intersection lens, suggested branches, and
    (if a temporal cue + history) a time-region mask. NEVER an answer."""
    import numpy as np

    focus: list[str] = []
    activated: list[dict[str, Any]] = []
    intersection: list[dict[str, Any]] = []
    branches: list[str] = []
    n_space = 0
    space_idx = None
    try:
        from .phase_space import _load, _SPACE
        if _load() and _SPACE.get("phases") is not None:
            space_idx = _SPACE["idx"]
            n_space = len(_SPACE["terms"])
    except Exception:
        pass

    # 1) focus concepts = typed tokens the graph actually knows (recent first)
    for t in reversed(_tokens(partial_text)):
        if t not in focus and _known(t, space_idx, store):
            focus.append(t)
        if len(focus) >= 4:
            break

    # 2) activate each focus concept's phase-space neighbourhood (the primed field)
    if space_idx is not None and focus:
        from .phase_space import _SPACE, neighbors
        seen = set(focus)
        for f in focus:
            for term, res in neighbors(f, k=k):
                if term not in seen and res > 0.25:
                    activated.append({"concept": term, "resonance": round(res, 3), "via": f})
                    seen.add(term)
        activated.sort(key=lambda a: -a["resonance"])

        # 3) intersection lens: concepts resonating with ALL focus concepts at once
        if len(focus) >= 2:
            P = np.asarray(_SPACE["phases"], dtype=np.float32)
            idxs = [space_idx[f] for f in focus if f in space_idx]
            if len(idxs) >= 2:
                mins = np.full(P.shape[0], 2.0, dtype=np.float32)
                for i in idxs:
                    mins = np.minimum(mins, np.cos(P - P[i]).mean(axis=1))
                for i in idxs:
                    mins[i] = -2.0
                order = np.argsort(-mins)
                for j in order[:k]:
                    if mins[j] > 0.2:
                        intersection.append({"concept": _SPACE["terms"][int(j)],
                                             "resonance": round(float(mins[j]), 3)})

    # 4) branches = the strongest primed candidates, phrased as directions (not answers)
    src = intersection or activated
    for c in src[:3]:
        branches.append(f"{c['concept']} 쪽인가요?")


    # With explicit history, rank its turns; otherwise reach into EPISODIC MEMORY
    # (recorded lived episodes) and voice a predictive completion. Never invents.
    temporal = None
    if _TEMPORAL_CUE.search(partial_text):
        if history:
            temporal = _temporal_mask(focus, history)
        else:
            try:
                from .episodic_memory import complete as _ep_complete
                comp = _ep_complete(partial_text, focus)
                if comp:
                    temporal = {"cue": True, "episodic_completion": comp}
            except Exception:
                pass

    field = n_space or 1
    narrowed = len(intersection) or len(activated) or field
    return {
        "focus": focus,
        "activated": activated[:k],
        "intersection": intersection,
        "branches": branches,
        "temporal": temporal,
        "narrowed_to": narrowed,
        "field_size": n_space,
        "narrowed_fraction": round(1.0 - narrowed / field, 4) if n_space else 0.0,
        "primed": bool(focus),
        "note": "priming only — candidate field + branches, never an answer; "
                "the real answer runs on Enter through every gate",
    }


def _temporal_mask(focus: list[str], history: list[dict[str, Any]], top: int = 4
                   ) -> dict[str, Any]:
    """Rank past conversation turns by overlap with the focus concepts (and recency),
    surfacing the time-regions and the concepts active then. Honest episodic recall:
    it only ever returns concepts that were REALLY in the history."""
    focus_set = {f for f in focus}
    scored = []
    n = len(history)
    for pos, turn in enumerate(history):
        concepts = turn.get("concepts") or _tokens(str(turn.get("text", "")))
        overlap = len(focus_set.intersection(concepts))
        recency = (pos + 1) / n                       # later turns weigh a little more
        score = overlap + 0.15 * recency
        if overlap > 0 or not focus_set:
            scored.append((score, turn, concepts))
    scored.sort(key=lambda s: -s[0])
    regions = []
    for score, turn, concepts in scored[:top]:
        regions.append({
            "at": turn.get("at"),
            "matched": sorted(focus_set.intersection(concepts)),
            "concepts": [c for c in concepts if c not in focus_set][:6],
            "score": round(score, 3),
        })
    return {"cue": True, "regions": regions,
            "note": "conversation time-regions ranked by concept overlap — episodic recall, not invention"}
