# -*- coding: utf-8 -*-
"""Macro-geo binding: symbolic place anchors, tight-radius nearest lookup, snapshot inheritance.
Offline by construction — the OSM resolver is opt-in and honestly absent here."""
import packages.perception.geo_anchor as ga
import packages.perception.spatial_memory as sm


def test_haversine_sanity():

    d = ga.haversine_m(37.5148, 127.0576, 37.5125, 127.0588)
    assert 200 < d < 600
    assert ga.haversine_m(37.5, 127.0, 37.5, 127.0) == 0.0


def test_anchor_mint_and_refresh_no_duplicates(tmp_path):
    ga._LEDGER = tmp_path / "geo.jsonl"
    a = ga.anchor_place("미켈란 빌딩", 37.5148, 127.0576, address="서울 강남구 봉은사로 520")
    assert a["anchored"] and a["times_seen"] == 1
    b = ga.anchor_place("미켈란 빌딩", 37.51481, 127.05761)      # re-seen → refreshed, not duplicated
    assert b["times_seen"] == 2 and len(ga._load()) == 1
    assert b["address"] == "서울 강남구 봉은사로 520"             # address survives a refresh


def test_nearest_is_radius_bound(tmp_path):
    ga._LEDGER = tmp_path / "geo.jsonl"
    ga.anchor_place("집", 37.5000, 127.0000)
    hit = ga.nearest_anchor(37.50005, 127.00005)                  # ~7m away → inside
    assert hit and hit["name"] == "집" and hit["distance_m"] < 30
    assert ga.nearest_anchor(37.51, 127.01) is None               # ~1.4km → honest None


def test_snapshot_inherits_anchor_name(tmp_path):
    ga._LEDGER = tmp_path / "geo.jsonl"
    sm._LEDGER = tmp_path / "spatial.jsonl"
    ga.anchor_place("사무실", 37.5148, 127.0576)
    r = sm.record_snapshot([{"label": "노트북", "x": 0.5, "y": 0.5}],
                           lat=37.51481, lon=127.05761)           # nameless room + GPS
    assert r["recorded"] and r["place"] == "사무실"                # inherited the anchored name
    assert r["geo"]["anchor"] == "사무실" and r["geo"]["distance_m"] < 30


def test_no_coords_stays_egocentric(tmp_path):
    ga._LEDGER = tmp_path / "geo.jsonl"
    sm._LEDGER = tmp_path / "spatial.jsonl"
    r = sm.record_snapshot([{"label": "컵", "x": 0.5, "y": 0.5}], place="책상")
    assert "geo" not in r and r["place"] == "책상"                 # untouched, honestly


def test_osm_resolver_is_optin(monkeypatch):
    monkeypatch.delenv("ATANOR_GEO_OSM", raising=False)
    assert ga.resolve_address(37.5, 127.0) is None                # network OFF by default
