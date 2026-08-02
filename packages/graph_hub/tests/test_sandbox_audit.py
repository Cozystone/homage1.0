from packages.graph_hub.audit import append_graph_hub_audit_event, list_graph_hub_audit_events
from packages.graph_hub.entitlement import grant_free_entitlement
from packages.graph_hub.sandbox import sandbox_preview


def test_sandbox_preview_and_audit():
    grant_free_entitlement("software_architect_demo")
    preview = sandbox_preview("software_architect_demo")
    assert preview["permissions"]["write_local_brain"] is False
    assert preview["estimated_nodes"] >= 1
    append_graph_hub_audit_event("sandbox_warning", "software_architect_demo", {"test": True})
    assert any(row["event_type"] == "sandbox_warning" for row in list_graph_hub_audit_events(20))
