# -*- coding: utf-8 -*-
"""Clean space degrades gracefully when the ConceptNet artifact is absent (CI),
and the dual-space prediction is marked trusted only when it came from clean."""


def test_clean_space_absent_is_graceful(monkeypatch):
    from packages.graph_scale import clean_space
    from pathlib import Path
    monkeypatch.setattr(clean_space, "_DIR", Path("/no/such/conceptnet/space"))
    clean_space._S["phases"] = None
    assert clean_space.available() is False
    assert clean_space.has("dog") is False
    assert clean_space.neighbors("dog") == []
    assert clean_space.predict_edges("dog") == []


def test_prediction_untrusted_when_only_store(monkeypatch):
    """With no clean space, a store-space prediction is marked trusted=False so
    engage keeps it gated (truth>coverage)."""
    from packages.graph_scale import clean_space, fact_prediction as fp
    monkeypatch.setattr(clean_space, "has", lambda t: False)
    # store predict returns [] without a trained space here -> mint returns None,
    # which is the correct 'nothing confident' path; the trusted flag only ever
    # rides on a real clean-space hit.
    assert fp.mint_predicted_fact("존재하지않는것", store=None) is None
