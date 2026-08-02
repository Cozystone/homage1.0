from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class HermesIntakeReport:
    repo_url: str
    repo_path: str
    source_commit: str
    license_detected: str
    license_file_present: bool
    mit_compatible: bool
    model_provider_abstraction_detected: bool
    external_provider_dependencies: list[str] = field(default_factory=list)
    tool_gateway_patterns: list[str] = field(default_factory=list)
    mcp_patterns: list[str] = field(default_factory=list)
    browser_automation_patterns: list[str] = field(default_factory=list)
    terminal_backend_patterns: list[str] = field(default_factory=list)
    cron_patterns: list[str] = field(default_factory=list)
    gateway_patterns: list[str] = field(default_factory=list)
    skills_memory_patterns: list[str] = field(default_factory=list)
    trajectory_compression_patterns: list[str] = field(default_factory=list)
    subagent_patterns: list[str] = field(default_factory=list)
    shell_execution_patterns: list[str] = field(default_factory=list)
    sandbox_patterns: list[str] = field(default_factory=list)
    cloud_backend_patterns: list[str] = field(default_factory=list)
    self_improvement_patterns: list[str] = field(default_factory=list)
    user_memory_patterns: list[str] = field(default_factory=list)
    reusable_architecture_patterns: list[str] = field(default_factory=list)
    code_reuse_candidates: list[str] = field(default_factory=list)
    code_rewrite_candidates: list[str] = field(default_factory=list)
    forbidden_or_high_risk_components: list[str] = field(default_factory=list)
    integration_recommendation: str = "clone_architecture_only"
    notes: list[str] = field(default_factory=list)
    hermes_code_executed_before_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
