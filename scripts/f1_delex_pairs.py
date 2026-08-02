# -*- coding: utf-8 -*-
"""Wall 1 / experiment 1 prep — DELEXICALIZE the bones→text pairs (research-ranked #1 lever).

WebNLG/E2E-era evidence: small models are fluent+faithful over a limited relation vocabulary when
entities are slot tokens and the model learns only the connective tissue (Step-by-Step NAACL'19:
faithfulness errors −56..−90% with fluency on par). Entity strings stop consuming model capacity,
and entity hallucination becomes structurally impossible (the decoder can only emit ENT_i, which
re-lexicalization maps back to the graph's own strings — G-F3 strengthened by construction).

Reads  data/graph_scale/bones_to_text.jsonl   {"bones": [[s,r,o],...], "text": ...}
Writes data/graph_scale/bones_to_text_delex.jsonl   same schema + {"slots": {"ENT_0": "..."}},
       with every entity surface form replaced by ENT_i in bones AND text (longest-first matching,
       word-boundary, case-insensitive; pairs whose text never mentions any entity are kept as-is).

  python scripts/f1_delex_pairs.py [--in ... --out ...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "data" / "graph_scale" / "bones_to_text.jsonl"
DST = REPO / "data" / "graph_scale" / "bones_to_text_delex.jsonl"
HOLD = REPO / "data" / "graph_scale" / "realizer_holdout.jsonl"
HOLD_DST = REPO / "data" / "graph_scale" / "realizer_holdout_delex.jsonl"


def delex_record(rec: dict) -> dict:
    bones = rec.get("bones") or []
    # entity inventory: subjects and objects, longest surface form first so 'New York City'
    # is slotted before 'New York'
    ents: list[str] = []
    for s, _r, o in bones:
        for e in (s, o):
            e = (e or "").strip()
            if e and e.lower() not in (x.lower() for x in ents):
                ents.append(e)
    ents.sort(key=len, reverse=True)
    slots: dict[str, str] = {}
    text = rec.get("text") or ""
    new_bones = [list(b) for b in bones]
    for e in ents:
        tok = f"ENT_{len(slots)}"
        pat = re.compile(rf"(?<![\w-]){re.escape(e)}(?![\w-])", re.IGNORECASE)
        if not pat.search(text):
            continue                       # only slot entities the text actually realizes
        slots[tok] = e
        text = pat.sub(tok, text)
        for b in new_bones:
            for i in (0, 2):
                if b[i].strip().lower() == e.lower():
                    b[i] = tok
    out = dict(rec)
    out["bones"], out["text"], out["slots"] = new_bones, text, slots
    return out


def relex(text: str, slots: dict[str, str]) -> str:
    for tok, surface in slots.items():
        text = text.replace(tok, surface)
    return text


def main() -> int:
    src = Path(sys.argv[sys.argv.index("--in") + 1]) if "--in" in sys.argv else SRC
    dst = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else DST
    for source, target in ((src, dst), (HOLD, HOLD_DST)):
        if not source.exists():
            print(f"skip {source} (missing)")
            continue
        n = slotted = 0
        with source.open(encoding="utf-8") as f, target.open("w", encoding="utf-8") as g:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = delex_record(json.loads(line))
                slotted += 1 if rec.get("slots") else 0
                g.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
        print(f"{target.name}: {n} pairs, {slotted} with slots ({slotted/max(1,n):.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
