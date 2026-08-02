# -*- coding: utf-8 -*-
"""The gloss lane's own measurement — reproducible, so an A-side change can be justified without B.

    python scripts/gloss_lane_recall.py --sample 20000
    python scripts/gloss_lane_recall.py --sample 20000 --show-misses 40

WHY THIS EXISTS. The last A-side change was justified by gloss-lane recall moving 0.609 -> 0.796, and
those numbers were measured ad hoc and then lived only in a source comment. That is not good enough for
a transfer experiment: E5's honesty condition is that the A-side improvement is driven by A's OWN
failures, never by looking at B, and "driven by A's failures" is only checkable if A's failures are
measured the same way twice.

WHAT IS MEASURED. A deterministic slice of `primary_gloss.jsonl` (726,170 dictionary senses) goes
through `extract`. Two numbers come out:

    yield         rows per 1,000 glosses -- how much structure the lane recovers overall
    cue recall    of the glosses that VISIBLY state a property, how many produced a row

The cue set that defines "visibly states a property" is deliberately broader than the extractor's own
patterns -- it is a DIAGNOSTIC net, not a scorer. Its job is to surface glosses that a reader can see
state a purpose or a material while the extractor returned nothing, so the misses can be read and a
real pattern found. Using the extractor's own patterns as the denominator would make recall 1.000 by
construction, which is the trap this design exists to avoid.

WHAT IT IS NOT. Not a correctness measure. A row that fires is not thereby right -- agreement against
ConceptNet is the separate check the mining report carries. This measures whether the lane SEES the
structure that is plainly there.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from packages.graph_scale.property_extraction import extract   # noqa: E402

GLOSSES = REPO / "data" / "graph_scale" / "primary_gloss.jsonl"
OUT = REPO / "data" / "perception" / "gloss_lane_recall.json"

#: the DIAGNOSTIC net: surface forms a human reads as "this gloss states a property". Broader than the
#: extractor on purpose -- every hit the extractor misses is a candidate lesson, and a net drawn to
#: match the extractor would report perfect recall and teach nothing.
CUES = re.compile(
    r"\b(used\s+(?:for|as|to|in)|for\s+(?:cutting|holding|making|storing|carrying|measuring)"
    r"|made\s+(?:of|from|out\s+of)|consisting\s+of|composed\s+of|constructed\s+(?:of|from)"
    r"|capable\s+of|able\s+to|serves?\s+to|designed\s+to|intended\s+(?:to|for)"
    r"|(?:that|which)\s+(?:can|is\s+used|serves|holds|carries|produces|contains)"
    r"|a\s+(?:device|tool|instrument|machine|implement|utensil|apparatus|vessel|container)\b"
    r"|employed\s+(?:for|to|as)|applied\s+to|meant\s+(?:for|to))\b", re.I)


def load(sample: int, offset: int = 0):
    """A deterministic slice — same lines, same order, every run."""
    rows = []
    with GLOSSES.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i < offset:
                continue
            if len(rows) >= sample:
                break
            try:
                r = json.loads(line)
            except Exception:
                continue
            w, g = str(r.get("word", "")).strip(), str(r.get("gloss", "")).strip()
            if w and g:
                rows.append((w, g))
    return rows


def measure(rows, show_misses: int = 0) -> dict:
    fired = 0
    total_rows = 0
    by_pred: dict[str, int] = {}
    cue_total = cue_fired = 0
    misses: list[dict] = []
    for word, gloss in rows:
        got = list(extract(word, gloss) or [])
        has_cue = bool(CUES.search(gloss))
        if has_cue:
            cue_total += 1
        if got:
            fired += 1
            total_rows += len(got)
            for pred, _obj in got:
                by_pred[pred] = by_pred.get(pred, 0) + 1
            if has_cue:
                cue_fired += 1
        elif has_cue and len(misses) < max(show_misses, 200):
            cue = CUES.search(gloss)
            misses.append({"word": word, "cue": cue.group(0).lower() if cue else "",
                           "gloss": gloss[:180]})

    # which cue phrases account for the misses -- the ranking that says what to fix next
    by_cue: dict[str, int] = {}
    for m in misses:
        by_cue[m["cue"]] = by_cue.get(m["cue"], 0) + 1
    return {
        "glosses": len(rows),
        "glosses_with_a_row": fired,
        "rows": total_rows,
        "rows_per_1k_glosses": round(total_rows / max(1, len(rows)) * 1000, 3),
        "by_predicate": by_pred,
        "cue_bearing_glosses": cue_total,
        "cue_recall": round(cue_fired / max(1, cue_total), 4),
        "top_missed_cues": sorted(by_cue.items(), key=lambda kv: -kv[1])[:12],
        "misses_sample": misses[:show_misses],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=20000)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--show-misses", type=int, default=0)
    args = ap.parse_args()
    if not GLOSSES.exists():
        sys.exit(f"no glosses at {GLOSSES}")
    rows = load(args.sample, args.offset)
    res = measure(rows, args.show_misses)
    res["slice"] = {"offset": args.offset, "sample": args.sample}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"glosses {res['glosses']:,}   rows {res['rows']:,}   "
          f"per 1k {res['rows_per_1k_glosses']}")
    print(f"cue-bearing {res['cue_bearing_glosses']:,}   CUE RECALL {res['cue_recall']:.4f}")
    print(f"by predicate: {res['by_predicate']}")
    print(f"top missed cues: {res['top_missed_cues']}")
    for m in res["misses_sample"]:
        print(f"   [{m['cue']}] {m['word']}: {m['gloss']}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
