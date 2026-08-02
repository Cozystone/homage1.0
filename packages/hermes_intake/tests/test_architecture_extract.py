from packages.hermes_intake.architecture_extract import extract_architecture_summary
from packages.hermes_intake.models import HermesIntakeReport


def test_architecture_extract_summary():
    report = HermesIntakeReport("repo", "path", "commit", "MIT", True, True, True, tool_gateway_patterns=["tools.py"])
    summary = extract_architecture_summary(report)
    assert summary["agent_loop"] is True
    assert summary["tools"] == ["tools.py"]
