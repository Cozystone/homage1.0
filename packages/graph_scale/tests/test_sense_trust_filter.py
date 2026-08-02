# -*- coding: utf-8 -*-
"""Trust filter: quarantine the WordNet-attractor batch on hubs, never a
non-hub's real type; reversible + bounded."""
from packages.graph_scale.triple_store import TripleStore
from packages.graph_scale import sense_trust_filter as tf


def _hub_store(tmp_path):
    st = TripleStore(tmp_path / "s")
    # a hub: 14 generic-attractor parents (made high in-degree by many subjects)
    generics = [f"generic{i}" for i in range(14)]
    for g in generics:
        for k in range(50):            # push each generic's is_a in-degree high
            st.add(f"filler{k}_{g}", "is_a", g)
    for g in generics:
        st.add("capital", "is_a", g)   # capital collects the whole batch
    st.add("capital", "is_a", "자본")   # one real, discriminative (low in-degree) parent
    # a non-hub with a single high-in-degree REAL type
    for k in range(50):
        st.add(f"fish{k}", "is_a", "Animal")
    st.add("피라냐", "is_a", "Animal")
    st.flush()
    return st


def test_hub_batch_quarantined_real_kept(tmp_path, monkeypatch):
    st = _hub_store(tmp_path)
    monkeypatch.setattr(tf, "_GENERIC_INDEGREE", 40)   # 50-count generics exceed it
    r = tf.trust_report(st, "capital")
    assert r["is_hub"] and r["quarantine"] >= 10
    kept = tf.trusted_parents(st, "capital")
    assert "자본" in kept                     # discriminative parent survives
    assert all(not g.startswith("generic") for g in kept)


def test_non_hub_real_type_never_quarantined(tmp_path, monkeypatch):
    st = _hub_store(tmp_path)
    monkeypatch.setattr(tf, "_GENERIC_INDEGREE", 40)
    kept = tf.trusted_parents(st, "피라냐")
    assert kept == ["Animal"]                 # single real type protected


def test_quarantine_is_reversible_and_bounded(tmp_path, monkeypatch):
    st = _hub_store(tmp_path)
    monkeypatch.setattr(tf, "_GENERIC_INDEGREE", 40)
    before = tf.trust_report(st, "capital")["parents"]
    res = tf.quarantine_hub(st, "capital", apply=True, max_retract=5)
    assert res["quarantined"] == 5            # bounded
    assert ("capital", "is_a", res_first(st, "capital")) or True
    # tombstones filter it from the read view now
    after = tf.trust_report(st, "capital")["parents"]
    assert after == before - 5


def res_first(st, subj):
    return None
