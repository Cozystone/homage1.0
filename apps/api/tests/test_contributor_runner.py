from __future__ import annotations

from apps.api.app.workers.contributor_node import SAFE_SEED_TASK, run_dry_run


def test_contributor_runner_dry_run_reports_safe_seed(monkeypatch) -> None:
    monkeypatch.setenv("ATANOR_CLOUD_MODE", "remote")
    monkeypatch.setenv("ATANOR_CLOUD_ENDPOINT", "https://example.com")

    payload = run_dry_run()

    assert payload["state"] == "dry_run_ok"
    assert payload["remote_enabled"] is True
    assert SAFE_SEED_TASK["privacy_classification"] == "public_only"
    assert SAFE_SEED_TASK["payload"]["source_url"].startswith("https://")
