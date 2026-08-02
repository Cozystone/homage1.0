# -*- coding: utf-8 -*-
"""Wild-web channels — route ONE wild segment through the constitutional safety gates into the four
data channels. Pure orchestration over transforms (pure) + store (I/O); no network here.

Gate order is the constitution (fail-closed, most-destructive first):
    moral/harm  -> reject entirely (nothing stored)
    PII         -> drop entirely (email/phone never even quarantined)
    injection   -> drop from learning (a segment is inert DATA, never an instruction)
then the surviving RAW segment is archived (Channel 1) and its SHAPE / POINTERS / HYPOTHESES are
distilled into Channels 2-4. A raw segment never becomes a fact; a template is only usable after
2-domain consensus; a topic is 'ungrounded'; a causal pair is a 'hypothesis'.
"""
from __future__ import annotations

from typing import Any, Iterable

from . import store as S
from . import transforms as T

_TOPICS_PER_SEGMENT = 8   # cap curiosity fan-out per segment (pointers, not answers)


def route_segment(segment: str, source_url: str) -> dict[str, Any]:
    """Run one segment through the gates and channels. Returns a per-segment receipt:
    {segment, quarantined, register, topics, causal, dropped}. `register` is
    'promoted'|'staged'|'duplicate'|None; `dropped` is the reject reason or None."""
    seg = (segment or "").strip()
    rc: dict[str, Any] = {"segment": seg[:80], "quarantined": False, "register": None,
                          "fragments": 0, "fragment_promoted": 0,
                          "topics": 0, "causal": 0, "causal_corroborated": 0, "dropped": None}

    if len(seg) < 12:
        rc["dropped"] = "short"
        return rc
    if T.is_harmful(seg):                       # [test 5] vile -> rejected entirely
        rc["dropped"] = "harmful"
        return rc
    if T.is_pii(seg):                           # [test 6] email/phone -> dropped entirely
        rc["dropped"] = "pii"
        return rc
    if T.has_injection(seg):                    # inert data, never instructed-from -> dropped
        rc["dropped"] = "injection"
        return rc

    dom = S.domain_of(source_url)

    # Channel 1 — RAW archive (never surfaced as fact)
    S.quarantine(source_url, seg)
    rc["quarantined"] = True

    # Channel 2 — REGISTER (anonymize -> template -> consensus>=2 domains)
    template = T.anonymize_wild(seg)
    norm = T.normalize_template(template)
    if norm:
        rc["register"] = S.stage_register(template, T.dialogue_act(seg), norm, dom, source_url)

    # Channel 2b — FRAGMENT REGISTER (discourse-act SKELETONS -> consensus >= 2 domains). The lever:
    # whole segments are near-unique across strangers (only boilerplate converged); the 12..60-char
    # discourse frame inside them DOES recur, so this is where cross-domain register consensus fires.
    for fr in T.extract_fragments(seg):
        st = S.stage_fragment(fr["fragment"], fr["act"], dom, source_url)
        if st == "duplicate":                       # same fragment, same domain — no new signal
            continue
        rc["fragments"] += 1                        # a NEW domain-sighting of this fragment
        if st == "promoted":
            rc["fragment_promoted"] += 1            # just crossed the 2-domain consensus bar

    # Channel 3 — TOPICS (ungrounded curiosity pointers)
    names, _places = T._derive_identity(seg)
    for tok in T.extract_topics(seg, names)[:_TOPICS_PER_SEGMENT]:
        if S.add_topic(tok):
            rc["topics"] += 1

    # Channel 4 — CAUSAL (hypotheses for later self-grounding; corroborate on >= 2 distinct domains)
    for c in T.mine_causal(seg):
        st = S.add_causal(c["cause"], c["effect"], source_url, c["pattern"])
        if st == "duplicate":                       # same edge, same domain — no new signal
            continue
        rc["causal"] += 1                           # a NEW domain-sighting of this edge
        if st == "corroborated":
            rc["causal_corroborated"] += 1          # just crossed the 2-domain consensus bar

    return rc


def process_segments(pairs: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """Route many (segment, source_url) pairs; return aggregate session counts."""
    agg: dict[str, Any] = {
        "segments": 0, "quarantined": 0, "register_staged": 0, "register_promoted": 0,
        "register_duplicate": 0, "fragment_candidates": 0, "fragment_promoted": 0,
        "topics": 0, "causal_candidates": 0, "causal_corroborated": 0,
        "dropped_short": 0, "dropped_harmful": 0, "dropped_pii": 0, "dropped_injection": 0,
    }
    for seg, url in pairs:
        agg["segments"] += 1
        rc = route_segment(seg, url)
        if rc["dropped"]:
            key = f"dropped_{rc['dropped']}"
            agg[key] = agg.get(key, 0) + 1
            continue
        if rc["quarantined"]:
            agg["quarantined"] += 1
        if rc["register"] == "promoted":
            agg["register_promoted"] += 1
        elif rc["register"] == "staged":
            agg["register_staged"] += 1
        elif rc["register"] == "duplicate":
            agg["register_duplicate"] += 1
        agg["fragment_candidates"] += rc["fragments"]
        agg["fragment_promoted"] += rc["fragment_promoted"]
        agg["topics"] += rc["topics"]
        agg["causal_candidates"] += rc["causal"]
        agg["causal_corroborated"] += rc["causal_corroborated"]
    return agg
