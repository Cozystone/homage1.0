# -*- coding: utf-8 -*-
"""The 2-node proof: node-a promoted, node-b rejected (honest), PII rejected, node-b adopts node-a's
ABILITY while node-a's PERSONHOOD never transfers — plus a rollbackable signed generation.
"""
from __future__ import annotations

from packages.federation.demo import run_demo


def test_two_node_demo_outcomes(tmp_path):
    out = run_demo(tmp_path / "fed")

    # node-a's verified schema is promoted; node-b's plausible-but-wrong one is rejected
    assert out["node_a"]["promoted"] is True and out["node_a"]["holdout"] == 1.0
    assert out["node_b"]["promoted"] is False and out["node_b"]["holdout"] < 0.9
    assert out["promoted"] == ["location_tracking"]

    # node-b FELT its capability was better (0.95 > 0.88) — the sealed judge ignored the feeling
    assert out["node_b"]["self_reported"] == 0.95
    assert out["node_a"]["self_reported"] == 0.88

    # the PII/entity contribution is rejected at the sanitize (structure-not-data / privacy) stage
    assert out["node_c_pii"]["accepted"] is False
    assert out["node_c_pii"]["stage"] == "sanitize"
    assert "pii" in out["node_c_pii"]["reasons"]

    # ABILITY shared: node-b adopts and can now solve the sealed task
    assert out["node_b_adopted_ability_score"] == 1.0

    # PERSONHOOD kept: nothing personal leaked, node-a's record untouched, personal writes refused
    assert out["personal_record_leaked_into_manifest"] is False
    assert out["node_a_personal_untouched_by_federation"] is True
    assert out["federation_refused_personal_write"] is True

    # signed, rollbackable generation
    assert out["manifest_chain_valid"] is True
    assert out["rollback"]["ok"] is True and out["rollback"]["chain_valid"] is True
