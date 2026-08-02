# -*- coding: utf-8 -*-
"""First autopoiesis organ: ATANOR produces gated work orders on its own components —
diagnosis read from its own source, operator gate absolute, duplicates suppressed."""
from packages.continuous_self.self_patch_proposals import (
    _diagnose, pending_patches, propose_code_patch)


def test_diagnosis_reads_my_own_source_at_the_flagged_site(tmp_path):
    finding = "UNSALTED hash at scripts/build_c1_battery.py:136"
    d = _diagnose(finding)
    assert d["site"] == "scripts/build_c1_battery.py:136"
    assert d["source_excerpt"] and "136:" in d["source_excerpt"]   # looked at, not imagined


def test_proposal_is_gated_and_deduplicated(tmp_path):
    led = tmp_path / "proposals.jsonl"
    p1 = propose_code_patch("UNSALTED hash at scripts/build_c1_battery.py:136", ledger=led)
    assert p1 and p1["status"] == "proposed" and p1["produced_by"] == "atanor.self_inspection"
    # nothing auto-applies: the only state this organ can write is "proposed"
    assert pending_patches(led) and pending_patches(led)[0]["id"] == p1["id"]
    # noticing twice is attention; proposing twice is noise
    assert propose_code_patch("UNSALTED  hash at scripts/build_c1_battery.py:136", ledger=led) is None
    assert len(pending_patches(led)) == 1


def test_wiring_level_finding_without_site_still_proposes_honestly(tmp_path):
    led = tmp_path / "p.jsonl"
    p = propose_code_patch("[B_unwired_assets] 25", ledger=led)
    assert p and p["diagnosis"]["site"] is None
    assert "wiring level" in p["diagnosis"]["note"]
