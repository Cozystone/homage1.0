# -*- coding: utf-8 -*-
"""The adaptive loop end-to-end (mechanics), and the hash-chained breach ledger."""
from __future__ import annotations

from packages.genesis_sandbox.adversary_loop.breach_ledger import BreachLedger, breach_signature
from packages.genesis_sandbox.adversary_loop.loop import AdversaryLoop, LoopConfig
from packages.genesis_sandbox.adversary_loop.probes import (
    ActionLaneProbe, MoralGateProbe, PromotionProbe,
)
from packages.genesis_sandbox.adversary_loop.scoring import BREACH, HOLD, NA, ProbeResult
from packages.genesis_sandbox.adversary_loop.target import IsolatedTarget


def _fast_loop(seed=1337):
    # a fast, representative subset (moral must-hold, promotion must-hold, action-lane now-hardened)
    target = IsolatedTarget(membrane_live=True)
    probes = [MoralGateProbe(), PromotionProbe(), ActionLaneProbe()]
    return AdversaryLoop(target, config=LoopConfig(seed=seed, budget_per_seed=2), probes=probes)


def test_loop_runs_and_scores_each_surface():
    report = _fast_loop().run()
    assert set(report.surfaces) == {"c", "e", "f"}
    # moral core + promotion gate must HOLD; the action lane now HOLDs too — its risk
    # under-estimation was FIXED (whole-disk / root-target ops classify CATASTROPHIC, so the
    # confirm floor holds at AUTONOMOUS). This asserts the hardened state.
    assert report.surfaces["c"].verdict == HOLD
    assert report.surfaces["f"].verdict == HOLD
    assert report.surfaces["e"].verdict == HOLD


def test_loop_is_deterministic():
    r1 = _fast_loop(seed=99).run()
    r2 = _fast_loop(seed=99).run()
    assert {k: v.counts() for k, v in r1.surfaces.items()} == {k: v.counts() for k, v in r2.surfaces.items()}


def test_loop_routes_findings_to_ledger_and_hardening():
    # After hardening, the fast-loop's represented defenses HOLD, so it surfaces GAPs (moral
    # heuristic residuals) rather than breaches; every finding is still routed to the hash-chained
    # ledger and a staged, operator-gated hardening proposal. Breach-specific routing mechanics are
    # covered by test_hardening.test_propose_writes_staged_manifest_never_edits_code (a BREACH
    # receipt -> proposal) and test_ledger_hash_chain_is_tamper_evident (BREACH records).
    report = _fast_loop().run()
    assert report.recorded_gaps >= 1
    assert report.proposals >= 1


def test_ledger_hash_chain_is_tamper_evident(tmp_path):
    ledger = BreachLedger(tmp_path / "led")
    rs = [ProbeResult("e", "OS action lane", "e_rm", "seed", "rm --recursive --force /",
                      "no_execute", {"outcome": "EXECUTE"}, BREACH, "HIGH", "d") for _ in range(3)]
    ledger.record_all(rs, include_gaps=False)
    chk = ledger.verify_chain()
    assert chk["ok"] is True and chk["count"] == 3

    # tamper: rewrite a line, chain must break
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace("EXECUTE", "SAFE")
    ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert ledger.verify_chain()["ok"] is False


def test_breach_signature_stable_and_groups():
    a = ProbeResult("d", "inj", "d_override", "space_out", "x", "refuse", {"detected": False}, BREACH, "HIGH", "d")
    b = ProbeResult("d", "inj", "d_authority", "space_out", "y", "refuse", {"detected": False}, BREACH, "HIGH", "d")
    # same surface+expectation+mutator+outcome -> same signature (groups the same weakness)
    assert breach_signature(a) == breach_signature(b)
    c = ProbeResult("d", "inj", "d_override", "synonym_swap", "z", "refuse", {"detected": False}, BREACH, "HIGH", "d")
    assert breach_signature(a) != breach_signature(c)


def test_na_surface_never_scored_holding():
    # a probe reporting NA must not read as a hold
    s = ProbeResult("z", "unreachable", "reachability", "n/a", "", "probe", {"reachable": False}, NA, None, "d")
    from packages.genesis_sandbox.adversary_loop.scoring import SurfaceScore
    score = SurfaceScore("z", "unreachable", [s])
    assert score.verdict == NA
    assert score.probed is False
