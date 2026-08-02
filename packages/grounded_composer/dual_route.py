# -*- coding: utf-8 -*-
"""Dual-route composer — the human production architecture, wired (S2.5b / E-F3).

Sinclair's two modes as code: the IDIOM route (main) retrieves a mined human frame and drops the
verified bones into its slots — fluency inherited from human skeletons, zero parameters; the OPEN
route (auxiliary) asks the neural realizer to generate. BOTH outputs pass the same grounding gate
(every content word must trace to the bones or the frame's function-word anchors), and if neither
survives the gate the composer stays silent (voice-or-silence). Empty bones abstain immediately —
the G-F3 knowing/saying contract at composer level.

    route order:  frames (idiom, main) -> realizer (open, aux) -> honest abstention
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from packages.construction_bank.frames import load_frames, fill_frame
from packages.reasoning_vm.ace.match_features import tokenize, _stem

ABSTAIN = "I don't have grounded information about that."
_REL_WORDS = {"is_a": "is a", "alias": "also called", "located_in": "is located in",
              "capable_of": "can", "has_property": "is", "used_for": "is used for",
              "part_of": "is part of", "made_of": "is made of", "has_a": "has",
              "manner_of": "is a manner of", "defined_as": "is defined as",
              "grounded_in": "is grounded in"}
_FUNC = {"the", "a", "an", "of", "to", "in", "is", "are", "was", "were", "and", "or", "for", "on",
         "at", "by", "with", "as", "it", "its", "this", "that", "can", "has", "have", "also",
         "called", "used", "made", "part", "located", "kind", "manner", "grounded", "defined"}


@dataclass
class DualResult:
    text: str
    route: str          # 'frame' | 'realizer' | 'abstain'
    grounded: bool
    receipt: dict


def _content_stems(text: str) -> set[str]:
    return {_stem(w) for w in tokenize(text) if w.lower() not in _FUNC and len(w) > 1}


def grounding_gate(text: str, bones: list[list[str]], extra_allowed: set[str] | None = None) -> tuple[bool, dict]:
    """Receipt check: every content stem in the output must trace to the bones (subjects/objects) or
    the explicitly allowed frame anchors. One untraceable content word = the gate refuses (fabrication
    is never spoken)."""
    allowed: set[str] = set(extra_allowed or set())
    for s, r, o in bones:
        allowed |= _content_stems(str(s)) | _content_stems(str(o))
        allowed |= _content_stems(_REL_WORDS.get(r, str(r).replace("_", " ")))   # relation words are verified
    out_stems = _content_stems(text)
    untraced = sorted(out_stems - allowed)
    return (not untraced), {"content_words": len(out_stems), "untraced": untraced}


def _cap(out: str) -> str:
    # English orthography: a sentence starts uppercase even when the entity label is lowercase.
    # Stems are compared case-insensitively, so this never affects the grounding receipt.
    return out[0].upper() + out[1:] if out and out[0].islower() else out


def _frame_route(bones: list[list[str]]) -> str | None:
    """Idiom route: ONLY a real mined-skeleton match (audit #3). Returns None when no bank frame
    matches, so the caller can fall to the neural realizer BEFORE the generic prose fallback."""
    frames = load_frames()
    if not frames or not bones:
        return None
    s, rel, o = bones[0]
    rel_words = _REL_WORDS.get(rel, rel.replace("_", " ")).split()
    best = None
    for fr in frames:
        if fr.slots != 2:
            continue
        toks = fr.frame.split()
        try:
            i1 = toks.index("<SLOT>")
            i2 = len(toks) - 1 - toks[::-1].index("<SLOT>")
        except ValueError:
            continue
        it = iter(toks[i1 + 1:i2])
        if all(w in it for w in rel_words):              # rel words IN ORDER between the two slots
            if best is None or fr.count > best.count:
                best = fr
    if best is None:
        return None
    out = fill_frame(best, [str(s), str(o)])
    return _cap(out if out.endswith((".", "!", "?")) else out + ".")


def _generic_prose(bones: list[list[str]]) -> str:
    s, rel, o = bones[0]
    rel_words = _REL_WORDS.get(rel, rel.replace("_", " ")).split()
    return _cap(f"{str(s)} {' '.join(rel_words)} {str(o)}.")


def realize_dual(bones: list[list[str]], history: list[str] | None = None,
                 realizer_fn=None, telemetry: dict | None = None) -> DualResult:
    """Route order (audit #3): real frame -> neural realizer -> generic prose -> abstain. Every route
    passes the same grounding gate. If a `telemetry` dict is passed, the realizer's fate is counted
    (attempts / generation_success / exception / empty / grounding_rejected + a rejection sample), so
    a {realizer: 0} result can be proven to mean 'reached but domain-unfit' rather than 'never ran'
    or 'always crashed' (audit round-3 #3)."""
    if not bones:                                        # G-F3 at composer level: no bones -> abstain
        return DualResult(ABSTAIN, "abstain", True, {"reason": "empty_bones"})

    # -- 1. idiom route: a real mined human skeleton -----------------------------------------------
    frame_out = _frame_route(bones)
    if frame_out:
        ok, receipt = grounding_gate(frame_out, bones)
        if ok:
            return DualResult(frame_out, "frame", True, receipt)

    # -- 2. open route: the neural realizer (reached when no frame matched) -------------------------
    if realizer_fn is not None:
        if telemetry is not None:
            telemetry["attempts"] = telemetry.get("attempts", 0) + 1
        gen, crashed = "", False
        try:
            gen = realizer_fn(bones, history or [])
        except Exception as e:
            crashed = True
            if telemetry is not None:
                telemetry["exception"] = telemetry.get("exception", 0) + 1
                telemetry.setdefault("exception_sample", str(e)[:120])
        if not crashed and telemetry is not None:
            if gen and gen.strip():
                telemetry["generation_success"] = telemetry.get("generation_success", 0) + 1
            else:
                telemetry["empty"] = telemetry.get("empty", 0) + 1
        if gen and gen.strip():
            ok, receipt = grounding_gate(gen, bones)
            if ok:
                if telemetry is not None:
                    telemetry["grounding_ok"] = telemetry.get("grounding_ok", 0) + 1
                return DualResult(gen.strip(), "realizer", True, receipt)
            if telemetry is not None:
                telemetry["grounding_rejected"] = telemetry.get("grounding_rejected", 0) + 1
                telemetry.setdefault("rejected_sample", gen.strip()[:120])

    # -- 3. generic grounded prose fallback (S-rel-O) ----------------------------------------------
    generic = _generic_prose(bones)
    ok, receipt = grounding_gate(generic, bones)
    if ok:
        return DualResult(generic, "generic", True, receipt)

    # -- neither survived the gate: voice-or-silence ----------------------------------------------
    return DualResult(ABSTAIN, "abstain", True, {"reason": "gate_refused_both_routes"})
