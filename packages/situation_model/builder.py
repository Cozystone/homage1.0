# -*- coding: utf-8 -*-
"""Situation-model builder — read UNFAMILIAR text, build a world, reason over it (Grand Plan v2, G3).

This is the transfer core the owner and Gemini both point at: not a per-exam engine, but ONE
domain-blind mechanism — parse any scenario into a structure, then reason over the structure. It
generalises the self-causal reasoner's proven pattern (which transferred to a variant world on first
try) from one genre to arbitrary text: a passage of sentences becomes a SITUATION GRAPH of entities,
events (with order/time), and stated constraints; questions are answered by traversing that graph;
anything the graph does not support is abstained on (never fabricated — the honest floor).

No-LLM, no pretraining, no dictionary of the domain: the structure is extracted with generic
syntactic heuristics (who did what to whom, when, and what rules were stated) that carry no
commitment to any subject matter. That domain-blindness is exactly what makes it TRANSFER — a
chemistry passage and a crime report parse through the same mechanism.

v0 scope, honestly bounded: single-clause SVO events, explicit temporal ordering (before/after/then/
first/finally + numbered steps), stated negations and conditionals as constraints, and question types
who/what/when/did-X/order. It is measured against a sealed battery, not asserted to be complete;
where its heuristics do not reach, it abstains. The gate (G3) is a novel-text battery, not this file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_STOP = {"the", "a", "an", "this", "that", "these", "those", "his", "her", "its", "their", "our",
         "my", "your", "he", "she", "it", "they", "we", "i", "you", "there", "then", "so"}
_PRONOUN = {"he", "she", "it", "they", "him", "her", "them"}
_TIME_CUE = re.compile(r"\b(before|after|then|first|next|later|finally|earlier|meanwhile|"
                       r"subsequently|afterwards?|initially)\b", re.IGNORECASE)
_NEG = re.compile(r"\b(not|never|no longer|didn'?t|did not|cannot|can'?t|won'?t|refused to)\b",
                  re.IGNORECASE)
_COND = re.compile(r"\b(if|unless|provided that|as long as|whenever)\b", re.IGNORECASE)
# a verb-ish token (heuristic: not stop, ends in common verb shapes or is a known light verb)
_LIGHT_VERBS = {"is", "was", "are", "were", "has", "had", "have", "went", "gave", "took", "made",
                "said", "told", "saw", "found", "left", "moved", "put", "sent", "got", "came",
                "did", "does", "opened", "closed", "turned", "broke", "fixed", "met", "called"}


@dataclass
class Entity:
    name: str
    mentions: int = 1


@dataclass
class Event:
    subject: str
    verb: str
    obj: str
    order: int                       # position in the narrative (0-based)
    time_cue: str = ""               # explicit ordering word if present
    negated: bool = False
    conditional: str = ""            # the condition clause, if the event was stated conditionally
    raw: str = ""


@dataclass
class Situation:
    entities: dict[str, Entity] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)   # stated rules that are not simple events
    state: Any = None                                      # WorldState tracker (typed state organs)
    canon: dict = field(default_factory=dict)              # variant -> canonical spelling, from THIS text
    _source_text: str = ""                                 # verbatim passage, for mechanism reasoning

    def actors(self) -> list[str]:
        return sorted(self.entities, key=lambda e: -self.entities[e].mentions)


_LEAD_DROP = _STOP | {"finally", "then", "next", "later", "first", "initially", "earlier",
                      "meanwhile", "subsequently", "afterward", "afterwards"}


def _clean_np(s: str) -> str:
    toks = [t for t in re.findall(r"[A-Za-z][A-Za-z'-]*", s or "")]
    # drop leading stop-words AND leading time cues (measured: 'Finally the auditor' leaked the cue
    # into the entity name), so the subject is the actor, not the narration around it
    while toks and toks[0].lower() in _LEAD_DROP:
        toks = toks[1:]
    return " ".join(toks).strip()


# tokens a sentence boundary may NOT follow — a capital after these is a mid-clause proper noun
# ('gave the milk to Jeff'), not a new sentence
_NO_SPLIT_AFTER = {"to", "of", "and", "or", "with", "from", "than", "for", "at", "in", "on", "by",
                   "the", "a", "an", "is", "was", "are", "were", "either", "as", "his", "her",
                   "their", "then", "that", "but", "gave", "handed", "passed", "told", "asked"}


def _split_sentences(text: str) -> list[str]:
    # keep numbered list items as their own sentences (observation-log genre), then split on . ! ?
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    out = []
    for p in parts:
        p = p.strip()
        if p:
            out.append(re.sub(r"^\s*\d+[.)]\s*", "", p))    # drop a leading list number
    # FALLBACK — punctuation-independent segmentation (measured: stripping periods collapsed the
    # whole passage into one unparsed blob, acc 0.99 -> 0.04; sentence boundaries must not have a
    # single point of failure). If splitting produced one long blob, recover boundaries from
    # capitalization: a Capitalized token after a lowercase token starts a new sentence, unless the
    # lowercase token is a preposition/connective (mid-clause proper nouns stay attached).
    from packages.situation_model.text_normalizer import segment_by_verbs
    # A single unsplit blob holding two clauses is the signature of stripped punctuation. The old
    # trigger (>12 words) missed every SHORT merged pair — 'Sandra travelled to the office Sandra
    # went to the bathroom' is 10 words, stayed one 'sentence', and its whole tail became a
    # location (measured, case_punct@0.025 acc 0.792). The structural trigger is the verb count.
    if len(out) == 1 and len(segment_by_verbs(out[0])) > 1:
        words = out[0].split()
        segs, cur = [], [words[0]]
        for w in words[1:]:
            prev = cur[-1].lower().strip(",;")
            if (w[:1].isupper() and cur and cur[-1][:1].islower()
                    and prev not in _NO_SPLIT_AFTER):
                segs.append(" ".join(cur))
                cur = [w]
            else:
                cur.append(w)
        segs.append(" ".join(cur))
        # a capital-split segment can still hold two clauses (a sentence ENDING in a proper noun
        # blocks the next capital cut: '...gave it to Jeff Then Bill...'); verbs finish the job —
        # segment_by_verbs is a no-op on any segment that already holds a single clause
        segs = [sub for seg in segs for sub in segment_by_verbs(seg)]
        if len(segs) > 1:
            return segs
    return out


def _parse_event(sentence: str, order: int, last_subject: str) -> Event | None:
    """Generic SVO extraction: <subject NP> <verb> <object NP...>. Resolves a leading pronoun to the
    last subject (lightweight coreference). Returns None if no verb is found."""
    s = sentence.strip().rstrip(".!?")
    cue_m = _TIME_CUE.search(s)
    cue = cue_m.group(1).lower() if cue_m else ""
    cond = ""
    cm = _COND.search(s)
    if cm:
        # split "if <cond>, <event>" — the event is the main clause
        after = s[cm.end():]
        comma = after.find(",")
        if comma != -1:
            cond = after[:comma].strip()
            s = after[comma + 1:].strip()
    words = s.split()
    # find the first verb-ish token after position 0
    vi = None
    for i, w in enumerate(words):
        lw = w.lower().strip(",")
        if i == 0:
            continue
        if lw in _LIGHT_VERBS or re.search(r"(ed|es|s)$", lw) and lw not in _STOP and len(lw) > 3:
            vi = i
            break
    if vi is None:
        return None
    subj = _clean_np(" ".join(words[:vi]))
    if not subj or subj.lower() in _PRONOUN:
        subj = last_subject or subj
    verb = words[vi].lower().strip(",")
    obj = _clean_np(" ".join(words[vi + 1:]))
    negated = bool(_NEG.search(s))
    return Event(subject=subj, verb=verb, obj=obj, order=order, time_cue=cue,
                 negated=negated, conditional=cond, raw=sentence.strip())


def build(text: str) -> Situation:
    """Build a situation graph from arbitrary narrative text. Domain-blind by construction.

    Surface repair runs first (typos folded onto the passage's own majority spellings), so a
    corrupted rendering of a world we could otherwise read does not cost us the world. The repair
    is learned from this text alone and adds no vocabulary — see text_normalizer."""
    from packages.situation_model.state_tracker import StateTracker
    from packages.situation_model.text_normalizer import (build_canon_map, apply_canon,
                                                          repair_with_lexicon,
                                                          snap_to_frame_vocab)
    sit = Situation()
    tracker = StateTracker()
    sit.state = tracker
    # three independent sources of the right spelling, all no-ops on clean text: the vocabulary
    # ATANOR already holds (a room whose every mention is corrupted has no in-passage majority),
    # the frame keywords ('teh football' left 'teh' inside the object NP and broke counting —
    # snapping only in the fallback was too late), then this passage's own majority vote.
    # snap BEFORE lexicon repair: the lexicon buckets by first letter, so a corrupted
    # FRAME keyword ('eent') can only be mis-repaired there ('event', same initial) —
    # after which it is a known word and untouchable. The frame vocabulary must get
    # first claim on its own keywords; the lexicon then heals content words.
    sit._source_text = text                        # the TRUE original, BEFORE any repair — mechanism
    #                                                reasoning reads natural words ('bumped'), never a
    #                                                mis-'correction' (lexicon repair turned the valid
    #                                                'bumped' into 'bumper' because it was absent from
    #                                                the 82k graph vocab). Repair is for frame matching.
    text = repair_with_lexicon(snap_to_frame_vocab(text))
    sit.canon = build_canon_map(text)              # also lets a question be read in the same spelling
    text = apply_canon(text, sit.canon)
    last_subject = ""
    for i, sent in enumerate(_split_sentences(text)):
        tracker.ingest(sent, i)
        ev = _parse_event(sent, i, last_subject)
        if ev is None:
            if _NEG.search(sent) or _COND.search(sent) or " must " in sent.lower():
                sit.constraints.append(sent.strip())
            continue
        if ev.subject:
            last_subject = ev.subject
        for who in (ev.subject, ev.obj):
            key = who.lower().strip()
            if key and key not in _STOP:
                if key in sit.entities:
                    sit.entities[key].mentions += 1
                else:
                    sit.entities[key] = Entity(name=who)
        if ev.conditional:
            sit.constraints.append(f"conditional: if {ev.conditional} -> {ev.subject} {ev.verb} {ev.obj}")
        sit.events.append(ev)
    # GWT-1 submission: the world just built becomes the model's CURRENT situation, submitted to the
    # ignition workspace so situation_model actually competes as a heavy parallel module (the seam the
    # completion gauge found blind). Best-effort — building a world must never break on submission.
    try:
        from packages.situation_model.workspace_submit import note_situation
        note_situation(sit)
    except Exception:
        pass
    return sit
