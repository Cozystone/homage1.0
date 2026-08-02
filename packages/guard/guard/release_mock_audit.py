from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


RISK_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(mock|fake|stub|placeholder|canned|hardcoded|not[_-]?configured)",
    re.IGNORECASE,
)

BLOCKER_PATTERNS = (
    re.compile(r"fake[_ -]?(graph[_ -]?)?count", re.IGNORECASE),
    re.compile(r"fake[_ -]?node", re.IGNORECASE),
    re.compile(r"fake[_ -]?web[_ -]?evidence", re.IGNORECASE),
    re.compile(r"fake[_ -]?(dht|peer|token|did|blockchain)", re.IGNORECASE),
    re.compile(r"prompt[_ -]?specific[_ -]?canned", re.IGNORECASE),
)

ALLOWED_CONTEXT_PATTERNS = (
    re.compile(r"\b(test|tests|proof|fixture|demo|audit|report)\b", re.IGNORECASE),
    re.compile(r"(release[_-]?mock[_-]?audit|audit[_-]?release[_-]?mock[_-]?risks)", re.IGNORECASE),
    re.compile(r"(placeholder\s*[:=]|placeholder=|placeholders?\s*=|\{placeholders\}|aria-label=\{.*placeholder|join\([\"']\?[\"']\))", re.IGNORECASE),
    re.compile(r"does_not_claim|must_not|not claim|no fake|not fake|does not .*fake|not .*fake", re.IGNORECASE),
    re.compile(r"fake[_ -]?[A-Za-z0-9_ -]*['\"]?\s*[:=]\s*False\b", re.IGNORECASE),
    re.compile(r"canned[_ -]?[A-Za-z0-9_ -]*['\"]?\s*[:=]\s*(False|false)\b", re.IGNORECASE),
    re.compile(r"local[_ -]?mock|mock_billing|mock detector|mock_free", re.IGNORECASE),
)

DEFAULT_SKIP_PARTS = {
    ".git",
    ".next",
    "node_modules",
    "__pycache__",
    "dist",
    "dist-artifacts",
    "target",
    "reports",
}

DEFAULT_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".mjs", ".rs", ".md", ".json"}

RELEASE_CRITICAL_PARTS = {
    "apps",
    "packages",
    "scripts",
    "README.md",
    "docs",
}


@dataclass(frozen=True)
class MockRisk:
    severity: str
    category: str
    path: str
    line: int
    evidence: str
    recommendation: str


def load_allowlist(path: Path | None) -> dict[str, dict]:
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("allowlist", data if isinstance(data, list) else [])
    allowlist: dict[str, dict] = {}
    for entry in entries:
        key = entry.get("key")
        reason = entry.get("reason")
        expires = entry.get("expires")
        if not key or not reason or not expires:
            raise ValueError("Each release mock allowlist entry requires key, reason, and expires.")
        allowlist[str(key)] = dict(entry)
    return allowlist


def _is_probably_allowed(path: Path, line: str) -> bool:
    if "packages/guard/" in path.as_posix():
        return True
    haystack = f"{path.as_posix()} {line}"
    return any(pattern.search(haystack) for pattern in ALLOWED_CONTEXT_PATTERNS)


def _release_sensitivity(path: Path) -> str:
    parts = set(path.parts)
    if "tests" in parts or "docs" in parts or "reports" in parts:
        return "non_release_support"
    if path.name in RELEASE_CRITICAL_PARTS or parts.intersection(RELEASE_CRITICAL_PARTS):
        return "release_critical"
    return "unknown"


def _allowlist_key(path: Path, line_number: int, line: str) -> str:
    token = RISK_PATTERN.search(line)
    matched = token.group(1).lower() if token else "risk"
    return f"{path.as_posix()}:{line_number}:{matched}"


def _severity_for(path: Path, line_number: int, line: str, allowlist: dict[str, dict]) -> tuple[str, str, str]:
    key = _allowlist_key(path, line_number, line)
    if key in allowlist:
        return (
            "INFO",
            "allowlisted_with_reason",
            f"Allowlisted until {allowlist[key]['expires']}: {allowlist[key]['reason']}",
        )
    if _is_probably_allowed(path, line):
        return (
            "INFO",
            "allowed_fixture_or_honest_boundary",
            "Keep the boundary explicit; do not expose it as a production claim.",
        )
    if any(pattern.search(line) for pattern in BLOCKER_PATTERNS):
        return (
            "BLOCKER",
            "release_blocker",
            "Remove fake production behavior or clearly isolate it behind a non-release proof/test path.",
        )
    return (
        "REVIEW",
        "production_mock_risk",
        "Classify this as proof/test-only, rename it to honest local simulation, or remove it before release.",
    )


def _iter_files(roots: Iterable[Path], *, skip_parts: set[str] | None = None) -> Iterable[Path]:
    skips = skip_parts or DEFAULT_SKIP_PARTS
    for root in roots:
        if root.is_file():
            if root.suffix in DEFAULT_EXTENSIONS:
                yield root
            continue
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in DEFAULT_EXTENSIONS:
                continue
            if any(part in skips for part in path.parts):
                continue
            yield path


def audit_mock_risks(
    roots: Iterable[Path],
    *,
    repo_root: Path | None = None,
    allowlist_path: Path | None = None,
    changed_files_only: Iterable[Path] | None = None,
    release_critical_only: bool = False,
) -> dict:
    repo = repo_root or Path.cwd()
    allowlist = load_allowlist(allowlist_path)
    changed = {path.resolve() for path in changed_files_only or []}
    risks: list[MockRisk] = []
    for path in sorted(set(_iter_files(roots))):
        if changed and path.resolve() not in changed:
            continue
        if release_critical_only and _release_sensitivity(path) != "release_critical":
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            risks.append(
                MockRisk(
                    "BLOCKER",
                    "utf8_decode",
                    str(path.relative_to(repo) if path.is_relative_to(repo) else path),
                    1,
                    "File is not valid UTF-8.",
                    "Resave as UTF-8 before release.",
                )
            )
            continue
        for line_number, line in enumerate(lines, start=1):
            if not RISK_PATTERN.search(line):
                continue
            relative = str(path.relative_to(repo) if path.is_relative_to(repo) else path)
            severity, category, recommendation = _severity_for(Path(relative.replace("\\", "/")), line_number, line, allowlist)
            risks.append(
                MockRisk(
                    severity=severity,
                    category=category,
                    path=relative.replace("\\", "/"),
                    line=line_number,
                    evidence=line.strip()[:240],
                    recommendation=recommendation,
                )
            )
    counts: dict[str, int] = {}
    for risk in risks:
        counts[risk.severity] = counts.get(risk.severity, 0) + 1
    return {
        "passed": counts.get("BLOCKER", 0) == 0,
        "counts": counts,
        "risks": [asdict(risk) for risk in risks],
        "honesty": {
            "external_llm_used": False,
            "external_sllm_used": False,
            "release_gate_only": True,
            "does_not_auto_fix": True,
        },
    }


def write_mock_risk_report(report: dict, json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# ATANOR No-Mock Release Gate",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- BLOCKER: `{report.get('counts', {}).get('BLOCKER', 0)}`",
        f"- REVIEW: `{report.get('counts', {}).get('REVIEW', 0)}`",
        f"- INFO: `{report.get('counts', {}).get('INFO', 0)}`",
        "",
        "## Findings",
        "",
    ]
    risks = report.get("risks") or []
    if not risks:
        lines.append("No mock/scaffold risk terms found.")
    for risk in risks[:200]:
        lines.extend(
            [
                f"### {risk['severity']} - {risk['category']}",
                "",
                f"- file: `{risk['path']}:{risk['line']}`",
                f"- evidence: `{risk['evidence']}`",
                f"- recommendation: {risk['recommendation']}",
                "",
            ]
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
