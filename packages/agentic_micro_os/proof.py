from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from .action_bus import DashboardActionBus
from .brain_access import BrainAccessRequest, BrainAccessRoad
from .browser_gateway import BrowserGateway
from .capabilities import CapabilityKernel
from .cloud_gateway import CloudGateway
from .loop import BoundedAgentLoop
from .mcp_gateway import MCPGateway


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "agentic_micro_os" / "proofs"


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, object]:
    kernel = CapabilityKernel()
    dashboard_token = kernel.issue("dashboard_action")
    browser_token = kernel.issue("browser_read_mock")
    mcp_token = kernel.issue("mcp_call_mock")
    bus = DashboardActionBus(kernel)
    road = BrainAccessRoad()
    cloud = CloudGateway(road)

    safe_action = bus.validate("set_orb_state", {"state": "thinking"}, dashboard_token)
    arbitrary_js = bus.validate("arbitrary_js_eval", {"code": "alert(1)"}, dashboard_token)
    local_direct = road.request(BrainAccessRequest("local_brain", "local_brain_direct_write", "x", "raw", "raw", "proof", "loop"))
    local_draft = road.request(BrainAccessRequest("local_brain", "local_brain_memory_candidate_draft", "x", "candidate", "redacted", "proof", "loop"))
    cloud_read = cloud.verified_read_summary("verified context")
    cloud_prod = cloud.production_write("mutate")
    mcp_unknown = None
    try:
        MCPGateway(kernel=kernel).call_mock("unknown", {}, mcp_token)
    except PermissionError as exc:
        mcp_unknown = str(exc)
    browser_ok = BrowserGateway(kernel=kernel).read_mock("http://127.0.0.1:3041", browser_token)
    loop_state = BoundedAgentLoop("Improve SPLATRA orb safely", max_cycles=3).run()
    git_commit = kernel.decide("git_commit", None)
    git_push = kernel.decide("git_push", None)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "safe_dashboard_action": safe_action,
        "arbitrary_js_rejected": arbitrary_js["allowed"] is False,
        "local_brain_write_blocked": local_direct.allowed is False,
        "local_brain_candidate_draft": local_draft.allowed and local_draft.approval_required,
        "cloud_verified_read": cloud_read.allowed,
        "cloud_production_write_blocked": cloud_prod.allowed is False,
        "mcp_unknown_rejected": mcp_unknown == "unknown MCP descriptor",
        "browser_allowlist": browser_ok.source == "browser",
        "loop_budget_stop": loop_state.stopped_reason == "max_cycles",
        "auto_commit_blocked": git_commit.allowed is False,
        "auto_push_blocked": git_push.allowed is False,
        "patch_requires_approval": loop_state.patch_proposals[0].requires_human_approval,
        "invariants": {
            "external_llm": False,
            "external_sllm": False,
            "atanor_model_slot_only": True,
            "local_brain_direct_write": False,
            "production_store_direct_write": False,
            "candidate_promotion": False,
            "unrestricted_shell": False,
            "arbitrary_js_eval": False,
            "auto_commit": False,
            "auto_push": False,
            "human_approval_required": True,
            "proof_only": True,
        },
    }
    payload["passed"] = all(
        bool(payload[key])
        for key in [
            "safe_dashboard_action",
            "arbitrary_js_rejected",
            "local_brain_write_blocked",
            "local_brain_candidate_draft",
            "cloud_verified_read",
            "cloud_production_write_blocked",
            "mcp_unknown_rejected",
            "browser_allowlist",
            "loop_budget_stop",
            "auto_commit_blocked",
            "auto_push_blocked",
            "patch_requires_approval",
        ]
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "agentic_micro_os_proof.json"
    md_path = output_dir / "agentic_micro_os_proof.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return payload


def _markdown(payload: dict[str, object]) -> str:
    lines = ["# Agentic Micro-OS Proof", "", f"- Passed: `{payload['passed']}`"]
    for key, value in payload.items():
        if key not in {"outputs", "invariants"}:
            lines.append(f"- {key}: `{value}`")
    lines.append("\nThis proof does not execute Hermes runtime, real browser automation, real MCP servers, or production mutations.\n")
    return "\n".join(lines)


def main() -> None:
    result = run_proof()
    print(json.dumps({"passed": result["passed"], "outputs": result["outputs"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
