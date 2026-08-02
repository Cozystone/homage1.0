# -*- coding: utf-8 -*-
"""How much of the Wikipedia sweep is about THINGS rather than about named entities? Measured.

    python scripts/wiki_rows_that_are_about_things.py

WHY. The lead-sentence sweep finished: 6,899,110 pages in 1.69 hours, 91,881 candidate rows over 87,077
subjects, which is 2.8x what the whole store holds for capable_of. Then reading twelve rows at random
showed the number was the wrong thing to be pleased about:

    glycolonitrile        dissolve in water                     right
    halymenia             grow in oceans worldwide              right
    obeticholic acid      treat primary biliary cholangitis     right
    red comet             examine sylvia plath                  a book ABOUT Plath, not a capability
    young trudeau         deal with his parents                 a biography's contents
    mutapa empire         border zambezi                        an empire is not a thing with abilities
    miss campeche         select state representative           a pageant

The census that started this work found the store's property axes were songs, genes and ISS missions --
named entities carrying database edges rather than things a person points at. Reading LEAD SENTENCES
fixed the REGISTER (a lead is a definition, so it states obvious properties encyclopedic prose omits) and
did nothing about the POPULATION, because Wikipedia's articles are mostly about named entities however
you read them. The title filter allowed three words and any capitalised title, so Mutapa Empire, Young
Trudeau and Nitro Motorsports all walked in.

The agreement figures had already said this and I under-weighted them: capable_of 0.235 against the
dictionary lane's 0.317 over a genuinely common-noun population.

SO THE QUESTION IS WHETHER THE PILE IS SALVAGEABLE, and it is a measurement rather than an opinion: keep
only rows whose subject is a COMMON NOUN the dictionary knows -- one word, listed in Kaikki as a noun --
and score that subset the same way. If agreement rises sharply the sweep produced a usable lane hiding
inside a mixed one; if it does not, the register was never the problem and the sweep needs a different
population, not a different filter.

Nothing is deleted. The filter writes a separate lane and the original stays as it was harvested.
"""
from __future__ import annotations

import collections
import gzip
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LEDGER = Path("data/cloud_brain/derived_candidates")
KAIKKI = Path("data/graph_scale/kaikki-en.jsonl.gz")
CONCEPTNET = Path("data/perception/concept_properties.json")
OUT = Path("data/perception/wiki_rows_about_things.json")
RELS = ("used_for", "capable_of", "made_of")
CN = {"used_for": "UsedFor", "capable_of": "CapableOf", "made_of": "MadeOf"}


def common_nouns() -> set[str]:
    """Single-word nouns the dictionary lists. A named entity is not in here as a common noun."""
    out: set[str] = set()
    with gzip.open(KAIKKI, "rt", encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("pos") != "noun":
                continue
            w = (d.get("word") or "").strip().lower()
            if w and re.fullmatch(r"[a-z]{3,20}", w):
                out.add(w)
    return out


def agreement(pairs, rel: str, ref_by) -> tuple[int, int]:
    """(checkable, agreed) against ConceptNet — an independent source, not the patterns that mined this."""
    mine = collections.defaultdict(set)
    for s, o in pairs:
        mine[s].add(o)
    ok = tot = 0
    for s, objs in mine.items():
        have = ref_by.get(s, {}).get(CN[rel])
        if not have:
            continue
        tot += 1
        ok += any(any(w in h or h in w for w in o.split()) for o in objs for h in have)
    return tot, ok


def main() -> None:
    if not CONCEPTNET.exists():
        sys.exit(f"no {CONCEPTNET}")
    ref = json.loads(CONCEPTNET.read_text(encoding="utf-8"))
    ref_by = {}
    for concept, feats in ref.items():
        d = collections.defaultdict(set)
        for f in feats:
            rel, _, obj = f.partition(":")
            d[rel].add(obj.replace("_", " "))
        ref_by[concept] = d

    print("reading the dictionary for the common-noun vocabulary ...")
    nouns = common_nouns()
    print(f"  {len(nouns):,} single-word common nouns\n")

    print(f"{'relation':<13}{'rows':>9}{'about things':>14}{'kept':>7}"
          f"{'agreement all':>15}{'agreement things':>18}")
    report = {}
    for rel in RELS:
        path = LEDGER / f"wiki_lead_{rel}.jsonl"
        if not path.exists():
            continue
        allp, thing = [], []
        for ln in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except Exception:
                continue
            allp.append((r["s"], r["o"]))
            if r["s"] in nouns:
                thing.append((r["s"], r["o"]))
        t_all, ok_all = agreement(allp, rel, ref_by)
        t_thg, ok_thg = agreement(thing, rel, ref_by)
        a_all = ok_all / t_all if t_all else float("nan")
        a_thg = ok_thg / t_thg if t_thg else float("nan")
        report[rel] = {"rows": len(allp), "rows_about_things": len(thing),
                       "kept": len(thing) / max(len(allp), 1),
                       "agreement_all": a_all, "checkable_all": t_all,
                       "agreement_things": a_thg, "checkable_things": t_thg}
        print(f"{rel:<13}{len(allp):>9,}{len(thing):>14,}{len(thing) / max(len(allp), 1):>7.1%}"
              f"{a_all:>15.3f}{a_thg:>18.3f}")
        out = LEDGER / f"wiki_thing_{rel}.jsonl"
        with out.open("w", encoding="utf-8") as fh:
            for s, o in thing:
                fh.write(json.dumps({"s": s, "p": rel, "o": o, "weight": 1.0,
                                     "src": "wikipedia_lead_common_noun", "tier": "candidate"}) + "\n")

    rose = [r for r in report.values()
            if r["checkable_things"] >= 10 and r["agreement_things"] > r["agreement_all"] + 0.05]
    print()
    print(f"-> restricting to common nouns raises agreement on {len(rose)} of {len(report)} relations")
    print("   dictionary lane, for comparison: used_for 0.559  capable_of 0.317  made_of 0.400")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"vocabulary": len(nouns), "by_relation": report,
                               "dictionary_lane_reference": {"used_for": 0.559, "capable_of": 0.317,
                                                             "made_of": 0.400},
                               "note": "nothing deleted; the filtered rows are written to a separate "
                                       "wiki_thing_* lane and the harvested lane is untouched."},
                              indent=2), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
