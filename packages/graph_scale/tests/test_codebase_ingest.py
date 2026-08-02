# -*- coding: utf-8 -*-
"""Codebase self-knowledge: AST -> structural triples, queryable, candidate-only."""


def test_ingest_extracts_structure(tmp_path):
    from packages.graph_scale.codebase_ingest import ingest_codebase, _triples_for_file
    src = tmp_path / "pkg"
    src.mkdir()
    (src / "mod.py").write_text(
        'def helper():\n    """Do a helping thing."""\n    return 1\n'
        'def main():\n    """Entry."""\n    return helper()\n', encoding="utf-8")
    t = {(a, b, c) for a, b, c in _triples_for_file(src / "mod.py", tmp_path)}
    assert ("pkg.mod", "is_a", "python_module") in t
    assert ("pkg.mod", "has_function", "main") in t
    assert ("main", "calls", "helper") in t                 # call graph captured
    assert ("helper", "documented_as", "Do a helping thing.") in t
    r = ingest_codebase(root=tmp_path, subdir="pkg", out=tmp_path / "cb.jsonl", skip_tests=False)
    assert r["written_to_production"] is False and r["functions"] >= 2


def test_about_queries_self_knowledge(tmp_path):
    """Ingest a scratch tree and read it back — through the STORE, which is the read path now.

    This test used to patch LEDGER and read the JSONL. That is no longer where answers come from, and
    the migration exposed a real defect: the ingest wrote its store to the production location no
    matter which root it was handed, so running this test destroyed the repo's own 117k-triple graph
    while reporting success. Both the store and the ledger now follow the caller's path, and this
    test pins that by asserting the scratch ingest is READABLE at the scratch root."""
    from packages.graph_scale import codebase_ingest as cb
    store = tmp_path / "store"
    cb.ingest_codebase(root=_make(tmp_path), subdir="pkg", out=tmp_path / "cb.jsonl",
                       skip_tests=False, store_root=store)
    a = cb.about("main", store_root=store)
    assert a["known"] is True
    assert any(x["predicate"] == "calls" and x["object"] == "helper" for x in a["is"])


def test_scratch_ingest_never_touches_the_production_store(tmp_path):
    """The defect that motivated the path rule: a scratch ingest must not write production.

    Passing only `root` (no explicit out/store_root) is the shape the old test used, and it is the
    shape that clobbered the real graph. Asserting on the RETURNED paths keeps this honest without
    the test needing to touch production to prove it left production alone."""
    from packages.graph_scale import codebase_ingest as cb
    r = cb.ingest_codebase(root=_make(tmp_path), subdir="pkg", skip_tests=False)
    assert str(cb.CODE_STORE) not in r["store"]
    assert str(cb.LEDGER) not in r["ledger"]
    assert str(tmp_path) in r["store"] and str(tmp_path) in r["ledger"]


def _make(tmp_path):
    src = tmp_path / "pkg"; src.mkdir(exist_ok=True)
    (src / "mod.py").write_text(
        'def helper():\n    return 1\ndef main():\n    return helper()\n', encoding="utf-8")
    return tmp_path
