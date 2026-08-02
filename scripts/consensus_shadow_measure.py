# -*- coding: utf-8 -*-
"""What the two-domain gate costs on property relations — measured WITHOUT touching the gate.

    python scripts/consensus_shadow_measure.py --limit 3000

THE FINDING THIS EXISTS TO QUANTIFY. Running the acquisition loop on ATANOR's own corpora, with no
network and no rate limit, still landed nothing, and the reason is not a bug:

    trowel [used for]
      en.wikipedia.org   digging, finish concrete floors, masonry, tiling
      en.wiktionary.org  spreading
      -> every object appears in exactly ONE domain

Two independent sources describe the same tool with different, non-overlapping purposes, and both are
right. The two-domain rule was built for FUNCTIONAL relations: "the capital of France" has one answer, so
two sources naming different answers means one is wrong and disagreement is evidence of error. A property
relation is SET-VALUED -- each source names a different subset of a true set -- so requiring the same
element from two sources is requiring a coincidence rather than testing a claim.

WHY THIS SCRIPT MEASURES INSTEAD OF FIXING. Changing the floor changes the standard of evidence for what
may enter ATANOR's graph, which is the owner's decision, not mine; and "the gate is too strict" is what
every wrong repair sounds like from the inside. So nothing here writes to the ledger, nothing calls
`acquire`, and the production floor is untouched. This runs the same evidence and the same extractor and
tallies the result at several floors side by side, so the decision can be made against numbers and a
readable sample rather than against my summary of one example.

READ THE SAMPLE, NOT ONLY THE TABLE. The question is not "how much more would land" -- a lower floor
always lands more. The question is whether what lands at floor 1 is TRUE, and only reading it answers
that.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.knowledge_acquisition.consensus import canonical_object          # noqa: E402
from packages.knowledge_acquisition.evidence import LocalIndexEvidence         # noqa: E402
from packages.knowledge_acquisition.relation_extract import (                  # noqa: E402
    extract_from_documents)

_STOP = {"a", "an", "the", "of", "for", "to", "in", "on", "with", "and", "or", "by", "as", "at",
         "from", "into", "that", "which", "it", "its", "their", "other", "such", "some", "any",
         "one", "two", "used", "using", "use", "make", "made", "makes", "be", "being", "been", "is",
         "are", "was", "were", "can", "may", "also", "very", "more", "most", "etc"}


def _stem(w: str) -> str:
    """Crude suffix stripping, so scoring and score-keeping share a token. A hand rule, and it lives
    HERE rather than in the consensus organ precisely because it is one -- this file measures, it does
    not decide."""
    for suf in ("ations", "ation", "ings", "ing", "ies", "ers", "er", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[:-len(suf)]
            break
    return w


def content_words(obj: str) -> frozenset:
    toks = [t for t in __import__("re").split(r"[^a-z]+", obj.lower()) if t]
    return frozenset(_stem(t) for t in toks if t not in _STOP and len(t) > 2)


def paraphrase_key(objs):
    """Group objects whose content words are SUBSETS of one another, keeping the fullest surface form.

    Subset containment is deliberately conservative. It merges lawns into cut-grass-on-lawns and scoring
    into score-keeping -- both genuinely the same claim at different specificity, where the shorter is
    entailed by the longer. It does NOT merge transporting-infants with transporting-babies, which are
    also the same claim; missing those is the price of not merging things that merely look alike, and a
    matcher that manufactures agreement is worse than a floor that is too high."""
    items = [(o, content_words(o)) for o in objs]
    items = [(o, cw) for o, cw in items if cw]
    items.sort(key=lambda t: -len(t[1]))
    groups: list[tuple[str, frozenset, list[str]]] = []
    for o, cw in items:
        for i, (rep, rcw, members) in enumerate(groups):
            if cw <= rcw or rcw <= cw:
                members.append(o)
                groups[i] = (rep, rcw | cw if rcw <= cw else rcw, members)
                break
        else:
            groups.append((o, cw, [o]))
    return {m: rep for rep, _cw, members in groups for m in members}


QUESTIONS = Path("data/acquisition_daemon/deficit_questions.txt")
OUT = Path("data/perception/consensus_shadow.json")
NEAR = Path("data/perception/consensus_shadow_rows.jsonl")
MERGED = Path("data/perception/consensus_shadow_merges.jsonl")
FLOORS = (1, 2, 3)
ASK = {"used for": "used_for", "capable of": "capable_of", "made of": "made_of"}


def parse(question: str):
    from packages.base_brain.relational_lookup import parse_relational_shape
    shape = parse_relational_shape(question)
    if not shape:
        return None
    ent = str(shape.get("entity") or "").strip().lower()
    rel = str(shape.get("rel_norm") or "").strip().lower()
    return (ent, rel) if ent and rel in ASK else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=3000)
    ap.add_argument("--questions", type=Path, default=QUESTIONS)
    args = ap.parse_args()
    if not args.questions.exists():
        sys.exit(f"no {args.questions}")

    ev = LocalIndexEvidence()
    lines = [ln.strip() for ln in args.questions.read_text(encoding="utf-8").splitlines()
             if ln.strip()][:args.limit]
    print(f"{len(lines):,} questions, evidence = ATANOR's own corpora only (no network)")
    print(f"{'asked':>8}{'with docs':>11}{'with sightings':>16}"
          + "".join(f"{'floor ' + str(f):>10}" for f in FLOORS))

    seen_docs = sightings = 0
    landed = {f: 0 for f in FLOORS}
    landed_p = {f: 0 for f in FLOORS}
    mfh = MERGED.open("w", encoding="utf-8")
    per_rel = collections.defaultdict(lambda: {"asked": 0, **{f: 0 for f in FLOORS}})
    domains = collections.Counter()
    NEAR.parent.mkdir(parents=True, exist_ok=True)
    fh = NEAR.open("w", encoding="utf-8")
    asked = 0
    for q in lines:
        got = parse(q)
        if not got:
            continue
        ent, rel = got
        asked += 1
        per_rel[rel]["asked"] += 1
        docs = ev.documents(ent, rel, q)
        if docs:
            seen_docs += 1
            domains.update(u.split("/")[2] for u, _t in docs)
        pairs = extract_from_documents(docs, ent, rel)
        if pairs:
            sightings += 1
        by = collections.defaultdict(set)
        for obj, url in pairs:
            by[canonical_object(obj)].add(url.split("/")[2])
        best = max((len(v) for v in by.values()), default=0)
        # THE SAME TALLY under paraphrase grouping, run beside the exact one rather than replacing it,
        # so the two are comparable on identical evidence.
        rep = paraphrase_key(list(by))
        merged = collections.defaultdict(set)
        for k, doms in by.items():
            merged[rep.get(k, k)] |= doms
        best_p = max((len(v) for v in merged.values()), default=0)
        for f in FLOORS:
            if best >= f:
                landed[f] += 1
                per_rel[rel][f] += 1
            if best_p >= f:
                landed_p[f] += 1
        if best_p > best:
            groups = collections.defaultdict(list)
            for k in by:
                groups[rep.get(k, k)].append(k)
            for r, ms in groups.items():
                if len(ms) > 1 and len(merged[r]) > max(len(by[m]) for m in ms):
                    mfh.write(json.dumps({"entity": ent, "relation": ASK[rel], "merged_into": r,
                                          "from": ms,
                                          "domains": sorted(merged[r])}) + chr(10))
        if by:
            fh.write(json.dumps({"entity": ent, "relation": ASK[rel], "n_docs": len(docs),
                                 "max_domains": best,
                                 "objects": {k: sorted(v) for k, v in
                                             sorted(by.items(), key=lambda kv: -len(kv[1]))[:6]}}) + "\n")
        if asked % 500 == 0:
            print(f"{asked:>8,}{seen_docs:>11,}{sightings:>16,}"
                  + "".join(f"{landed[f]:>10,}" for f in FLOORS), flush=True)
    fh.close()
    mfh.close()
    print(f"{asked:>8,}{seen_docs:>11,}{sightings:>16,}"
          + "".join(f"{landed[f]:>10,}" for f in FLOORS))
    print(f"{'':>8}{'':>11}{'with paraphrase':>16}"
          + "".join(f"{landed_p[f]:>10,}" for f in FLOORS))

    print()
    print(f"{'relation':<14}{'asked':>8}" + "".join(f"{'floor ' + str(f):>10}" for f in FLOORS))
    for rel, d in sorted(per_rel.items()):
        print(f"{ASK[rel]:<14}{d['asked']:>8,}" + "".join(f"{d[f]:>10,}" for f in FLOORS))
    print()
    print("corpora that answered:", dict(domains.most_common(6)))
    print(f"\nthe production floor is {FLOORS[1]} and is UNCHANGED by this script.")
    print(f"read {MERGED} to judge the paraphrase grouping -- a matcher that manufactures "
          f"agreement is worse than a floor that is too high.")
    print(f"read {NEAR} before deciding anything -- a lower floor always lands more, and whether what "
          f"it lands is TRUE is a question only the rows answer.")

    OUT.write_text(json.dumps({"asked": asked, "with_docs": seen_docs,
                               "with_sightings": sightings,
                               "landed_by_floor": {str(f): landed[f] for f in FLOORS},
                               "landed_by_floor_paraphrase": {str(f): landed_p[f] for f in FLOORS},
                               "by_relation": {ASK[r]: {str(k): v for k, v in d.items()}
                                               for r, d in per_rel.items()},
                               "corpora": dict(domains),
                               "evidence": "LocalIndexEvidence (wikipedia + wiktionary), no network",
                               "production_floor": 2, "floor_changed": False},
                              indent=2), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
