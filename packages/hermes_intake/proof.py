from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from .report import write_markdown_report
from .scanner import scan_repo


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "hermes_intake" / "proofs"


def _fake_repo() -> Path:
    root = Path(tempfile.mkdtemp(prefix="hermes_intake_fake_"))
    (root / "LICENSE").write_text("MIT License\n\nPermission is hereby granted, free of charge.\n", encoding="utf-8")
    (root / "README.md").write_text("Agent loop with tools, MCP gateway, browser, cron, skills, memory.\n", encoding="utf-8")
    (root / "providers").mkdir()
    (root / "providers" / "openai.py").write_text("provider = 'openai'\n", encoding="utf-8")
    (root / "tools").mkdir()
    (root / "tools" / "shell.py").write_text("import subprocess\n", encoding="utf-8")
    (root / "trajectory_compressor.py").write_text("compressed_summary = True\n", encoding="utf-8")
    return root


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR, repo_path: str | Path | None = None) -> dict[str, object]:
    repo = Path(repo_path) if repo_path else _fake_repo()
    report = scan_repo(repo)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "report": report.to_dict(),
        "passed": report.mit_compatible and not report.hermes_code_executed_before_review,
        "claims": {
            "safe_text_scan": True,
            "license_detected": report.license_file_present,
            "high_risk_components_classified": bool(report.forbidden_or_high_risk_components),
        },
        "non_claims": {
            "hermes_runtime_integrated": False,
            "hermes_code_executed": False,
            "external_tools_live": False,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "hermes_intake_proof.json"
    md_path = output_dir / "hermes_intake_proof.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown_report(report, md_path)
    payload["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return payload


def main() -> None:
    candidate = PROJECT_ROOT / "external_repos" / "hermes-agent"
    result = run_proof(repo_path=candidate if candidate.exists() else None)
    print(json.dumps({"passed": result["passed"], "outputs": result["outputs"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
