from pathlib import Path

from packages.hermes_intake.scanner import scan_repo


def make_repo(tmp_path: Path) -> Path:
    (tmp_path / "LICENSE").write_text("MIT License\nPermission is hereby granted, free of charge.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("tools MCP browser cron skills memory gateway provider\n", encoding="utf-8")
    (tmp_path / "providers").mkdir()
    (tmp_path / "providers" / "openai.py").write_text("provider='openai'\n", encoding="utf-8")
    return tmp_path


def test_scan_repo_detects_patterns_without_execution(tmp_path):
    report = scan_repo(make_repo(tmp_path))
    assert report.mit_compatible is True
    assert report.hermes_code_executed_before_review is False
    assert report.model_provider_abstraction_detected is True
    assert report.mcp_patterns
    assert report.integration_recommendation.startswith("clone_architecture_only")
