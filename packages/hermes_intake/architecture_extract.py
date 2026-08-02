from __future__ import annotations

from .models import HermesIntakeReport


def extract_architecture_summary(report: HermesIntakeReport) -> dict[str, object]:
    return {
        "agent_loop": bool(report.tool_gateway_patterns or report.trajectory_compression_patterns),
        "tools": report.tool_gateway_patterns[:8],
        "mcp": report.mcp_patterns[:8],
        "gateway": report.gateway_patterns[:8],
        "cron": report.cron_patterns[:8],
        "skills_memory": report.skills_memory_patterns[:8],
        "trajectory_compression": report.trajectory_compression_patterns[:8],
        "recommendation": report.integration_recommendation,
    }
