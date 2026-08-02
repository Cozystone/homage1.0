# -*- coding: utf-8 -*-
"""Formulaic frame bank — the idiom-principle route's first-class resource (S2.5a).

These are DELEXICALISED skeletons mined statistically from human replies (docs/ATANOR_condensed_
language_research.md: ~56% of assistant discourse is framable). They are deliberately kept SEPARATE
from the reviewed ConstructionCandidate pipeline: frames are disclosed statistical skeletons, not
hand-authored claims, so they must NOT enter the human-review promotion queue (that would violate the
bank invariants). The dual-route composer retrieves a frame, fills its <SLOT>s from the verified bones
+ interlocutor vocabulary (alignment priming), then the grounding gate decides whether to speak.
Fluency is inherited from the human frame; zero model parameters are spent on it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_FRAMES_PATH = Path(__file__).resolve().parents[2] / "data" / "construction_bank" / "formulaic_frames.jsonl"
_SLOT = "<SLOT>"
_CACHE: "list[Frame] | None" = None


@dataclass(frozen=True)
class Frame:
    frame: str                 # e.g. "the <SLOT> of <SLOT>"
    slots: int
    count: int                 # corpus frequency (higher = more formulaic)
    fillers: tuple[str, ...]   # up to 3 real filler examples from the corpus
    source: str = "wow_replies"

    @property
    def anchors(self) -> list[str]:
        return [w for w in self.frame.split() if w != _SLOT]


def load_frames(path: Path | None = None, refresh: bool = False) -> list[Frame]:
    global _CACHE
    if _CACHE is not None and not refresh and path is None:
        return _CACHE
    p = path or _FRAMES_PATH
    out: list[Frame] = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                out.append(Frame(r["frame"], int(r.get("slots", r["frame"].count(_SLOT))),
                                 int(r.get("count", 0)), tuple(r.get("fillers", []) or []),
                                 r.get("source", "wow_replies")))
            except Exception:
                continue
    if path is None:
        _CACHE = out
    return out


def fill_frame(frame: Frame | str, slot_values: list[str]) -> str:
    """Realise a frame by dropping the ordered slot_values into its <SLOT> positions (idiom route).
    Extra slots left unfilled are dropped with their trailing filler word — never invents content."""
    f = frame.frame if isinstance(frame, Frame) else frame
    parts, vi = [], 0
    for tok in f.split():
        if tok == _SLOT:
            if vi < len(slot_values):
                parts.append(slot_values[vi]); vi += 1
        else:
            parts.append(tok)
    s = " ".join(parts).strip()
    return re.sub(r"\s+", " ", s[:1].upper() + s[1:]) if s else ""


def best_frame(n_slots: int, prefer_frequent: bool = True) -> Frame | None:
    """Pick the most formulaic frame matching a desired slot count (v0 selection; the composer will
    later score by act/discourse-move fit)."""
    cands = [fr for fr in load_frames() if fr.slots == n_slots]
    if not cands:
        return None
    return max(cands, key=lambda fr: fr.count) if prefer_frequent else cands[0]
