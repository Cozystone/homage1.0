from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.agentic_micro_os import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_status_is_proof_only_and_external_models_disabled() -> None:
    payload = _client().get("/api/agentic-os/status").json()

    assert payload["proof_only"] is True
    assert payload["external_llm"] is False
    assert payload["external_sllm"] is False
    assert payload["hermes_runtime_executed"] is False
    assert payload["hermes_code_copied"] is False
    assert payload["modules"]["splatra_cosmos_cell"] == "available"
    assert payload["modules"]["browser_read"] == "proof_only"
    assert payload["modules"]["mcp_allowlist_gateway"] == "proof_only"
    assert payload["modules"]["splatra_evaluator"] == "proof_only"
    assert payload["modules"]["web_explorer_loop"] == "proof_only"
    assert payload["tool_gateway_phase1"]["browser_read"]["browser_automation"] is False
    assert payload["tool_gateway_phase1"]["web_explorer_loop"]["aggressive_crawling"] is False


def test_action_validation_accepts_safe_dashboard_action() -> None:
    response = _client().post(
        "/api/agentic-os/action/validate",
        json={"action_type": "set_orb_state", "payload": {"state": "thinking"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["allowed"] is True
    assert payload["ui_command"]["execute_js"] is False


def test_action_validation_rejects_arbitrary_js_eval() -> None:
    payload = _client().post(
        "/api/agentic-os/action/validate",
        json={"action_type": "arbitrary_js_eval", "payload": {"code": "alert(1)"}},
    ).json()

    assert payload["allowed"] is False
    assert payload["arbitrary_js_eval"] is False


def test_brain_access_blocks_direct_local_write() -> None:
    payload = _client().post(
        "/api/agentic-os/brain-access/request",
        json={
            "target": "local_brain",
            "operation": "local_brain_direct_write",
            "query": "write memory",
        },
    ).json()

    assert payload["response"]["allowed"] is False
    assert payload["response"]["mutation_performed"] is False
    assert payload["local_brain_direct_write"] is False


def test_brain_access_candidate_draft_requires_approval() -> None:
    payload = _client().post(
        "/api/agentic-os/brain-access/request",
        json={
            "target": "local_brain",
            "operation": "local_brain_memory_candidate_draft",
            "query": "draft memory only",
        },
    ).json()

    assert payload["response"]["allowed"] is True
    assert payload["response"]["approval_required"] is True
    assert payload["response"]["mutation_performed"] is False


def test_loop_propose_returns_approval_required_patch_without_git() -> None:
    payload = _client().post("/api/agentic-os/loop/propose", json={"goal": "proof", "max_cycles": 1}).json()

    assert payload["approval_required"] is True
    assert payload["patch_proposals"]
    assert payload["auto_commit"] is False
    assert payload["auto_push"] is False


def test_hermes_intake_status_never_executes_runtime() -> None:
    payload = _client().get("/api/agentic-os/hermes-intake/status").json()

    assert payload["hermes_runtime_executed"] is False
    assert payload["hermes_code_copied"] is False


def test_browser_read_api_reads_public_snapshot_only() -> None:
    payload = _client().post(
        "/api/agentic-os/browser-read",
        json={
            "url": "http://127.0.0.1:3041/?section=agent-os",
            "visible_text": "Agentic Micro-OS proof-only status",
        },
    ).json()

    assert payload["allowed"] is True
    assert payload["browser_automation"] is False
    assert payload["arbitrary_js_eval"] is False
    assert payload["observation"]["metadata"]["fetched"] is False


def test_browser_read_api_rejects_private_payload() -> None:
    payload = _client().post(
        "/api/agentic-os/browser-read",
        json={
            "url": "http://127.0.0.1:3041",
            "visible_text": "raw_private_memory should be blocked",
        },
    ).json()

    assert payload["allowed"] is False
    assert "private" in payload["denied_reason"]
    assert payload["external_llm"] is False


def test_mcp_allowlist_api_validates_without_real_mcp_call() -> None:
    payload = _client().post("/api/agentic-os/mcp/validate", json={}).json()

    assert payload["allowed"] is True
    assert payload["real_mcp_called"] is False
    assert payload["production_store_mutated"] is False
    assert payload["candidate_promotion"] is False


def test_mcp_allowlist_api_rejects_mutation() -> None:
    payload = _client().post(
        "/api/agentic-os/mcp/validate",
        json={"descriptor": "render_preview", "method": "delete", "payload": {"scene": "orb"}},
    ).json()

    assert payload["allowed"] is False
    assert "method" in payload["reason"]


def test_splatra_evaluator_api_is_proposal_only() -> None:
    payload = _client().post(
        "/api/agentic-os/splatra/evaluate",
        json={"candidate_id": "orb_candidate", "particle_budget": 50000, "target_fps": 60},
    ).json()

    assert payload["allowed"] is True
    assert payload["patch_applied"] is False
    assert payload["generated_code_executed"] is False
    assert payload["local_brain_write"] is False
    assert payload["production_store_mutated"] is False
    assert payload["metrics"]["particle_budget_ok"] is True


def test_web_explorer_status_is_proof_only() -> None:
    payload = _client().get("/api/agentic-os/web-explorer/status").json()

    assert payload["available"] is True
    assert payload["proof_only"] is True
    assert payload["external_llm"] is False
    assert payload["default_limits"]["max_runtime_sec"] == 21600


def test_open_web_explorer_status_is_proof_only_and_budgeted() -> None:
    payload = _client().get("/api/agentic-os/web-explorer/open/status").json()

    assert payload["available"] is True
    assert payload["proof_only"] is True
    assert payload["fixed_allowlist_required"] is False
    assert payload["live_web_default"] is False
    assert payload["default_limits"]["max_pages"] == 300
    assert payload["default_limits"]["max_depth"] == 3
    assert payload["external_llm"] is False


def test_web_explorer_run_once_creates_drafts_without_mutation() -> None:
    client = _client()
    payload = client.post(
        "/api/agentic-os/web-explorer/run-once",
        json={
            "goal": "research local TTS alternatives",
            "allowed_domains": ["docs.local"],
            "pages": [
                {"url": "http://docs.local/fish", "title": "Fish", "visible_text": "Fish public runtime notes"},
                {"url": "https://blocked.example/fish", "title": "Blocked", "visible_text": "blocked"},
                {"url": "http://docs.local/private", "title": "Private", "visible_text": "raw_private_memory should fail"},
            ],
            "max_pages": 30,
        },
    ).json()

    assert payload["pages_read"] == 1
    assert payload["pages_rejected"] == 2
    assert payload["candidate_drafts_count"] == 1
    assert payload["skill_drafts_count"] == 1
    assert payload["skill_drafts"][0]["promotion_required"] is True
    assert payload["production_store_mutated"] is False
    assert payload["local_brain_write"] is False
    assert payload["candidate_promotion"] is False
    assert "production write blocked" in payload["safety_blocks"]

    run_id = payload["run_id"]
    run_payload = client.get(f"/api/agentic-os/web-explorer/runs/{run_id}").json()
    drafts_payload = client.get("/api/agentic-os/skills/drafts").json()
    assert run_payload["run"]["run_id"] == run_id
    assert drafts_payload["skill_drafts"]


def test_open_web_explorer_run_uses_fixture_and_keeps_safety() -> None:
    client = _client()
    payload = client.post(
        "/api/agentic-os/web-explorer/open/run",
        json={
            "goal": "open web research for ATANOR",
            "seed_urls": ["https://example.com/fish"],
            "max_pages": 6,
            "max_depth": 2,
            "per_domain_delay_sec": 0,
            "fixtures": [
                {
                    "url": "https://example.com/fish",
                    "html": "<html><title>Fish</title><body>Fish Speech local runtime notes. <a href='https://example.com/splatra'>SPLATRA</a><a href='https://example.com/login'>login</a></body></html>",
                },
                {
                    "url": "https://example.com/splatra",
                    "html": "<html><title>SPLATRA</title><body>SPLATRA WebGPU particle compression notes.</body></html>",
                },
            ],
        },
    ).json()

    assert payload["pages_read"] == 2
    assert payload["pages_rejected"] == 1
    assert payload["candidate_drafts_count"] == 2
    assert payload["skill_drafts_count"] == 1
    assert payload["production_store_mutated"] is False
    assert payload["candidate_promotion"] is False
    assert payload["skill_drafts"][0]["status"] == "draft"
    assert any("login" in block or "credentialed" in block for block in payload["safety_blocks"])

    run_payload = client.get(f"/api/agentic-os/web-explorer/open/runs/{payload['run_id']}").json()
    assert run_payload["run"]["run_id"] == payload["run_id"]
