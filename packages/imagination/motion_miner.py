# -*- coding: utf-8 -*-
"""Motion-relation miner — the web expedition's kinetic ear.

The physics compiler (scene_compiler) can DRIVE a fall or an orbit, but only when the graph
names the motion. This miner closes that gap without a single hard-coded narrative: when the
expedition's consensus gate passes sentences (2+ independent domains), we listen for KINETIC
clauses — " ", " " — and smelt just those subject/verb(/object)
triples into a MOTION LEDGER the imagination layer reads.

Honesty contract:
 * source = consensus-backed sentences only (the same 2-domain standard as expedition candidates),
 provenance (domains) carried on every entry;
 * lands in data/imagination/motion_relations.jsonl — a PRESENTATION-layer sidecar. It never
 touches the answer pack (pack promotion stays gated: diet-flood BINDING) and never feeds the
 answer path — it only lets the aquarium's particles move the way the corroborated web says
 things move;
 * the motion vocabulary is SHARED with the compiler (_MOTION_CUES) — one place, no second table.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from packages.imagination.scene_compiler import _MOTION_CUES, _physics_of

_LEDGER = Path(__file__).resolve().parents[2] / "data" / "imagination" / "motion_relations.jsonl"
_MAX_ENTRIES = 2000


# The verb must follow within the same short clause (< ~24 chars) so we never bridge two clauses.
_NOUN = r"[가-힣A-Za-z0-9·]{1,24}"
_CLAUSE = re.compile(
    rf"({_NOUN})(?:이|가|은|는)\s+(?:({_NOUN})(?:\s*주위)?(?:을|를)\s+)?([^\s,.!?]{{0,24}}?(?:"
    + "|".join(sorted({c for cues, _ in _MOTION_CUES for c in cues if re.match(r"^[가-힣]", c)},
                      key=len, reverse=True))
    + r")[가-힣]{0,6})")


def mine_motion_relations(sentence: str) -> list[dict[str, Any]]:
    """Kinetic triples in one sentence: [{subject, predicate, object|None, motion}].
    Only clauses whose verb the physics compiler recognizes (shared vocabulary) survive."""
    out: list[dict[str, Any]] = []
    for m in _CLAUSE.finditer(str(sentence or "")):
        subject, obj, verb = m.group(1), m.group(2), m.group(3)
        motion = _physics_of(verb)
        if not motion:
            continue
        if obj and obj.endswith("주위"):
            obj = obj[:-2].strip() or None
        out.append({"subject": subject, "predicate": verb, "object": obj or None,
                    "motion": motion})
    return out


def _load() -> list[dict[str, Any]]:
    try:
        with _LEDGER.open("r", encoding="utf-8") as fh:
            return [json.loads(ln) for ln in fh if ln.strip()]
    except Exception:
        return []


def record_from_consensus(candidates: list[dict[str, Any]]) -> int:
    """Mine every consensus-backed candidate ({text, domains}) and append NEW kinetic triples to
    the ledger (deduped on subject+motion+object, bounded ring). Returns how many were added."""
    entries = _load()
    seen = {(e.get("subject"), e.get("motion"), e.get("object")) for e in entries}
    added = 0
    for c in candidates or []:
        for rel in mine_motion_relations(str(c.get("text") or "")):
            key = (rel["subject"], rel["motion"], rel["object"])
            if key in seen:
                continue
            seen.add(key)
            entries.append({**rel, "domains": list(c.get("domains") or [])[:6],
                            "at": round(time.time(), 2)})
            added += 1
    if added:
        try:
            _LEDGER.parent.mkdir(parents=True, exist_ok=True)
            with _LEDGER.open("w", encoding="utf-8") as fh:
                for e in entries[-_MAX_ENTRIES:]:
                    fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        except Exception:
            return 0
    return added


def motion_relations_for(labels: set[str]) -> list[dict[str, Any]]:
    """Mined kinetic relations touching any of these concept labels — what the imagination layer
    merges into a scene so real queries get real physics."""
    want = {str(l).replace(" ", "") for l in labels if l}
    out: list[dict[str, Any]] = []
    for e in _load():
        s = str(e.get("subject") or "").replace(" ", "")
        o = str(e.get("object") or "").replace(" ", "")
        if s in want or (o and o in want):
            out.append(e)
    return out
