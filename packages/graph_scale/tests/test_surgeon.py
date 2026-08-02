# -*- coding: utf-8 -*-
"""The Surgeon: catch type-disjoint contamination in real time, precisely."""
from packages.graph_scale.surgeon import inspect, scan


class _Store:
    def __init__(self, facts):
        self._f = {}
        for s, p, o in facts:
            self._f.setdefault(s, []).append((s, p, o))
    def facts_about(self, t, limit=30):
        return self._f.get(t, [])[:limit]


def _store():
    return _Store([
        ("방콕", "is_a", "도시"), ("방콕", "is_a", "수도"),          # PLACE (2 signals)
        ("소크라테스", "is_a", "철학자"), ("소크라테스", "is_a", "사람"),  # PERSON
        ("피라냐", "is_a", "물고기"), ("피라냐", "is_a", "동물"),       # SPECIES
    ])


def test_cuts_place_is_a_group():
    v = inspect(_store(), "방콕", "청교도")
    assert v.status == "contaminated"
    assert v.subject_family == "PLACE" and v.obj_family == "GROUP"


def test_spares_consistent_edges():
    st = _store()
    assert inspect(st, "방콕", "지역").status in ("clean", "suspect")   # PLACE/PLACE-ish
    assert inspect(st, "피라냐", "동물").status == "clean"              # SPECIES/SPECIES


def test_does_not_cut_soft_mismatch_or_weak_subject():
    # a subject with only ONE type signal must not be excised (precision rule)
    st = _Store([("x", "is_a", "도시")])                  # single PLACE signal
    assert inspect(st, "x", "청교도").status == "suspect"   # not enough to cut


def test_scan_reports_incisions_nondestructively():
    st = _store()
    r = scan(st, [("방콕", "청교도"), ("피라냐", "동물"), ("소크라테스", "사람")])
    assert r["contaminated"] == 1 and r["reviewed"] == 3
    assert r["incisions"][0]["subject"] == "방콕"
    assert 0.0 <= r["contamination_rate"] <= 1.0
