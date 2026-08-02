# -*- coding: utf-8 -*-
"""Sensus reads REAL scorecards and builds an honest weakness map.

Pins that the sensus reads the actual on-disk ATANOR scorecards (never fabricates), derives normalized
scores in [0, 1], and attaches the three existence flags probed from the real repo.
"""
from __future__ import annotations

from pathlib import Path

from packages.self_evolution import deficiency_sensus as ds


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_sensus_reads_the_real_on_disk_scorecards():
    """The always-present live scorecards must be READ from their real files, not invented."""
    wm = {w.domain: w for w in ds.build_weakness_map()}
    # every registry domain is sensed
    for domain in ("consciousness", "efficiency", "knowledge", "fluency", "code", "relational_routing"):
        assert domain in wm, domain

    # consciousness score is derived from the real audit scorecard on disk
    cons = wm["consciousness"]
    src = _root() / cons.evidence["source"]
    assert src.exists(), f"sensus must read a real file: {src}"
    assert src.name == "scorecard.json"
    assert cons.score is not None and 0.0 <= cons.score <= 1.0
    assert cons.evidence["present"] >= 1  # real counts, not a placeholder

    # efficiency score is derived from the real metacog baselines on disk
    eff = wm["efficiency"]
    assert (_root() / eff.evidence["source"]).exists()
    assert eff.score is not None and 0.0 <= eff.score <= 1.0
    assert eff.evidence["n"] >= 1

    # knowledge score is derived from the real wild_web sessions on disk
    know = wm["knowledge"]
    assert (_root() / know.evidence["source"]).exists()
    assert know.score is not None and 0.0 <= know.score <= 1.0

    # fluency score is the real measured faithfulness; naturalness is explicitly unmeasured
    flu = wm["fluency"]
    assert (_root() / flu.evidence["source"]).exists()
    assert flu.score is not None and 0.0 <= flu.score <= 1.0
    assert "naturalness" in flu.evidence["unmeasured_axis"].lower()


def test_computed_scorecards_are_read_from_cache():
    """The two COMPUTED scorecards (code mastery, relational accuracy) are read from cached real runs."""
    ds.refresh_relational_scorecard()  # cheap (~0.05s); guarantees a real cached file
    code_cache = _root() / "data" / "self_evolution" / "scorecards" / "code_mastery_v1.json"
    if not code_cache.exists():
        ds.refresh_code_scorecard()   # one-time ~10s on a clean checkout; cached thereafter
    wm = {w.domain: w for w in ds.build_weakness_map()}
    assert wm["relational_routing"].score is not None
    assert 0.0 <= wm["relational_routing"].score <= 1.0
    assert wm["code"].score is not None
    assert 0.0 <= wm["code"].score <= 1.0


def test_score_is_normalized_and_flags_are_boolean():
    for w in ds.build_weakness_map():
        assert (w.score is None) or (0.0 <= w.score <= 1.0), w.domain
        assert isinstance(w.gate_exists, bool)
        assert isinstance(w.generator_exists, bool)
        assert isinstance(w.verifier_exists, bool)
        # evolvable is exactly the conjunction of the three existence flags
        assert w.evolvable == (w.gate_exists and w.generator_exists and w.verifier_exists), w.domain
