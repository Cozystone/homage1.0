# -*- coding: utf-8 -*-
"""Mine what a thing is FOR and what it can DO from dictionary definitions — the starved relations.

    python scripts/mine_object_properties_from_glosses.py mine     # -> candidate ledger, default-deny
    python scripts/mine_object_properties_from_glosses.py check    # agreement against ConceptNet

WHY THESE THREE RELATIONS AND WHY FROM A DICTIONARY. A census of the production store, 115,455,726
triples, found the attribute mass sitting almost entirely in structure:

    part_of 3,828,705   has_a 2,282,294   made_of 1,300,565        (96% of attribute triples)
    has_property 196,813   used_for 39,673   capable_of 22,662     (0.24% of the store)
    desires 0 -- the predicate exists in the dictionary and nothing was ever written under it

The store knows what things are BUILT FROM and what they BELONG TO. It barely knows what they are FOR,
what they can DO, or what they are LIKE -- which are the axes human object representations mostly turn on
(Hebart et al. 2020). Held-out effective dimensionality: 5.13 for the vision encoder, ~49 for people.

AND THE PROVENANCE EXPLAINS THE GAP. The store's sources.txt is wikidata plus encyclopedia and wiki
articles about NAMED ENTITIES. Those state occupation, country, author, employer -- and they never state
that a knife is used for cutting, because it is too obvious to write down. That is reporting bias (Gordon
and Van Durme, 2013), and no amount of crawling more encyclopedia fixes it: the fact is missing from that
register by definition.

A DICTIONARY IS THE ONE REGISTER WHOSE JOB IS STATING THE OBVIOUS. kaikki-en is already on disk, 492 MB,
already used by this project, and its noun glosses are genus-differentia by editorial convention:

    portmanteau   A large travelling case usually MADE OF LEATHER, and opening into two equal sections.
    thesaurus     A publication that PROVIDES SYNONYMS for the words of a language.
    dictionary    A reference work LISTING WORDS or names ... EXPLAINING their meanings.

No crawl, no new dataset, no external model. The patterns below are hand-written and that is a stated
compromise, not the destination -- this repository's rule is that hand rules are training wheels. They are
defensible HERE because the corpus is deliberately formulaic: lexicographers write to a house style, so a
pattern over a dictionary is reading a convention rather than guessing at free text. What makes it
honest is that nothing is claimed about precision; precision is MEASURED against an independent source.

MEASURED, 2026-07-31, over 598,510 noun entries and 334,310 definitional glosses:

    relation      candidates   subjects   in store today   agreement with ConceptNet
    used_for           7,950      7,738           39,673   0.559  (186 checkable)
    made_of            1,828      1,801        1,300,565   0.400  (15 checkable)
    capable_of           593        593           22,662   0.118  (17 checkable)

AGREEMENT IS A LOWER BOUND ON PRECISION, not precision, and the sample says so plainly: bath -> "bathing"
is scored DIFFER because ConceptNet phrases it "cleaning baby". Real extractions counted as
disagreements include dynamite -> mining, flour -> bake bread, hay -> fodder, runway -> access. The
readable sample the `check` command prints is better evidence than the ratio, which is why it prints one.

capable_of at 593 is the honest weak spot. Dictionaries write "a bird that flies", not "that can fly", so
the pattern that looks for a modal barely fires. Extracting the verb out of a relative clause is the fix
and it is not written, so capable_of stays thin.

EVERYTHING LANDS AS A CANDIDATE. Same ledger, same format and same default-deny gate the ConceptNet
connector already writes to. Nothing here touches production; promotion stays the operator gate.
"""
from __future__ import annotations

import collections
import gzip
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.graph_scale.property_extraction import extract                      # noqa: E402

KAIKKI = Path("data/graph_scale/kaikki-en.jsonl.gz")
LEDGER = Path("data/cloud_brain/derived_candidates")
CONCEPTNET = Path("data/perception/concept_properties.json")
REPORT = Path("data/perception/gloss_mining_report.json")

# Glosses that define a WORD rather than a THING. Mining these produces relations about spelling.
SKIP = re.compile(r"^\s*(abbreviation|alternative|alt\.|plural|singular|initialism|acronym|obsolete|"
                  r"synonym|misspelling|archaic form|clipping|contraction|ellipsis|short for|"
                  r"commonwealth|american|british|dated form|eye dialect|honorific|nickname|"
                  r"surname|a male given name|a female given name|given name|any of|the act of)\b",
                  re.I)
STOP_OBJ = {"it", "them", "this", "that", "which", "something", "someone", "one", "other", "others",
            "a", "an", "the", "such", "these", "those", "its", "their", "his", "her", "any", "all"}

# Objects the patterns DID grab and should not have. Measured, not guessed: the first run's readable
# sample showed pawn -> "some end", plastic -> "place", skeleton -> "this sport", card -> "achieve a
# purpose". Every one is a gloss that names no purpose, only the shape of one.
GENERIC_OBJ = {"purpose", "purposes", "end", "ends", "place", "places", "access", "support", "use",
               "uses", "thing", "things", "means", "way", "ways", "form", "forms", "type", "types",
               "kind", "kinds", "sort", "part", "parts", "person", "people", "someone", "something",
               "example", "reference", "sport", "game", "activity", "process", "action", "effect",
               "result", "purposeful", "personify", "represent", "denote", "indicate", "refer"}
DEICTIC = re.compile(r"\b(this|that|these|those|such|some|any|it)\b", re.I)

# The patterns, the generic-object filter and the relative-clause verb rule now live in
# packages/graph_scale/property_extraction, because a second harvester (the Wikipedia lead
# sweep) needs the same judgement and two copies of a judgement drift apart.


def mine(limit: int | None = None) -> None:
    if not KAIKKI.exists():
        sys.exit(f"no dictionary at {KAIKKI}")
    by_pred: dict[str, set] = collections.defaultdict(set)
    words = glosses = 0
    with gzip.open(KAIKKI, "rt", encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("pos") != "noun":
                continue
            w = (d.get("word") or "").strip().lower()
            if not w or not re.fullmatch(r"[a-z][a-z\-]*", w):
                continue
            words += 1
            for sense in d.get("senses", [])[:3]:
                g = (sense.get("glosses") or [""])[0]
                if not g or SKIP.match(g):
                    continue
                glosses += 1
                for pred, o in extract(w, g):
                    by_pred[pred].add((w, o))
                # has_property USED TO BE MINED HERE and was cut after measurement, not before. An
                # adjective standing between the article and the genus noun produced 230,050 candidates
                # over 117,695 subjects -- more than the whole store holds -- at 0.108 agreement with
                # ConceptNet against used_for's 0.547. Volume was the tell: the pattern fires on every
                # definition, so it was harvesting sentence shape rather than properties. The rows it
                # wrote are set aside as .rejected rather than deleted, so the evidence stays readable.
            if limit and words >= limit:
                break
    total = sum(len(v) for v in by_pred.values())
    print(f"{words:,} noun entries, {glosses:,} definitional glosses -> {total:,} candidates")
    print()
    print(f"{'relation':<16}{'candidates':>12}{'distinct subjects':>20}{'in store today':>16}")
    store_today = {"used_for": 39673, "capable_of": 22662, "has_property": 196813, "made_of": 1300565}
    for pred in sorted(by_pred, key=lambda k: -len(by_pred[k])):
        subs = len({s for s, _o in by_pred[pred]})
        print(f"{pred:<16}{len(by_pred[pred]):>12,}{subs:>20,}{store_today.get(pred, 0):>16,}")

    LEDGER.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    written = 0
    for pred, rows in by_pred.items():
        path = LEDGER / f"kaikki_gloss_{pred}.jsonl"
        seen = set()
        if path.exists():
            for ln in path.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(ln)
                    seen.add((r.get("s"), r.get("o")))
                except Exception:
                    pass
        with path.open("a", encoding="utf-8") as out:
            for s, o in sorted(rows):
                if (s, o) in seen:
                    continue
                seen.add((s, o))
                out.write(json.dumps({"s": s, "p": pred, "o": o, "weight": 1.0,
                                      "src": "kaikki_gloss", "tier": "candidate", "at": now}) + "\n")
                written += 1
    print()
    print(f"wrote {written:,} candidate rows to {LEDGER} -- CANDIDATE tier, nothing promoted")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"noun_entries": words, "glosses": glosses,
                                  "candidates": {k: len(v) for k, v in by_pred.items()},
                                  "subjects": {k: len({s for s, _ in v}) for k, v in by_pred.items()},
                                  "store_today": store_today, "written": written,
                                  "tier": "candidate", "promoted": 0}, indent=2), encoding="utf-8")
    print(f"wrote {REPORT}")


def check(sample: int = 25) -> None:
    """Agreement with ConceptNet where BOTH have an opinion — an independent source, not my patterns.

    This is a weak check and is reported as one. ConceptNet is itself crowd data with its own gaps, so
    disagreement is not proof of error; what it can catch is a pattern that is systematically producing
    junk, which would show up as agreement near zero."""
    if not CONCEPTNET.exists():
        sys.exit(f"no {CONCEPTNET}; run property_dimensions_from_text.py extract first")
    ref = json.loads(CONCEPTNET.read_text(encoding="utf-8"))
    ref_by = {}
    for concept, feats in ref.items():
        d = collections.defaultdict(set)
        for f in feats:
            rel, _, obj = f.partition(":")
            d[rel].add(obj.replace("_", " "))
        ref_by[concept] = d
    NAME = {"used_for": "UsedFor", "capable_of": "CapableOf", "made_of": "MadeOf",
            "has_property": "HasProperty"}
    rows = {}
    print(f"{'relation':<16}{'checkable':>11}{'agreed':>9}{'agreement':>12}")
    shown = []
    for pred, cn in NAME.items():
        path = LEDGER / f"kaikki_gloss_{pred}.jsonl"
        if not path.exists():
            continue
        mine_by = collections.defaultdict(set)
        for ln in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except Exception:
                continue
            mine_by[r["s"]].add(r["o"])
        ok = tot = 0
        for s, objs in mine_by.items():
            have = ref_by.get(s, {}).get(cn)
            if not have:
                continue
            tot += 1
            hit = any(any(w in h or h in w for w in o.split()) for o in objs for h in have)
            ok += hit
            if len(shown) < sample and tot % 7 == 0:
                shown.append(f"  {s:<14} {pred:<13} mine={sorted(objs)[:2]}  conceptnet={sorted(have)[:2]}"
                             f"  {'agree' if hit else 'DIFFER'}")
        rows[pred] = {"checkable_subjects": tot, "agreed": ok,
                      "agreement": (ok / tot) if tot else None}
        print(f"{pred:<16}{tot:>11,}{ok:>9,}{(ok / tot if tot else float('nan')):>12.3f}")
    print()
    print("a sample to read -- DIFFER is not automatically wrong, ConceptNet has its own gaps:")
    for s in shown[:sample]:
        print(s)
    if REPORT.exists():
        d = json.loads(REPORT.read_text(encoding="utf-8"))
        d["conceptnet_agreement"] = rows
        d["agreement_caveat"] = ("ConceptNet is crowd data with its own gaps, so disagreement is not "
                                 "proof of error. What this catches is a pattern producing junk, which "
                                 "would show as agreement near zero.")
        REPORT.write_text(json.dumps(d, indent=2), encoding="utf-8")
        print()
        print(f"updated {REPORT}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "mine"
    {"mine": mine, "check": check}.get(cmd, mine)()
