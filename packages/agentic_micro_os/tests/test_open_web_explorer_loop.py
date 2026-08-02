from packages.agentic_micro_os.web_explorer_loop import (
    FixtureOpenWebFetcher,
    OpenWebExplorerConfig,
    OpenWebExplorerLoop,
    OpenWebPolicy,
    run_open_web_proof,
)


def test_open_web_policy_accepts_public_url() -> None:
    decision = OpenWebPolicy().validate_url("https://example.com/public/fish-speech")

    assert decision.allowed is True


def test_open_web_policy_rejects_private_internal_and_sensitive_patterns() -> None:
    policy = OpenWebPolicy()
    urls = [
        "http://127.0.0.1:3041/",
        "http://10.0.0.1/page",
        "file:///tmp/private.txt",
        "chrome://settings",
        "https://example.com/login",
        "https://example.com/account/profile",
        "https://example.com/payment/checkout",
        "https://example.com/upload",
        "https://example.com/model.safetensors",
    ]

    decisions = [policy.validate_url(url) for url in urls]

    assert all(decision.allowed is False for decision in decisions)


def test_open_web_loop_dedupes_duplicate_content_and_creates_drafts() -> None:
    fixtures = {
        "https://example.com/a": "<html><title>A</title><body>Fish Speech public runtime notes.<a href='https://example.com/b'></a></body></html>",
        "https://example.com/b": "<html><title>B</title><body>Fish Speech public runtime notes.</body></html>",
    }
    config = OpenWebExplorerConfig(
        "open web fish research",
        seed_urls=["https://example.com/a"],
        max_pages=5,
        max_depth=2,
        per_domain_delay_sec=0,
    )

    result = OpenWebExplorerLoop(config, fetcher=FixtureOpenWebFetcher(fixtures)).run()

    assert result.pages_read == 1
    assert result.pages_rejected == 1
    assert result.candidate_drafts_count == 1
    assert result.skill_drafts_count == 1
    assert result.skill_drafts[0]["promotion_required"] is True
    assert "production write blocked" in result.safety_blocks
    assert any("duplicate content rejected" in block for block in result.safety_blocks)
    assert result.invariants["production_store_mutated"] is False
    assert result.invariants["candidate_promotion"] is False


def test_open_web_loop_enforces_per_domain_budget() -> None:
    fixtures = {
        "https://example.com/a": "<html><title>A</title><body>Fish public. <a href='https://example.com/b'>B</a></body></html>",
        "https://example.com/b": "<html><title>B</title><body>SPLATRA public.</body></html>",
    }
    config = OpenWebExplorerConfig(
        "domain budget",
        seed_urls=["https://example.com/a"],
        max_pages=5,
        max_depth=2,
        max_pages_per_domain=1,
        per_domain_delay_sec=0,
    )

    result = OpenWebExplorerLoop(config, fetcher=FixtureOpenWebFetcher(fixtures)).run()

    assert result.pages_read == 1
    assert result.pages_rejected == 1
    assert any("per-domain budget reached" in block for block in result.safety_blocks)


def test_open_web_loop_stops_by_max_pages_and_keeps_state_log() -> None:
    fixtures = {
        "https://example.com/a": "<html><title>A</title><body>Fish public. <a href='https://example.com/b'>B</a></body></html>",
        "https://example.com/b": "<html><title>B</title><body>SPLATRA public.</body></html>",
    }
    config = OpenWebExplorerConfig("page budget", ["https://example.com/a"], max_pages=1, max_depth=2, per_domain_delay_sec=0)

    result = OpenWebExplorerLoop(config, fetcher=FixtureOpenWebFetcher(fixtures)).run()

    assert result.pages_read == 1
    assert result.stopped_reason == "max_pages"
    assert result.state_log
    assert result.report_triggered is True
    assert result.report_reason == "loop budget stopped"


def test_open_web_report_not_mandatory_for_small_clean_run() -> None:
    fixtures = {
        "https://example.com/a": "<html><title>A</title><body>Small public note.</body></html>",
    }
    config = OpenWebExplorerConfig("small run", ["https://example.com/a"], max_pages=5, max_depth=1, per_domain_delay_sec=0)

    result = OpenWebExplorerLoop(config, fetcher=FixtureOpenWebFetcher(fixtures)).run()

    assert result.pages_read == 1
    assert result.report_triggered is False
    assert result.report_reason == "compact state log only"
    assert result.state_log


def test_open_web_proof_uses_fixture_fetcher_and_no_external_models() -> None:
    payload = run_open_web_proof("open web research for ATANOR", max_runtime_sec=30, max_pages=6, max_depth=2)

    assert payload["pages_read"] == 2
    assert payload["candidate_drafts_count"] == 2
    assert payload["skill_drafts_count"] == 1
    assert payload["invariants"]["external_llm"] is False
    assert payload["invariants"]["auto_push"] is False
