from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "guard"))

from guard.release_mock_audit import audit_mock_risks, write_mock_risk_report  # noqa: E402


SCAN_ROOTS = [
    ROOT / "apps" / "api" / "app",
    ROOT / "apps" / "web" / "app",
    ROOT / "packages",
    ROOT / "scripts",
    ROOT / "README.md",
    ROOT / "docs",
]


def main() -> int:
    report = audit_mock_risks(SCAN_ROOTS, repo_root=ROOT)
    write_mock_risk_report(
        report,
        ROOT / "reports" / "release" / "no_mock_gate.json",
        ROOT / "reports" / "release" / "no_mock_gate.md",
    )
    print(f"BLOCKER={report['counts'].get('BLOCKER', 0)} REVIEW={report['counts'].get('REVIEW', 0)} INFO={report['counts'].get('INFO', 0)}")
    return 1 if report["counts"].get("BLOCKER", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
