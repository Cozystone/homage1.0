# -*- coding: utf-8 -*-
"""Conversation weave — the session model for a voice-first, always-on presence (owner 2026-07-13:
" ... ").

The bias to break: "session = a chunk of time" (a text-era artifact of the app open/close boundary).
An ambient voice presence has no such boundary — it is ONE continuous relationship-stream. So sessions
are NOT the primary unit here. This module is the substrate that replaces them:

 • ONE continuous stream (never resets) — the truth of ambient presence.
 • THREADS, not sessions — a thread is a line of intent. Each utterance joins the thread it RESONATES
 with (concept overlap + recency warmth), so an interleaved "coffee … weather … back to coffee"
 rejoins the coffee thread, not the last one. This is exactly what makes deixis resolvable: ""
 /"" bind to the currently WARM thread's focus, not to a clock position.
 • EPISODES, emergent not declared — the stream is segmented at NATURAL boundaries (a long silence, a
 topic shift) the way human episodic memory chunks experience. Episodes are derived and revisable.

Three lenses read the one weave: by_thread (this ongoing concern), by_episode (this natural chunk),
by_rhythm (the relationship's lived days). Text and voice are the same substrate — a text session is
just a thread with sharp boundaries; voice is a thread with fuzzy ones.

No-LLM: concepts are content-word sets; resonance is overlap × recency; nothing is fabricated.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

# --- tunables ---------------------------------------------------------------
_WARM_HALF_LIFE = 6 * 3600.0     # a thread's warmth halves every 6h of silence
_THREAD_JOIN = 0.30              # min resonance to JOIN an existing thread (else start a new one)
_EPISODE_GAP = 1800.0           # a silence longer than this (30 min) opens a new episode
_EPISODE_SHIFT = 0.15           # overlap with the current episode below this = a topic-shift boundary
_CONCEPTS_PER_THREAD = 24       # bound a thread's accumulated concept set

# light Korean/!English content extraction — drop frame/deictic/stop words so the SUBJECT surfaces.
_STOP = {
    "뭐야", "무엇", "어떤", "어느", "가장", "정말", "진짜", "너는", "당신", "그리고", "근데", "그래서",
    "중요한", "중요", "필요한", "그것", "이것", "얘기", "이야기", "문제", "생각", "느낌", "부분",
    "이거", "그거", "저거", "이건", "그건", "요즘", "관련", "우리", "내가", "네가", "그냥", "다시",
    "the", "a", "an", "is", "are", "to", "of", "and", "it", "this", "that", "what", "how", "do",
}
_DEIXIS = {"이거", "그거", "저거", "이것", "그것", "저것", "이건", "그건", "여기", "거기", "아까", "그"}
_JOSA = re.compile(r"(은|는|이|가|을|를|의|에|에서|도|로|으로|과|와|이나|나|처럼|만|까지|부터)$")


def _concepts(text: str) -> set[str]:
    """The content-word set of an utterance — the fingerprint used for thread resonance."""
    out: set[str] = set()
    for tok in re.findall(r"[가-힣]{2,}|[A-Za-z]{2,}|[0-9]{2,}", str(text or "")):
        w = tok.lower()
        if "가" <= tok[0] <= "힣" and len(w) > 2:
            w = _JOSA.sub("", w) or w
        if len(w) >= 2 and w not in _STOP:
            out.add(w)
    return out




# wires the ATANOR concept graph (is_a / related) so a subtopic gains its parent concept before
# matching; standalone, it's a no-op and we fall back to surface tokens (honestly weaker).
_EXPANDER = None   # Optional[Callable[[set[str]], set[str]]]


def set_concept_expander(fn) -> None:
    """Inject a semantic concept expander (e.g. graph is_a/related). Pass None to reset to surface-only."""
    global _EXPANDER
    _EXPANDER = fn


def _concepts_expanded(text: str) -> set[str]:
    c = _concepts(text)
    if _EXPANDER is not None:
        try:
            c = c | set(_EXPANDER(set(c)))
        except Exception:
            pass
    return c


def graph_expander(concepts: set[str]) -> set[str]:
    """Production expander: lift each concept toward its PARENT concepts (is_a / instance_of) from the
 ATANOR graph, so gains and resonates with the coffee thread. Best-effort — returns an
 empty set (surface-only fallback) when the store is unavailable. Activate with
 `set_concept_expander(graph_expander)` where the graph is loaded (e.g. engine startup)."""
    out: set[str] = set()
    try:
        from packages.graph_scale.answer_bridge import _store
        kg = _store()
        if kg is None:
            return out
        for c in concepts:
            for _s, p, o in (kg.facts_about(c, limit=6) or []):
                if p in ("is_a", "instance_of", "subclass_of") and isinstance(o, str) and 2 <= len(o) <= 12:
                    out.add(o)
    except Exception:
        pass
    return out




_DEIXIS_TOKEN_RE = re.compile(r"(^|\s)(이거|그거|저거|이것|그것|저것|이건|그건|이걸|그걸|여기|거기|아까)")


def _is_continuation(concepts: set[str], text: str) -> bool:
    """A continuation carries reference/intent but no fresh TOPIC — " ", " ". It must
 not fork a new thread; it continues the warm one (and resolves its deixis against it). A deictic
 utterance that ALSO names a new topic (" ") is NOT a continuation — it has moved on."""
    if len(concepts) == 0:
        return True
    return bool(_DEIXIS_TOKEN_RE.search(str(text or ""))) and len(concepts) <= 1


def _warmth(last_ts: float, now: float) -> float:
    dt = max(0.0, now - float(last_ts))
    return 0.5 ** (dt / _WARM_HALF_LIFE)


def _overlap(a: set[str], b: set[str]) -> float:
    """Overlap coefficient |a∩b| / min(|a|,|b|). Unlike Jaccard it does NOT dilute as a thread
    accumulates concepts — the 10th 'coffee' utterance still resonates with a long coffee thread."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def new_state() -> dict[str, Any]:
    return {"utterances": [], "threads": [], "episodes": [], "next_id": 1}


def _nid(state: dict[str, Any]) -> int:
    i = state["next_id"]
    state["next_id"] = i + 1
    return i


def _resonance(concepts: set[str], thread: dict[str, Any], now: float) -> float:
    """How strongly an utterance belongs to a thread: concept overlap, damped by how cold the thread
    has gone. A warm thread is easy to rejoin; a long-dormant one needs a stronger topical match."""
    return _overlap(concepts, set(thread["concepts"])) * (0.4 + 0.6 * _warmth(thread["last_ts"], now))


def _attach(thread: dict[str, Any], concepts: set[str], now: float) -> int:
    """Add an utterance's concepts to an existing thread and warm it. Returns the thread id."""
    thread["concepts"] = list(dict.fromkeys(list(concepts) + thread["concepts"]))[:_CONCEPTS_PER_THREAD]
    thread["last_ts"] = now
    thread["count"] += 1
    return thread["id"]


def assign_thread(state: dict[str, Any], concepts: set[str], now: float) -> tuple[int, bool]:
    """Join the best-resonating thread, or open a new one. Returns (thread_id, is_new)."""
    best, best_score = None, 0.0
    for th in state["threads"]:
        s = _resonance(concepts, th, now)
        if s > best_score:
            best, best_score = th, s
    if best is not None and best_score >= _THREAD_JOIN:
        return _attach(best, concepts, now), False
    th = {"id": _nid(state), "concepts": list(concepts)[:_CONCEPTS_PER_THREAD],
          "last_ts": now, "count": 1}
    state["threads"].append(th)
    return th["id"], True


def _current_episode(state: dict[str, Any]) -> Optional[dict[str, Any]]:
    return state["episodes"][-1] if state["episodes"] else None


def _is_boundary(state: dict[str, Any], concepts: set[str], now: float) -> bool:
    """A natural episode boundary: a long silence, or a topic shift away from the current episode."""
    ep = _current_episode(state)
    if ep is None:
        return True
    if now - ep["end_ts"] > _EPISODE_GAP:
        return True                                   # the relationship went quiet, then resumed
    return _overlap(concepts, set(ep["concepts"])) < _EPISODE_SHIFT   # the subject moved on


def ingest(state: dict[str, Any], text: str, ts: Optional[float] = None,
           speaker: str = "user") -> dict[str, Any]:
    """Weave one utterance into the stream: segment the episode, assign the thread, record it. Returns
    the placement {thread_id, episode_id, new_thread, new_episode} — the substrate a UI/self reads."""
    now = float(ts if ts is not None else time.time())
    concepts = _concepts_expanded(text)

    # topic-shift episode either (only a real silence gap can), because it has not changed the subject.
    cont = _is_continuation(concepts, text)
    wt = warm_thread(state, now)
    warm_ok = wt is not None and _warmth(wt["last_ts"], now) >= 0.25
    ep0 = _current_episode(state)
    if cont and warm_ok:
        new_episode = ep0 is None or (now - ep0["end_ts"] > _EPISODE_GAP)
    else:
        new_episode = _is_boundary(state, concepts, now)
    if new_episode:
        ep = {"id": _nid(state), "start_ts": now, "end_ts": now,
              "utt_ids": [], "thread_ids": [], "concepts": list(concepts)[:_CONCEPTS_PER_THREAD]}
        state["episodes"].append(ep)
    ep = _current_episode(state)
    if cont and warm_ok:
        thread_id, new_thread = _attach(wt, concepts, now), False
    else:
        thread_id, new_thread = assign_thread(state, concepts, now)
    uid = _nid(state)
    state["utterances"].append({"id": uid, "ts": now, "speaker": speaker, "text": str(text or ""),
                                "concepts": sorted(concepts), "thread_id": thread_id,
                                "episode_id": ep["id"]})
    ep["end_ts"] = now
    ep["utt_ids"].append(uid)
    if thread_id not in ep["thread_ids"]:
        ep["thread_ids"].append(thread_id)
    ep["concepts"] = list(dict.fromkeys(ep["concepts"] + list(concepts)))[:_CONCEPTS_PER_THREAD]
    return {"utterance_id": uid, "thread_id": thread_id, "episode_id": ep["id"],
            "new_thread": new_thread, "new_episode": new_episode}


def warm_thread(state: dict[str, Any], now: Optional[float] = None) -> Optional[dict[str, Any]]:
    """The thread currently in focus — the warmest (most recently active). What 'this'/'that' means."""
    if not state["threads"]:
        return None
    n = float(now if now is not None else time.time())
    return max(state["threads"], key=lambda th: _warmth(th["last_ts"], n))


def resolve_deixis(state: dict[str, Any], term: str, now: Optional[float] = None) -> Optional[str]:
    """Resolve a user's deictic / coined shorthand ("", "", " ") to a referent: the
 FOCUS of the currently-warm thread. Deixis binds to the active thread, not a clock position — the
 same mechanism that lets the self follow non-dictionary personal language in context."""
    t = str(term or "").strip()
    if t and t not in _DEIXIS and not any(d in t for d in _DEIXIS):
        return t                                       # not deictic — it already names its referent
    th = warm_thread(state, now)
    if th is None or not th["concepts"]:
        return None
    # the focus = the thread's DOMINANT concept (the one running through its utterances = the topic),
    # not an alphabetical or last-token accident.
    from collections import Counter
    tally: Counter = Counter()
    for u in state["utterances"]:
        if u["thread_id"] == th["id"]:
            tally.update(u["concepts"])
    return tally.most_common(1)[0][0] if tally else th["concepts"][0]


# --- three lenses on the one weave -----------------------------------------
def by_thread(state: dict[str, Any]) -> list[dict[str, Any]]:
    """The intent lens — each ongoing concern with its utterances, across time/episodes."""
    out = []
    for th in sorted(state["threads"], key=lambda t: -t["last_ts"]):
        utts = [u["id"] for u in state["utterances"] if u["thread_id"] == th["id"]]
        out.append({"thread_id": th["id"], "concepts": th["concepts"], "count": th["count"],
                    "last_ts": th["last_ts"], "utterance_ids": utts})
    return out


def by_episode(state: dict[str, Any]) -> list[dict[str, Any]]:
    """The chunk lens — the emergent natural segments (topic shifts / silences)."""
    return [{"episode_id": ep["id"], "start_ts": ep["start_ts"], "end_ts": ep["end_ts"],
             "concepts": ep["concepts"], "thread_ids": ep["thread_ids"],
             "utterance_ids": list(ep["utt_ids"])} for ep in state["episodes"]]


def by_rhythm(state: dict[str, Any]) -> list[dict[str, Any]]:
    """The rhythm lens — the relationship's lived days (a UI convenience; NOT the primary unit)."""
    days: dict[str, list[int]] = {}
    for u in state["utterances"]:
        day = time.strftime("%Y-%m-%d", time.localtime(u["ts"]))
        days.setdefault(day, []).append(u["id"])
    return [{"day": d, "utterance_ids": ids} for d, ids in sorted(days.items())]


# --- persistence ------------------------------------------------------------
def load_state(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            s = json.loads(path.read_text(encoding="utf-8"))
            base = new_state()
            base.update({k: s.get(k, base[k]) for k in base})
            return base
        except Exception:
            pass
    return new_state()


def save_state(path: Path, state: dict[str, Any]) -> None:
    """Crash-safe: write to a temp sibling, fsync, then os.replace atomically — a power loss mid-write
    leaves the old weave intact or the new one complete, never a half-written, corrupt file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(state, ensure_ascii=False))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _default_state_path() -> Path:
    return Path(__file__).resolve().parents[2] / "runtime" / "weave" / "weave_state.json"
