# -*- coding: utf-8 -*-
"""One identity, several cues, and any cue brings the rest — which is what knowing someone is.

    from packages.perception.who import bind, recall

    bind("voice", calibration_vector, seen_as="the person at the door")
    recall("voice", heard_now)      # -> the whole entity, including what was seen

WHAT THE OWNER ASKED FOR, and the reason it is not a Person class. A face field and a voice field on
a person object would be exactly the hardcoding they said to avoid: it fixes in advance which
modalities a thing has, which cue is primary, and in what order they are consulted. People do not
work that way. A voice on the phone summons a face nobody is looking at, a smell summons a room, and
none of it runs in a prescribed order.

WHAT MAKES IT NATURAL INSTEAD IS CONTENT ADDRESSING. An identity is a bundle of cues, and ANY of them
retrieves the bundle. That is one mechanism, applied identically to every modality, with nothing that
knows what a face or a voice is. Adding hearing to a thing already seen requires no new code path --
it is another cue on the same node.

AND IT IS THE ORGAN THAT WAS MISSING RATHER THAN THE PIECES. Searching this repository for anything
cross-modal -- a voice bound to a signature, a speaker bound to an identity -- returned nothing.
`object_recognition` stores instances and matches by cosine over signature vectors and is already
modality-blind; `Talker` learned this morning to calibrate a voice; `face_cortex` and `visual_kg`
exist. Every piece was here and no line connected any two of them. Fifteen times today the same
shape: built, present, unread.

THE HONEST BOUNDARY. This retrieves; it does not understand. Recalling that a voice belongs to the
same entity whose appearance was recorded is association, and calling it recognition of a PERSON
would be claiming more than a cosine can carry. What it buys is that the rest of the system -- the
graph, the workspace, whatever later renders a remembered face -- has one node to hang things on.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "perception" / "identities.jsonl"
MAX_CUES = 12                 # per modality, per identity: multi-view drift, same as object_recognition
MAX_IDENTITIES = 2000
#: A cue matches when it is nearer than this AND clearly nearer than the runner-up. Two conditions
#: because either alone fails in a way that matters: a threshold with no margin claims a winner in a
#: crowded field, and a margin with no threshold claims one when nothing is close at all.
NEAR = 0.62
MARGIN = 0.05


def _load() -> list:
    if not LEDGER.exists():
        return []
    out = []
    for ln in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def _save(rows) -> None:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                    for r in rows[-MAX_IDENTITIES:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def _cos(a, b) -> float:
    a, b = np.asarray(a, dtype=np.float64).ravel(), np.asarray(b, dtype=np.float64).ravel()
    if a.size != b.size or a.size == 0:
        return 0.0
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return 0.0 if na == 0 or nb == 0 else float(a @ b / (na * nb))


def _best(rows, modality: str, cue) -> tuple:
    scored = []
    for r in rows:
        views = (r.get("cues") or {}).get(modality) or []
        s = max((_cos(cue, v) for v in views), default=-1.0)
        if s > -1.0:
            scored.append((s, r))
    if not scored:
        return (None, 0.0, 0.0)
    scored.sort(key=lambda x: -x[0])
    runner = scored[1][0] if len(scored) > 1 else -1.0
    return (scored[0][1], scored[0][0], scored[0][0] - runner)


def bind(modality: str, cue, *, identity: str | None = None, **facts) -> dict:
    """Attach a cue to an identity — the one it already belongs to, or a new one.

    `facts` is whatever else is known right now and is stored verbatim: what it was called, what it
    was doing, where. Nothing here interprets them, which is what keeps this from becoming a schema
    for people."""
    rows = _load()
    cue = [float(v) for v in np.asarray(cue, dtype=np.float64).ravel()]
    hit = None
    if identity:
        # A NAME GIVEN IS NOT A HINT. The first version looked up the id and, when it was not found
        # yet, FELL THROUGH to similarity matching -- so the second person introduced was matched to
        # the first by voice and every subsequent one joined them. Four people collapsed onto one
        # node, every fact overwrote the last, and recall then answered "ana" to everybody with an
        # impossible margin of 1.9, which is the sentinel for "there was nobody else to compare to"
        # wearing the appearance of certainty.
        hit = next((r for r in rows if r.get("id") == identity), None)
    else:
        r, sim, margin = _best(rows, modality, cue)
        if r is not None and sim >= NEAR and margin >= MARGIN:
            hit = r
    if hit is None:
        hit = {"id": identity or "e%d" % (len(rows) + 1), "cues": {}, "facts": {},
               "first_seen": time.strftime("%Y-%m-%dT%H:%M:%S"), "times": 0}
        rows.append(hit)
    views = hit.setdefault("cues", {}).setdefault(modality, [])
    views.append(cue)
    del views[:-MAX_CUES]
    hit["facts"].update({k: v for k, v in facts.items() if v is not None})
    hit["times"] = int(hit.get("times", 0)) + 1
    hit["last_seen"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _save(rows)
    return {"identity": hit["id"], "modalities": sorted(hit["cues"]), "times": hit["times"]}


def recall(modality: str, cue) -> dict | None:
    """One cue in, the whole bundle out — including the modalities this cue is not.

    Returns None rather than a guess when nothing is close enough or two are equally close. Silence
    is the honest answer to 'who is this', and a wrong identity is worse than none: everything
    downstream would then activate the wrong memories."""
    rows = _load()
    r, sim, margin = _best(rows, modality, cue)
    if r is None or sim < NEAR or margin < MARGIN:
        return None
    return {"identity": r["id"], "similarity": round(sim, 3), "margin": round(margin, 3),
            "known_by": sorted(r.get("cues", {})),
            "also": sorted(set(r.get("cues", {})) - {modality}),
            "facts": dict(r.get("facts") or {}), "times": r.get("times", 0),
            "first_seen": r.get("first_seen"), "last_seen": r.get("last_seen")}


def voice_print(envelopes) -> np.ndarray:
    """What is left of a voice once WHAT WAS SAID averages out — the throat, not the word.

    THE MEASUREMENT THAT FORCED THIS. Binding raw spectral envelopes as a voice cue does not work,
    and it fails for a reason worth stating: over six speakers and six vowels, same-person pairs sit
    at median cosine 0.880 and different-person pairs at 0.779, with the tenth percentile of
    same-person (0.781) landing exactly on the median of different-person. At the best available
    cut-off, 0.83, it accepts 73% of same-person AND 21% of different-person. An envelope is mostly a
    record of the vowel; the speaker is the smaller part of it.

    Averaging several utterances is the fix and it is not a trick -- it is Joos's 1948 point and
    Ladefoged and Broadbent's 1957 experiment arriving as arithmetic. Whatever the person happened to
    say cancels; the tract does not. Which also means recognising a stranger from ONE word is
    genuinely hard rather than a shortcoming here: people need a moment with an unfamiliar voice too.
    """
    E = [np.asarray(e, dtype=np.float64).ravel() for e in envelopes]
    if not E:
        return np.zeros(1)
    m = np.mean(E, axis=0)
    return m - m.mean()


def recall_from(modality: str, cues) -> dict | None:
    """Several cues from one source — the honest interface for identifying a voice.

    `recall` with a single cue is kept because a glance is sometimes all there is, but for a voice it
    should be read as a guess. This averages first, which is what makes the answer about the speaker
    rather than about the sentence."""
    return recall(modality, voice_print(cues))


def cue_of(identity: str, modality: str):
    """What this identity's cue in another modality looks like — what makes recall REACH.

    This is the piece a later renderer needs: hearing a voice and getting back the appearance vector
    is what would let a remembered face be drawn rather than merely referred to."""
    for r in _load():
        if r.get("id") == identity:
            views = (r.get("cues") or {}).get(modality) or []
            return np.mean(np.asarray(views, dtype=np.float64), axis=0) if views else None
    return None


def summary() -> dict:
    rows = _load()
    both = sum(1 for r in rows if len(r.get("cues") or {}) > 1)
    return {"identities": len(rows), "known_in_more_than_one_way": both,
            "modalities": sorted({m for r in rows for m in (r.get("cues") or {})})}
