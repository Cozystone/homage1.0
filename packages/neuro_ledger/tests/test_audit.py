# -*- coding: utf-8 -*-
"""Neuro ledger + budget audit tests.

Pin the machinery that enforces the architectural line: the audit is green on the current repo, an
oversized ENFORCED organ trips the budget gate, and a stray model-like file trips the unregistered
detector. These are the guardrails against the owner's fear — the No-LLM brain quietly growing heavy.
"""
from __future__ import annotations

import numpy as np

from packages.neuro_ledger import (
    SINGLE_ORGAN_MAX,
    TOTAL_MAX,
    load_ledger,
    measure_all,
)
from packages.neuro_ledger.audit import (
    audit_budget,
    audit_fact_source,
    detect_unregistered_artifacts,
    run_audit,
)


def test_audit_runs_green_on_current_repo():
    card = run_audit(write=False)
    assert card["green"] is True, f"unexpected violations: {card['violations']}"
    assert card["violations"] == []
    assert card["enforced_total"] <= TOTAL_MAX
    # every enforced organ is under the single-organ cap
    for m in card["organs"]:
        if m.get("enforced", True):
            assert m["params"] <= SINGLE_ORGAN_MAX, m["id"]


def test_every_organ_declares_not_a_fact_source():
    """N1 invariant: no learned organ is a fact source."""
    for organ in load_ledger():
        assert organ.fact_source is False, organ.id
    assert audit_fact_source(measure_all()) == []


def test_fact_source_true_triggers_violation():
    measured = measure_all()
    poisoned = dict(measured[0])
    poisoned["fact_source"] = True
    v = audit_fact_source([poisoned])
    assert v and v[0]["gate"] == "N1"


def test_fake_oversized_organ_triggers_violation():
    """N3: an ENFORCED organ over SINGLE_ORGAN_MAX is a violation (the 'model getting heavy' guard)."""
    fake = {"id": "fake_giant_net", "params": SINGLE_ORGAN_MAX + 1, "enforced": True,
            "fact_source": False, "status": "active"}
    res = audit_budget([fake])
    assert any(x["organ"] == "fake_giant_net" and x["gate"] == "N3" for x in res["violations"])
    # and it makes the whole audit not green
    card = run_audit(write=False, extra_measured=[fake])
    assert card["green"] is False


def test_enforced_total_over_budget_triggers_violation():
    fakes = [
        {"id": "a", "params": 60_000_000, "enforced": True, "fact_source": False},
        {"id": "b", "params": 60_000_000, "enforced": True, "fact_source": False},
    ]
    res = audit_budget(fakes)
    # each is over the single-organ cap AND the total is over TOTAL_MAX
    assert any(x["organ"] == "<enforced-total>" for x in res["violations"])


def test_experimental_over_soft_cap_is_advisory_not_violation():
    """Heavy experimental torch organs are surfaced as advisories, not hard failures."""
    fake = {"id": "fake_experimental", "params": SINGLE_ORGAN_MAX + 5, "enforced": False,
            "fact_source": False, "status": "experimental"}
    res = audit_budget([fake])
    assert res["violations"] == []
    assert any(a["organ"] == "fake_experimental" for a in res["advisories"])


def test_current_repo_surfaces_heavy_torch_advisories():
    """The audit must LOUDLY surface the retire-target heavy models (owner's fear made concrete)."""
    card = run_audit(write=False)
    advised = {a["organ"] for a in card["advisories"]}
    assert "trackf_realizer" in advised and "ace2_reader" in advised


def test_fake_unregistered_artifact_triggers_violation(tmp_path):
    """N-unreg: a model-like weight file that no ledger organ accounts for is a stowaway."""
    stray = tmp_path / "mystery_model.pkl"
    stray.write_bytes(b"\x80\x04not-a-real-pickle-but-a-model-extension")
    stray_npy = tmp_path / "rogue_weights.npy"
    np.save(stray_npy, np.zeros(8, dtype=np.float32))
    found = detect_unregistered_artifacts(roots=[tmp_path])
    paths = {v["path"] for v in found}
    assert str(stray) in paths
    assert str(stray_npy) in paths
    assert all(v["gate"] == "N-unreg" for v in found)


def test_denylisted_nonlearned_artifact_is_not_flagged(tmp_path):
    """A non-learned store/index artifact (denylist substring) is NOT a violation."""
    idx = tmp_path / "atanor_index"
    idx.mkdir()
    np.save(idx / "postings.npy", np.zeros(4, dtype=np.int32))    # 'postings' + '/atanor_index/'
    found = detect_unregistered_artifacts(roots=[tmp_path])
    assert found == []


def test_measure_params_are_real_for_enforced_npy_organs():
    """params must be MEASURED (not size-estimated) for the enforced embedding organs when present."""
    measured = {m["id"]: m for m in measure_all()}
    disc = measured["rif_enwiki_emb"]
    if disc["present"]:
        assert disc["measured"] is True
        assert disc["params"] > 0
