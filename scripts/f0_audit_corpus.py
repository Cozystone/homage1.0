# -*- coding: utf-8 -*-
"""Track F / F0 — audit the register composition of the assembled corpus against the G-F0 gate.

The measured cause of the 0.60 fluency plateau was COMPOSITION, not size ([[corpus-composition-is-
the-bottleneck]]: 52% wiki / 2% dialogue). So F0's gate is a composition gate, checked here before F1
is allowed to consume the corpus:

  G-F0:  conversational+assistive register >= 50%   AND   raw-wiki <= 30%   AND   >= 2B tokens

Buckets (by source file):
  assistive-grounded  bones_to_text.jsonl        realising a fact fluently = assistant behaviour
  dialogue            dialogue_register/grounded  the conversational register (from the adopted sets)
  self                self logs + M4s autobiography
  wiki-explanatory    wiki body paragraphs        capped — must not dominate

Token counts are whitespace-word estimates x1.3 (subword factor); good enough for a composition gate.

  python scripts/f0_audit_corpus.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GS = REPO / "data" / "graph_scale"
SUBWORD = 1.3

BUCKETS = {
    "assistive-grounded": [GS / "bones_to_text.jsonl"],
    "dialogue":           [GS / "dialogue_register.jsonl", GS / "dialogue_grounded.jsonl"],
    "self":               [GS / "embodiment_autobiography.jsonl", REPO / "data" / "flywheel" / "turns.jsonl"],
    "wiki-explanatory":   [GS / "wiki_passages_en_body" / "passages.tsv"],
}
WIKI_CAP = 0.30
CONV_MIN = 0.50
TOK_MIN = 2_000_000_000


def _tokens_jsonl(p: Path, fields=("text", "response", "content")) -> int:
    if not p.exists():
        return 0
    n = 0
    with p.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            for f in fields:
                v = r.get(f)
                if isinstance(v, str):
                    n += len(v.split())
                    break
    return int(n * SUBWORD)


def _tokens_tsv(p: Path, sample_rows: int = 200_000) -> int:
    """Estimate by sampling the first `sample_rows` and scaling by the file's total line count (a 15GB
    body corpus can't be fully re-read for a composition estimate)."""
    if not p.exists():
        return 0
    n = rows = sampled_bytes = 0
    with p.open(encoding="utf-8", errors="ignore") as fh:
        while rows < sample_rows:
            line = fh.readline()               # readline (not iteration) keeps tell() usable
            if not line:
                break
            tab = line.find("\t")
            if tab >= 0:
                n += len(line[tab + 1:].split())
                rows += 1
        sampled_bytes = fh.tell()
    if rows == 0:
        return 0
    # scale the sample to the whole file by byte ratio (cheap total-size proxy)
    try:
        scale = max(1.0, p.stat().st_size / sampled_bytes) if sampled_bytes else 1.0
    except Exception:
        scale = 1.0
    return int(n * SUBWORD * scale)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    counts: dict[str, int] = {}
    for bucket, paths in BUCKETS.items():
        tot = 0
        for p in paths:
            tot += _tokens_tsv(p) if p.suffix == ".tsv" else _tokens_jsonl(p)
        counts[bucket] = tot
    total = sum(counts.values()) or 1

    print("=== F0 register-composition audit (G-F0 gate) ===")
    for b, c in counts.items():
        print(f"  {b:20} {c:>14,} tok   {c/total*100:5.1f}%")
    conv = (counts["assistive-grounded"] + counts["dialogue"]) / total
    wiki = counts["wiki-explanatory"] / total
    print(f"\n  total tokens (est)   {total:>14,}")
    print(f"  conversational+assistive : {conv*100:5.1f}%   [gate >= 50%]")
    print(f"  raw-wiki                 : {wiki*100:5.1f}%   [gate <= 30%]")
    gate = conv >= CONV_MIN and wiki <= WIKI_CAP and total >= TOK_MIN
    print(f"\n  G-F0: {'PASS' if gate else 'NOT MET'}  "
          f"(conv>=50 {'ok' if conv>=CONV_MIN else 'X'} · wiki<=30 {'ok' if wiki<=WIKI_CAP else 'X'} · "
          f">=2B {'ok' if total>=TOK_MIN else 'X'})")
    if not gate:
        need = []
        if conv < CONV_MIN:
            need.append("acquire dialogue datasets (WoW/DailyDialog/MultiWOZ) to raise the conversational share")
        if wiki > WIKI_CAP:
            need.append("cap the wiki-explanatory sampling")
        if total < TOK_MIN:
            need.append("grow total tokens toward 2B")
        print("  to close: " + "; ".join(need))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
