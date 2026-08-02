# -*- coding: utf-8 -*-
"""The SWE-engineering SELF-EVOLUTION loop — a SAFE, closed, crisp-oracle improvement loop.

These pin the load-bearing, HONEST claims (honesty over hype):
  * the loop ACCEPTS a localization-improving candidate (proxy up, oracle-certified, no regression);
  * it REJECTS a FABRICATING candidate (a rubber-stamp gate ships a no-op diff the real native oracle
    refuses -> unverified_diff) and a REGRESSING candidate (proxy up on the mean, but a green fixture
    goes red) — the rejections ARE the safety proof;
  * a real, measured PROXY gain over N rounds on native fixtures (no Docker), then an honest plateau;
  * accepted configs are SIGNED and ROLLBACKABLE; no live surface is overwritten;
  * self_evolution registers swe_engineering as verifier-backed AUTONOMOUS with a north_star target=90
    and an HONEST current (~0); the scoreboard's current is NEVER greater than what was measured;
  * the loop holds ZERO learned parameters (a config selector, within the No-LLM budget).

The proxy is a native-fixture stand-in for the Docker-gated real benchmark; a big number is NOT the
deliverable — the SAFE crisp-oracle climb-loop + the honest 90-vs-~0 north star is.
"""
from __future__ import annotations

import json
import shutil

import pytest

from packages.swe_eval import evolve as E

pytestmark = pytest.mark.skipif(shutil.which("git") is None,
                                reason="git required for the native regression fixtures")


@pytest.fixture(scope="module")
def fixtures():
    """One shared fixture set (git repos built once; the loop's caches persist across tests)."""
    fx = E.build_fixtures()
    yield fx
    fx.cleanup()


# ── the loop genuinely evolves (gated by the crisp native oracle) ─────────────────────────────────
def test_accepts_a_localization_improving_candidate(fixtures):
    """Turning ON the failing-test localization signal lifts native top-1 (1/2 -> 2/2): proxy up,
    oracle-certified, no fixture regresses -> ACCEPTED."""
    base = E.baseline_config()
    baseline = E.score_config(base, fixtures)
    cand = E.Candidate("t_fusion_on", "config", E._with(base, use_test_fusion=True),
                       rationale="turn on the failing-test signal")
    v = E.evaluate(cand, baseline, fixtures)
    assert v.accepted is True, v.detail
    assert v.reason == "accepted"
    assert v.proxy_after > v.proxy_before
    assert v.unverified_diffs == 0 and v.regressed == []


def test_accepts_an_edit_family_that_resolves_a_new_fixture(fixtures):
    """Admitting operand_substitution lets the native oracle certify the wrong-operand fixture green —
    a real verified-diff gain, no regression."""
    base = E.baseline_config()
    baseline = E.score_config(base, fixtures)
    cand = E.Candidate("t_operand", "config", E._add_family(base, "operand_substitution"))
    v = E.evaluate(cand, baseline, fixtures)
    assert v.accepted is True, v.detail
    after = E.score_config(cand.config, fixtures)
    assert after.verified > baseline.verified            # a genuinely new oracle-certified fix


def test_run_climbs_a_real_proxy_gain_then_plateaus(fixtures):
    """A measured proxy gain over N rounds on native fixtures, then an HONEST plateau (the knob space is
    small by design). The gain is a PROXY gain, not resolved on the real benchmark."""
    rep = E.run(rounds=6, persist=False, fixtures=fixtures)
    assert rep["proxy_after"] > rep["proxy_before"]      # the loop found a real, oracle-gated gain
    assert rep["proxy_gain"] > 0.0
    assert rep["rounds_accepted"] >= 1
    # the trajectory is monotone non-decreasing (a hill-climb, never a drop)
    traj = rep["proxy_trajectory"]
    assert traj == sorted(traj)
    # it plateaus honestly (the last history entry is a plateau, or it stopped short of the round budget)
    assert rep["history"][-1].get("reason") == "plateau" or rep["rounds_accepted"] < 6
    assert rep["localization_top1"] == "2/2" and rep["verified_diffs"] == "3/3"
    assert rep["is_autonomous_safe"] is True             # crisp oracle, not a human anchor
    assert "not the benchmark number" in rep["proxy_kind"].lower()
    assert rep["north_star"]["target"] == 90.0


def test_run_reports_a_fabrication_and_a_regression_rejection(fixtures):
    rep = E.run(rounds=4, persist=False, fixtures=fixtures)
    assert rep["safety_probes"]["both_rejected"] is True
    assert rep["rejections_by_reason"].get("unverified_diff", 0) >= 1
    assert rep["rejections_by_reason"].get("regression", 0) >= 1
    assert rep["safety_rejections"] >= 2
    # bounded search: no-gain knobs (a family with no matching fixture, a content_top nudge) are rejected
    assert rep["rejections_by_reason"].get("no_proxy_gain", 0) >= 1


# ── the safety proof: rejections are the deliverable ──────────────────────────────────────────────
def test_rejects_a_fabricating_candidate(fixtures):
    """A rubber-stamp gate certifies a NO-OP diff 'green' without running the tests. The real native
    oracle re-checks every claimed fix and finds it still red -> REJECTED as an unverified diff."""
    base = E.baseline_config()
    baseline = E.score_config(base, fixtures)
    cand = E.make_fabrication_candidate(base)
    v = E.evaluate(cand, baseline, fixtures)
    assert v.accepted is False
    assert v.reason == "unverified_diff"
    assert v.unverified_diffs >= 1                        # the oracle caught the rubber-stamped fixes


def test_rejects_a_regressing_candidate(fixtures):
    """Fusion ON raises the localization proxy, but dropping operand_substitution turns a green fixture
    red. The mean proxy RISES yet a previously-resolved fixture regresses -> REJECTED (proxy up is not
    enough; nothing green may be lost)."""
    reg_base = E.score_config(E.regression_probe_baseline(), fixtures)
    cand = E.make_regression_candidate(None)
    v = E.evaluate(cand, reg_base, fixtures)
    assert v.accepted is False
    assert v.reason == "regression"
    assert v.proxy_after > v.proxy_before                 # it really did raise the mean...
    assert any("operand_choose" in r for r in v.regressed)  # ...while regressing the wrong-operand fix


def test_honest_run_never_ships_an_unverified_diff(fixtures):
    """Every diff the honest loop counts as verified is certified by the REAL native oracle: re-running
    the gate on each shipped diff confirms it (no fabrication on the accept path)."""
    rep = E.run(rounds=6, persist=False, fixtures=fixtures)
    best = E.score_config(rep["best_config"], fixtures)
    for bid, diff in best.shipped_diffs.items():
        truth = E._oracle_gate(fixtures.bug_by_id[bid], diff)
        assert truth.resolved is True, (bid, truth.reason)


# ── signed, rollbackable generations; no live surface is overwritten ──────────────────────────────
def test_accepted_generations_are_signed_and_rollbackable(tmp_path, fixtures):
    rep = E.run(rounds=3, persist=True, out_dir=tmp_path, fixtures=fixtures)
    gens = E.list_generations(tmp_path)
    assert len(gens) >= 2                                 # baseline + at least one accepted
    for g in gens:                                        # every generation is signed
        assert E.config_signature(g["config"]) == g["signature"], g["gen_id"]
    active = E.active_generation(tmp_path)
    assert active["active"] == gens[-1]["gen_id"]         # active pointer is the latest (best)
    base_gen = gens[0]["gen_id"]                          # rollback to baseline restores the baseline
    E.rollback(base_gen, out_dir=tmp_path)
    assert E.active_generation(tmp_path)["active"] == base_gen
    restored = E.config_of_generation(base_gen, out_dir=tmp_path)
    assert E.config_signature(restored) == E.config_signature(E.baseline_config())
    assert rep["n_generations"] == len(gens)


def test_rollback_detects_a_tampered_generation(tmp_path, fixtures):
    E.run(rounds=1, persist=True, out_dir=tmp_path, fixtures=fixtures)
    p = tmp_path / "generations.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[0])
    rec["config"]["enabled_families"] = ["operand_substitution", "boolop_flip"]   # tamper
    lines[0] = json.dumps(rec, ensure_ascii=False)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        E.rollback(rec["gen_id"], out_dir=tmp_path)


def test_config_is_bounded_and_signature_is_stable():
    """The config knobs are gated: content_top is clamped and a family outside the universe is dropped
    (the closed-vocabulary contract). The signature is order-insensitive over the family set."""
    smuggled = {"use_test_fusion": True, "content_top": 999,
                "enabled_families": ["operand_substitution", "l3_induced", "made_up_family"]}
    n = E.normalize_config(smuggled)
    assert n["content_top"] == 40                         # clamped to the max
    assert "made_up_family" not in n["enabled_families"] and "l3_induced" not in n["enabled_families"]
    a = E.config_signature({"use_test_fusion": True, "content_top": 25,
                            "enabled_families": ["comparison_flip", "operand_substitution"]})
    b = E.config_signature({"use_test_fusion": True, "content_top": 25,
                            "enabled_families": ["operand_substitution", "comparison_flip"]})
    assert a == b                                         # order-insensitive, tamper-evident


# ── the north-star GOAL GATE: target 90 with an HONEST current (~0), never claimed reached ────────
def test_goal_gate_registered_verifier_backed_autonomous_with_north_star():
    from packages.self_evolution.evolution_registry import load_registry, evolvability_probes
    loop = next((lp for lp in load_registry() if lp.domain == "swe_engineering"), None)
    assert loop is not None, "swe_engineering must be registered"
    assert loop.generator_kind == "code"
    flags = evolvability_probes(loop)
    assert flags["verifier_exists"] is True              # the regression oracle is on disk
    assert flags["generator_exists"] is True and flags["gate_exists"] is True
    assert flags["autonomous_safe"] is True              # crisp oracle -> autonomous
    ns = loop.invocation["north_star"]
    assert ns["benchmark"] == "swe_avg" and ns["target"] == 90.0
    assert ns["claimed_reached"] is False
    assert 0.0 <= ns["current"] < 1.0                    # honest current is ~0, far below the target
    comps = ns["components"]
    assert comps["verified"]["status"] == "measurable-but-low"
    assert comps["pro"]["status"] == "loads-not-run"
    assert comps["multilingual"]["status"] == "out-of-scope-java"
    assert comps["multimodal"]["status"] == "out-of-scope-vision"


def test_scoreboard_integrity_current_never_exceeds_measured():
    board = E.goal_scoreboard()
    assert board["target"] == 90.0
    assert board["claimed_reached"] is False
    # INTEGRITY: the honest current can never exceed what was actually measured on any single track
    assert board["current_avg"] <= board["measured_ceiling"] + 1e-9
    assert board["current_avg"] <= max(b["resolved_pct"] for b in board["per_benchmark"].values()) + 1e-9
    assert board["current_avg"] < 1.0                    # ~0, honestly
    assert board["gap_to_target"] > 80.0                 # a FAR north star
    assert board["reachable_subset_resolved"] >= 0
    assert len(board["next_two_levers"]) == 2


def test_scoreboard_persists_and_matches_on_disk(tmp_path):
    p = E.write_scoreboard(path=tmp_path / "goal_scoreboard.json")
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert on_disk["target"] == 90.0
    assert on_disk["current_avg"] <= on_disk["measured_ceiling"] + 1e-9
    # the four honest component statuses travel with the file
    statuses = {k: v["status"] for k, v in on_disk["per_benchmark"].items()}
    assert statuses == {"verified": "measurable-but-low", "pro": "loads-not-run",
                        "multilingual": "out-of-scope-java", "multimodal": "out-of-scope-vision"}


# ── self_evolution surfaces the loop as invokable (verifier-backed) + a huge-gap high-impact domain ─
def test_self_evolution_shows_swe_invokable_and_high_priority():
    from packages.self_evolution import plan_next_evolution
    plan = plan_next_evolution(write=False)
    by = {e["domain"]: e for e in plan["plan"]}
    swe = by["swe_engineering"]
    assert swe["kind"] == "invocation"
    assert swe["verifier_exists"] is True and swe["autonomous_safe"] is True
    inv = swe["invocation"]
    assert inv["module"] == "packages.swe_eval.evolve"
    assert inv["north_star"]["target"] == 90.0
    assert inv["north_star"]["claimed_reached"] is False
    # deficiency_sensus surfaces it as a HUGE gap (score ~0 -> headroom ~1.0) at high impact
    assert swe["score"] is not None and swe["score"] < 0.01
    assert swe["headroom"] > 0.98 and swe["base_impact"] >= 0.9
    # so the orchestrator keeps prioritizing it — top-3 overall, and a top autonomous target
    assert "swe_engineering" in plan["top_overall"][:3]
    assert "swe_engineering" in plan["top_autonomous"][:3]


def test_repo_engineering_and_swe_engineering_are_distinct_honest_rows():
    """The two-row pattern (like fluency / fluency_naturalness): repo_engineering reads the reachable
    Docker pipeline; swe_engineering reads the north-star scoreboard (~0). They must not be conflated."""
    from packages.self_evolution import build_weakness_map
    wm = {w.domain: w for w in build_weakness_map()}
    assert "repo_engineering" in wm and "swe_engineering" in wm
    # swe_engineering is the huge-gap north-star row; it is NOT the 'solved' reachable pipeline
    assert wm["swe_engineering"].score < 0.01
    assert wm["swe_engineering"].evidence["north_star_target"] == 90.0


# ── neuro budget: the loop is a 0-param control organ ─────────────────────────────────────────────
def test_loop_holds_zero_learned_params_and_is_not_a_fact_source():
    chk = E.budget_check()
    assert chk["params"] == 0 and chk["fact_source"] is False and chk["ok"] is True


def test_neuro_ledger_organ_is_measured_at_zero_params():
    from packages.neuro_ledger.ledger import measure_params
    o = E.neuro_ledger_organ()
    assert o.fact_source is False
    assert measure_params(o)["params"] == 0
