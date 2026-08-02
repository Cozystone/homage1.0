# -*- coding: utf-8 -*-
"""Self-judged autonomy: trust earns the reversible band, the hard ceiling never
moves (dangerous/irreversible actions always need an operator, at any trust)."""
from packages.graph_scale.autonomy_self import (
    HARD_CEILING, recommend_tier, self_decide, trust_score)


def test_hard_ceiling_never_moves_even_at_max_trust():
    for cls in ("production_deploy", "git_push", "store_truncate_or_delete", "code_to_live"):
        d = self_decide(cls, reversible=True, blast=0.0, trust=1.0)   # max trust
        assert d["mode"] == "needs_operator" and d["ceiling_hit"] is True


def test_irreversible_always_needs_operator():
    d = self_decide("local_ledger_write", reversible=False, blast=0.0, trust=1.0)
    assert d["mode"] == "needs_operator" and d["ceiling_hit"] is True


def test_reversible_band_opens_with_trust():
    low = self_decide("local_ledger_write", reversible=True, blast=0.1, trust=0.2)
    high = self_decide("local_ledger_write", reversible=True, blast=0.1, trust=0.9)
    assert low["mode"] == "needs_operator"      # little trust -> ask
    assert high["mode"] == "auto"               # earned trust -> act (reversible only)


def test_full_host_is_never_self_recommended():
    assert recommend_tier(1.0)["recommended_tier"] != "FULL_HOST_AUTHORITY"
    assert recommend_tier(0.1)["recommended_tier"] == "OBSERVE_ONLY"


def test_trust_is_earned_not_asserted():
    t = trust_score()
    assert 0.0 <= t["score"] <= 1.0 and "confirmed_predictions" in t
