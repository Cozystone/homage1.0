from packages.hermes_intake.models import HermesIntakeReport
from packages.hermes_intake.risk_assessment import assess_risk


def test_risk_assessment_flags_external_providers():
    report = HermesIntakeReport("repo", "path", "commit", "MIT", True, True, True, external_provider_dependencies=["providers/openai.py"])
    risk = assess_risk(report)
    assert risk["external_llm_provider_risk"] is True
    assert risk["overall"] == "high_risk_adapt_rewrite"
