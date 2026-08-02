from packages.agentic_micro_os.web_explorer_loop import (
    INVARIANTS,
    HermesWebExplorerLoop,
    WebExplorerConfig,
    WebPageInput,
    run_proof,
)


def test_web_explorer_proof_scenarios_and_invariants() -> None:
    pages = [
        WebPageInput("http://docs.local/fish", "Fish", "Fish runtime public notes"),
        WebPageInput("https://blocked.example/fish", "Blocked", "public notes"),
        WebPageInput("http://docs.local/private", "Private", "raw_private_memory should not pass"),
    ]
    config = WebExplorerConfig(
        goal="research local TTS alternatives",
        allowed_domains=["docs.local"],
        pages=pages,
    )

    result = HermesWebExplorerLoop(config).run_once()

    assert result.pages_read == 1
    assert result.pages_rejected == 2
    assert result.candidate_drafts_count == 1
    assert result.skill_drafts_count == 1
    assert result.skill_drafts[0]["status"] == "draft"
    assert result.skill_drafts[0]["promotion_required"] is True
    assert "production write blocked" in result.safety_blocks
    assert result.invariants == INVARIANTS
    assert result.invariants["local_brain_write"] is False
    assert result.invariants["auto_commit"] is False
    assert result.invariants["auto_push"] is False


def test_web_explorer_stops_by_page_budget() -> None:
    pages = [
        WebPageInput("http://docs.local/one", "One", "one"),
        WebPageInput("http://docs.local/two", "Two", "two"),
    ]
    config = WebExplorerConfig("budget test", ["docs.local"], pages, max_pages=1)

    result = HermesWebExplorerLoop(config).run_once()

    assert result.pages_read == 1
    assert result.stopped_reason == "max_pages"


def test_web_explorer_cli_proof_payload_is_safe() -> None:
    payload = run_proof("research local TTS alternatives and SPLATRA particle rendering", max_runtime_sec=10)

    assert payload["pages_read"] >= 1
    assert payload["candidate_drafts_count"] >= 1
    assert payload["skill_drafts_count"] == 1
    assert payload["invariants"]["external_llm"] is False
    assert payload["invariants"]["production_store_mutated"] is False
