# -*- coding: utf-8 -*-
"""Measure the R2 graph-density lift: shipped promotable-subject coverage vs the coverage
after overlaying the ConceptNet staging store (scripts/stage_r2_conceptnet.py). READ-ONLY:
opens the shipped kg_triples columns as read-only memmaps and its term shards as read-only
sqlite (mode=ro), so it CANNOT modify the shipped store. Nothing here writes production.

THE NUMBER THAT VALIDATES R2: promotable-subject coverage. A subject "carries a promotable
functional relation" if it has >=1 edge with predicate in {capable_of, used_for, has_a,
part_of, made_of, has_property}. We report shipped coverage (expected ~0.058%) and the
coverage after the staging overlay, plus how many concepts cross into COMPOSED-FIRE shape
(is_a AND a functional relation) once staging is promoted.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import zlib
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
SHIPPED = REPO / "data" / "graph_scale" / "kg_triples"
STAGING = REPO / "data" / "graph_scale" / "staging_r2_conceptnet"

FUNC6 = ["capable_of", "used_for", "has_a", "part_of", "made_of", "has_property"]
FUNC3 = ["capable_of", "has_a", "used_for"]   # the task's 0.058% definition
NEEDED = sorted(set(FUNC6 + ["is_a"]))


def memmap_col(root: Path, name: str) -> np.ndarray:
    p = root / f"{name}.col"
    n = p.stat().st_size // 4
    return np.asarray(np.memmap(str(p), dtype="<i4", mode="r", shape=(n,))) if n else np.zeros(0, "<i4")


def main() -> int:
    # ---- shipped store: READ-ONLY ------------------------------------------------
    s = memmap_col(SHIPPED, "s")
    p = memmap_col(SHIPPED, "p")
    sh_conns = [sqlite3.connect(
        f"file:{(SHIPPED / 'term_shards' / f'terms_{i:02d}.db').as_posix()}?mode=ro", uri=True)
        for i in range(16)]

    def sh_lookup(term: str):
        shard = zlib.crc32(term.encode("utf-8")) % 16
        r = sh_conns[shard].execute("SELECT rowid FROM t WHERE term=?", (term,)).fetchone()
        return (r[0] - 1) * 16 + shard if r else None

    pid = {name: sh_lookup(name) for name in NEEDED}
    all_subj = np.unique(s)
    D = int(len(all_subj))
    all_subj_set = set(int(x) for x in all_subj)

    subj_by_pred: dict[str, set[int]] = {}
    edge_count: dict[str, int] = {}
    for name in NEEDED:
        i = pid[name]
        if i is None:
            subj_by_pred[name] = set()
            edge_count[name] = 0
            continue
        mask = p == i
        edge_count[name] = int(mask.sum())
        subj_by_pred[name] = set(int(x) for x in np.unique(s[mask]))

    func3_ids = set().union(*[subj_by_pred[n] for n in FUNC3]) if FUNC3 else set()
    func6_ids = set().union(*[subj_by_pred[n] for n in FUNC6]) if FUNC6 else set()
    isa_ids = subj_by_pred["is_a"]

    baseline3 = len(func3_ids) / D
    baseline6 = len(func6_ids) / D
    cf_baseline = len(isa_ids & func6_ids)

    # ---- staging store: distinct functional subjects (strings) -------------------
    st_s = memmap_col(STAGING, "s")
    st_p = memmap_col(STAGING, "p")
    st_terms = [ln.rstrip("\n") for ln in (STAGING / "terms.txt").open(encoding="utf-8")]
    st_id = {t: i for i, t in enumerate(st_terms)}
    st_func_pids = [st_id[n] for n in FUNC6 if n in st_id]
    st_isa_pid = st_id.get("is_a")
    st_func_mask = np.isin(st_p, st_func_pids)
    staging_func_subjects = [st_terms[i] for i in np.unique(st_s[st_func_mask])]
    staging_isa_subjects = set(
        st_terms[i] for i in np.unique(st_s[st_p == st_isa_pid])) if st_isa_pid is not None else set()

    # ---- overlay: map staging functional subjects onto the shipped vocabulary ----
    cat: Counter[str] = Counter()
    staging_func_ids_in_shipped: set[int] = set()
    newly_func_examples: list[str] = []
    for surf in staging_func_subjects:
        sid = sh_lookup(surf)
        if sid is None:
            cat["brand_new_concept_grows_vocab"] += 1
            continue
        if sid in all_subj_set:
            staging_func_ids_in_shipped.add(sid)
            if sid in func6_ids:
                cat["shipped_subject_already_functional"] += 1
            else:
                cat["shipped_subject_NEWLY_functional"] += 1
                if len(newly_func_examples) < 40:
                    newly_func_examples.append(surf)
        else:
            cat["known_term_not_yet_a_subject"] += 1

    combined_func_ids = func6_ids | staging_func_ids_in_shipped   # both subsets of all_subj_set
    combined_pct = len(combined_func_ids) / D
    newly_func = len(combined_func_ids) - len(func6_ids)

    # composed-fire: is_a AND a functional relation (the richer-bones shape)
    cf_after = len(isa_ids & combined_func_ids)
    cf_lift = cf_after - cf_baseline

    report = {
        "shipped_store": {
            "distinct_subjects_D": D,
            "total_edges": int(len(s)),
            "predicate_edge_counts": edge_count,
            "predicate_ids": pid,
            "subjects_with_functional3(capable_of|has_a|used_for)": len(func3_ids),
            "subjects_with_functional6": len(func6_ids),
            "subjects_with_is_a": len(isa_ids),
            "baseline_coverage_functional3_pct": round(baseline3 * 100, 4),
            "baseline_coverage_functional6_pct": round(baseline6 * 100, 4),
            "composed_fire_baseline(is_a AND functional6)": cf_baseline,
        },
        "staging_store": {
            "distinct_functional_subjects": len(staging_func_subjects),
            "distinct_is_a_subjects": len(staging_isa_subjects),
        },
        "overlay_onto_shipped_vocabulary": dict(cat),
        "density_lift": {
            "baseline_functional6_coverage_pct": round(baseline6 * 100, 4),
            "combined_functional6_coverage_pct": round(combined_pct * 100, 4),
            "lift_multiple_x": round(combined_pct / baseline6, 1) if baseline6 else None,
            "shipped_subjects_newly_functional": newly_func,
        },
        "composed_fire_lift": {
            "baseline_concepts_with_is_a_AND_functional": cf_baseline,
            "after_overlay": cf_after,
            "newly_composed_fire_concepts": cf_lift,
            "note": "shipped subjects that ALREADY have an is_a and would gain a functional "
                    "relation from staging (cross into composed-firing shape)",
        },
        "newly_functional_examples": newly_func_examples,
    }
    (STAGING / "R2_DENSITY_LIFT.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    for c in sh_conns:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
