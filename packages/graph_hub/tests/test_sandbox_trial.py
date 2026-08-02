from __future__ import annotations

from packages.graph_hub.entitlement import grant_free_entitlement
from packages.graph_hub.installer import install_cartridge
from packages.graph_hub.local_fingerprint import local_seed_fingerprint
from packages.graph_hub.sandbox_trial import get_sandbox_trial, run_sandbox_trial_query, start_sandbox_trial


def test_sandbox_trial_decrements_and_auto_detaches_without_local_write() -> None:
    grant_free_entitlement("software_architect_demo")
    install_cartridge("software_architect_demo")
    before = local_seed_fingerprint()["fingerprint_hash"]

    started = start_sandbox_trial("software_architect_demo", intent="testing deployment")
    assert started["state"] == "active"
    assert started["remaining_queries"] == 5
    assert started["local_write"] is False
    assert started["cloud_merge"] is False
    assert started["pair_edges_sent"] == 0

    session_id = started["session_id"]
    states = []
    for index in range(5):
        result = run_sandbox_trial_query(session_id, f"trial query {index}")
        states.append(result["state"])
        assert result["local_write"] is False
        assert result["cloud_merge"] is False
        assert result["pair_edges_sent"] == 0
        assert result["answer_mode"] == "bounded_graph_extract"

    assert states[-1] == "detached"
    final = get_sandbox_trial(session_id)
    assert final["state"] == "detached"
    assert final["remaining_queries"] == 0
    assert final["cleanup_status"] == "working_memory_overlay_purged"
    assert final["local_fingerprint_unchanged"] is True
    assert local_seed_fingerprint()["fingerprint_hash"] == before
