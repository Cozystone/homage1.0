from __future__ import annotations

from .capabilities import CapabilityKernel
from .models import CapabilityDecision, CapabilityToken


ALLOWED_DASHBOARD_ACTIONS = {
    "set_orb_state",
    "set_orb_emotion",
    "set_orb_lod",
    "set_splatra_scene_mode",
    "set_splatra_scene_command",
    "set_splatra_scene_choreography",
    "set_particle_budget",
    "show_render_preview",
    "show_proposal_card",
    "show_approval_request",
    "pin_status_card",
    "open_agora",
    "open_voice_status",
    "open_splatra_cell_status",
}

REJECTED_DASHBOARD_ACTIONS = {
    "arbitrary_js_eval",
    "direct_dom_mutation",
    "unsafe_inner_html",
    "file_write",
    "shell_command",
    "brain_write",
    "auto_commit",
    "auto_push",
}


class DashboardActionBus:
    def __init__(self, kernel: CapabilityKernel | None = None) -> None:
        self.kernel = kernel or CapabilityKernel()

    def validate(self, action_type: str, payload: dict[str, object], token: CapabilityToken | None) -> dict[str, object]:
        if action_type in REJECTED_DASHBOARD_ACTIONS:
            return {"allowed": False, "reason": f"rejected dashboard action: {action_type}"}
        if action_type not in ALLOWED_DASHBOARD_ACTIONS:
            return {"allowed": False, "reason": f"unknown dashboard action: {action_type}"}
        decision: CapabilityDecision = self.kernel.decide("dashboard_action", token)
        if not decision.allowed:
            return {"allowed": False, "reason": decision.reason}
        return {"allowed": True, "ui_command": {"type": action_type, "payload": payload, "execute_js": False}}
