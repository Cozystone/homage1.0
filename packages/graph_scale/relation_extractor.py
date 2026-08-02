# -*- coding: utf-8 -*-
"""Relation extractor v3 — rule × topology fusion (the upstream quality lever).

Owner's flagged priority (2026-07-09): to truly UNDERSTAND a book, lift relation
extraction from co-occurrence to a rule + topology-based higher-order parser. The
existing relation_miner (Korean, store-prose, 3-gate) is the prior art; this adds
the two things a book needs — ENGLISH higher-order patterns and, crucially, a
TOPOLOGY gate: a rule proposes a triple's STRUCTURE (syntax), and the trained
phase geometry judges whether that triple is geometrically PLAUSIBLE (RotatE:
θ_s + r ≈ θ_o). Structure ∧ geometry = a candidate worth keeping; everything
still lands as gated CANDIDATES (Surgeon-reviewed is_a), never production.

Why fusion beats either alone:
  * rules alone over-generate ('the book is a good idea' -> a junk is_a);
  * topology alone can't read a sentence — it only scores pairs you hand it.
Together: the rule reads the sentence, the geometry vetoes the nonsense. This is
the honest engine behind 'read a book and extract real relations, not word soup'.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

LEDGER_DIR = Path(__file__).resolve().parents[2] / "data" / "cloud_brain" / "derived_candidates"

# pronouns / determiners / vacuous heads that must never become graph nodes
_STOP = {"it", "this", "that", "these", "those", "there", "here", "he", "she",
         "they", "we", "i", "you", "who", "what", "which", "one", "someone",
         "something", "anything", "everything", "nothing", "a", "an", "the",
         "such", "some", "any", "all", "no", "his", "her", "their", "its",
         "way", "thing", "things", "idea", "case", "kind", "sort", "part",
         "example", "result", "reason", "fact", "point", "number", "set",
         # possessive pronouns, ordinals, and quantifier heads that are not nouns
         "mine", "yours", "ours", "hers", "theirs", "whose", "each", "both",
         "either", "neither", "first", "second", "third", "fourth", "fifth",
         "next", "last", "former", "latter", "other", "another", "more", "most",
         "many", "few", "several", "question", "matter", "issue", "topic"}

# causal / functional verbs -> predicate (precision set; entity-valued relations)
_VERB_PRED = {
    "causes": "원인", "cause": "원인", "produces": "결과", "produce": "결과",
    "contains": "구성요소", "contain": "구성요소", "requires": "requires",
    "require": "requires", "enables": "enables", "prevents": "prevents",
    "prevent": "prevents", "uses": "used_for", "use": "used_for",
}
_VERB_ALT = "|".join(sorted(_VERB_PRED, key=len, reverse=True))

# a subject NP (non-greedy) and an object NP that ends at a clause/prep boundary
# (lookahead, non-capturing) so "a fast process that..." yields "fast process",
# not the single word "fast" a bare non-greedy \b would grab.
_SUBJ = r"([A-Za-z][\w\- ]{1,38}?)"
_OBJ = (r"([A-Za-z][\w\- ]{1,38}?)"
        r"(?=[.,;:)\"']| (?:and|or|but|that|which|who|whose|is|are|was|were|in|on|"
        r"of|for|with|to|by|as|from|will|can|could|would|should|has|have|had)\b|$)")

# --- English higher-order patterns: (regex, predicate, subj_grp, obj_grp, hyponym)
_EN_PATTERNS = [
    # definitional copula: "X is/are a/an/the Y"
    (re.compile(r"\b" + _SUBJ + r" (?:is|are|was|were) (?:a|an|the) " + _OBJ),
     "is_a", 1, 2, False),
    # explicit definition: "X is defined as / refers to / is known as Y"
    (re.compile(r"\b" + _SUBJ + r" (?:is defined as|refers to|is known as) " + _OBJ),
     "defined_as", 1, 2, False),
    # hyponymy: "X such as Y" / "X including Y"  -> (Y, is_a, X)
    (re.compile(r"\b" + _SUBJ + r" (?:such as|including|like) " + _OBJ),
     "is_a", 2, 1, True),
    # causal / functional verb: "X <verb> Y"  (group 2 = verb, group 3 = object)
    (re.compile(r"\b" + _SUBJ + r" (" + _VERB_ALT + r") " + _OBJ),
     "__VERB__", 1, 3, False),
]

# --- Korean patterns (complement relation_miner's causal/part-of set: definitional)
_KO_PATTERNS = [
    (re.compile(r"([가-힣A-Za-z0-9]{2,16})[은는]\s*([가-힣A-Za-z0-9]{2,16})의?\s*(?:일종|한\s*종류)"),
     "is_a", 1, 2, False),
    (re.compile(r"([가-힣A-Za-z0-9]{2,16})[은는이가]\s*([가-힣A-Za-z0-9]{2,16}?)(?:이다|다)\b"),
     "is_a", 1, 2, False),
]


# finite/reporting verbs and clause markers — a clean noun phrase contains none.
# Their presence means the regex swallowed a whole clause ('Amos reported that
# the answer' -> the real subject is 'answer'), so we split and keep the tail.
_CLAUSE = re.compile(r"\b(?:that|which|who|whom|where|when|while|because|since|"
                     r"reported|reports|said|says|concluded|noted|notes|found|finds|"
                     r"showed|shows|suggested|suggests|argued|argues|believes|"
                     r"believe|thinks|think|claims|claim|observed|proposed|proposes|"
                     r"is|are|was|were|has|have|had|will|would|can|could)\b",
                     re.IGNORECASE)
_MAX_WORDS = 5          # a real noun phrase head is short; longer = a swallowed clause


def _np_head(phrase: str, *, is_subject: bool = False) -> str:
    """Reduce a noun phrase to a clean head: for a subject, first split off any
    trailing clause (keep the NP nearest the verb), then drop a leading article,
    cap length/words, and reject pronouns, vacuous heads, and verb-bearing runs."""
    p = re.sub(r"\s+", " ", phrase).strip().strip(" ,.;:'\"()")
    if is_subject:
        # keep only the clause segment nearest the matched verb (the last one)
        segs = _CLAUSE.split(p)
        p = segs[-1].strip() if len(segs) > 1 else p
    # drop a leading conjunction/adverb ('but overcoming...') then a leading article
    p = re.sub(r"^(?:but|and|or|so|yet|however|thus|therefore|then|because|although|"
               r"while|if|when)\s+", "", p, flags=re.I)
    p = re.sub(r"^(?:a|an|the|this|that|these|those|some|any)\s+", "", p, flags=re.I)
    p = p.strip(" ,.;:'\"()")
    if not p or len(p) < 2 or len(p) > 40 or len(p.split()) > _MAX_WORDS:
        return ""
    if p.lower() in _STOP or p.split()[-1].lower() in _STOP:
        return ""
    if not re.search(r"[A-Za-z가-힣]", p):
        return ""
    # a clean head must not still carry a finite verb (English)
    if re.search(r"[A-Za-z]", p) and _CLAUSE.search(p):
        return ""
    return p


def topology_score(subject: str, predicate: str, obj: str) -> float | None:
    """The geometry gate: how plausible is (s, p, o) under the trained phase
    space? RotatE closeness in [0,1], or None when any of the three is untrained
    (then the triple is an unvalidated candidate, not rejected)."""
    try:
        from .phase_space import _load, _SPACE
        from .fact_prediction import _load_relations
    except Exception:
        return None
    if not _load() or _SPACE.get("phases") is None:
        return None
    rel, preds = _load_relations()
    if rel is None or predicate not in preds:
        return None
    idx = _SPACE["idx"]
    ia, io = idx.get(subject), idx.get(obj)
    if ia is None or io is None:
        return None
    import numpy as np
    r = rel[preds.index(predicate)]
    ph = np.asarray(_SPACE["phases"], dtype=np.float32)
    d = float(np.abs(np.sin((ph[ia] + r - ph[io]) / 2.0)).sum())
    # normalize by the ACTUAL phase width (trained 64-dim), not the DIM=8 constant
    return round(1.0 - d / ph.shape[1], 4)


def extract_triples(sentence: str, lang: str = "en") -> list[dict[str, Any]]:
    """Rule pass: higher-order patterns -> structural (s, p, o) candidates with
    the pattern that fired. No topology yet (see extract_from_sentences)."""
    pats = _KO_PATTERNS if lang == "ko" else _EN_PATTERNS
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for rx, pred, sg, og, _hyp in pats:
        for m in rx.finditer(sentence):
            if pred == "__VERB__":
                verb = m.group(2).lower()
                predicate = _VERB_PRED.get(verb)
                if not predicate:
                    continue
            else:
                predicate = pred
            s, o = _np_head(m.group(sg), is_subject=True), _np_head(m.group(og))
            if not s or not o or s.lower() == o.lower():
                continue
            key = (s.lower(), predicate, o.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append({"s": s, "p": predicate, "o": o, "pattern": rx.pattern[:30]})
    return out


def extract_from_sentences(sentences: list[str], *, lang: str = "en",
                           store: Any = None, min_topology: float = 0.5,
                           out_dir: str | Path | None = None,
                           write: bool = True) -> dict[str, Any]:
    """The fusion pass: extract triples by rule, then let the topology gate veto
    the geometrically-implausible is_a (when both endpoints are trained), Surgeon-
    review the rest, and append survivors to the candidate ledger. Candidate-only.
    Returns an audit dict. Triples whose endpoints are untrained keep a null
    topology and pass on structure alone (still candidates, never production)."""
    out_dir = Path(out_dir) if out_dir else LEDGER_DIR
    try:
        from .surgeon import inspect as surgeon_inspect
    except Exception:
        surgeon_inspect = None

    kept: dict[str, list[dict[str, Any]]] = {}
    stats = {"sentences": 0, "raw": 0, "topology_vetoed": 0, "surgeon_excised": 0}
    for sent in sentences:
        stats["sentences"] += 1
        for t in extract_triples(sent, lang=lang):
            stats["raw"] += 1
            s, p, o = t["s"], t["p"], t["o"]
            topo = topology_score(s, p, o)
            # geometry veto: a trained pair that scores clearly implausible is cut
            if topo is not None and topo < min_topology:
                stats["topology_vetoed"] += 1
                continue
            if p == "is_a" and surgeon_inspect is not None and store is not None:
                try:
                    v = surgeon_inspect(store, s, o)
                    if isinstance(v, dict) and v.get("contaminated"):
                        stats["surgeon_excised"] += 1
                        continue
                except Exception:
                    pass
            kept.setdefault(p, []).append({**t, "topology": topo})

    written = 0
    if write and kept:
        out_dir.mkdir(parents=True, exist_ok=True)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        for p, rows in kept.items():
            # keep Korean predicate names distinct: sanitizing to [a-z_] collapsed

            safe = re.sub(r"[^\w가-힣]+", "_", p.lower()).strip("_") or "rel"
            path = out_dir / f"extracted_{safe}.jsonl"
            seen = set()
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        r = json.loads(line)
                        seen.add((r.get("s"), r.get("o")))
                    except Exception:
                        pass
            with path.open("a", encoding="utf-8") as fh:
                for r in rows:
                    if (r["s"], r["o"]) in seen:
                        continue
                    seen.add((r["s"], r["o"]))
                    fh.write(json.dumps({"s": r["s"], "p": p, "o": r["o"],
                                         "topology": r["topology"], "pattern": r["pattern"],
                                         "src": "extracted:rule+topology", "tier": "candidate",
                                         "at": now}, ensure_ascii=False) + "\n")
                    written += 1
    return {**stats, "candidates_written": written, "predicates": sorted(kept),
            "written_to_production": False,
            "note": "rule×topology candidates — Surgeon-reviewed, gated; promotion stays the evidence gate"}
