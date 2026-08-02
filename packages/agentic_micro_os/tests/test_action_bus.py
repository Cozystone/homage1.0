from packages.agentic_micro_os.action_bus import DashboardActionBus
from packages.agentic_micro_os.capabilities import CapabilityKernel


def test_dashboard_safe_action_and_arbitrary_js():
    kernel = CapabilityKernel()
    token = kernel.issue("dashboard_action")
    bus = DashboardActionBus(kernel)
    assert bus.validate("set_orb_state", {"state": "thinking"}, token)["allowed"] is True
    assert bus.validate("arbitrary_js_eval", {"code": "x"}, token)["allowed"] is False
