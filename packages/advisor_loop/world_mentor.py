# -*- coding: utf-8 -*-
"""World mentor — a mentally-immature ATANOR self-reflects on the gaps in its WORLD MODEL, asks a
mentor (GPT-5.4) HOW to build understanding of them, then learns the actual facts ITSELF from the
diverse web. GPT teaches ABOUT the world (a curriculum); ATANOR comes to understand the world.

Owner (2026-07-21): GPT tells the still-immature ATANOR about the world; ATANOR, from its own self-
retrospection, gets advice on building the parts of its world model it doesn't grasp, and so comes
to understand the world.

Doctrine boundary (BINDING): GPT gives the CURRICULUM — which concepts to grasp first, which
relation axes are weak, how to structure the learning — NOT the facts themselves. ATANOR acquires
the actual world-facts through its OWN source-weighted, consensus-checked web (web_knowledge), so no
mentor sentence is injected into the graph as knowledge. Guidance in; understanding self-built.
No-LLM stays a runtime property.
"""
from __future__ import annotations

import collections
import json
from collections import Counter
from pathlib import Path
from typing import Any

from packages.advisor_loop.advisor_session import ask_cli
from packages.brain_link.web_knowledge import learn_from_web
from packages.realizer_struct.frame_realizer import realize

REPO = Path(__file__).resolve().parents[2]
GRAPH = REPO / "data" / "graph_scale" / "bones_to_text.jsonl"
LEARNED = REPO / "data" / "advisor_loop" / "world_model_learned.jsonl"
LOG = REPO / "data" / "advisor_loop" / "world_mentor.log"
SEARX = "http://localhost:8888"


def already_understood() -> set[str]:
    """Concepts ATANOR has already learned from its own web this lifetime. Doctrine keeps these OUT
    of the graph (they are journal entries, not mined bones), so retrospection must consult the
    journal too — otherwise the same gaps resurface forever."""
    out: set[str] = set()
    if not LEARNED.exists():
        return out
    for line in LEARNED.open(encoding="utf-8"):
        if line.strip():
            try:
                out.add(json.loads(line)["concept"].lower())
            except Exception:
                continue
    return out


def retrospect_world_gaps(scan: int = 30000) -> dict[str, Any]:
    """ATANOR's self-reflection: which foundational concepts does it USE but cannot EXPLAIN (known-
    of but not understood), and which relation axes are thin (a weak world-model dimension)?

    Overnight defect (2026-07-21): four rounds produced 12 journal entries but only THREE unique
    concepts — city/country/island were relearned every round, so the world model never advanced.
    Cause: gaps were read from the GRAPH alone, and self-learned facts never enter the graph (by
    doctrine), so they stayed 'gaps' permanently. Fix: subtract what the journal says is already
    understood, so each round reaches genuinely NEW ground."""
    subjects: set[str] = set()
    rel_count: Counter = Counter()
    objects: Counter = Counter()
    n = 0
    for line in GRAPH.open(encoding="utf-8"):
        if n >= scan:
            break
        r = json.loads(line); n += 1
        subjects.add(r["subject"].lower())
        for s, rel, o in r["bones"]:
            rel_count[rel] += 1
            objects[o.lower()] += 1
    understood = already_understood()
    dangling = [o for o, c in objects.most_common(4000)
                if o not in subjects and o not in understood and len(o) > 3 and o.isalpha()][:20]
    thin_axes = [rel for rel in ("causes", "used_for", "part_of", "has_property", "located_in")
                 if rel_count.get(rel, 0) < rel_count.get("is_a", 1) * 0.1]
    return {"foundational_gaps": dangling, "thin_relation_axes": thin_axes,
            "relation_coverage": dict(rel_count.most_common(8))}


def ask_mentor_curriculum(gaps: dict[str, Any], advisor: str = "openclaw") -> str:
    """GPT-5.4 advises HOW to build the missing world model — a curriculum, not facts."""
    prompt = (
        "You are mentoring ATANOR, a mentally-immature No-LLM graph-native AI, on building its WORLD "
        "MODEL. It self-reflected and found it USES these foundational concepts constantly but cannot "
        f"explain any of them: {', '.join(gaps['foundational_gaps'][:12])}. Its relation coverage is "
        f"{gaps['relation_coverage']}, and these understanding-axes are THIN: {gaps['thin_relation_axes']}. "
        "Do NOT define the concepts for it (it will learn the facts itself from the web). Instead give "
        "a CURRICULUM as a plain-text numbered list of EXACTLY four items: (1) which 3 concepts to "
        "understand FIRST and why they are foundational, (2) which relation axis it should strengthen "
        "to reason causally about the world, (3) one structural principle for organizing world "
        "knowledge, (4) a blind spot in how it is reflecting. Start item 1 immediately; no preamble."
    )
    return ask_cli(advisor, prompt, timeout_s=240).reply


def learn_gap(concept: str, used_domains: Counter | None = None) -> dict[str, Any] | None:
    """ATANOR fills a world-model gap ITSELF via its source-weighted web (not from the mentor).
    `used_domains` accumulates across a round so successive concepts SPREAD across the web instead
    of all landing on Wikipedia (the owner's 'wikipedia 작작 써라' directive, honored at round scope)."""
    got = learn_from_web(concept, SEARX, used_domains if used_domains is not None else Counter())
    if not got:
        return None
    gloss, url, domain = got
    # World-CAUSAL half of the convergent target: as ATANOR reads a concept's gloss, extract any
    # STATED causal relations in it (friction causes heat) and record them under the consensus store.
    # Extraction only — nothing asserted; a causal edge becomes a graph bone only once independent
    # domains agree (the promotion gate), so this thickens the 0.35%-causal graph honestly.
    causal_found = 0
    try:
        from packages.temporal_reasoning.causal_relation_extractor import extract, observe
        edges = extract(gloss)
        if edges:
            causal_found = observe(edges, domain=domain)
    except Exception:
        pass
    rec = {"concept": concept, "understanding": gloss, "source": url, "domain": domain,
           "causal_edges_seen": causal_found}
    LEARNED.parent.mkdir(parents=True, exist_ok=True)
    with LEARNED.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def harvest_causes(concept: str, used_domains: Counter | None = None) -> int:
    """The WORLD-causal half of the convergent target: a definition ('a city is a settlement') has
    no causal structure, so to grow the 0.35%-causal graph ATANOR must READ causation — it queries
    'what causes X' / 'how does X work' and extracts stated causal relations from the results,
    recording them per-domain for the consensus gate. Extraction only; nothing asserted. Returns
    how many new (edge, source) observations were recorded."""
    try:
        from packages.brain_link.web_knowledge import _ENCYCLOPEDIC, _is_english, searxng_ranked
        from packages.temporal_reasoning.causal_relation_extractor import extract, observe
    except Exception:
        return 0
    ud = used_domains if used_domains is not None else Counter()
    # dictionary/translation sites answer 'what causes X' with a gloss of the WORD 'causes', not an
    # explanation of X — pure noise for causal harvest (measured: '爱词霸', 'EDR 일영대역사전').
    _DICT = ("dictionary", "dict.", "词典", "translate", "wordreference", "glosbe", "iciba",
             "weblio", "naver.com", "wordow", "vocabulary.com")
    seen = 0
    for q in (f"why does {concept} happen", f"how {concept} forms", f"what causes {concept}"):
        for r in searxng_ranked(q, SEARX, ud)[:4]:
            dom = (r.get("domain") or "").lower()
            if any(d in dom for d in _DICT) or any(e in dom for e in _ENCYCLOPEDIC):
                continue                                   # skip dictionaries + encyclopedic mirrors
            text = (r.get("content") or "") + ". " + (r.get("title") or "")
            if not _is_english(text):                      # English-only doctrine
                continue
            edges = extract(text)
            if edges:
                seen += observe(edges, domain=dom)
    return seen


def run_round(learn_first: int = 3, advisor: str = "openclaw", now_utc: float = 0.0,
              *, harvest: bool = False) -> dict[str, Any]:
    """One world-understanding round: retrospect gaps -> mentor curriculum -> self-learn top gaps,
    and (harvest) read each concept's CAUSAL structure into the consensus store."""
    gaps = retrospect_world_gaps()
    curriculum = ask_mentor_curriculum(gaps, advisor=advisor)
    used_domains: Counter = Counter()               # shared across the round -> web diversity pressure
    learned = [r for r in (learn_gap(c, used_domains) for c in gaps["foundational_gaps"][:learn_first]) if r]
    causal_observed = 0
    if harvest:
        for r in learned:
            try:
                causal_observed += harvest_causes(r["concept"], used_domains)
            except Exception:
                pass
    out = {"gaps": gaps, "curriculum": curriculum, "learned": learned,
           "causal_observed": causal_observed, "ts": now_utc}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False) + "\n")
    return out
