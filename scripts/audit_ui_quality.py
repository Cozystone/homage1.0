from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "ui-quality" / "latest.md"
EXTENSIONS = {".tsx", ".ts", ".css", ".py", ".md", ".json"}
SCAN_ROOTS = [
    ROOT / "apps" / "web" / "app",
    ROOT / "apps" / "api" / "app",
    ROOT / "docs",
    ROOT / "README.md",
    ROOT / "QUICKSTART.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
]
SKIP_PARTS = {".git", ".next", "node_modules", "dist", "dist-artifacts", "reports"}


@dataclass(frozen=True)
class Rule:
    name: str
    severity: str
    pattern: re.Pattern[str]
    recommendation: str
    auto_fix_safe: str = "no"


RULES = [
    Rule("replacement-character", "BLOCKER", re.compile("\ufffd"), "Fix file encoding or replace corrupted text."),
    Rule("common-mojibake", "HIGH", re.compile(r"[留筌援臾媛꾩쟾꾨땲]{2,}"), "Rewrite corrupted Korean as valid UTF-8 text."),
    Rule("local-windows-path", "HIGH", re.compile(r"\b[A-Z]:\\[^`\\s]+", re.IGNORECASE), "Remove local absolute paths from public docs/UI."),
    Rule("secret-marker", "BLOCKER", re.compile(r"(api[_-]?key|secret|token)\s*[:=]\s*['\"](?!<)[^'\"]{8,}", re.IGNORECASE), "Remove committed secrets."),
    Rule("overclaim-global-live", "HIGH", re.compile(r"Global Contributor Network Live|Worldwide Contributor Mesh Live|Infinite Compute", re.IGNORECASE), "Use preview or verified runtime wording."),
    Rule("dual-graph-term", "BLOCKER", re.compile(r"Dual Graph|dual graph|dualGraph|dual_graph|dual-graph|DualGraph|Dual Ontology Graph|graphMode\s*=\s*dual|graph_type\s*=\s*dual", re.IGNORECASE), "Use Unified Knowledge Graph / Unified Ontology Graph."),
    Rule("dual-brain-label", "HIGH", re.compile(r"Dual Brain|dual brain|dual-brain", re.IGNORECASE), "Use Unified Brain for source/reasoning mode labels."),
    Rule("user-facing-identifier", "MEDIUM", re.compile(r"\b(node_id|peer_id|device_name)\b"), "Avoid exposing identifiers in user-facing UI."),
    Rule("legacy-mock-label", "MEDIUM", re.compile(r"\b(mock|stub|placeholder)\b", re.IGNORECASE), "Ensure demo/scaffold states are labeled honestly."),
]


def iter_files() -> list[Path]:
    files: set[Path] = set()
    for root in SCAN_ROOTS:
        if root.is_file():
            if root.suffix in EXTENSIONS:
                files.add(root)
            continue
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in EXTENSIONS:
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            files.add(path)
    return sorted(files)


def line_at(text: str, offset: int) -> tuple[int, str]:
    line_no = text.count("\n", 0, offset) + 1
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    if end == -1:
        end = len(text)
    return line_no, text[start:end].strip()


def main() -> int:
    issues: list[dict[str, str]] = []
    for path in iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            issues.append(
                {
                    "severity": "BLOCKER",
                    "file": str(path.relative_to(ROOT)),
                    "line": "1",
                    "rule": "utf8-decode",
                    "evidence": "File is not valid UTF-8.",
                    "recommendation": "Resave the file as UTF-8 without BOM.",
                    "auto": "no",
                }
            )
            continue
        for rule in RULES:
            if path.name == "audit_ui_quality.py" and rule.name in {"dual-graph-term", "dual-brain-label"}:
                continue
            if path.name.startswith("test_") and rule.name == "dual-brain-label":
                continue
            for match in rule.pattern.finditer(text):
                line_no, evidence = line_at(text, match.start())
                if rule.name == "local-windows-path" and "C:\\fakepath" in evidence:
                    continue
                if rule.name in {"dual-graph-term", "dual-brain-label"} and re.search(
                    r"\b(no|not|deprecated|legacy|removed|do not|does not|must not)\b",
                    evidence,
                    re.IGNORECASE,
                ):
                    continue
                issues.append(
                    {
                        "severity": rule.severity,
                        "file": str(path.relative_to(ROOT)),
                        "line": str(line_no),
                        "rule": rule.name,
                        "evidence": evidence[:220],
                        "recommendation": rule.recommendation,
                        "auto": rule.auto_fix_safe,
                    }
                )

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    counts = {severity: 0 for severity in ["BLOCKER", "HIGH", "MEDIUM", "LOW"]}
    for issue in issues:
        counts[issue["severity"]] = counts.get(issue["severity"], 0) + 1
    lines = [
        "# ATANOR UI Quality Audit",
        "",
        "This report scans user-facing source and documentation for release trust risks.",
        "",
        "## Summary",
        "",
        *[f"- {severity}: {counts.get(severity, 0)}" for severity in ["BLOCKER", "HIGH", "MEDIUM", "LOW"]],
        "",
        "## Issues",
        "",
    ]
    if not issues:
        lines.append("No issues found.")
    for issue in issues:
        lines.extend(
            [
                f"### {issue['severity']} - {issue['rule']}",
                "",
                f"- file: `{issue['file']}:{issue['line']}`",
                "- route: unknown",
                f"- evidence: `{issue['evidence']}`",
                f"- recommended fix: {issue['recommendation']}",
                f"- auto-fix safe: {issue['auto']}",
                "",
            ]
        )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT}")
    print(f"Issues: {len(issues)}")
    return 1 if any(issue["severity"] in {"BLOCKER", "HIGH"} for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
