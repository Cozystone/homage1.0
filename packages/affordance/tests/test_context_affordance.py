# -*- coding: utf-8 -*-
"""The affordance engine: perceive state → lay walkable paths by RESONANCE, not conditions.
Graph off in tests (deterministic) — the doctrine holds on concept overlap alone."""
from packages.affordance.context_affordance import Observation, propose, resonance
from packages.os_action_lane.models import GateOutcome, RiskLevel, TrustTier


def test_joy_lights_the_good_news_path():
    obs = Observation(concepts=["웃음", "기쁨"], source="face")
    out = propose(obs, use_graph=False)
    assert not out["silent"]
    assert out["chosen"]["affordance_id"] in {"warm_good_news", "particle_response"}
    ids = {p["affordance_id"] for p in out["paths"]}
    assert "warm_good_news" in ids                       # the joy path resonated
    assert "offer_rest" not in ids                       # the fatigue path did NOT (no if/then)


def test_fatigue_lights_the_rest_path_not_joy():
    obs = Observation(concepts=["피곤", "하품", "눈감김"], source="face")
    out = propose(obs, use_graph=False)
    ids = {p["affordance_id"] for p in out["paths"]}
    assert "offer_rest" in ids and "warm_good_news" not in ids


def test_grounding_is_the_real_resonating_concepts():
    obs = Observation(concepts=["웃음", "기쁨"], source="face")
    chosen = next(p for p in propose(obs, use_graph=False)["paths"]
                  if p["affordance_id"] == "warm_good_news")
    assert set(chosen["grounding"]) & {"웃음", "기쁨"}    # honest why — actual overlap, not invented


def test_no_resonance_is_silence():
    obs = Observation(concepts=["쿠버네티스", "환율"], source="screen")
    out = propose(obs, use_graph=False)
    assert out["silent"] and out["chosen"] is None       # voice-or-silence: nothing fires


def test_internal_particle_path_is_autonomous_external_needs_approval():
    obs = Observation(concepts=["기쁨", "웃음"], source="face")
    paths = {p["affordance_id"]: p for p in propose(obs, tier=TrustTier.ASSIST, use_graph=False)["paths"]}
    # the particle path is READONLY (internal) → runs now even at a low tier
    assert paths["particle_response"]["outcome"] == int(GateOutcome.EXECUTE)
    assert paths["particle_response"]["risk"] == int(RiskLevel.READONLY)
    # asking the user is REVERSIBLE → waits for approval until GUARDED
    assert paths["warm_good_news"]["outcome"] == int(GateOutcome.NEEDS_APPROVAL)


def test_guarded_tier_lets_reversible_paths_run():
    obs = Observation(concepts=["기쁨", "웃음"], source="face")
    paths = {p["affordance_id"]: p for p in propose(obs, tier=TrustTier.GUARDED, use_graph=False)["paths"]}
    assert paths["warm_good_news"]["outcome"] == int(GateOutcome.EXECUTE)


def test_kill_switch_blocks_every_path():
    obs = Observation(concepts=["기쁨", "웃음"], source="face")
    out = propose(obs, tier=TrustTier.AUTONOMOUS, kill_switch=True, use_graph=False)
    assert all(p["outcome"] == int(GateOutcome.BLOCKED) for p in out["paths"])


def test_resonance_partial_credit_for_compounds():

    score, hits = resonance(["머리색", "외형변화"], ["외형변화", "머리색", "변화"], use_graph=False)
    assert score > 0.5 and "외형변화" in hits
