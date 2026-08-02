# -*- coding: utf-8 -*-
"""Concepts ATANOR has a WORD for and no PROPERTIES of — the deficit map curiosity aims at.

    python scripts/deficit_map.py                       # -> data/perception/deficit_map.json

WHY A MAP AND NOT A TOPIC LIST. Curiosity that picks topics is a random walk; curiosity that picks
MEASURED HOLES terminates when the hole closes. A hole here is exact and checkable: the term exists in
the store's dictionary, so ATANOR can say the word, and not one attribute triple has it as a subject, so
ATANOR can say nothing about what it is for, what it can do, or what it is made of.

WHY THE VOCABULARY COMES FROM A DICTIONARY. The store's own most-attributed concepts turned out to be
albums, genes and ISS missions -- a population of database records, not of things a person points at.
Taking the candidate list from Kaikki's common nouns fixes the population at the source: those ARE the
pointed-at things, which is the whole reason the owner put the dictionary first in the ladder.

THE SECOND SOURCE THIS REPLACES TONIGHT, and why. `acquisition_daemon.structural_gaps` is the designed
curiosity organ and its signal is better than this one -- it asks what the graph's OWN induced schema
says an entity should have. It also runs bincount and argsort across 115,455,726-row columns, which
measured 6.5 GB and climbing on this machine with 1.8 GB free, and would have taken the overnight
Wikipedia sweep down with it. So it is not disabled because it is wrong; it is disabled because it needs
a memory pass first, and that is daytime work with the owner awake.

The questions this emits go into the EXISTING daemon through `observe`, which records a real abstention
as pressure. Nothing here invents a new curiosity path.
"""
from __future__ import annotations

import collections
import gzip
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.graph_scale.triple_store import TripleStore                      # noqa: E402

STORE = Path("data/graph_scale/kg_triples")
KAIKKI = Path("data/graph_scale/kaikki-en.jsonl.gz")
OUT = Path("data/perception/deficit_map.json")
QUESTIONS = Path("data/acquisition_daemon/deficit_questions.txt")
ATTRIBUTE_PREDICATES = ("has_property", "capable_of", "used_for", "made_of", "part_of", "has_a",
                        "desires", "causes", "has_subevent")
# What to ask about a thing with no properties. These mirror the relations the census found starved.
ASK = [("used_for", "what is a {w} used for"),
       ("capable_of", "what can a {w} do"),
       ("made_of", "what is a {w} made of")]
SKIP_GLOSS = re.compile(r"^\s*(abbreviation|alternative|plural|singular|initialism|acronym|obsolete|"
                        r"synonym|misspelling|clipping|contraction|short for|surname|"
                        r"a male given name|a female given name|given name)\b", re.I)
MAX_WORDS = 20000


CONCRETE_GLOSS = re.compile(r"^\s*(?:A|An)\s+[a-z]")
# A definition that FRAMES the thing as an artifact or a material. Added after the first live batch
# returned 38 pursued and 0 queued: the questions were being asked of dale, folk, sweetheart, thingy,
# fir, martini, maple, drama and induction -- a valley, a people, an endearment, trees, a drink, an art
# form. "What is a fir used for" and "what is drama made of" have no answers to find, so the loop was
# fetching the web to confirm that nothing was there. The fix is the word list, not the consensus floor.
ARTIFACT_GLOSS = re.compile(
    r"\b(used\s+(?:for|to|in|as)|device|tool|instrument|machine|implement|utensil|container|vessel|"
    r"apparatus|equipment|garment|weapon|vehicle|made\s+(?:of|from)|furniture|appliance|fastener|"
    r"receptacle)\b", re.I)


def dictionary_nouns(limit: int = MAX_WORDS) -> list[str]:
    """Nouns that denote a concrete thing, ordered by how everyday the word is.

    TWO WRONG PROXIES CAME FIRST and both were caught by looking at what they actually produced,
    which is the only reason this one is defensible.

    Ranking by SENSE COUNT was backwards. I took "many senses" for "ordinary word", so the loop's
    first questions were bite, snap, buck, case, double, wash, sweep, tag, pop, load, miss, skip --
    verbs wearing a noun's clothes. Every one returned 0 object sightings or no consensus, because
    there is no single thing for "what is a snap made of" to be about.

    Ranking by WORD LENGTH was worse. Shortest-first produced aak, abb, abe, ack, ade, ail, ait, aja
    -- the three-letter corners of a dictionary, not the vocabulary anyone uses.

    WHAT ACTUALLY SEPARATES THEM is in the entry already. A common word has many DERIVED terms and an
    obscure one has none, which ranks cleanly across the words that had been tested by hand:

        dog 757   chair 193   spoon 93   ale 68   kettle 37   kestrel 13   trowel 8   bollard 3
        abb 1     aak 0

    (`translations` looks like the natural signal and is not: this dump carries them for almost
    nothing, so dog has 998 and kettle, chair and spoon all have 0.)

    And the failed words share one property the successful ones do not: they are ALSO VERBS. bite,
    snap, buck, wash and sweep each have a verb entry; trowel, bollard and kestrel do not. So a word
    that is also a verb is dropped outright rather than down-ranked -- the polysemy that breaks a
    property question is precisely verb-noun polysemy.

    The sense cap is gone with it. `dog` has 22 senses and is an excellent target; what mattered was
    never the count but whether the FIRST gloss names a countable thing, which the "A <lowercase>"
    test already checks.

    A THIRD CORRECTION came from the first live batch: 38 pursued, 0 queued. Common words are dominated
    by natural kinds, people and abstractions -- dale, folk, sweetheart, fir, martini, maple, drama,
    induction -- and the three questions asked of every word ("used for", "can do", "made of") presume
    an ARTIFACT. There is no answer anywhere for what a fir is used for, so the loop was spending web
    fetches to confirm an absence. ARTIFACT_GLOSS keeps only words whose own definition frames them as
    a made thing or a material, which is where those questions have answers to find, and the surviving
    head of the list reads road, car, cloth, camera, cutter, railway, borer, detector, battery.

    The consensus floor was NOT touched. Lowering a gate to manufacture yield is the one repair that is
    never allowed, and 0 out of 38 is a fact about the questions, not about the gate.
    """
    derived: dict[str, int] = {}
    first: dict[str, str] = {}
    is_verb: set[str] = set()
    with gzip.open(KAIKKI, "rt", encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            w = (d.get("word") or "").strip().lower()
            if not w or not re.fullmatch(r"[a-z]{3,20}", w):
                continue
            pos = d.get("pos")
            if pos == "verb":
                is_verb.add(w)
                continue
            if pos != "noun":
                continue
            good = [s["glosses"][0] for s in d.get("senses", [])
                    if s.get("glosses") and not SKIP_GLOSS.match(s["glosses"][0])]
            if not good:
                continue
            derived[w] = derived.get(w, 0) + len(d.get("derived") or []) + len(d.get("synonyms") or [])
            first.setdefault(w, good[0])
    keep = [w for w in derived
            if w not in is_verb
            and CONCRETE_GLOSS.match(first.get(w, ""))
            and ARTIFACT_GLOSS.search(first.get(w, ""))]
    return sorted(keep, key=lambda w: (-derived[w], w))[:limit]


def subjects_with_attributes(store: TripleStore) -> np.ndarray:
    """Every term id that is the SUBJECT of at least one attribute triple. One pass, sorted for
    searchsorted -- a python set of 3.6 million ints costs an order of magnitude more memory, and the
    machine is running an overnight sweep beside this."""
    ids = []
    for n in ATTRIBUTE_PREDICATES:
        i = store.terms.lookup(n)
        if i is not None:
            ids.append(int(i))
    if not ids:
        sys.exit("no attribute predicate resolved -- harness failure, not a finding")
    P = np.memmap(STORE / "p.col", dtype=np.int32, mode="r")
    S = np.memmap(STORE / "s.col", dtype=np.int32, mode="r")
    want = np.array(sorted(ids), dtype=np.int32)
    keep = []
    CH = 10_000_000
    for a in range(0, len(P), CH):
        m = np.isin(np.asarray(P[a:a + CH]), want)
        if m.any():
            keep.append(np.unique(np.asarray(S[a:a + CH])[m]))
    return np.unique(np.concatenate(keep)) if keep else np.array([], np.int32)


def main() -> None:
    store = TripleStore(str(STORE))
    print("reading the dictionary for the pointed-at population ...")
    words = dictionary_nouns()
    print(f"  {len(words):,} common nouns")
    print("one pass over the store for subjects that already carry an attribute ...")
    have = subjects_with_attributes(store)
    print(f"  {len(have):,} subjects have at least one attribute triple")

    known_word = missing = unknown_term = 0
    deficit: list[str] = []
    for w in words:
        tid = store.terms.lookup(w)
        if tid is None:
            unknown_term += 1                 # not even a word in the store: a different kind of hole
            continue
        known_word += 1
        idx = int(np.searchsorted(have, int(tid)))
        if idx < len(have) and int(have[idx]) == int(tid):
            continue
        missing += 1
        deficit.append(w)

    print()
    print(f"{'dictionary nouns':<34}{len(words):>10,}")
    print(f"{'  term exists in the store':<34}{known_word:>10,}")
    print(f"{'  term not in the store at all':<34}{unknown_term:>10,}")
    print(f"{'  WORD BUT NO PROPERTIES':<34}{missing:>10,}   <- the deficit")
    if known_word:
        print(f"{'  deficit share of known words':<34}{missing / known_word:>9.1%}")

    QUESTIONS.parent.mkdir(parents=True, exist_ok=True)
    lines = [tmpl.format(w=w) for w in deficit for _rel, tmpl in ASK]
    QUESTIONS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"dictionary_nouns": len(words), "known_word": known_word,
                               "unknown_term": unknown_term, "deficit": missing,
                               "questions_written": len(lines),
                               "relations_asked": [r for r, _t in ASK],
                               "sample": deficit[:40]}, indent=2), encoding="utf-8")
    print()
    print(f"sample: {', '.join(deficit[:16])}")
    print(f"wrote {OUT}")
    print(f"wrote {QUESTIONS}  ({len(lines):,} questions)")


if __name__ == "__main__":
    main()
