# -*- coding: utf-8 -*-
"""Edge-level density lift: for each promotable functional relation, count the shipped
edges, the staging edges, and their deduplicated UNION (what the store would hold after an
operator promotion). Subject-coverage alone understates the lift because ConceptNet also
DEEPENS concepts that already carry one functional relation (more relations per concept =
richer composed firing). READ-ONLY on the shipped store (mode=ro sqlite, read-only memmaps).
"""
from __future__ import annotations

import json
import sqlite3
import zlib
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
SHIPPED = REPO / "data" / "graph_scale" / "kg_triples"
STAGING = REPO / "data" / "graph_scale" / "staging_r2_conceptnet"
FUNC6 = ["capable_of", "used_for", "has_a", "part_of", "made_of", "has_property"]


def memmap_col(root: Path, name: str) -> np.ndarray:
    p = root / f"{name}.col"
    n = p.stat().st_size // 4
    return np.asarray(np.memmap(str(p), dtype="<i4", mode="r", shape=(n,))) if n else np.zeros(0, "<i4")


def main() -> int:
    s = memmap_col(SHIPPED, "s"); p = memmap_col(SHIPPED, "p"); o = memmap_col(SHIPPED, "o")
    conns = [sqlite3.connect(
        f"file:{(SHIPPED / 'term_shards' / f'terms_{i:02d}.db').as_posix()}?mode=ro", uri=True)
        for i in range(16)]

    def lookup(term: str):
        sh = zlib.crc32(term.encode("utf-8")) % 16
        r = conns[sh].execute("SELECT rowid FROM t WHERE term=?", (term,)).fetchone()
        return (r[0] - 1) * 16 + sh if r else None

    def term(gid: int) -> str:
        sh, rid = gid % 16, gid // 16 + 1
        r = conns[sh].execute("SELECT term FROM t WHERE rowid=?", (rid,)).fetchone()
        return r[0] if r else ""

    pid = {name: lookup(name) for name in FUNC6}

    # staging (s,o) string pairs per relation, straight from its columns
    st_s = memmap_col(STAGING, "s"); st_p = memmap_col(STAGING, "p")
    st_o = memmap_col(STAGING, "o")
    st_terms = [ln.rstrip("\n") for ln in (STAGING / "terms.txt").open(encoding="utf-8")]
    st_id = {t: i for i, t in enumerate(st_terms)}

    per_rel = {}
    tot_shipped = tot_staging = tot_union = tot_new = 0
    for name in FUNC6:
        # shipped edges -> string pairs
        shipped_pairs: set[tuple[str, str]] = set()
        if pid[name] is not None:
            mask = p == pid[name]
            ss, oo = s[mask], o[mask]
            uniq = set(int(x) for x in np.unique(np.concatenate([ss, oo]))) if len(ss) else set()
            idmap = {g: term(g) for g in uniq}
            shipped_pairs = {(idmap[int(a)], idmap[int(b)]) for a, b in zip(ss, oo)}
        # staging edges -> string pairs
        staging_pairs: set[tuple[str, str]] = set()
        spid = st_id.get(name)
        if spid is not None:
            m = st_p == spid
            for a, b in zip(st_s[m], st_o[m]):
                staging_pairs.add((st_terms[int(a)], st_terms[int(b)]))
        union = shipped_pairs | staging_pairs
        new = staging_pairs - shipped_pairs
        per_rel[name] = {
            "shipped": len(shipped_pairs), "staging": len(staging_pairs),
            "union": len(union), "net_new_from_staging": len(new),
        }
        tot_shipped += len(shipped_pairs); tot_staging += len(staging_pairs)
        tot_union += len(union); tot_new += len(new)

    report = {
        "per_relation": per_rel,
        "totals": {
            "shipped_functional_edges": tot_shipped,
            "staging_functional_edges": tot_staging,
            "union_functional_edges": tot_union,
            "net_new_functional_edges_from_staging": tot_new,
            "edge_density_lift_x": round(tot_union / tot_shipped, 2) if tot_shipped else None,
        },
    }
    (STAGING / "R2_EDGE_UNION.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    for c in conns:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
