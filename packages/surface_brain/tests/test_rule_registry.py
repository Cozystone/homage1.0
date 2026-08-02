from __future__ import annotations

from packages.surface_brain.monitor import repair_answer_for_mode
from packages.surface_brain.repair_rules import RepairRule
from packages.surface_brain.review_queue import approve_repair_candidate, enqueue_repair_candidates
from packages.surface_brain.rule_registry import disable_rule, get_enabled_repair_rules, load_production_rules, rollback_rule


def test_enabled_production_rule_is_loaded_by_monitor(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    rule = RepairRule(
        rule_id="production_custom_replace",
        name="production_custom_replace",
        description="Replace custom internal token.",
        trigger_terms=["CUSTOM_INTERNAL_TOKEN"],
        mode_scope="default_only",
        action="replace",
        replacement="근거",
        severity="high",
        source="proof",
    )
    candidate = enqueue_repair_candidates([rule], source_run_id="run-c")[0]
    approve_repair_candidate(candidate["candidate_id"], reviewer="tester")

    enabled = get_enabled_repair_rules()
    assert {row.rule_id for row in enabled} == {"production_custom_replace"}

    result = repair_answer_for_mode("CUSTOM_INTERNAL_TOKEN 기준입니다.", mode="default", trace={})
    assert "CUSTOM_INTERNAL_TOKEN" not in result["repaired_answer"]
    assert "production_custom_replace" in result["production_rules_used"]


def test_disabled_and_rolled_back_rules_are_not_used(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    rule = RepairRule(
        rule_id="production_disable_me",
        name="production_disable_me",
        description="Replace custom internal token.",
        trigger_terms=["DISABLE_ME_TOKEN"],
        mode_scope="default_only",
        action="replace",
        replacement="근거",
        severity="high",
        source="proof",
    )
    candidate = enqueue_repair_candidates([rule], source_run_id="run-d")[0]
    approve_repair_candidate(candidate["candidate_id"], reviewer="tester")
    disable_rule("production_disable_me", actor="tester")

    result = repair_answer_for_mode("DISABLE_ME_TOKEN 기준입니다.", mode="default", trace={})
    assert "DISABLE_ME_TOKEN" in result["repaired_answer"]
    assert "production_disable_me" not in result["production_rules_used"]

    rolled = rollback_rule("production_disable_me", actor="tester")
    assert rolled["enabled"] is False
    assert load_production_rules()[0]["enabled"] is False
