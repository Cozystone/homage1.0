# -*- coding: utf-8 -*-
"""Causal relation extractor — grow the graph's CAUSAL density from stated causation on the web.

Measured gap (2026-07-21): the graph is 83.6% is_a + alias and 0.35% causal — a naming dictionary,
not a model of how the world works. GPT-5.4's peer verdict and the world-mentor's curriculum both
name the same lack: world-grounded context where "meaning, relevance, and consequence accumulate."
causal_self.py grows the SELF-causal half (laws ATANOR lives); this grows the WORLD-causal half:
explicit (cause -> effect) relations between concepts, which web text states directly.

Doctrine, kept exactly:
  * NO-LLM / NO FABRICATION: causation is EXTRACTED by pattern, never generated. A pattern like
    "friction causes heat" yields a candidate edge; nothing is invented.
  * CONSENSUS GATE: a candidate becomes emittable only when independent SOURCES (distinct domains)
    state it — the same k-source discipline as fact learning. One page saying it is a hypothesis,
    not a fact; two independent pages is evidence.
  * QUARANTINE: extracted edges land in a counted side store with provenance, merged into the graph
    only through the normal promotion gate — never a silent production write (mirrors causal_corpus).
  * HONEST TYPING: the relation is the one the TEXT used (causes / enables / prevents / requires /
    used_for), not a coerced single label; polarity (prevents) is preserved.

Bound: stated causation is not verified causation — people assert wrong causes. Consensus across
independent sources reduces but does not eliminate that; edges carry source counts so nothing is
oversold, and downstream use stays hypothesis-flagged until the promotion gate accepts it.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "data" / "temporal_reasoning" / "causal_relation_counts.json"

# Each pattern maps a surface causal connective to the relation it asserts and the argument order.
# "{c} CAUSES {e}" is (cause -> effect); "{e} BECAUSE {c}" is the reverse. Kept small and explicit —
# these are the connectives, not a knowledge table; they carry no commitment to any subject.
# a lowercase noun-phrase argument: 1 to 3 WHOLE words (greedy within the window, so 'heat' is not
# truncated to 'hea' — the non-greedy version did exactly that). Determiners are stripped later.
_A = r"((?:the\s+|a\s+|an\s+)?[a-z][a-z'\-]+(?:\s+[a-z][a-z'\-]+){0,2})"
_PATTERNS = [
    # forward: cause first
    (re.compile(rf"\b{_A}\s+causes?\s+{_A}", re.I), "causes", False),
    (re.compile(rf"\b{_A}\s+leads?\s+to\s+{_A}", re.I), "causes", False),
    (re.compile(rf"\b{_A}\s+results?\s+in\s+{_A}", re.I), "causes", False),
    (re.compile(rf"\b{_A}\s+triggers?\s+{_A}", re.I), "causes", False),
    (re.compile(rf"\b{_A}\s+enables?\s+{_A}", re.I), "enables", False),
    (re.compile(rf"\b{_A}\s+prevents?\s+{_A}", re.I), "prevents", False),
    (re.compile(rf"\b{_A}\s+requires?\s+{_A}", re.I), "requires", False),
    (re.compile(rf"\b{_A}\s+is\s+used\s+to\s+{_A}", re.I), "used_for", False),
    # reverse: effect first, cause after the connective
    (re.compile(rf"\b{_A}\s+is\s+caused\s+by\s+{_A}", re.I), "causes", True),
    (re.compile(rf"\b{_A}\s+because\s+of\s+{_A}", re.I), "causes", True),
    (re.compile(rf"\b{_A}\s+due\s+to\s+{_A}", re.I), "causes", True),
]

# argument words too generic to be a real causal node — dropping them avoids "it causes problems"
_GENERIC = {"it", "this", "that", "they", "he", "she", "we", "you", "which", "who", "what",
            "problem", "problems", "issue", "issues", "thing", "things", "them", "one", "some",
            "people", "someone", "something", "anything", "everything", "change", "changes",
            # metalinguistic subjects — "the term is used to describe" is not world causation
            "term", "word", "name", "phrase", "expression"}
# a causal argument headed by a VERB/MODAL/COPULA is an extraction misfire, not a concept: measured
# noise from the graph bootstrap was "can causes confusion", "gravity causes is the acceleration",
# "star would requires metric". Strip these from the front, and reject an arg still headed by one.
_VERBLEAD = {"is", "are", "was", "were", "be", "been", "being", "am", "has", "have", "had",
             "can", "could", "will", "would", "shall", "should", "may", "might", "must", "do",
             "does", "did", "also", "not", "only", "then", "thus", "therefore", "normally",
             "usually", "often", "sometimes", "mainly", "partly", "generally", "typically"}
_STOPLEAD = re.compile(r"^(the|a|an|some|any|this|that|these|those|its|their|his|her|our|your|my)\s+",
                       re.I)


# words that begin a NEW clause/phrase — a causal argument ends before them ('heat when two
# surfaces' is the node 'heat', not 'heat when two')
_BOUNDARY = {"when", "where", "while", "if", "because", "since", "as", "that", "which", "who",
             "and", "or", "but", "to", "for", "with", "in", "on", "at", "by", "from", "than",
             "after", "before", "so", "then", "of", "into", "during", "unless", "though"}


def _clean_arg(s: str) -> str:
    """Normalize a causal argument to a concept key: strip a leading determiner, cut at the first
    clause boundary, cap at three content words."""
    s = s.strip().lower().strip(" .,;:'\"-")
    words = s.split()
    _DET = {"the", "a", "an", "some", "any", "this", "that", "these", "those", "its", "their",
            "his", "her", "our", "your", "my"}
    while words and (words[0] in _VERBLEAD or words[0] in _DET):   # peel leading verbs + determiners
        words = words[1:]
    out = []
    for w in words:
        if w in _BOUNDARY or w in _VERBLEAD:
            break                    # a new clause / a verb starts — the concept ended
        out.append(w)
        if len(out) == 3:
            break
    return " ".join(out)


@dataclass
class CausalEdge:
    cause: str
    relation: str        # causes | enables | prevents | requires | used_for
    effect: str

    def key(self) -> str:
        return f"{self.cause}|{self.relation}|{self.effect}"


def extract(text: str) -> list[CausalEdge]:
    """Every stated causal relation in a snippet — pattern extraction only, nothing invented."""
    out: list[CausalEdge] = []
    seen: set[str] = set()
    for rx, rel, reverse in _PATTERNS:
        for m in rx.finditer(text or ""):
            a, b = _clean_arg(m.group(1)), _clean_arg(m.group(2))
            cause, effect = (b, a) if reverse else (a, b)
            if not cause or not effect or cause == effect:
                continue
            if cause in _GENERIC or effect in _GENERIC:
                continue
            if len(cause) < 3 or len(effect) < 3:
                continue
            # after cleaning, an arg that is still a single function/verb word is an extraction
            # misfire ('can', 'time', a bare verb) — reject rather than pollute the graph
            if cause in _VERBLEAD or effect in _VERBLEAD or cause in _BOUNDARY or effect in _BOUNDARY:
                continue
            e = CausalEdge(cause, rel, effect)
            if e.key() not in seen:
                seen.add(e.key())
                out.append(e)
    return out


# ---------------------------------------------------------------- consensus store

def _load() -> dict[str, dict]:
    if not STORE.exists():
        return {}
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def observe(edges: list[CausalEdge], *, domain: str) -> int:
    """Record edges seen from ONE source (domain). Consensus is counted across DISTINCT domains, so
    the same page repeating a claim cannot manufacture agreement. Returns how many were newly seen."""
    store = _load()
    added = 0
    for e in edges:
        rec = store.setdefault(e.key(), {"cause": e.cause, "relation": e.relation,
                                         "effect": e.effect, "domains": []})
        if domain and domain not in rec["domains"]:
            rec["domains"].append(domain)
            added += 1
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(store, ensure_ascii=False, indent=0), encoding="utf-8")
    return added


def consensus_edges(min_sources: int = 2) -> list[dict[str, Any]]:
    """Causal edges independent sources agree on — the ones eligible to become graph bones. Below
    the threshold an edge stays a quarantined hypothesis, never asserted."""
    out = []
    for rec in _load().values():
        n = len(rec.get("domains", []))
        if n >= min_sources:
            out.append({"cause": rec["cause"], "relation": rec["relation"],
                        "effect": rec["effect"], "sources": n})
    out.sort(key=lambda r: -r["sources"])
    return out


def to_bones(min_sources: int = 2) -> list[list[str]]:
    """Consensus causal edges as graph bones [cause, relation, effect] — for the promotion gate to
    merge, NEVER written to production here. Provenance (source count) lives in the store."""
    return [[e["cause"], e["relation"], e["effect"]] for e in consensus_edges(min_sources)]


def stats() -> dict[str, Any]:
    store = _load()
    at2 = sum(1 for r in store.values() if len(r.get("domains", [])) >= 2)
    return {"candidate_edges": len(store), "consensus_edges": at2,
            "by_relation": _rel_counts(store)}


def _rel_counts(store: dict) -> dict[str, int]:
    c: dict[str, int] = defaultdict(int)
    for r in store.values():
        if len(r.get("domains", [])) >= 2:
            c[r["relation"]] += 1
    return dict(c)
