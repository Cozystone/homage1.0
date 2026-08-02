# -*- coding: utf-8 -*-
"""SELF-TEST for the S1 landing chain — builds two TINY authentic sharded stores in a temp dir
and drives the whole measure->promote->swap->rollback pipeline end to end, asserting every
safety property. Re-runnable anytime (e.g. before the real operator promotion). Touches only a
throwaway temp dir; never data/graph_scale.

  python scripts/selftest_landing_chain.py

Proves:
  * plan_merge net-new / dup / new-term counts are exact (incl. a same-subject different-object
    edge that must NOT be a dup);
  * StoreMerger.build copies shipped byte-identically and appends only novel edges;
  * verify() catches nothing wrong (prefix identity, prior facts resolve, English-only);
  * legacy unsigned swap()/rollback() calls fail closed (the signed boundary is covered by
    scripts/tests/test_promotion_swap_boundary.py);
  * English-only fail-closed: a Hangul-contaminated staging store is REFUSED and cleaned up;
  * completeness guard flags a mid-write (torn) store;
  * firewall T0 nogood quarantines a contradiction, and build(exclude_triples=...) keeps it out;
  * build_t0_axioms harvests only UNAMBIGUOUS functional facts (drops multi-valued subjects).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.graph_scale.triple_store import TripleStore  # noqa: E402
import landing_chain_lib as L  # noqa: E402
from build_t0_axioms import harvest_axioms  # noqa: E402


def _build(root: Path, triples, source=None, url=""):
    if root.exists():
        shutil.rmtree(root)
    st = TripleStore(root, dict_backend="sharded")
    sid = st.intern_source(source, url) if source else None
    for s, p, o in triples:
        st.add(s, p, o, source=sid)
    st.flush(); st.terms.flush(); st.rebuild_index()
    if hasattr(st.terms, "close"):
        st.terms.close()
    del st


def _facts(root: Path, subj: str):
    st = TripleStore(root)
    out = st.facts_about(subj, limit=20)
    if hasattr(st.terms, "close"):
        st.terms.close()
    return out


def run(base: Path) -> None:
    shipped = base / "kg_triples"
    staged = base / "staging"

    _build(shipped, [
        ("france", "capital", "paris"),
        ("france", "is_a", "country"),
        ("japan", "capital", "tokyo"),
        ("bolivia", "capital", "sucre"),     # ambiguous ->
        ("bolivia", "capital", "la paz"),    #   T0 must drop bolivia
        ("dog", "is_a", "animal"),
        ("paris", "located_in", "france"),
    ])
    _build(staged, [
        ("france", "capital", "paris"),      # dup
        ("germany", "capital", "berlin"),    # novel (2 new terms)
        ("japan", "capital", "kyoto"),       # novel by (s,o); CONTRADICTS capital(japan)=tokyo
        ("cat", "is_a", "animal"),           # novel (1 new term)
    ], source="wikidata-truthy", url="https://www.wikidata.org/w/index.php?search={s}")

    # ---- completeness guard --------------------------------------------------
    ok, det = L.store_completeness(staged)
    assert ok, det
    # simulate a mid-write store: bump meta count above the column rows
    torn = base / "staging_torn"
    shutil.copytree(staged, torn)
    m = json.loads((torn / "meta.json").read_text(encoding="utf-8"))
    m["count"] = m["count"] + 100
    (torn / "meta.json").write_text(json.dumps(m), encoding="utf-8")
    ok2, det2 = L.store_completeness(torn)
    assert not ok2 and "mid-write" in det2["reason"], det2
    print("[ok] completeness guard flags a torn/mid-write store")

    # ---- T0 harvest (unambiguous only) --------------------------------------
    sh = L.ReadOnlyStore(shipped)
    facts, stats = harvest_axioms(sh, ["capital"])
    sh.close()
    fset = {tuple(f) for f in facts}
    assert ("france", "capital", "paris") in fset
    assert ("japan", "capital", "tokyo") in fset
    assert not any(f[0] == "bolivia" for f in facts), "ambiguous bolivia must be dropped"
    assert stats["capital"]["ambiguous_dropped"] == 1
    print(f"[ok] T0 harvest emitted {len(facts)} unambiguous axioms, dropped bolivia (ambiguous)")

    # ---- plan (dry-run measure) ---------------------------------------------
    plan = L.plan_merge(staged, shipped)
    assert plan["totals"]["net_new"] == 3, plan
    assert plan["totals"]["duplicates"] == 1, plan
    assert plan["n_new_terms"] == 4, plan
    assert plan["per_relation"]["capital"]["net_new"] == 2, plan  # germany/berlin + japan/kyoto
    assert plan["per_relation"]["is_a"]["net_new"] == 1, plan
    print("[ok] plan_merge exact: net_new=3 dup=1 new_terms=4 (japan/kyoto NOT a dup of tokyo)")

    # ---- firewall T0 nogood --------------------------------------------------
    fw = L.firewall_nogood_check(staged, "wikidata-truthy", facts)
    assert len(fw["quarantined"]) == 1 and fw["quarantined"][0]["object"] == "kyoto", fw
    print("[ok] firewall quarantines capital(japan)=kyoto vs axiom capital(japan)=tokyo")

    # ---- build WITH firewall exclusion --------------------------------------
    merged = base / "kg_triples.staged_merge.selftest"
    merger = L.StoreMerger(shipped, staged, provenance="wikidata-truthy")
    br = merger.build(merged, source_url="https://www.wikidata.org/w/index.php?search={s}",
                      exclude_triples=[("japan", "capital", "kyoto")])
    assert br["novel_edges_appended"] == 2, br     # germany/berlin, cat/animal (kyoto excluded)
    assert br["firewall_excluded"] == 1, br
    assert br["merged_edges_total"] == 9, br       # 7 shipped + 2 novel
    print(f"[ok] build appended {br['novel_edges_appended']} novel, excluded {br['firewall_excluded']} (firewall)")

    # ---- verify --------------------------------------------------------------
    vr = merger.verify(merged)
    assert vr["ok"], vr
    assert vr["checks"]["prefix_byte_identical"]
    assert vr["checks"]["novel_rows_english_only"]["ok"]
    print("[ok] verify: prefix byte-identical, prior facts resolve, English-only, counts")

    # ---- final mutation authority --------------------------------------------
    unsigned_swap_refused = False
    try:
        L.StoreMerger.swap(shipped, merged)
    except TypeError:
        unsigned_swap_refused = True
    assert unsigned_swap_refused, "legacy two-path swap must not be callable"
    unsigned_rollback_refused = False
    try:
        L.StoreMerger.rollback(shipped)
    except RuntimeError:
        unsigned_rollback_refused = True
    assert unsigned_rollback_refused, "rollback needs a distinct future signed schema"
    assert _facts(shipped, "germany") == []
    assert ("germany", "capital", "berlin") in _facts(merged, "germany")
    print("[ok] unsigned swap/rollback fail closed; live store remains unchanged")

    # ---- English-only fail-closed -------------------------------------------
    bad = base / "staging_bad"
    _build(bad, [("seoul", "capital", "대한민국"), ("berlin", "is_a", "city")],
           source="wikidata-truthy")
    merged_bad = base / "kg_triples.staged_merge.bad"
    refused = False
    try:
        L.StoreMerger(shipped, bad, provenance="wikidata-truthy").build(merged_bad)
    except ValueError:
        refused = True
    assert refused and not merged_bad.exists(), "Hangul staging must be refused + cleaned up"
    print("[ok] English-only fail-closed: Hangul staging REFUSED and half-build cleaned up")


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="s1_landing_selftest_"))
    try:
        print(f"self-test temp dir: {base}")
        run(base)
        print("=" * 60)
        print("S1 LANDING CHAIN SELF-TEST: ALL PASSED")
        return 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
