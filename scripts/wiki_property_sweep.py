# -*- coding: utf-8 -*-
"""Read Wikipedia the way a person does: understand the sentence, keep the structure, drop the text.

    python scripts/wiki_property_sweep.py                    # the whole dump, hours, resumable
    python scripts/wiki_property_sweep.py --max-pages 2000   # a taste

THE OWNER'S FRAMING, 2026-07-31: 사람도 글이나 나무위키를 읽을때 원문을 다 뇌에 저장하는게 아니라
이해하고 구조화하고 넘어가듯이 atanor도 글을 순서대로 쭉 흝으면서 이해하고 넘기고가 가능하니 더
효율적이지 않을까?

THAT IS EXACTLY WHAT THIS DOES, and the property matters more than it sounds. 25 GB of dump goes past in
a stream; what stays on disk is (subject, predicate, object) rows. Nothing keeps the article. Memory cost
is bounded by how much STRUCTURE was found, not by how much was read -- which is the only way "read
everything" is a plan rather than a wish.

WHY WIKIPEDIA WHEN A CENSUS SAID WIKIPEDIA IS THE PROBLEM. The store's attribute mass came from wikidata
and encyclopedia articles about NAMED ENTITIES, and its leading property axes turned out to be songs,
genes and ISS missions. That is a fact about which SENTENCES were mined, not about the corpus: the
infobox-shaped facts (occupation, country, author) are what got taken. A Wikipedia LEAD SENTENCE is a
different register entirely -- it is a definition by editorial convention, and definitions state the
obvious things encyclopedic prose omits:

    A knife is a tool with a cutting edge, used to cut things.
    A kettle is a metal container that boils water, used for making tea.

So this reads leads only, takes the article title as the subject, and refuses any sentence that is not
plainly about that subject. Precision over volume; the last lane that chased volume was cut at 0.108.

RESUMABLE, because the run is long and the machine is not promised to stay up. Progress and candidates are
flushed together every FLUSH_PAGES, so a kill loses at most that window and never leaves the ledger
disagreeing with the checkpoint.

SELF-CHECKING, because a sweep that only reports volume is how the has_property mistake happened. Every
CHECK_EVERY pages it scores its own output against ConceptNet and prints agreement beside the count. If
agreement falls, that is visible in the log at the time rather than in the morning.

EVERYTHING LANDS AS A CANDIDATE. Default-deny; promotion stays the operator gate. Nothing here touches
production and nothing here reaches the network -- the dump is local.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.cloud_brain.wikipedia_dump_reader import iter_wikipedia_sentences   # noqa: E402
from packages.graph_scale.property_extraction import extract                      # noqa: E402

DUMP = Path("data/knowledge_sources/enwiki-full.xml.bz2")
LEDGER = Path("data/cloud_brain/derived_candidates")
CONCEPTNET = Path("data/perception/concept_properties.json")
STATE = Path("data/perception/wiki_property_sweep_state.json")
LOG = Path("data/perception/wiki_property_sweep_log.jsonl")
LEAD_SENTENCES = 4
FLUSH_PAGES = 20000
CHECK_EVERY = 200000

# Titles that are not things. "List of", "2019 in film", disambiguation pages: mining these attributes
# facts to a page rather than to an object.
BAD_TITLE = re.compile(r"^(list|index|timeline|outline|history|glossary|comparison|table|"
                       r"category|portal|template|draft)\b", re.I)


def _subject_of(title: str) -> str | None:
    """The article title as a thing, or None. Conservative: a rejected page costs nothing.

    The first version of this folded a lowercase-start test into a re.I pattern, where [a-z] matches
    capitals too, so it rejected every article on the dump. 301 titles in and 0 accepted is not a strict
    filter, it is a broken one -- which is why the smoke run is 4,000 pages and not the whole 25 GB."""
    t = title.strip()
    if not t or BAD_TITLE.match(t) or len(t.split()) > 3:
        return None
    if not t[0].isupper():
        return None
    if not re.fullmatch(r"[A-Za-z][A-Za-z\- ]{2,40}", t):
        return None
    return t.lower()


def _is_about(subject: str, sentence: str, index: int) -> bool:
    """Does this lead sentence assert something about the article's subject, or about something else?"""
    s = sentence.strip()
    low = s.lower()
    if low.startswith(subject):
        return True
    for art in ("the ", "a ", "an "):
        if low.startswith(art + subject):
            return True
    return index > 1 and (low.startswith("it ") or low.startswith("they "))


def _agreement(by_pred) -> dict:
    """Score what has been mined so far against ConceptNet -- an independent source, not my patterns."""
    if not CONCEPTNET.exists():
        return {}
    ref = json.loads(CONCEPTNET.read_text(encoding="utf-8"))
    ref_by = {}
    for concept, feats in ref.items():
        d = collections.defaultdict(set)
        for f in feats:
            rel, _, obj = f.partition(":")
            d[rel].add(obj.replace("_", " "))
        ref_by[concept] = d
    NAME = {"used_for": "UsedFor", "capable_of": "CapableOf", "made_of": "MadeOf"}
    out = {}
    for pred, cn in NAME.items():
        mine = collections.defaultdict(set)
        for s, o in by_pred.get(pred, ()):
            mine[s].add(o)
        ok = tot = 0
        for s, objs in mine.items():
            have = ref_by.get(s, {}).get(cn)
            if not have:
                continue
            tot += 1
            ok += any(any(w in h or h in w for w in o.split()) for o in objs for h in have)
        out[pred] = {"checkable": tot, "agreed": ok, "agreement": (ok / tot) if tot else None}
    return out


def _flush(by_pred, seen) -> int:
    LEDGER.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    written = 0
    for pred, rows in by_pred.items():
        path = LEDGER / f"wiki_lead_{pred}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            for s, o in sorted(rows):
                if (pred, s, o) in seen:
                    continue
                seen.add((pred, s, o))
                fh.write(json.dumps({"s": s, "p": pred, "o": o, "weight": 1.0,
                                     "src": "wikipedia_lead", "tier": "candidate", "at": now}) + "\n")
                written += 1
    return written


def _load_seen() -> set:
    seen = set()
    for path in LEDGER.glob("wiki_lead_*.jsonl"):
        for ln in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
                seen.add((r["p"], r["s"], r["o"]))
            except Exception:
                pass
    return seen


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--resume", action="store_true", help="skip pages already swept")
    ap.add_argument("--require-complement", action="store_true",
                    help="drop bare-verb capable_of rows; see the module docstring for the A/B")
    args = ap.parse_args()
    if not DUMP.exists():
        sys.exit(f"no dump at {DUMP}")

    skip_to = 0
    if args.resume and STATE.exists():
        skip_to = int(json.loads(STATE.read_text(encoding="utf-8")).get("pages_done", 0))
        print(f"resuming: skipping the first {skip_to:,} pages")
    seen = _load_seen()
    print(f"{len(seen):,} candidate rows already on disk")
    print(f"reading {DUMP} ({DUMP.stat().st_size / 1e9:.1f} GB) -- leads only, "
          f"structure kept, text discarded")
    print(f"{'pages':>12}{'subjects':>11}{'used_for':>10}{'capable_of':>12}{'made_of':>9}"
          f"{'rows/1k pg':>12}{'elapsed':>10}")

    by_pred = collections.defaultdict(set)
    totals = collections.Counter()
    pages = 0
    subjects = set()
    last_title = None
    subject = None
    started = time.time()
    written_total = 0
    LOG.parent.mkdir(parents=True, exist_ok=True)

    for rec in iter_wikipedia_sentences(DUMP, max_pages=None):
        if rec.title != last_title:
            last_title = rec.title
            pages += 1
            subject = _subject_of(rec.title)
            if pages % FLUSH_PAGES == 0:
                w = _flush(by_pred, seen)
                written_total += w
                for k, v in by_pred.items():
                    totals[k] += len(v)
                by_pred.clear()
                el = time.time() - started
                print(f"{pages:>12,}{len(subjects):>11,}{totals['used_for']:>10,}"
                      f"{totals['capable_of']:>12,}{totals['made_of']:>9,}"
                      f"{written_total / max(pages / 1000, 1):>12.1f}"
                      f"{el / 3600:>9.2f}h")
                STATE.write_text(json.dumps({"pages_done": pages, "rows": written_total,
                                             "totals": dict(totals),
                                             "elapsed_h": el / 3600}, indent=2), encoding="utf-8")
            if pages % CHECK_EVERY == 0:
                agree = _agreement({k: {(s, o) for s, o in v} for k, v in
                                    _reload_for_check().items()})
                with LOG.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"pages": pages, "rows": written_total,
                                         "agreement": agree}) + "\n")
                line = "  ".join(f"{k} {v['agreement']:.3f} (n={v['checkable']})"
                                 for k, v in agree.items() if v.get("agreement") is not None)
                print(f"    self-check at {pages:,} pages: {line or 'nothing checkable yet'}")
            if args.max_pages and pages > args.max_pages:
                break
        if skip_to and pages <= skip_to:
            continue
        if not subject or rec.sentence_index > LEAD_SENTENCES:
            continue
        if not _is_about(subject, rec.text, rec.sentence_index):
            continue
        for pred, obj in extract(subject, rec.text,
                                 require_complement=args.require_complement):
            by_pred[pred].add((subject, obj))
            subjects.add(subject)

    w = _flush(by_pred, seen)
    written_total += w
    for k, v in by_pred.items():
        totals[k] += len(v)
    agree = _agreement(_reload_for_check())
    el = time.time() - started
    print(f"\nswept {pages:,} pages in {el / 3600:.2f}h -> {written_total:,} candidate rows "
          f"over {len(subjects):,} subjects")
    for k, v in sorted(agree.items()):
        if v.get("agreement") is not None:
            print(f"  {k:<12} agreement {v['agreement']:.3f}  (checkable {v['checkable']:,})")
    STATE.write_text(json.dumps({"pages_done": pages, "rows": written_total,
                                 "totals": dict(totals), "elapsed_h": el / 3600,
                                 "agreement": agree, "tier": "candidate", "promoted": 0},
                                indent=2), encoding="utf-8")
    print(f"wrote {STATE}  |  ledger {LEDGER}  |  CANDIDATE tier, nothing promoted")


def _reload_for_check() -> dict:
    """Read back what is on disk, so the self-check scores the ledger and not an in-memory window."""
    out = collections.defaultdict(set)
    for path in LEDGER.glob("wiki_lead_*.jsonl"):
        for ln in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
                out[r["p"]].add((r["s"], r["o"]))
            except Exception:
                pass
    return out


if __name__ == "__main__":
    main()
