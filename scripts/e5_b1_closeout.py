# -*- coding: utf-8 -*-
"""Close the E5 B1 void — the same sentences through both extractors, so only A differs.

    python scripts/e5_b1_closeout.py --pages 200000

WHAT WENT WRONG THE FIRST TIME. The E5 seal recorded B1's baseline as 13.318 facts per 1k pages, taken
over the WHOLE 6.9M-page corpus, and the post-A run measured a 200k-page slice. Property density varies
enormously across Wikipedia slices, so the two numbers do not measure the same thing and their ratio
(-62.3%) means nothing. I cut that baseline, and the defect was mine.

WHY THIS IS NOT JUST "RERUN THE SWEEP". `wiki_property_sweep` dedups against rows already on disk, so a
second run over the same pages is scored against a ledger the first run already filled — the later run
looks worse for a reason that has nothing to do with the extractor. Running the two extractors over the
SAME streamed sentences removes that confound along with every other one: same dump, same page order,
same lead-sentence selection, same subject filter. The only thing that differs is the function under
test.

WHAT THIS IS AND IS NOT. It is a fair before/after of the A-side change on B1's own input distribution,
and it settles a question currently answered "unknown". It is NOT sealed E5 evidence: A is already
committed and the B2 direction is already known, so this is a POST-HOC diagnostic. It is labelled that
way in its own output so a later reader cannot mistake it for a gate. A real second E5 needs a fresh
A-side improvement and a seal cut before the work.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.cloud_brain.wikipedia_dump_reader import iter_wikipedia_sentences   # noqa: E402
from packages.graph_scale.property_extraction import extract as extract_new       # noqa: E402
from scripts.wiki_property_sweep import BAD_TITLE, LEAD_SENTENCES, _is_about, _subject_of    # noqa: E402

DUMP = REPO / "data" / "knowledge_sources" / "enwiki-full.xml.bz2"
#: WHERE THE RESULT GOES. This was a constant, and running the script for E5-2 overwrote E5-1's
#: record, then E5-3 overwrote E5-2's -- each number surviving only because it had also been copied
#: into a prereg. Same defect as the destructive default in codebase_ingest, found the same day: an
#: artifact path that ignores which run produced it. The path now follows the frozen extractor being
#: compared against, which is unique per run by construction.
DEFAULT_OUT = REPO / "data" / "e5_measurements"


def out_path_for(old: Path) -> Path:
    """A result file named after the run that produced it, in the append-only ledger room."""
    tag = old.parent.name or "run"          # e.g. e5_transfer_seal_3
    return DEFAULT_OUT / f"{tag}_b1_arm.json"


def load_old(path: Path):
    """The pre-A extractor, loaded from the file the seal hashed."""
    spec = importlib.util.spec_from_file_location("old_property_extraction", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.extract


def run(pages: int, old_path: Path) -> dict:
    extract_old = load_old(old_path)
    n_pages = 0
    subjects: set = set()
    rows_old: set = set()
    rows_new: set = set()
    last_title = None
    subject = None
    started = time.time()
    # the reader streams SENTENCES, not pages; a page boundary is a title change. Mirroring the
    # sweep's own loop exactly is the point -- any difference in how pages are counted or leads are
    # selected would show up as a yield difference that has nothing to do with the extractor.
    for rec in iter_wikipedia_sentences(str(DUMP), max_pages=None):
        if rec.title != last_title:
            last_title = rec.title
            n_pages += 1
            subject = None if BAD_TITLE.match(rec.title or "") else _subject_of(rec.title)
            if n_pages > pages:
                break
            if n_pages % 20000 == 0:
                print(f"  {n_pages:>8,} pages  old {len(rows_old):>7,}  new {len(rows_new):>7,}  "
                      f"({time.time()-started:.0f}s)", flush=True)
        if not subject or rec.sentence_index > LEAD_SENTENCES:
            continue
        if not _is_about(subject, rec.text, rec.sentence_index):
            continue
        subjects.add(subject)
        for pred, obj in extract_old(subject, rec.text) or []:
            rows_old.add((subject, pred, obj))
        for pred, obj in extract_new(subject, rec.text) or []:
            rows_new.add((subject, pred, obj))
    n_subjects = len(subjects)

    per1k_old = len(rows_old) / max(1, n_pages) * 1000
    per1k_new = len(rows_new) / max(1, n_pages) * 1000
    kept = rows_old & rows_new
    return {
        "kind": "same-slice before/after; sealed measurement procedure since E5-2",
        "why": ("Written for E5-1's post-hoc closeout and PROMOTED to the sealed B1 procedure by the "
                "E5-2 and E5-3 seals, which name this file. Whether a given run is sealed evidence "
                "is decided by the seal that invoked it, not by this header."),
        "pages_read": n_pages,
        "subjects": n_subjects,
        "rows_old": len(rows_old),
        "rows_new": len(rows_new),
        "per_1k_pages_old": round(per1k_old, 4),
        "per_1k_pages_new": round(per1k_new, 4),
        "relative_change": round((per1k_new - per1k_old) / per1k_old, 4) if per1k_old else None,
        "rows_old_kept_by_new": len(kept),
        "rows_lost_by_new": len(rows_old - rows_new),
        "rows_added_by_new": len(rows_new - rows_old),
        "elapsed_s": round(time.time() - started, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=200000)
    ap.add_argument("--old", type=str, required=True, help="path to the pre-A extractor file")
    ap.add_argument("--out", type=str, default=None,
                    help="result file; defaults to a name derived from --old, in the ledger room")
    args = ap.parse_args()
    if not DUMP.exists():
        sys.exit(f"no dump at {DUMP}")
    old = Path(args.old)
    res = run(args.pages, old)
    out = Path(args.out) if args.out else out_path_for(old)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        sys.exit(f"{out} already exists. This is a ledger: a record is added, never replaced. "
                 f"Pass --out to name a different file.")
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
