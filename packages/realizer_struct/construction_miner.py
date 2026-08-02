# -*- coding: utf-8 -*-
"""Construction miner — the "사람처럼" growth mechanism: ACQUIRE new speech frames from usage,
never memorize surface. This is how a child generalizes a construction after a few exemplars, and
it is the doctrine's "새 술어엔 프레임" made automatic.

Mechanism (per the NLG/construction-grammar research):
  1. ALIGN: for a single-bone (s, r, o) pair whose text expresses it, take the CONNECTIVE span
     between the subject mention and the object mention.
  2. DELEXICALIZE: replace s→{s}, o→{o}. What remains is a TEMPLATE (a construction), not a string.
  3. ENTRENCH by TYPE-frequency (Goldberg: productivity ∝ #distinct fillers): a template seen with
     MANY different (s,o) pairs is productive and licensed for novel fillers; a template seen with
     few stays item-specific and is discarded. So we learn structure, and only structure.

Output: a frame lexicon {relation: "{s} <connective> {o}"} mined from the corpus — classifier-scale
(one template per relation), zero surface memorization, hallucination-safe (copy + template only).
Merges into FRAMES to grow the realizer's range without growing any weight matrix.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "data" / "graph_scale" / "bones_to_text.jsonl"
OUT = REPO / "data" / "realizer_struct" / "mined_frames.json"

_ART = re.compile(r"^(a|an|the)\s+", re.IGNORECASE)
# a connective is a short, mostly-lowercase linking phrase (verbs/preps), not a run of proper nouns
_CONNECTIVE_OK = re.compile(r"^[a-z][a-z ,'-]{0,28}$")


def _find_connective(text: str, s: str, o: str) -> str | None:
    """The delexicalized linking span between the subject and a NEARBY following object mention."""
    si = text.find(s)
    if si < 0:
        return None
    after = text[si + len(s):]
    # object must follow the subject within a short window (a single clause, not a paragraph away)
    m = re.search(r"\b" + re.escape(o) + r"\b", after[:80])
    if not m:
        return None
    span = after[:m.start()]
    span = _ART.sub("", span.strip())            # drop the article that belongs to the {o} slot
    span = re.sub(r"\s+", " ", span).strip(" ,")
    if not span or not _CONNECTIVE_OK.match(span):
        return None
    # normalize a trailing article back for template use (we re-add a/an at realize time)
    return span


def mine(max_pairs: int = 120000, min_types: int = 8) -> dict:
    """Return {relation: {"template","types","support","examples"}} for relations whose most-common
    connective is entrenched (seen with >= min_types distinct object fillers)."""
    # relation -> connective -> set of distinct (s,o) — type frequency
    conn_types: dict = defaultdict(lambda: defaultdict(set))
    seen = 0
    with CORPUS.open(encoding="utf-8") as f:
        for line in f:
            if seen >= max_pairs:
                break
            r = json.loads(line)
            if len(r["bones"]) != 1:
                continue
            s, rel, o = r["bones"][0]
            if not s or not o or rel in ("a", "the"):
                continue
            seen += 1
            c = _find_connective(r["text"], s, o)
            if c is not None:
                conn_types[rel][c].add((s.lower(), o.lower()))

    lexicon: dict = {}
    for rel, conns in conn_types.items():
        # entrench: pick the connective with the most DISTINCT filler pairs (productivity)
        ranked = sorted(conns.items(), key=lambda kv: -len(kv[1]))
        best_conn, fillers = ranked[0]
        if len(fillers) < min_types:
            continue                              # not productive enough — item-specific, discard
        lexicon[rel] = {
            "template": f"{{s}} {best_conn} {{o}}",
            "connective": best_conn,
            "types": len(fillers),                # distinct filler pairs = entrenchment strength
            "support": sum(len(v) for v in conns.values()),
            "alt_connectives": [c for c, v in ranked[1:4]],
        }
    return lexicon


def main() -> int:
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    lex = mine()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(lex, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"mined {len(lex)} entrenched frames (type-frequency >= 8):")
    for rel, d in sorted(lex.items(), key=lambda kv: -kv[1]["types"]):
        print(f"  [{rel:<12}] template {d['template']:<28} types={d['types']} support={d['support']}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
