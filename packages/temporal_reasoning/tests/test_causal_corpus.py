# -*- coding: utf-8 -*-
"""Causal corpus: action→outcome order pairs from real human records (postmortems, GDELT),
fed to the learned field through a quarantined store."""
from packages.temporal_reasoning.causal_corpus import (feed, mine_incident_timeline,
                                                       retrain_field_with_causal, STORE)

_POSTMORTEM = """
Summary: elevated error rates after a config deploy.
Timeline (all times UTC):
14:02 - config deploy started to production fleet
14:09 - error rate rose sharply on api tier
14:14 - oncall paged and incident declared
14:31 - rollback completed and errors subsided
15:10 - postmortem review scheduled
"""


def test_incident_timeline_yields_true_order_pairs():
    pairs = mine_incident_timeline(_POSTMORTEM)
    assert pairs, "clock-stamped lines must yield pairs"
    flat = set(pairs)
    assert ("deploy", "error") in flat or ("config", "error") in flat    # action -> outcome
    assert ("rollback", "postmortem") in flat or ("errors", "postmortem") in flat
    # order is real: nothing claims postmortem precedes deploy
    assert ("postmortem", "deploy") not in flat


def test_midnight_rollover_keeps_order_monotone():
    txt = "23:50 - deploy started\n00:05 - alerts fired overnight\n00:20 - rollback done"
    pairs = mine_incident_timeline(txt)
    assert ("deploy", "alerts") in set(pairs)              # 00:05 correctly read as NEXT day


def test_feed_quarantine_and_field_retrain(tmp_path, monkeypatch):
    import packages.temporal_reasoning.causal_corpus as cc
    monkeypatch.setattr(cc, "STORE", tmp_path / "causal_counts.json")
    r = cc.feed(mine_incident_timeline(_POSTMORTEM) * 3, source="fixture")   # 3x for min_count
    assert r["total_evidence"] > 0 and (tmp_path / "causal_counts.json").exists()
    field = cc.retrain_field_with_causal(min_count=2)
    assert field is not None
    # the learned phases recover the causal order: deploy precedes rollback
    conf = field.order_confidence("deploy", "rollback")
    assert conf is not None and conf > 0.5                 # learned from evidence, not asserted
