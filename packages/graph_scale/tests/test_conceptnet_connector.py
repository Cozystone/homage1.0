# -*- coding: utf-8 -*-
"""ConceptNet -> gated candidate lane: mapped, weight-filtered, never production."""

_CANNED = {"edges": [
    {"start": {"label": "dog"}, "end": {"label": "animal"},
     "rel": {"@id": "/r/IsA"}, "weight": 2.5},
    {"start": {"label": "knife"}, "end": {"label": "cutting"},
     "rel": {"@id": "/r/UsedFor"}, "weight": 3.0},
    {"start": {"label": "dog"}, "end": {"label": "pet"},       # RelatedTo not mapped
     "rel": {"@id": "/r/RelatedTo"}, "weight": 5.0},
    {"start": {"label": "x"}, "end": {"label": "x"},           # self-edge dropped
     "rel": {"@id": "/r/IsA"}, "weight": 2.0},
    {"start": {"label": "weak"}, "end": {"label": "thing"},    # below weight floor
     "rel": {"@id": "/r/IsA"}, "weight": 0.3},
]}


def _stub(url):
    return _CANNED


def test_fetch_maps_and_filters():
    from packages.graph_scale.conceptnet_connector import fetch_edges
    edges = fetch_edges("dog", fetcher=_stub)
    preds = {(s, p, o) for s, p, o, w in edges}
    assert ("dog", "is_a", "animal") in preds
    assert ("knife", "used_for", "cutting") in preds
    assert all(p != "related_to" for _s, p, _o, _w in edges)   # chatty rel dropped
    assert not any(s == o for s, _p, o, _w in edges)           # self-edge dropped
    assert all(w >= 1.0 for _s, _p, _o, w in edges)            # weak dropped


def test_harvest_writes_candidates_not_production(tmp_path):
    from packages.graph_scale.conceptnet_connector import harvest
    r = harvest(["dog", "knife"], out_dir=tmp_path, store=None, fetcher=_stub)
    assert r["written_to_production"] is False
    assert r["candidates_written"] > 0
    assert "is_a" in r["predicates"] and "used_for" in r["predicates"]
    isa = (tmp_path / "conceptnet_is_a.jsonl").read_text(encoding="utf-8")
    assert '"tier": "candidate"' in isa and "conceptnet" in isa
    # idempotent: re-harvest adds no duplicates
    r2 = harvest(["dog", "knife"], out_dir=tmp_path, store=None, fetcher=_stub)
    assert r2["candidates_written"] == 0


def test_harvest_from_dump_parses_conceptnet_tsv(tmp_path):
    """Offline dump path: parse ConceptNet's TSV, map + filter, land candidates."""
    from packages.graph_scale.conceptnet_connector import harvest_from_dump
    dump = tmp_path / "cn.csv"
    dump.write_text(
        "/a/x\t/r/IsA\t/c/en/dog\t/c/en/animal\t{\"weight\": 2.5}\n"
        "/a/y\t/r/UsedFor\t/c/en/knife\t/c/en/cutting\t{\"weight\": 3.0}\n"
        "/a/z\t/r/RelatedTo\t/c/en/dog\t/c/en/pet\t{\"weight\": 5.0}\n"     # unmapped rel
        "/a/w\t/r/IsA\t/c/fr/chien\t/c/fr/animal\t{\"weight\": 2.0}\n"       # lang filtered
        "/a/k\t/r/IsA\t/c/ko/고양이\t/c/ko/동물\t{\"weight\": 2.0}\n",       # korean kept
        encoding="utf-8")
    r = harvest_from_dump(dump, out_dir=tmp_path, store=None)
    assert r["harvested"] is True and r["written_to_production"] is False
    assert "is_a" in r["predicates"] and "used_for" in r["predicates"]
    isa = (tmp_path / "conceptnet_is_a.jsonl").read_text(encoding="utf-8")
    assert "고양이" in isa and "동물" in isa          # korean assertion landed
    assert "chien" not in isa                          # french filtered out


def test_harvest_from_dump_missing_file_is_honest(tmp_path):
    from packages.graph_scale.conceptnet_connector import harvest_from_dump
    r = harvest_from_dump(tmp_path / "nope.csv")
    assert r["harvested"] is False and r["reason"] == "dump_not_found"
