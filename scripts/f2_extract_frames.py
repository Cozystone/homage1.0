# -*- coding: utf-8 -*-
"""S2.5a — extract the top-10k formulaic frames from the WoW replies and stage them for the
construction bank (the idiom-principle route; docs/ATANOR_condensed_language_research.md E-F2).

A frame = a delexicalised skeleton (top-200 anchor words kept, content words -> <SLOT>) mined at the
4..8-gram grain, ranked by corpus frequency, each carrying up to 3 real filler examples. Output is a
sidecar the bank (and the dual-route composer) can load: data/graph_scale/formulaic_frames.jsonl.
Zero parameters; fluency inherited from human-written replies. No-LLM.

  python scripts/f2_extract_frames.py [n_frames]
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "data" / "graph_scale" / "dialogue_grounded.jsonl"
OUT = REPO / "data" / "graph_scale" / "formulaic_frames.jsonl"
W = re.compile(r"[A-Za-z']+")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    n_frames = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    reps = []
    with SRC.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                reps.append(json.loads(line)["text"])
            except Exception:
                continue
    freq = Counter(w.lower() for t in reps for w in W.findall(t))
    anchors = {w for w, _ in freq.most_common(200)}

    frames: Counter = Counter()
    fillers: dict[str, list[str]] = defaultdict(list)
    for t in reps:
        words = W.findall(t)
        toks = [w.lower() if w.lower() in anchors else "<SLOT>" for w in words]
        for n in (4, 5, 6, 7, 8):
            for i in range(len(toks) - n + 1):
                g = toks[i:i + n]
                if "<SLOT>" not in g:              # a frame must have at least one slot (else it's
                    continue                        # a literal quote, not a construction)
                if g.count("<SLOT>") > n // 2:      # and must be mostly skeleton, not mostly slots
                    continue
                key = " ".join(g)
                frames[key] += 1
                if len(fillers[key]) < 3:
                    fills = [w for w, tk in zip(words[i:i + n], g) if tk == "<SLOT>"]
                    fillers[key].append(" ".join(fills))

    kept = frames.most_common(n_frames)
    total_grams = sum(frames.values())
    covered = sum(c for _f, c in kept)
    with OUT.open("w", encoding="utf-8") as fh:
        for rank, (frame, count) in enumerate(kept):
            fh.write(json.dumps({"rank": rank, "frame": frame, "count": count,
                                 "slots": frame.count("<SLOT>"),
                                 "fillers": fillers[frame][:3],
                                 "source": "wow_replies", "license": "CC-BY-SA(WoW)"},
                                ensure_ascii=False) + "\n")
    print(f"RESULT frames {{'frames': {len(kept)}, 'corpus_grams': {total_grams}, "
          f"'coverage_of_framable': {round(covered/max(1,total_grams),4)}, 'out': '{OUT.name}'}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
