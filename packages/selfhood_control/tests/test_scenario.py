from __future__ import annotations

from packages.selfhood_control.scenario import all_scenarios, base_context


def test_all_scenarios_are_named_and_bounded() -> None:
    scenarios = all_scenarios()
    assert len(scenarios) == 7
    names = {name for name, _, _ in scenarios}
    assert "voice_status" in names
    assert "generated_code_blocked" in names


def test_base_context_has_no_store_mutation_flags() -> None:
    context = base_context()
    assert context.resource_state["disk_free_gib"] >= 0
    assert context.privacy_policy["raw_private_export_allowed"] is False
