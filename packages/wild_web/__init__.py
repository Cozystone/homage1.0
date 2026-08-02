# -*- coding: utf-8 -*-
"""wild_web — ATANOR roams the OPEN WEB and learns the world from WILD human communication
(forums, comment threads, Q&A boards) instead of curated datasets. (W-track W0, 2026-07-22.)

CONSTITUTION (immutable, mirrors external-minds-are-data — a wild sentence is DATA, never knowledge):
  Channel 1 RAW      -> data/wild_web/quarantine.jsonl {source_url, ts, segment}
                        A hearsay archive. Never surfaced as fact, never executed, never a triple.
  Channel 2 REGISTER -> data/wild_web/register_pool.jsonl
                        ANONYMIZE (names->SPEAKER_x, places->PLACE, numbers->N, URLs->URL) then keep
                        only the discourse SHAPE (template + dialogue-act). A template is PROMOTED to
                        the usable pool ONLY on CONSENSUS across >= 2 DISTINCT DOMAINS (the BINDING
                        rule; per-domain counts tracked in register_staging.jsonl). A phrase many
                        strangers on independent sites use is common register, not one person's words.
  Channel 2b FRAGMENT -> data/wild_web/fragment_pool.jsonl (W2 convergence lever)
                        WHOLE-segment templates are near-unique across strangers, so only boilerplate
                        ever converged. So Channel 2b drops to FRAGMENT granularity: the 12..60-char
                        discourse-ACT SKELETONS ('the trick is to', 'in my experience', 'that happens
                        when') that DO recur across independent domains (reuses register_harvest's
                        fragment doctrine; frame lexicon is the LAD surface layer). Same >= 2-DISTINCT-
                        DOMAIN consensus; UI chrome is rejected (never a fragment). Anonymized by
                        construction (a skeleton is function/discourse words only — no name rides in).
  Channel 3 TOPICS   -> data/wild_web/curiosity_topics.jsonl {topic, status:'ungrounded'}
                        Bare content POINTERS ATANOR must go and ground ITSELF later (world-mentor
                        pattern). Never answers.
  Channel 4 CAUSAL   -> data/wild_web/causal_candidates.jsonl {cause, effect, source_url,
                        status:'hypothesis'}. Explicit "X because Y" / "if X then Y" / "X leads to Y"
                        statements mined as HYPOTHESES for later self-grounding — never facts. Each
                        pair is CANONICALIZED (lemmatize + strip modifiers + fold degree phrases +
                        collapse change-of-state; transforms.canonicalize_causal) so PARAPHRASES map
                        to one edge ('overwatering'->'leaves turn yellow' == 'too much water'->
                        'yellowing' == over_water->yellow) and CORROBORATE on >= 2 DISTINCT DOMAINS
                        into causal_pool.jsonl — still a hypothesis, never a fact. (Feeds the
                        consciousness-audit HOT-3 starvation: 0 causal laws promoted.)

SAFETY-BY-CONSTRUCTION (gate order in channels.route_segment):
  moral/harm floor -> reject vile segments entirely; PII (email/phone) -> drop entirely;
  injection -> never executed/instructed-from (segments are inert DATA, dropped from learning);
  robots-lite + per-domain rate limit + public-pages-only live in session.py.

REUSE (read the organs, reuse hard):
  * packages/realcity_learning/harvest.py  — the CITY TWIN of this pipeline. Its pure, English,
    doctrine-critical transforms are reused verbatim: anonymize, normalize_template, extract_topics,
    dialogue_act, speaker_map. (reads_as_harm was NOT reused verbatim — its substring match flags
    'skill'->'kill'; wild open text needs word-boundaried harm detection. See transforms.is_harmful.)
  * packages/autonomy_kernel/register_harvest.py — the CONSENSUS-BY-DOMAIN architecture (hash-dedup,
    per-domain set counting, MIN_DOMAINS=2, append-only jsonl) is mirrored in store.stage_register.
  * packages/brain_link/web_knowledge.py — the SearXNG JSON contract + session domain-diversity idea
    (inverted: forums are the TARGET register here, not noise; wiki stays last resort).
  * packages/atanor_browser/page_distiller.py — _TextExtract (boilerplate/link-density HTML->blocks).
  * packages/graph_scale/injection_guard.py — has_injection.

Persistence lives ONLY in store.py behind a monkeypatchable DATA_DIR (realcity pattern). transforms.py
is pure/offline; session.py is the ONLY network module (fetch/search are injectable for offline tests).
"""
from __future__ import annotations

from . import channels, store, transforms
from .channels import process_segments, route_segment
from .transforms import (
    anonymize_wild,
    canonicalize_causal,
    extract_fragments,
    extract_segments,
    is_harmful,
    is_pii,
    mine_causal,
)

__all__ = [
    "transforms",
    "store",
    "channels",
    "route_segment",
    "process_segments",
    "extract_segments",
    "extract_fragments",
    "anonymize_wild",
    "canonicalize_causal",
    "mine_causal",
    "is_harmful",
    "is_pii",
    "wild_session",
]


def wild_session(*args, **kwargs):
    """Lazy proxy to session.wild_session (keeps the network module out of import path for offline
    tests that only touch transforms/channels/store)."""
    from .session import wild_session as _ws

    return _ws(*args, **kwargs)
