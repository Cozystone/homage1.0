# -*- coding: utf-8 -*-
"""How many dimensions does TEXT carry that pixels cannot? The owner's proposal, measured.

    python scripts/property_dimensions_from_text.py graph       # measure ATANOR'S OWN store -- do this
    python scripts/property_dimensions_from_text.py extract     # one pass over the ConceptNet dump
    python scripts/property_dimensions_from_text.py measure     # the dump, kept only for comparison

THE OWNER'S PROPOSAL, 2026-07-31: 비록 atanor가 직접 느낄순 없어도 인지적으로라도 고차원적으로 이해하게
하는게 좋지 않을까? 그 학습대상의 특성을 텍스트로나마 학습해서.

WHY IT IS THE RIGHT MOVE, and the vision numbers are the argument for it. A signature encoder trained on
street patches reaches 5.13 effective dimensions on held-out towns, against ~49 for human object
representations (Hebart et al. 2020). Four years of better losses would not close that, because MOST OF
THE MISSING DIMENSIONS HAVE NO SIGNAL IN THE PIXELS AT ALL. Hebart's axes include is-it-edible,
is-it-valuable, is-it-man-made, is-it-dangerous, does-it-move-on-its-own. No crop of a road contains
evidence about edibility. A vision organ cannot be short of that dimension; it is not measuring in it.

Text is. "A knife is used for cutting", "bread is food", "a car is dangerous" are exactly those axes,
stated. ConceptNet 5.7 is already on disk -- an owner-approved dataset, 498 MB, downloaded for the
candidate lane -- and its relations ARE the attribute vocabulary:

    HasProperty  CapableOf  UsedFor  MadeOf  AtLocation  PartOf  HasA  ReceivesAction  IsA

WHAT THIS DOES NOT CLAIM. Learning that bread is edible from a sentence is not tasting bread, and this
file makes no claim about experience -- only about how many independent distinctions the representation
supports. The owner's own framing is the honest one: 인지적으로라도. If the axes turn out to be real, a
humanoid body later grounds them; if they turn out to be a word-co-occurrence artefact, that shows up here
as the control matching the real thing.

MEASURE THE STORE WE HAVE, NOT A FRESH EXTRACTION. The first version of this file parsed the ConceptNet
dump into a new file, which is exactly how this project ends up with a hundred and thirty-three of
everything. The production store already holds 115,455,726 triples, and a census of it says the concepts
are ALREADY THERE:

    part_of 3,828,705   has_a 2,282,294   made_of 1,300,565
    has_property 196,813   used_for 39,673   capable_of 22,662   has_subevent 3,445   causes 2,246
    desires 0 -- the predicate is in the dictionary and nothing was ever written under it

    subjects with >= 8 attributes  125,461      >= 16  31,671      >= 49  1,970

The owner asked whether 20,000-50,000 clearly-learned concepts would be enough. BY COUNT the store is
already there. BY COMPOSITION it is not: 96% of the attribute mass is part_of / has_a / made_of, which say
what a thing is built from and what it belongs to. What a thing is FOR, what it can DO and what it is
LIKE -- the axes Hebart's dimensions actually turn on -- are 0.24% of the store between them. So the
bottleneck is not concept count and not the encoder: three specific relations are starved.

RESULT, and prediction 1 was REFUTED. Run 2026-07-31 over the production store:

    concepts  properties  density  eff dims  shuffled control
       1,854      2,411   0.0065      6.77    865.40
      20,000      8,324   0.0007     71.08   2345.73

At Hebart's own 1,854 concepts the store gives 6.77 -- barely above the vision encoder's 5.13, nowhere
near 49. And 71.08 at 20,000 concepts is NOT the good news it looks like: participation ratio over a
sparse binary matrix rises as the matrix gets sparser, which is what the shuffled control at 865 and 2345
is showing. THAT MEANS 6.77 AND 71.08 CANNOT BE PUT BESIDE 5.13 AND 49 AT ALL -- those come from learned
32-dimensional embeddings, and this measurement is not the same measurement. The number is not the
finding; it is a confounded number and is recorded as one.

WHAT IS THE FINDING IS PREDICTION 3, the axes, which need no normalisation to read:

    axis 1  has_a: More Than a Feeling, My Heart Will Go On, Morning Has Broken     -- songs
    axis 2  has_a: AKT1, MAPK1, MAPK3, MAP2K1, RAF1                                 -- genes
    axis 4  part_of: Expedition 19, Expedition 50, Expedition 18, Expedition 30     -- ISS missions
    axis 6  made_of: oil paint, canvas, paper                                       -- paintings

The 1,854 most-attributed concepts in ATANOR's store are ALBUMS, GENES AND SPACE MISSIONS. Only one axis
in the leading six is about objects at all. So the store's problem is not only which relations are thin --
it is that the entities carrying properties are database records rather than the kinds of thing a person
points at. Feeding more encyclopedia adds more of the same population.

That is what scripts/mine_object_properties_from_glosses.py is for: a dictionary's nouns ARE the
pointed-at population, and a dictionary states the obvious properties that encyclopedias omit.

REGISTERED before running:
    1  the text property space carries far more effective dimensions than vision does -- above 20 against
       5.13. If it does not, the owner's proposal does not solve the dimensionality problem and the
       constraint is elsewhere.
    2  and the structure is real, not an artefact of how many properties each concept happens to have: a
       control that shuffles each property column independently -- preserving how common every property
       is, destroying which concept has it -- must come out clearly different.
    3  the axes are INTERPRETABLE as attributes rather than as topics. The top loadings of the leading
       components should read like Hebart's dimensions (is-it-food, is-it-a-tool) rather than like
       subject areas (all-about-music). Reported as evidence to read, not as a number to pass.
"""
from __future__ import annotations

import collections
import gzip
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DUMP = Path("data/graph_scale/conceptnet-assertions-5.7.0.csv.gz")
STORE = Path("data/graph_scale/kg_triples")
GRAPH_OUT = Path("data/perception/property_dimensions_graph.json")
ATTRIBUTE_PREDICATES = ("has_property", "capable_of", "used_for", "made_of", "part_of", "has_a",
                        "desires", "causes", "has_subevent")
EXTRACT = Path("data/perception/concept_properties.json")
OUT = Path("data/perception/property_dimensions.json")

# Relations that attribute something TO a concept. RelatedTo and Synonym are excluded on purpose:
# they say two words go together, which is topic structure, not an attribute of a thing.
KEEP = {"/r/HasProperty", "/r/CapableOf", "/r/UsedFor", "/r/MadeOf", "/r/AtLocation",
        "/r/PartOf", "/r/HasA", "/r/ReceivesAction", "/r/IsA", "/r/HasSubevent",
        "/r/Desires", "/r/CreatedBy", "/r/Causes"}
MIN_WEIGHT = 1.0
MIN_PROPERTIES = 8          # a concept with two facts about it cannot exhibit fifty dimensions
MIN_CONCEPTS_PER_PROP = 5   # a property held by one thing is an id, not an axis
DIM_REPORT = 12


def _term(uri: str) -> str | None:
    """/c/en/knife/n/wn/artifact -> knife. Non-English returns None: this project is English-only."""
    p = uri.split("/")
    return p[3] if len(p) > 3 and p[1] == "c" and p[2] == "en" else None


def extract() -> None:
    if not DUMP.exists():
        sys.exit(f"no ConceptNet dump at {DUMP}")
    props: dict[str, set] = collections.defaultdict(set)
    kept = seen = 0
    with gzip.open(DUMP, "rt", encoding="utf-8") as fh:
        for line in fh:
            seen += 1
            f = line.rstrip("\n").split("\t")
            if len(f) < 5 or f[1] not in KEEP:
                continue
            a, b = _term(f[2]), _term(f[3])
            if not a or not b or a == b:
                continue
            try:
                if json.loads(f[4]).get("weight", 0.0) < MIN_WEIGHT:
                    continue
            except Exception:
                continue
            props[a].add(f"{f[1][3:]}:{b}")
            kept += 1
            if kept % 200000 == 0:
                print(f"  {seen:,} rows scanned, {kept:,} attributions, {len(props):,} concepts")
    rich = {k: sorted(v) for k, v in props.items() if len(v) >= MIN_PROPERTIES}
    print(f"\n{seen:,} rows -> {kept:,} attributions over {len(props):,} concepts")
    print(f"{len(rich):,} concepts have >= {MIN_PROPERTIES} properties")
    EXTRACT.parent.mkdir(parents=True, exist_ok=True)
    EXTRACT.write_text(json.dumps(rich), encoding="utf-8")
    print(f"wrote {EXTRACT} ({EXTRACT.stat().st_size // 1024 // 1024} MB)")


def participation_ratio(X) -> float:
    X = np.asarray(X, np.float64)
    X = X - X.mean(0)
    sv = np.linalg.svd(X, compute_uv=False)
    return float((sv ** 2).sum() ** 2 / (sv ** 4).sum())


def matrix(rich, n_concepts: int, seed: int = 0):
    """Concept x property binary matrix over the most-attributed concepts."""
    rng = np.random.default_rng(seed)
    names = sorted(rich, key=lambda k: -len(rich[k]))[:n_concepts]
    counts = collections.Counter(p for k in names for p in rich[k])
    feats = sorted(p for p, c in counts.items() if c >= MIN_CONCEPTS_PER_PROP)
    fi = {p: i for i, p in enumerate(feats)}
    M = np.zeros((len(names), len(feats)), np.float32)
    for r, k in enumerate(names):
        for p in rich[k]:
            j = fi.get(p)
            if j is not None:
                M[r, j] = 1.0
    return names, feats, M, rng


def measure() -> None:
    if not EXTRACT.exists():
        sys.exit(f"run `extract` first -- no {EXTRACT}")
    rich = json.loads(EXTRACT.read_text(encoding="utf-8"))
    print(f"{len(rich):,} concepts with >= {MIN_PROPERTIES} properties\n")
    rows = {}
    print(f"{'concepts':>10}{'properties':>12}{'density':>10}{'eff dims':>11}"
          f"{'shuffled control':>19}")
    for n in (200, 500, 1854, 5000, 20000):
        if n > len(rich):
            break
        names, feats, M, rng = matrix(rich, n)
        pr = participation_ratio(M)
        # CONTROL: shuffle each property column independently. Every property keeps exactly how common
        # it is; what is destroyed is WHICH concept has it. Structure has to be the difference.
        S = np.stack([rng.permutation(M[:, j]) for j in range(M.shape[1])], axis=1)
        prs = participation_ratio(S)
        rows[str(n)] = {"n_concepts": len(names), "n_properties": len(feats),
                        "density": float(M.mean()), "eff_dims": pr, "eff_dims_shuffled": prs}
        print(f"{len(names):>10,}{len(feats):>12,}{M.mean():>10.4f}{pr:>11.2f}{prs:>19.2f}")

    # 1,854 is Hebart's object count, so that row is the like-for-like comparison.
    key = "1854" if "1854" in rows else sorted(rows, key=lambda k: int(k))[-1]
    ref = rows[key]
    print(f"\nvision on held-out towns: 5.13 effective dimensions (InfoNCE + pool 2)")
    print(f"human object representations: ~49 (Hebart et al. 2020, from 1,854 objects), ~66 later")
    print(f"\n-> 1. text carries far more than vision: {ref['eff_dims'] > 20.0}   "
          f"({ref['eff_dims']:.2f} at {ref['n_concepts']:,} concepts vs 5.13)")
    print(f"-> 2. and it is not an artefact of property counts: "
          f"{abs(ref['eff_dims'] - ref['eff_dims_shuffled']) > 2.0}   "
          f"(real {ref['eff_dims']:.2f} vs shuffled {ref['eff_dims_shuffled']:.2f})")

    names, feats, M, _ = matrix(rich, min(1854, len(rich)))
    C = M - M.mean(0)
    _u, _s, vt = np.linalg.svd(C, full_matrices=False)
    axes = []
    print(f"\n-> 3. what the leading axes are made of (read these, they are the evidence):")
    for k in range(DIM_REPORT if len(vt) >= DIM_REPORT else len(vt)):
        top = [feats[j] for j in np.argsort(-np.abs(vt[k]))[:6]]
        axes.append(top)
        if k < 8:
            print(f"     axis {k + 1:>2}: {', '.join(top)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"by_n_concepts": rows, "leading_axes": axes,
                               "relations_kept": sorted(KEEP),
                               "min_properties_per_concept": MIN_PROPERTIES,
                               "min_concepts_per_property": MIN_CONCEPTS_PER_PROP,
                               "vision_reference_holdout": 5.13,
                               "human_reference": "49 (Hebart 2020 over 1,854 objects), 66 later",
                               "caveat": "participation ratio over a raw binary feature matrix is not "
                                         "the same measurement as over a learned 32-dim embedding; the "
                                         "shuffled control is what makes the comparison mean anything, "
                                         "and a joint vision+text embedding is the test that follows."},
                              indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")


def graph() -> None:
    """The same measurement, on the production store instead of a fresh parse of a dump.

    One pass collects every attribute triple whose subject is in the store at all; the ladder over
    concept counts is then taken from that one harvest rather than re-reading 115 million rows per row of
    the table."""
    from packages.graph_scale.triple_store import TripleStore

    st = TripleStore(str(STORE))
    ids = {}
    for n in ATTRIBUTE_PREDICATES:
        i = st.terms.lookup(n)
        if i is not None:
            ids[int(i)] = n
    if not ids:
        sys.exit("no attribute predicate resolved -- harness failure, not a finding")
    P = np.memmap(STORE / "p.col", dtype=np.int32, mode="r")
    S = np.memmap(STORE / "s.col", dtype=np.int32, mode="r")
    O = np.memmap(STORE / "o.col", dtype=np.int32, mode="r")
    want = np.array(sorted(ids), dtype=np.int32)
    CH = 10_000_000

    pairs: dict[int, set] = collections.defaultdict(set)
    for a in range(0, len(P), CH):
        pc = np.asarray(P[a:a + CH])
        m = np.isin(pc, want)
        if not m.any():
            continue
        for sv, pv, ov in zip(np.asarray(S[a:a + CH])[m], pc[m], np.asarray(O[a:a + CH])[m]):
            pairs[int(sv)].add((int(pv), int(ov)))
    print(f"{len(P):,} triples -> {sum(len(v) for v in pairs.values()):,} attribute triples over "
          f"{len(pairs):,} subjects")
    order = sorted(pairs, key=lambda k: -len(pairs[k]))

    rows = {}
    print()
    print(f"{'concepts':>10}{'properties':>12}{'density':>10}{'eff dims':>11}{'shuffled':>11}")
    for n in (200, 500, 1854, 5000, 20000):
        if n > len(order):
            break
        keep = order[:n]
        fc = collections.Counter(f for s in keep for f in pairs[s])
        feats = sorted(f for f, c in fc.items() if c >= MIN_CONCEPTS_PER_PROP)
        if len(feats) < 20:
            print(f"{n:>10,}  only {len(feats)} shared properties -- too sparse to measure")
            continue
        fi = {f: j for j, f in enumerate(feats)}
        M = np.zeros((len(keep), len(feats)), np.float32)
        for r, s in enumerate(keep):
            for f in pairs[s]:
                j = fi.get(f)
                if j is not None:
                    M[r, j] = 1.0
        rng = np.random.default_rng(0)
        pr = participation_ratio(M)
        prs = participation_ratio(np.stack([rng.permutation(M[:, j]) for j in range(M.shape[1])], 1))
        rows[str(n)] = {"n_concepts": len(keep), "n_properties": len(feats),
                        "density": float(M.mean()), "eff_dims": pr, "eff_dims_shuffled": prs}
        print(f"{len(keep):>10,}{len(feats):>12,}{M.mean():>10.4f}{pr:>11.2f}{prs:>11.2f}")
        if n == 1854:
            vt = np.linalg.svd(M - M.mean(0), full_matrices=False)[2]
            axes = []
            for k in range(min(8, len(vt))):
                top = []
                for j in np.argsort(-np.abs(vt[k]))[:5]:
                    pid, oid = feats[j]
                    try:
                        top.append(f"{ids.get(pid, pid)}:{st.terms.term(oid)}")
                    except Exception:
                        top.append(f"{ids.get(pid, pid)}:<{oid}>")
                axes.append(top)
            rows[str(n)]["leading_axes"] = axes

    key = "1854" if "1854" in rows else (sorted(rows, key=lambda k: int(k))[-1] if rows else None)
    if not key:
        sys.exit("nothing measurable")
    ref = rows[key]
    print()
    print("vision on held-out towns: 5.13 effective dimensions (InfoNCE + pool 2)")
    print("human object representations: ~49 (Hebart et al. 2020, from 1,854 objects), ~66 later")
    print()
    print(f"-> 1. the store carries far more than vision: {ref['eff_dims'] > 20.0}   "
          f"({ref['eff_dims']:.2f} over {ref['n_concepts']:,} concepts vs 5.13)")
    print(f"-> 2. and it is not an artefact of how many properties each concept has: "
          f"{abs(ref['eff_dims'] - ref['eff_dims_shuffled']) > 2.0}   "
          f"(real {ref['eff_dims']:.2f} vs shuffled {ref['eff_dims_shuffled']:.2f})")
    print("-> 3. what the leading axes are made of -- read these, they are the evidence:")
    for i, ax in enumerate(ref.get("leading_axes", [])[:6]):
        print(f"     axis {i + 1}: {', '.join(ax)}")

    GRAPH_OUT.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_OUT.write_text(json.dumps({"store": str(STORE), "by_n_concepts": rows,
                                     "attribute_predicates": sorted(ids.values()),
                                     "vision_reference_holdout": 5.13,
                                     "human_reference": "49 (Hebart 2020), 66 later"},
                                    indent=2), encoding="utf-8")
    print()
    print(f"wrote {GRAPH_OUT}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "graph"
    {"extract": extract, "measure": measure, "graph": graph}.get(cmd, graph)()
