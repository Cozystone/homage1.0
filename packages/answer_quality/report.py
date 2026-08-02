from __future__ import annotations

from pathlib import Path
from typing import Any

from .storage import REPORT_ROOT, ensure_dirs


def write_markdown_report(run: dict[str, Any], scored_candidates: list[dict[str, Any]]) -> Path:
    ensure_dirs()
    path = REPORT_ROOT / f"{run['run_id']}.md"
    avg = run.get("average_scores", {})
    lines = [
        f"# ATANOR Answer Quality Report {run['run_id']}",
        "",
        f"- Benchmark: {run['benchmark_set']}",
        f"- Prompts: {run['total_prompts']}",
        f"- Overall: {avg.get('overall', 0.0)}",
        f"- Naturalness: {avg.get('naturalness', 0.0)}",
        f"- Trace hygiene: {avg.get('trace_hygiene', 0.0)}",
        f"- Template smell: {avg.get('template_smell', 0.0)}",
        f"- Grounding: {avg.get('grounding', 0.0)}",
        "",
        "## Worst Cases",
    ]
    for case in run.get("worst_cases", []):
        lines.append(f"- {case['overall']} / {case['generator']} / {case['query']} / flags={case.get('flags', [])}")
    lines.extend(["", "## Feedback"])
    for feedback in run.get("surface_feedback", [])[:20]:
        lines.append(f"- {feedback['type']}: {feedback['suggestion']} (auto_promoted={feedback['auto_promoted']})")
    lines.extend(
        [
            "",
            "## Honesty",
            "- No external LLM judge was used.",
            "- Scores are deterministic local heuristics, not human-level linguistic judgment.",
            "- Feedback is reviewable and is not auto-promoted into production Surface Brain weights.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
