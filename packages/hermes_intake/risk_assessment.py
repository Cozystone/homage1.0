from __future__ import annotations

from .models import HermesIntakeReport


def assess_risk(report: HermesIntakeReport) -> dict[str, object]:
    risks = {
        "external_llm_provider_risk": bool(report.external_provider_dependencies),
        "unrestricted_shell_risk": bool(report.shell_execution_patterns),
        "persistent_memory_risk": bool(report.user_memory_patterns),
        "browser_side_effect_risk": bool(report.browser_automation_patterns),
        "license_ok": report.mit_compatible,
        "hermes_runtime_executed": report.hermes_code_executed_before_review,
    }
    risks["overall"] = "high_risk_adapt_rewrite" if any(v for k, v in risks.items() if k.endswith("_risk")) else "low"
    return risks
