from __future__ import annotations

import subprocess
from pathlib import Path

from .license_check import detect_license
from .models import HermesIntakeReport
from .repo_fetch_plan import HERMES_REPO_URL


TEXT_EXTENSIONS = {".md", ".py", ".toml", ".json", ".yaml", ".yml", ".txt", ".ts", ".tsx", ".js"}

PATTERNS = {
    "external_provider_dependencies": ["openai", "anthropic", "openrouter", "ollama", "vllm", "litellm", "provider"],
    "tool_gateway_patterns": ["toolsets.py", "model_tools.py", "tools/registry", "register_tool", "tool_call"],
    "mcp_patterns": ["mcp_serve.py", "optional-mcps", "MCP", "mcp"],
    "browser_automation_patterns": ["browser", "playwright", "selenium"],
    "terminal_backend_patterns": ["terminal", "pty", "shell", "subprocess"],
    "cron_patterns": ["cron", "scheduler", "scheduled"],
    "gateway_patterns": ["gateway", "tui_gateway", "session.py"],
    "skills_memory_patterns": ["skills", "optional-skills", "memory", "MemoryProvider"],
    "trajectory_compression_patterns": ["trajectory_compressor", "compressed_summary", "trajectory"],
    "subagent_patterns": ["subagent", "delegate", "delegation"],
    "shell_execution_patterns": ["subprocess", "os.system", "shell=True", "terminal"],
    "sandbox_patterns": ["sandbox", "docker", "container"],
    "cloud_backend_patterns": ["cloud", "s3", "gcp", "azure", "aws"],
    "self_improvement_patterns": ["self-improving", "skill improvement", "curator", "learns across sessions"],
    "user_memory_patterns": ["memory provider", "persistent memory", "user memory", "memory_manager"],
}


def _commit(repo_path: Path) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(repo_path), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _iter_text_files(repo_path: Path) -> list[Path]:
    result: list[Path] = []
    for path in repo_path.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        if path.suffix.lower() in TEXT_EXTENSIONS or path.name in {"LICENSE", "AGENTS.md", "README.md"}:
            result.append(path)
    return result


def _collect(repo_path: Path, needles: list[str]) -> list[str]:
    hits: list[str] = []
    lower_needles = [needle.lower() for needle in needles]
    for path in _iter_text_files(repo_path):
        rel = path.relative_to(repo_path).as_posix()
        rel_lower = rel.lower()
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        if any(needle in rel_lower or needle in text for needle in lower_needles):
            hits.append(rel)
        if len(hits) >= 24:
            break
    return hits


def scan_repo(repo_path: str | Path, repo_url: str = HERMES_REPO_URL) -> HermesIntakeReport:
    root = Path(repo_path)
    license_info = detect_license(root)
    fields = {name: _collect(root, needles) for name, needles in PATTERNS.items()}
    provider_detected = bool(fields["external_provider_dependencies"])
    reusable = [
        "capability-footprint ladder",
        "tool registry and toolset distribution concepts",
        "MCP-as-edge-extension pattern",
        "gateway/TUI separation",
        "cron/scheduled automation concept",
        "trajectory compression concept",
        "skills as draftable procedures",
    ]
    high_risk = [
        "external model provider adapters",
        "terminal/shell execution",
        "persistent memory providers",
        "messaging gateway secrets",
        "real browser automation",
        "auto-install and setup commands",
    ]
    recommendation = "clone_architecture_only"
    if license_info["mit_compatible"]:
        recommendation = "clone_architecture_only; copy_safe_modules_with_notice only after per-file review"
    return HermesIntakeReport(
        repo_url=repo_url,
        repo_path=str(root),
        source_commit=_commit(root),
        license_detected=str(license_info["license_detected"]),
        license_file_present=bool(license_info["license_file_present"]),
        mit_compatible=bool(license_info["mit_compatible"]),
        model_provider_abstraction_detected=provider_detected,
        reusable_architecture_patterns=reusable,
        code_reuse_candidates=["interfaces and documentation patterns only in v0"],
        code_rewrite_candidates=["tool gateway", "MCP allowlist gateway", "bounded loop", "skill draft lifecycle"],
        forbidden_or_high_risk_components=high_risk,
        integration_recommendation=recommendation,
        notes=["Hermes code was scanned as text only; no Hermes module import or runtime execution."],
        **fields,
    )
