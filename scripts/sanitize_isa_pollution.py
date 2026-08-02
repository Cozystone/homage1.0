# -*- coding: utf-8 -*-
"""Retract is_a edges that the clean phase space says are noise. DRY RUN by default.

!! DO NOT --apply YET. MEASURED 2026-07-17: THE SIGNAL DOES NOT GENERALISE. !!
 Dry run over 48 hub subjects: 5304 is_a rows examined, 1266 (23%) would be retracted.
 Auditing a random sample of those decisions says the resonance gate is only trustworthy on
 CONCRETE subjects, which is the only place it was validated:

 concrete (works) crocodile: reptile .739 / crocodilian reptile .797 vs action .081
 abstract (fails) KEEPS obvious junk — justice --> 'chemical phenomenon',
 courage --> 'subjective created mythology', democracy --> 'amount',
 democracy --> 'thing', art --> '', force --> ''
 and DROPS a defensible edge — democracy -x-> 'representative'

 So applying this would tombstone 1266 rows, destroy some real knowledge, and STILL leave the
 abstract pollution behind. That is worse than the disease. The read-time gate in
 dual_brain._english_compare_answer stands because it was measured on the case it fixes;
 generalising that one measurement into a store-wide write is exactly the over-reach this file
 now documents.

THREE SIGNALS TRIED. ALL THREE FAIL, EACH DIFFERENTLY. (2026-07-17)
 1. subject->parent resonance Concrete: clean (.72-.80 vs .08-.35). Abstract: keeps junk
 (justice/'chemical phenomenon' passes) and drops real
 (democracy/'representative').
 2. source provenance No information: EVERY is_a row is src=0 "curated:legacy", good
 and bad alike (crocodile 388/388, justice 259/259, courage
 388/388). These rows predate the provenance system.
 3. sibling resonance Best of the three, and still unusable. On hand-picked cases it
 looked decisive (REAL .81-.82 vs junk .13-.51), but the FULL
 distribution over 5255 scored edges overlaps:
 .65-.80 holds junk (gravity -> 'feeling' .76)
 .30-.65 holds real (friendship -> '' .45 = trust)
 and the bottom band, which looked uniformly junk, is NOT:
 science -> '' scores -0.17 and is a TRUE parent
 ( = academic discipline; science IS one).
 It fails on CROSS-LINGUAL edges — 's other children are
 Korean, so an English subject cannot resonate with them.
 cf. gravity -> '' .04, correctly junk. The signal cannot
 tell those two apart.

 Every threshold destroys real knowledge. There is NO signal in this store today that
 separates real is_a from junk across abstract and cross-lingual edges. This sweep is not
 blocked by caution — it is blocked by the absence of evidence, and tombstoning on a signal
 measured insufficient would be fabrication-by-deletion.

WHAT WOULD ACTUALLY UNBLOCK IT (in rough order of cost)
 a. Re-ingest is_a with provenance so k-source consensus becomes computable (the store already
 has the machinery: intern_source/src.col/source_of — only the legacy rows lack it).
 b. A learned edge-validity discriminator trained where resonance IS reliable (concrete,
 same-language), held out on abstract AND cross-lingual pairs before any write.
 c. Language-aware siblings: TRIED (2026-07-17). ALSO FAILS, and worse than the others —
 scoring against same-language children only does not separate at all:
 science -> '' REAL .366 gravity -> '' junk .342 (0.024 apart)
 friendship -> '' REAL .449 democracy -> 'thing' junk .512 (INVERTED)
 Real edges now score BELOW junk edges. This closes the structural family: the phase space
 simply does not encode is_a validity for abstract or cross-lingual pairs, and no threshold
 over it can. Path (b), a learned discriminator with a held-out abstract+cross-lingual set,
 is the only one left standing — and it must beat these numbers on that holdout BEFORE any
 write, not after.

WHY THIS EXISTS
 The cartridge's is_a is heavily polluted: 'crocodile' carries 192 parents, of which 150 are
 things like 'alteration', 'matrix', 'athlete', 'sexual relationship'. Any lane that walks is_a
 inherits the noise — measured, common_ancestor(crocodile, alligator) returned 'action', so the
 contrast said "Both are a kind of action". Gating at read time fixes one caller; the data stays
 dirty for every other caller, which is why this sweep exists.

THE SIGNAL IS MEASURED, NOT INVENTED
 clean_space.resonance separates real parents from noise with a wide margin (2026-07-17):
 real reptile .739 crocodilian reptile .797 beverage .795 drink .79
 noise action .081 opinion .149 athlete .263 matrix .346
 engage._relevant already ships this exact test at this exact threshold (<0.35 reject) to
 silence polysemy noise, and this sweep reuses it rather than deriving a second rule.

WHY RETRACTION IS SAFE HERE
 TripleStore.retract is append-only: it writes a tombstone to retractions.jsonl with a reason
 and a timestamp. Nothing is deleted, every decision is audited, and reverting the sweep is
 deleting the lines it appended. That is the only reason this is runnable at all.

WHY IT IS DRY RUN BY DEFAULT
 This mutates the owner's knowledge base at scale (~30% of is_a rows on the sampled subjects).
 The owner's own doctrine gates store writes behind an operator, so --apply is opt-in and the
 dry run prints exactly what it would tombstone.

USAGE
 python scripts/sanitize_isa_pollution.py --limit 200 # dry run, report only

``--apply`` is permanently refused until a replacement discriminator clears a
held-out abstract and cross-lingual E4/E5 gate.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200, help="how many hub subjects to sweep")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="disabled: the measured signal does not generalize",
    )
    ap.add_argument("--threshold", type=float, default=0.65,
                    help="sibling-resonance floor; below it the parent is noise")
    ap.add_argument("--report", default="", help="write the full decision list here")
    args = ap.parse_args()
    if args.apply:
        print(
            "REFUSING before graph scan: the retraction signal failed "
            "generalization; no mutation proposal will be produced."
        )
        return 2

    import numpy as np

    from packages.graph_scale import clean_space
    from packages.graph_scale.lexicon_lane import _store

    st = _store()
    root = st.root
    S = np.memmap(root / "s.col", dtype=np.int32, mode="r")
    P = np.memmap(root / "p.col", dtype=np.int32, mode="r")
    O = np.memmap(root / "o.col", dtype=np.int32, mode="r")
    isa_id = st.terms.lookup("is_a")
    _kid_cache: dict[str, list[str]] = {}

    def _children(parent: str, cap: int = 12) -> list[str]:
        if parent in _kid_cache:
            return _kid_cache[parent]
        oid = st.terms.lookup(parent)
        out: list[str] = []
        if oid is not None:
            rows = np.where((O == oid) & (P == isa_id))[0][:400]
            out = [st.terms.term(int(S[r])) for r in rows][:cap]
        _kid_cache[parent] = out
        return out

    def sibling_score(subj: str, parent: str) -> float | None:
        """Mean resonance between the subject and the parent's OTHER children.

        THE signal (measured 2026-07-17). Subject->parent resonance collapses on abstract
        parents because their embeddings are diffuse; their EXTENSIONS are not. A real parent's
        other children look like the subject; a junk parent's do not:
            REAL  crocodile/reptile .818   coffee/beverage .813   tea/beverage .822
            junk  crocodile/action .130    crocodile/matrix .154
            junk  justice/'chemical phenomenon' .422   courage/'subjective created mythology' .464
                  democracy/'amount' .461   democracy/'thing' .512
        The abstract cases that defeated the plain gate are separated here with room to spare.
        None = the parent has no other children, i.e. NO EVIDENCE — the caller must keep, never
        drop (measured: democracy -> 'form of government' has only itself as a child).
        """
        kids = [k for k in _children(parent) if k != subj]
        if not kids:
            return None
        rs = [r for r in (clean_space.resonance(subj, k) for k in kids) if r is not None]
        return (sum(rs) / len(rs)) if rs else None
    # Sweep the subjects that actually carry many is_a rows — pollution rides on hub degree, and a
    # subject with two parents has nothing to clean.
    subjects = _hub_subjects(st, args.limit)
    print(f"sweeping {len(subjects)} hub subjects (dry_run={not args.apply})")

    decisions: list[dict] = []
    kept = dropped = 0
    t0 = time.time()
    for i, subj in enumerate(subjects, 1):
        isa = [(s, p, o) for s, p, o in st.facts_about(subj, limit=400) if p == "is_a"]
        if len(isa) < 3:            # nothing to clean; never strip a sparse taxonomy
            continue
        for s, p, o in isa:
            score = sibling_score(subj, o)
            # NO EVIDENCE => KEEP. A parent with no other children tells us nothing, and silence
            # is not a reason to delete someone's knowledge.
            ok = (score is None) or (score >= args.threshold)
            decisions.append({"s": subj, "o": o, "keep": bool(ok),
                              "score": None if score is None else round(score, 3)})
            if ok:
                kept += 1
                continue
            dropped += 1
        if i % 25 == 0:
            print(f"  …{i}/{len(subjects)}  kept={kept} dropped={dropped}  {time.time()-t0:.0f}s")

    total = kept + dropped
    print(f"\n=== is_a rows examined {total} | keep {kept} | "
          f"would retract {dropped} "
          f"({100 * dropped // max(1, total)}%) in {time.time()-t0:.0f}s")
    print(
        "SHADOW REPORT - nothing was written; this failed signal has no "
        "mutation authority."
    )

    if args.report:
        Path(args.report).write_text(
            "\n".join(json.dumps(d, ensure_ascii=False) for d in decisions), encoding="utf-8")
        print(f"decision list → {args.report}")
    return 0


def _hub_subjects(st, limit: int) -> list[str]:
    """Subjects worth sweeping: the ones measured to carry pollution, then any hub the store
    surfaces. Kept explicit and small — a blind full-store pass is a separate, bigger decision."""
    seed = ["crocodile", "alligator", "democracy", "gravity", "coffee", "tea", "music", "art",
            "computer", "science", "war", "peace", "river", "mountain", "bread", "winter",
            "ocean", "forest", "money", "freedom", "justice", "memory", "sleep", "dream",
            "language", "history", "poetry", "friendship", "courage", "entropy", "firewall",
            "photosynthesis", "reptile", "beverage", "animal", "bird", "fish", "tree", "flower",
            "city", "country", "planet", "star", "metal", "liquid", "gas", "energy", "force"]
    return seed[:limit]


if __name__ == "__main__":
    raise SystemExit(main())
