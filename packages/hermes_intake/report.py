from __future__ import annotations

from pathlib import Path

from .architecture_extract import extract_architecture_summary
from .code_reuse_plan import build_code_reuse_plan
from .models import HermesIntakeReport
from .risk_assessment import assess_risk


def write_markdown_report(report: HermesIntakeReport, path: Path) -> Path:
    architecture = extract_architecture_summary(report)
    risk = assess_risk(report)
    reuse = build_code_reuse_plan(report.source_commit, report.license_detected)
    lines = [
        "# ATANOR Hermes Agent Intake Report",
        "",
        f"- Repo: `{report.repo_url}`",
        f"- Commit: `{report.source_commit}`",
        f"- License: `{report.license_detected}`",
        f"- MIT compatible: `{report.mit_compatible}`",
        f"- Hermes code executed: `{report.hermes_code_executed_before_review}`",
        f"- Recommendation: `{report.integration_recommendation}`",
        "",
        "## Reusable Patterns",
    ]
    lines.extend(f"- {item}" for item in report.reusable_architecture_patterns)
    lines.extend(["", "## High Risk / Rejected"])
    lines.extend(f"- {item}" for item in report.forbidden_or_high_risk_components)
    lines.extend(["", "## Architecture Summary", "```json", str(architecture), "```"])
    lines.extend(["", "## Risk", "```json", str(risk), "```"])
    lines.extend(["", "## Code Reuse Plan", "```json", str(reuse), "```"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
