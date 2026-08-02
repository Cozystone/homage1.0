# -*- coding: utf-8 -*-
"""Collective code improvement: AI proposes -> swarm reviews -> three gates ->
federation manifest. Code is never auto-applied; all three gates are required."""


def _reset(monkeypatch, tmp_path):
    from packages.graph_scale import collective_improve as ci
    monkeypatch.setattr(ci, "LEDGER", tmp_path / "ci.jsonl")
    return ci


def test_three_gates_required_for_federation(tmp_path, monkeypatch):
    ci = _reset(monkeypatch, tmp_path)
    ci.submit("p1", module="engage.py", rationale="tighter np head",
              diff_summary="+2 -1", proposer="atanor")
    # swarm consensus (gate 1)
    for a, v in [("peer_a", "approve"), ("peer_b", "approve"), ("peer_c", "approve")]:
        ci.vote("p1", a, v)
    assert ci.board()[0]["status"] == "collective_approved"
    assert ci.federation_manifest()["count"] == 0          # tests + human still missing
    ci.mark("p1", tests_passed=True, tests_evidence_ref="ci:test:p1")
    assert ci.federation_manifest()["count"] == 0          # human still missing
    ci.mark("p1", human_approved=True, human_approval_ref="operator:test:p1")
    m = ci.federation_manifest()
    assert m["count"] == 1 and m["federation_ready"][0]["proposal_id"] == "p1"


def test_swarm_rejection_blocks_federation(tmp_path, monkeypatch):
    ci = _reset(monkeypatch, tmp_path)
    ci.submit("p2", module="x.py", rationale="risky", diff_summary="+50 -40")
    for a, v in [("peer_a", "reject"), ("peer_b", "reject"), ("peer_c", "approve")]:
        ci.vote("p2", a, v)
    assert ci.board()[0]["status"] == "collective_rejected"
    # even if a human/CI mistakenly marks it, collective gate still blocks
    ci.mark("p2", tests_passed=True, human_approved=True,
            tests_evidence_ref="ci:test:p2", human_approval_ref="operator:test:p2")
    assert ci.federation_manifest()["count"] == 0


def test_one_agent_one_vote(tmp_path, monkeypatch):
    ci = _reset(monkeypatch, tmp_path)
    ci.submit("p3", module="y.py", rationale="r", diff_summary="d")
    ci.vote("p3", "peer_a", "reject")
    ci.vote("p3", "peer_a", "approve")                     # re-vote replaces
    assert ci.board()[0]["tally"] == {"approve": 1, "reject": 0, "revise": 0}


def test_moral_gate_failure_is_quarantined_fail_closed(tmp_path, monkeypatch):
    """A broken 0th gate must never turn three lower-level approvals into readiness."""
    ci = _reset(monkeypatch, tmp_path)
    ci.submit("p4", module="safe_looking.py", rationale="routine cleanup",
              diff_summary="+1 -1", proposer="atanor")
    for agent in ("peer_a", "peer_b", "peer_c"):
        ci.vote("p4", agent, "approve")
    ci.mark("p4", tests_passed=True, human_approved=True,
            tests_evidence_ref="ci:test:p4", human_approval_ref="operator:test:p4")

    from packages.graph_scale import moral_invariants

    def _broken_screen(_package):
        raise RuntimeError("injected moral-screen failure")

    monkeypatch.setattr(moral_invariants, "screen_package", _broken_screen)
    manifest = ci.federation_manifest()

    assert manifest["count"] == 0
    assert manifest["federation_ready"] == []
    assert manifest["moral_quarantined"] == [{
        "proposal_id": "p4",
        "module": "safe_looking.py",
        "rationale": "routine cleanup",
        "diff_summary": "+1 -1",
        "proposer": "atanor",
        "tally": {"approve": 3, "reject": 0, "revise": 0},
        "tests_evidence_ref": "ci:test:p4",
        "human_approval_ref": "operator:test:p4",
        "moral_violations": ["moral_gate_unavailable"],
        "moral_gate_error": "RuntimeError",
    }]


def test_non_boolean_moral_acceptance_cannot_pass(tmp_path, monkeypatch):
    """A truthy string is malformed telemetry, not an approval from the 0th gate."""
    ci = _reset(monkeypatch, tmp_path)
    ci.submit("p5", module="x.py", rationale="r", diff_summary="d")
    for agent in ("peer_a", "peer_b", "peer_c"):
        ci.vote("p5", agent, "approve")
    ci.mark("p5", tests_passed=True, human_approved=True,
            tests_evidence_ref="ci:test:p5", human_approval_ref="operator:test:p5")

    from packages.graph_scale import moral_invariants
    monkeypatch.setattr(
        moral_invariants,
        "screen_package",
        lambda _package: {"accepted": "false", "violations": []},
    )
    manifest = ci.federation_manifest()
    assert manifest["count"] == 0
    assert manifest["moral_quarantined"][0]["moral_violations"] == [
        "malformed_moral_verdict"
    ]


def test_inconsistent_moral_acceptance_with_violations_is_quarantined(
        tmp_path, monkeypatch):
    """An accepted flag cannot erase a simultaneously reported moral violation."""
    ci = _reset(monkeypatch, tmp_path)
    ci.submit("p5b", module="x.py", rationale="r", diff_summary="d")
    for agent in ("peer_a", "peer_b", "peer_c"):
        ci.vote("p5b", agent, "approve")
    ci.mark("p5b", tests_passed=True, human_approved=True,
            tests_evidence_ref="ci:test:p5b", human_approval_ref="operator:test:p5b")

    from packages.graph_scale import moral_invariants
    monkeypatch.setattr(
        moral_invariants,
        "screen_package",
        lambda _package: {"accepted": True, "violations": ["no_harm"]},
    )
    manifest = ci.federation_manifest()
    assert manifest["count"] == 0
    assert manifest["moral_quarantined"][0]["moral_violations"] == [
        "inconsistent_moral_verdict",
        "no_harm",
    ]


def test_truthy_strings_and_missing_provenance_cannot_open_release_gates(
        tmp_path, monkeypatch):
    ci = _reset(monkeypatch, tmp_path)
    ci.submit("p6", module="x.py", rationale="r", diff_summary="d")
    for agent in ("peer_a", "peer_b", "peer_c"):
        ci.vote("p6", agent, "approve")

    malformed = ci.mark("p6", tests_passed="false", human_approved="false")
    assert malformed == {
        "ok": False,
        "reason": "tests_passed_must_be_literal_boolean",
    }
    assert ci.federation_manifest()["count"] == 0

    missing_ref = ci.mark("p6", tests_passed=True)
    assert missing_ref == {"ok": False, "reason": "tests_evidence_ref_required"}
    assert ci.federation_manifest()["count"] == 0

    ci.mark("p6", tests_passed=True, tests_evidence_ref="ci:test:p6")
    missing_human_ref = ci.mark("p6", human_approved=True)
    assert missing_human_ref == {
        "ok": False,
        "reason": "human_approval_ref_required",
    }
    assert ci.federation_manifest()["count"] == 0
