# -*- coding: utf-8 -*-
"""A book is its own colored region: connected to all, yet a distinct bundle."""


def test_region_registered_with_stable_color(tmp_path, monkeypatch):
    from packages.graph_scale import graph_regions as gr
    monkeypatch.setattr(gr, "MANIFEST", tmp_path / "regions.jsonl")
    r1 = gr.register_region("book_thinking", "Thinking Fast and Slow", kind="book")
    assert r1["color"].startswith("#") and r1["kind"] == "book"
    # idempotent: same id keeps the same color
    r2 = gr.register_region("book_thinking", "Thinking Fast and Slow (v2)", kind="book")
    assert r2["color"] == r1["color"]
    assert sum(1 for r in gr._rows() if r["region_id"] == "book_thinking") == 1


def test_distinct_regions_get_distinct_colors_and_reserved_anchors(tmp_path, monkeypatch):
    from packages.graph_scale import graph_regions as gr
    monkeypatch.setattr(gr, "MANIFEST", tmp_path / "regions.jsonl")
    a = gr.register_region("book_geb", "Godel Escher Bach")
    b = gr.register_region("paper_kge", "KG Embedding Survey", kind="paper")
    assert a["color"] != b["color"]                 # different bundles, different hue
    regions = {r["region_id"]: r for r in gr.list_regions()}
    assert "core" in regions and "web" in regions   # reserved anchors always present
    assert gr.color_of("book_geb") == a["color"]
